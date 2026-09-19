#!/usr/bin/env python3
"""
poc_audit — static audit of the objects linked into a GameCube POC whose
interrupt-path properties must be provable on the final objects:
GBP-INIT-003A (profile `003a`, PI HSP masked for the whole run) and
GBP-INIT-003B (profile `003b`, one handler, one unmask call site).

Input: a directory holding `<object>.objdump.txt` (powerpc-eabi-objdump
-dr of every object of the POC) and `elf.nm.txt` (powerpc-eabi-nm of the
linked ELF), produced by `make initirqa-audit` / `make initirqb-audit`.

Checks common to both profiles (each one a finding when violated):
  objects     none of the profile's forbidden objects is linked, every
              required object is;
  symbols     no object of the POC references a forbidden symbol; a
              symbol with a caller table (profile 003b) is referenced from
              exactly the listed functions, exactly that many times each;
              an "investigate" symbol is reported wherever it appears;
  intmr       no store instruction in any object targets PI INTMR
              (0xCC003004). Register values are tracked through lis / ori /
              oris / addi / addis / li / mr inside each function by a
              forward data-flow pass over the function's control-flow graph
              (track_registers: branch targets merge by agreement, loops
              iterate to a fixpoint, calls clobber the volatile GPRs, a
              relocated immediate is unknown), so both GCC encodings are
              caught: `lis -13312; ori 12292; stw 0(r)` and `lis -13311;
              stw -53244(r)`, also when the base register lives in a
              callee-saved register across an early-return epilogue. Loads
              are allowed (INTMR is read-only here);
  intsr       stores to INTSR (0xCC003000, the W1C acknowledge) come only
              from the profile's listed functions, exactly once each
              (003a: h_write_intsr; 003b: h_write_intsr and the two one-shot
              handlers);
  callsites   gbp_regwrite_irq_u16 is called exactly the listed number of
              times per object (003a: 3 in gbp_initirqa_probe.o — A1, A2,
              STOP; 003b: those 3 plus 1 in gbp_initirqb_probe.o — the
              device ACK) and from no other object; gbp_regwrite_control_byte
              exactly twice, from gbp_initirqa_probe.o only; main.o calls
              the profile's transport constructor and probe entry point and
              nothing of the other profile;
  elf         the linked ELF defines the profile's required symbols and
              none of its forbidden ones.

Profile 003a: hsp_backend_irq.o, hsp_backend_intmr.o, gbp_initirqb_probe.o,
gbp_init_irq_probe.o and gbp_init_probe.o must not be linked; no object
references __UnmaskIrq, IRQ_Request, IRQ_Free or a one-shot handler
(__MaskIrq is reported for investigation).
Profile 003b: hsp_backend_irq.o, gbp_initirqa_probe.o and
gbp_initirqb_probe.o are required; hsp_backend_intmr.o (the direct INTMR
store of GBP-INIT-001) and the 001/002 probe objects are forbidden;
__UnmaskIrq is referenced exactly once, from h_irq_unmask; IRQ_Request
exactly from h_irq_install and h_irq_restore; __MaskIrq exactly from
h_irq_mask, hsp_backend_oneshot_isr and hsp_backend_oneshot_isr_ext;
IRQ_Free never; main.o calls hsp_backend_irq_transport_ext (not the
GBP-INIT-002 constructor) and gbp_initirqb_probe_run.
libogc2 itself defines and uses __UnmaskIrq (VIDEO/PAD/EXI setup); that
is library-internal and outside "our" objects, so the symbol checks are
done on the POC's objects (relocations), not on the ELF.

Profile video (GBP-VIDEO-001): the repeated drained service — the avsvc
interrupt path plus the memory-only record reset, the sequence core
gbp_avseq.o, the OGBPSEQ1 sidecar gbp_avseqdump.o and gbp_video_probe.o;
gbp_avsvc_probe.o and the v2 sidecar gbp_avdump.o are forbidden; the
delivery called from the probe is the QUIET variant (nothing is formatted
between the unmask and the re-mask); gbp_avblock_read exactly twice from
the probe; six IRQ-register write sites (3 stage + 1 shared service + 2 probe:
the lean cycles' ACK and the re-arm).

Profile avsvc (GBP-AV-SERVICE-001): hsp_backend_irq.o linked again (the
003B extended one-shot is the handler; a second delivery is forbidden, so
no generation wrapper); hsp_backend_irq_multi.o, hsp_backend_intmr.o and
the 001/002/003B/004 probe objects forbidden; the whole-block read
gbp_avblock_read is called exactly twice from the probe (AUDIO, VIDEO),
gbp_irq_service_deliver and gbp_irq_service_ack_write_postack exactly once
from it, gbp_irq_service_ack (the PREACK variant) never from the probe;
five IRQ-register write sites (A1/A2/STOP, ACK in the shared service, REARM
in the probe); no object references an ARQ_/AR_/AUDIO_/ASND/AESND/GX_/net_/
DSP_/SI_/SIO symbol (no libogc ARAM queue, no audio output, no GX, no
network, no serial); main.o uses the ext constructor, the probe entry and
the sidecar writer.

Usage:  tools/poc_audit.py <audit-dir> [--profile 003a|003b|004|avsvc|video|vstate] [--report FILE] [--json]
Exit status 0 when there is no finding.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

# Symbols that mean "this object can reach the filesystem". No object of the capture path may
# reference any of them: the save happens only after the teardown, from main, through sdlog.o.
_FS_SYMBOLS = ("fopen", "fwrite", "fread", "fclose", "fprintf", "fputs", "fputc", "remove", "rename",
               "mkdir", "opendir", "fatMountSimple", "fatUnmount", "fatInitDefault",
               "sdlog_save", "sdlog_save_blob", "sdlog_stream_open", "sdlog_stream_write", "sdlog_stream_close")

# What the SOURCE-CAPTURE path may not reach, on top of the filesystem. The
# stream-0005 audit (§V5.40.23) mutated a full-record CRC into
# gbp_vwitness_commit() and nothing objected: `gbp_crc32` was absent from every
# per-object list because gbp_vstatedump.o, gbp_vidxdump.o and gbp_avblock.o all
# use it legitimately — the first two are POST-CAPTURE serializers and the third
# summarises raw blocks outside the timed region. The rule therefore belongs to
# the capture path specifically, not to the whole program.
#
# `gbp_vidxdump_stream` is here for the same reason: serializing 8.9 MB is a
# post-teardown activity and must never become reachable from a block.
_CAPTURE_SYMBOLS = _FS_SYMBOLS + ("gbp_crc32", "gbp_crc32_update", "gbp_crc32_init",
                                  "gbp_crc32_final", "gbp_vidxdump_stream",
                                  "gbp_vstatedump_stream", "gbp_vcoldump_stream")

PROFILES = {
    "003a": {
        "forbidden_objects": ("hsp_backend_irq.o", "hsp_backend_intmr.o", "gbp_initirqb_probe.o", "gbp_init_irq_probe.o", "gbp_init_probe.o"),
        "required_objects": ("gbp_initirqa_probe.o",),
        "forbidden_symbols": ("__UnmaskIrq", "IRQ_Request", "IRQ_Free", "hsp_backend_oneshot_isr", "hsp_backend_oneshot_isr_ext",
                              "hsp_backend_irq_transport", "hsp_backend_irq_transport_ext", "hsp_backend_intmr_transport"),
        "investigate_symbols": ("__MaskIrq",),
        "symbol_callers": {},
        "elf_required": ("gbp_initirqa_probe_run", "gbp_regwrite_irq_u16", "gbp_regwrite_control_byte"),
        "elf_forbidden": ("hsp_backend_oneshot_isr", "hsp_backend_oneshot_isr_ext", "gbp_initirq_probe_run", "gbp_init_probe_run",
                          "gbp_initirqb_probe_run", "hsp_backend_irq_transport", "hsp_backend_irq_transport_ext", "hsp_backend_intmr_transport"),
        "irq_write_sites": {"gbp_initirqa_probe.o": 3},
        "control_write_sites": {"gbp_initirqa_probe.o": 2},
        "intsr_store_sites": {"h_write_intsr": 1},
        "main_must_call": ("gbp_initirqa_probe_run",),
        "main_must_not_call": ("hsp_backend_irq_transport", "hsp_backend_irq_transport_ext", "hsp_backend_intmr_transport", "gbp_initirqb_probe_run"),
    },
    "003b": {
        "forbidden_objects": ("hsp_backend_intmr.o", "hsp_backend_irq_multi.o", "gbp_init_irq_probe.o", "gbp_init_probe.o", "gbp_initirq4_probe.o"),
        "required_objects": ("hsp_backend_irq.o", "hsp_backend.o", "gbp_initirqa_probe.o", "gbp_irq_service.o", "gbp_initirqb_probe.o", "main.o"),
        "forbidden_symbols": ("IRQ_Free", "hsp_backend_irq_transport", "hsp_backend_intmr_transport", "gbp_initirq_probe_run", "gbp_init_probe_run"),
        "investigate_symbols": (),
        "symbol_callers": {"__UnmaskIrq": {"h_irq_unmask": 1},
                           "IRQ_Request": {"h_irq_install": 1, "h_irq_restore": 1},
                           "__MaskIrq": {"h_irq_mask": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1}},
        "elf_required": ("gbp_initirqb_probe_run", "gbp_initirqa_run_cause", "gbp_initirqa_teardown", "gbp_regwrite_irq_u16",
                         "gbp_regwrite_control_byte", "hsp_backend_oneshot_isr_ext", "hsp_backend_irq_transport_ext", "__UnmaskIrq", "__MaskIrq", "IRQ_Request"),
        "elf_forbidden": ("gbp_initirq_probe_run", "gbp_init_probe_run", "hsp_backend_intmr_transport"),
        # the device ACK call site moved from gbp_initirqb_probe.o to gbp_irq_service.o when the cycle service was
        # extracted for GBP-INIT-004 (the executed build d3da8cd had it in the probe object: 3 + 1 sites either way)
        "irq_write_sites": {"gbp_initirqa_probe.o": 3, "gbp_irq_service.o": 1},
        "control_write_sites": {"gbp_initirqa_probe.o": 2},
        "intsr_store_sites": {"h_write_intsr": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
        "main_must_call": ("hsp_backend_irq_transport_ext", "gbp_initirqb_probe_run"),
        "main_must_not_call": ("hsp_backend_irq_transport", "hsp_backend_intmr_transport", "gbp_initirqa_probe_run", "gbp_initirq_probe_run"),
    },
    # GBP-INIT-004: the multi-cycle interrupt object hsp_backend_irq_multi.o is linked INSTEAD of hsp_backend_irq.o
    # (the 002/003B object and its two handlers must not be in the binary); one __UnmaskIrq site; IRQ_Request from the
    # install/restore pair only; __MaskIrq from the mask primitive and the multi-cycle handler only; no INTMR store;
    # INTSR stores exactly in h_write_intsr and the handler; gbp_regwrite_irq_u16 at 3 (A1, A2, STOP) + 1 (ACK, in the
    # shared service) + 1 (REARM, in the 004 probe) LOGICAL call sites — execution counts are the log's business.
    "004": {
        "forbidden_objects": ("hsp_backend_irq.o", "hsp_backend_intmr.o", "gbp_initirqb_probe.o", "gbp_init_irq_probe.o", "gbp_init_probe.o"),
        "required_objects": ("hsp_backend_irq_multi.o", "hsp_backend.o", "gbp_initirqa_probe.o", "gbp_irq_service.o", "gbp_initirq4_probe.o", "main.o"),
        "forbidden_symbols": ("IRQ_Free", "hsp_backend_irq_transport", "hsp_backend_irq_transport_ext", "hsp_backend_intmr_transport",
                              "hsp_backend_oneshot_isr", "hsp_backend_oneshot_isr_ext", "gbp_initirq_probe_run", "gbp_init_probe_run",
                              "gbp_initirqb_probe_run"),
        "investigate_symbols": (),
        "symbol_callers": {"__UnmaskIrq": {"hm_irq_unmask": 1},
                           "IRQ_Request": {"hm_irq_install": 1, "hm_irq_restore": 1},
                           # two call sites in the handler: GCC duplicates the shared entry sequence (time base, PI reads,
                           # count++, mask) into the in-range and the out-of-range slot paths; both precede the single W1C
                           # store and every path masks before any store (manual inspection of the listing, DEVLOG 2026-09-15)
                           "__MaskIrq": {"hm_irq_mask": 1, "hsp_backend_oneshot_isr_multi": 2}},
        "elf_required": ("gbp_initirq4_probe_run", "gbp_initirqa_run_cause", "gbp_initirqa_teardown", "gbp_irq_service_deliver",
                         "gbp_irq_service_ack", "gbp_regwrite_irq_u16", "gbp_regwrite_control_byte", "hsp_backend_oneshot_isr_multi",
                         "hsp_backend_irq_transport_multi", "__UnmaskIrq", "__MaskIrq", "IRQ_Request"),
        "elf_forbidden": ("gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run", "hsp_backend_intmr_transport",
                          "hsp_backend_oneshot_isr", "hsp_backend_oneshot_isr_ext", "hsp_backend_irq_transport", "hsp_backend_irq_transport_ext"),
        "irq_write_sites": {"gbp_initirqa_probe.o": 3, "gbp_irq_service.o": 1, "gbp_initirq4_probe.o": 1},
        "control_write_sites": {"gbp_initirqa_probe.o": 2},
        "intsr_store_sites": {"h_write_intsr": 1, "hsp_backend_oneshot_isr_multi": 1},
        "main_must_call": ("hsp_backend_irq_transport_multi", "gbp_initirq4_probe_run"),
        "main_must_not_call": ("hsp_backend_irq_transport", "hsp_backend_irq_transport_ext", "hsp_backend_intmr_transport",
                               "gbp_initirqa_probe_run", "gbp_initirqb_probe_run", "gbp_initirq_probe_run"),
    },
    # GBP-AV-SERVICE-001: the 003B interrupt object (its extended one-shot is the installed handler) is linked; the 004
    # multi-cycle object and the direct INTMR store are not; the whole-block read is reached only through
    # gbp_avblock_read (two call sites in the probe: AUDIO then VIDEO); the ACK is written from the PRESVC value through
    # gbp_irq_service_ack_write_postack (the PREACK variant gbp_irq_service_ack is never called); no ARAM queue, audio
    # output, GX, network or serial symbol anywhere in the POC's objects.
    "avsvc": {
        "forbidden_objects": ("hsp_backend_irq_multi.o", "hsp_backend_intmr.o", "gbp_initirqb_probe.o", "gbp_initirq4_probe.o",
                              "gbp_init_irq_probe.o", "gbp_init_probe.o"),
        "required_objects": ("hsp_backend_irq.o", "hsp_backend.o", "gbp_initirqa_probe.o", "gbp_irq_service.o", "gbp_avblock.o",
                             "gbp_avdump.o", "gbp_crc32.o", "gbp_avsvc_probe.o", "sdlog.o", "main.o"),
        "forbidden_symbols": ("IRQ_Free", "hsp_backend_irq_transport", "hsp_backend_irq_transport_multi", "hsp_backend_intmr_transport",
                              "hsp_backend_oneshot_isr_multi", "gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run",
                              "gbp_initirq4_probe_run"),
        "forbidden_symbol_prefixes": ("ARQ_", "AR_", "AUDIO_", "ASND", "AESND", "GX_", "net_", "DSP_", "SI_", "SIO"),
        "investigate_symbols": (),
        "symbol_callers": {"__UnmaskIrq": {"h_irq_unmask": 1},
                           "IRQ_Request": {"h_irq_install": 1, "h_irq_restore": 1},
                           "__MaskIrq": {"h_irq_mask": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
                           "gbp_avblock_read": {"gbp_avsvc_probe_run": 2},
                           "gbp_irq_service_deliver": {"gbp_avsvc_probe_run": 1},
                           "gbp_irq_service_ack_write_postack": {"gbp_avsvc_probe_run": 1, "gbp_irq_service_ack": 1},
                           "gbp_irq_service_ack": {}},
        "elf_required": ("gbp_avsvc_probe_run", "gbp_avblock_read", "gbp_avdump_serialize", "gbp_crc32", "gbp_initirqa_run_cause",
                         "gbp_initirqa_teardown", "gbp_irq_service_deliver", "gbp_irq_service_ack_write_postack", "gbp_regwrite_irq_u16",
                         "gbp_regwrite_control_byte", "hsp_backend_oneshot_isr_ext", "hsp_backend_irq_transport_ext", "sdlog_save_blob",
                         "__UnmaskIrq", "__MaskIrq", "IRQ_Request"),
        "elf_forbidden": ("gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run", "gbp_initirq4_probe_run",
                          "hsp_backend_intmr_transport", "hsp_backend_oneshot_isr_multi", "hsp_backend_irq_transport_multi",
                          "hsp_backend_irq_transport", "ARQ_Init", "AR_Init", "AUDIO_Init", "ASND_Init", "GX_Init", "net_init"),
        "irq_write_sites": {"gbp_initirqa_probe.o": 3, "gbp_irq_service.o": 1, "gbp_avsvc_probe.o": 1},
        "control_write_sites": {"gbp_initirqa_probe.o": 2},
        "intsr_store_sites": {"h_write_intsr": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
        "main_must_call": ("hsp_backend_irq_transport_ext", "gbp_avsvc_probe_run", "gbp_avdump_serialize", "sdlog_save_blob"),
        "main_must_not_call": ("hsp_backend_irq_transport", "hsp_backend_irq_transport_multi", "hsp_backend_intmr_transport",
                               "gbp_initirqa_probe_run", "gbp_initirqb_probe_run", "gbp_initirq4_probe_run", "gbp_initirq_probe_run",
                               "gbp_irq_service_ack"),
    },
    # Profile video (GBP-VIDEO-001): the repeated drained service. Same interrupt path as avsvc
    # (the 003B extended one-shot, installed once) plus the memory-only record reset; the sequence
    # core gbp_avseq.o, the OGBPSEQ1 sidecar gbp_avseqdump.o and the probe gbp_video_probe.o replace
    # the AVSVC probe and its v2 sidecar, which are forbidden here. gbp_avblock_read is called
    # exactly twice from the probe (AUDIO, VIDEO); the delivery is the QUIET variant (the formatting
    # one is never called from the probe: nothing is formatted between the unmask and the re-mask).
    # SIX IRQ-register write sites: 3 in the stage (A1/A2/STOP), 1 in the shared service (the verify
    # cycles' ACK, which also takes the POSTACK snapshot) and 2 in the probe (the lean cycles' ACK,
    # written without any formatting, and the re-arm). The deliver-quiet entry shows TWO relocations
    # in the probe object for ONE source call site: GCC peels the first loop iteration (which has no
    # admission read) from the rest and duplicates the body — as it does for the 004 handler's entry
    # sequence. The property that bounds the experiment is the single __UnmaskIrq call site
    # (h_irq_unmask), pinned below and asserted per cycle by tests/unit/test_gbp_video.c.
    "video": {
        "forbidden_objects": ("hsp_backend_irq_multi.o", "hsp_backend_intmr.o", "gbp_initirqb_probe.o", "gbp_initirq4_probe.o",
                              "gbp_init_irq_probe.o", "gbp_init_probe.o", "gbp_avsvc_probe.o", "gbp_avdump.o"),
        "required_objects": ("hsp_backend_irq.o", "hsp_backend.o", "gbp_initirqa_probe.o", "gbp_irq_service.o", "gbp_avblock.o",
                             "gbp_avseq.o", "gbp_avseqdump.o", "gbp_crc32.o", "gbp_video_probe.o", "sdlog.o", "main.o"),
        "forbidden_symbols": ("IRQ_Free", "hsp_backend_irq_transport", "hsp_backend_irq_transport_multi", "hsp_backend_intmr_transport",
                              "hsp_backend_oneshot_isr_multi", "gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run",
                              "gbp_initirq4_probe_run", "gbp_avsvc_probe_run", "gbp_avdump_serialize"),
        "forbidden_symbol_prefixes": ("ARQ_", "AR_", "AUDIO_", "ASND", "AESND", "GX_", "net_", "DSP_", "SI_", "SIO"),
        "investigate_symbols": (),
        "symbol_callers": {"__UnmaskIrq": {"h_irq_unmask": 1},
                           "IRQ_Request": {"h_irq_install": 1, "h_irq_restore": 1},
                           "__MaskIrq": {"h_irq_mask": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
                           "gbp_avblock_read": {"gbp_video_probe_run": 2},
                           "gbp_irq_service_deliver_quiet": {"gbp_video_probe_run": 2, "gbp_irq_service_deliver": 1},
                           "gbp_irq_service_ack_write_postack": {"gbp_video_probe_run": 1, "gbp_irq_service_ack": 1},
                           "gbp_irq_service_deliver": {},
                           "gbp_irq_service_ack": {}},
        "elf_required": ("gbp_video_probe_run", "gbp_avblock_read", "gbp_avseqdump_serialize", "gbp_avseq_summarize", "gbp_avseq_boundaries",
                         "gbp_crc32", "gbp_initirqa_run_cause", "gbp_initirqa_teardown", "gbp_irq_service_deliver_quiet",
                         "gbp_irq_service_ack_write_postack", "gbp_regwrite_irq_u16", "gbp_regwrite_control_byte",
                         "hsp_backend_oneshot_isr_ext", "hsp_backend_irq_transport_ext", "sdlog_save_blob",
                         "__UnmaskIrq", "__MaskIrq", "IRQ_Request"),
        "elf_forbidden": ("gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run", "gbp_initirq4_probe_run",
                          "gbp_avsvc_probe_run", "gbp_avdump_serialize", "hsp_backend_intmr_transport", "hsp_backend_oneshot_isr_multi",
                          "hsp_backend_irq_transport_multi", "hsp_backend_irq_transport", "ARQ_Init", "AR_Init", "AUDIO_Init",
                          "ASND_Init", "GX_Init", "net_init"),
        "irq_write_sites": {"gbp_initirqa_probe.o": 3, "gbp_irq_service.o": 1, "gbp_video_probe.o": 2},
        "control_write_sites": {"gbp_initirqa_probe.o": 2},
        "intsr_store_sites": {"h_write_intsr": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
        "main_must_call": ("hsp_backend_irq_transport_ext", "gbp_video_probe_run", "gbp_avseqdump_serialize", "sdlog_save_blob"),
        "main_must_not_call": ("hsp_backend_irq_transport", "hsp_backend_irq_transport_multi", "hsp_backend_intmr_transport",
                               "gbp_initirqa_probe_run", "gbp_initirqb_probe_run", "gbp_initirq4_probe_run", "gbp_initirq_probe_run",
                               "gbp_avsvc_probe_run", "gbp_irq_service_ack"),
    },
    "vstate": {
        # GBP-VIDEO-002. The interrupt path is byte-for-byte the one GBP-VIDEO-001 executed
        # physically: one __UnmaskIrq call site, IRQ_Request only from the install/restore pair,
        # __MaskIrq only from the mask primitive and the two 002/003B handler bodies, no INTMR
        # store anywhere, and the same three INTSR store sites. Any change there is a BLOCKER.
        "forbidden_objects": ("hsp_backend_irq_multi.o", "hsp_backend_intmr.o", "gbp_initirqb_probe.o",
                              "gbp_initirq4_probe.o", "gbp_init_irq_probe.o", "gbp_init_probe.o",
                              "gbp_avsvc_probe.o", "gbp_avdump.o", "gbp_avseq.o", "gbp_avseqdump.o",
                              "gbp_video_probe.o"),
        "required_objects": ("hsp_backend_irq.o", "hsp_backend.o", "gbp_initirqa_probe.o", "gbp_irq_service.o",
                             "gbp_avblock.o", "gbp_time64.o", "gbp_vsig.o", "gbp_vstate.o",
                             "gbp_vstate_probe.o", "gbp_vstatedump.o", "gbp_crc32.o", "sdlog.o", "main.o", "gbp_vwitness.o"),
        "forbidden_symbols": ("IRQ_Free", "hsp_backend_irq_transport", "hsp_backend_irq_transport_multi",
                              "hsp_backend_intmr_transport", "hsp_backend_oneshot_isr_multi",
                              "gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run",
                              "gbp_initirq4_probe_run", "gbp_avsvc_probe_run", "gbp_avdump_serialize",
                              "gbp_video_probe_run", "gbp_avseqdump_serialize"),
        "forbidden_symbol_prefixes": ("ARQ_", "AR_", "AUDIO_", "ASND", "AESND", "GX_", "net_", "DSP_", "SI_", "SIO"),
        "investigate_symbols": (),
        "symbol_callers": {"__UnmaskIrq": {"h_irq_unmask": 1},
                           "IRQ_Request": {"h_irq_install": 1, "h_irq_restore": 1},
                           "__MaskIrq": {"h_irq_mask": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
                           "gbp_avblock_read": {"gbp_vstate_probe_run": 2},
                           "gbp_irq_service_deliver_quiet": {"gbp_vstate_probe_run": 2, "gbp_irq_service_deliver": 1},
                           "gbp_irq_service_ack_write_postack": {"gbp_vstate_probe_run": 1, "gbp_irq_service_ack": 1},
                           "gbp_irq_service_deliver": {},
                           "gbp_irq_service_ack": {},
                           # the signature and the state step run ONCE per cycle, in the probe, never
                           # in a handler and never in the sidecar writer
                           "gbp_vsig_block": {"gbp_vstate_probe_run": 1},
                           "gbp_vstate_block": {"gbp_vstate_probe_run": 1},
                           # the 64-bit time base comes from libogc2's gettime(), which is exactly the
                           # TBU/TBL/TBU retry loop; one wrapper, one call site
                           "gettime": {"h_ticks64": 1},
                           # the sidecar is streamed from main, after the teardown, and the sink is
                           # the only thing that writes to the card during the save
                           "gbp_vstatedump_stream": {"main": 1},
                           "sdlog_stream_write": {"sink_sd": 1}},
        "elf_required": ("gbp_vstate_probe_run", "gbp_vstate_report", "gbp_vstate_block", "gbp_vsig_block",
                         "gbp_vsig_flag_gbi", "gbp_vsig_flag_disc", "gbp_vsig_cost_add", "gbp_vsig_cost_quantile",
                         "gbp_vstate_target_reached", "gbp_vstate_safety_stop", "gbp_vstate_tail_truncate",
                         "gbp_vstatedump_stream", "gbp_vstatedump_layout", "gbp_avblock_read", "gbp_crc32",
                         "gbp_initirqa_run_cause", "gbp_initirqa_teardown", "gbp_irq_service_deliver_quiet",
                         "gbp_irq_service_ack_write_postack", "gbp_regwrite_irq_u16", "gbp_regwrite_control_byte",
                         "hsp_backend_oneshot_isr_ext", "hsp_backend_irq_transport_ext",
                         "sdlog_save", "sdlog_stream_open", "sdlog_stream_write", "sdlog_stream_close",
                         "gettime", "__UnmaskIrq", "__MaskIrq", "IRQ_Request"),
        "elf_forbidden": ("gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run",
                          "gbp_initirq4_probe_run", "gbp_avsvc_probe_run", "gbp_avdump_serialize",
                          "gbp_video_probe_run", "gbp_avseqdump_serialize", "hsp_backend_intmr_transport",
                          "hsp_backend_oneshot_isr_multi", "hsp_backend_irq_transport_multi",
                          "hsp_backend_irq_transport", "ARQ_Init", "AR_Init", "AUDIO_Init", "ASND_Init",
                          "GX_Init", "net_init"),
        # 3 in the stage (A1 / A2 / STOP), 1 in the shared service (the verify cycles' ACK), and 3 in
        # the probe: the lean ACK plus the re-arm, which GCC duplicates across the verify branch
        # (both copies write 0x0000, confirmed in the disassembly: `li r7,0` at each).
        "irq_write_sites": {"gbp_initirqa_probe.o": 3, "gbp_irq_service.o": 1, "gbp_vstate_probe.o": 3},
        "control_write_sites": {"gbp_initirqa_probe.o": 2},
        "intsr_store_sites": {"h_write_intsr": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
        # FILESYSTEM ISOLATION: no object in the capture path may reference the filesystem, directly
        # or transitively. Only sdlog.o may, and main.o calls it only after the probe has returned
        # from its teardown.
        "object_must_not_reference": {
            "gbp_vstate_probe.o": _FS_SYMBOLS,
            "gbp_vstate.o": _FS_SYMBOLS,
            "gbp_vqueue.o": _FS_SYMBOLS,
            "gbp_vsig.o": _FS_SYMBOLS,
            "gbp_vstatedump.o": _FS_SYMBOLS,
            "gbp_time64.o": _FS_SYMBOLS,
            "gbp_avblock.o": _FS_SYMBOLS,
            "gbp_irq_service.o": _FS_SYMBOLS,
            "gbp_initirqa_probe.o": _FS_SYMBOLS,
            "hsp_backend.o": _FS_SYMBOLS,
            "hsp_backend_irq.o": _FS_SYMBOLS,
        },
        "main_must_call": ("hsp_backend_irq_transport_ext", "gbp_vstate_probe_run", "gbp_vstatedump_stream",
                           "sdlog_stream_open", "sdlog_save"),
        "main_must_not_call": ("hsp_backend_irq_transport", "hsp_backend_irq_transport_multi",
                               "hsp_backend_intmr_transport", "gbp_initirqa_probe_run", "gbp_initirqb_probe_run",
                               "gbp_initirq4_probe_run", "gbp_initirq_probe_run", "gbp_avsvc_probe_run",
                               "gbp_video_probe_run", "gbp_irq_service_ack"),
    },
    "color": {
        # GBP-VIDEO-003. The SAME interrupt path and the SAME service loop as the vstate profile
        # above - one __UnmaskIrq call site, IRQ_Request only from the install/restore pair,
        # __MaskIrq only from the mask primitive and the two handler bodies, no INTMR store, the
        # same IRQ-register and whole-block read call sites. What differs is the sidecar writer
        # (OGBPCOL1, never OGBPSEQ1) and the capture module beside the state model.
        "forbidden_objects": ("hsp_backend_irq_multi.o", "hsp_backend_intmr.o", "gbp_initirqb_probe.o",
                              "gbp_initirq4_probe.o", "gbp_init_irq_probe.o", "gbp_init_probe.o",
                              "gbp_avsvc_probe.o", "gbp_avdump.o", "gbp_avseq.o", "gbp_avseqdump.o",
                              "gbp_video_probe.o"),
        "required_objects": ("hsp_backend_irq.o", "hsp_backend.o", "gbp_initirqa_probe.o", "gbp_irq_service.o",
                             "gbp_avblock.o", "gbp_time64.o", "gbp_vsig.o", "gbp_vstate.o", "gbp_vcolor.o",
                             "gbp_vstate_probe.o", "gbp_vstatedump.o", "gbp_vcoldump.o", "gbp_crc32.o",
                             "sdlog.o", "main.o", "gbp_vwitness.o"),
        "forbidden_symbols": ("IRQ_Free", "hsp_backend_irq_transport", "hsp_backend_irq_transport_multi",
                              "hsp_backend_intmr_transport", "hsp_backend_oneshot_isr_multi",
                              "gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run",
                              "gbp_initirq4_probe_run", "gbp_avsvc_probe_run", "gbp_avdump_serialize",
                              "gbp_video_probe_run", "gbp_avseqdump_serialize"),
        "forbidden_symbol_prefixes": ("ARQ_", "AR_", "AUDIO_", "ASND", "AESND", "GX_", "net_", "DSP_", "SI_", "SIO"),
        "investigate_symbols": (),
        "symbol_callers": {"__UnmaskIrq": {"h_irq_unmask": 1},
                           "IRQ_Request": {"h_irq_install": 1, "h_irq_restore": 1},
                           "__MaskIrq": {"h_irq_mask": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
                           "gbp_avblock_read": {"gbp_vstate_probe_run": 2},
                           "gbp_irq_service_deliver_quiet": {"gbp_vstate_probe_run": 2, "gbp_irq_service_deliver": 1},
                           "gbp_irq_service_ack_write_postack": {"gbp_vstate_probe_run": 1, "gbp_irq_service_ack": 1},
                           "gbp_irq_service_deliver": {},
                           "gbp_irq_service_ack": {},
                           "gbp_vsig_block": {"gbp_vstate_probe_run": 1},
                           "gbp_vstate_block": {"gbp_vstate_probe_run": 1},
                           # the capture is fed once per closed frame, from the service loop, and
                           # from nowhere else: no handler, no writer, no second opinion
                           "gbp_vcolor_frame": {"gbp_vstate_probe_run": 1},
                           "gettime": {"h_ticks64": 1},
                           # the sidecar is streamed from main, after the teardown
                           "gbp_vcoldump_stream": {"main": 1},
                           "sdlog_stream_write": {"sink_sd": 1}},
        "elf_required": ("gbp_vstate_probe_run", "gbp_vstate_report", "gbp_vstate_block", "gbp_vsig_block",
                         "gbp_vcolor_frame", "gbp_vcolor_eligible", "gbp_vcolor_init", "gbp_vcolor_done",
                         "gbp_vcoldump_stream", "gbp_vcoldump_layout", "gbp_avblock_read", "gbp_crc32",
                         "gbp_initirqa_run_cause", "gbp_initirqa_teardown", "gbp_irq_service_deliver_quiet",
                         "gbp_irq_service_ack_write_postack", "gbp_regwrite_irq_u16", "gbp_regwrite_control_byte",
                         "hsp_backend_oneshot_isr_ext", "hsp_backend_irq_transport_ext",
                         "sdlog_save", "sdlog_stream_open", "sdlog_stream_write", "sdlog_stream_close",
                         "gettime", "__UnmaskIrq", "__MaskIrq", "IRQ_Request"),
        "elf_forbidden": ("gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run",
                          "gbp_initirq4_probe_run", "gbp_avsvc_probe_run", "gbp_avdump_serialize",
                          "gbp_video_probe_run", "gbp_avseqdump_serialize", "hsp_backend_intmr_transport",
                          "hsp_backend_oneshot_isr_multi", "hsp_backend_irq_transport_multi",
                          "hsp_backend_irq_transport", "ARQ_Init", "AR_Init", "AUDIO_Init", "ASND_Init",
                          "GX_Init", "net_init"),
        "irq_write_sites": {"gbp_initirqa_probe.o": 3, "gbp_irq_service.o": 1, "gbp_vstate_probe.o": 3},
        "control_write_sites": {"gbp_initirqa_probe.o": 2},
        "intsr_store_sites": {"h_write_intsr": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
        "object_must_not_reference": {
            "gbp_vstate_probe.o": _FS_SYMBOLS,
            "gbp_vstate.o": _FS_SYMBOLS,
            "gbp_vqueue.o": _FS_SYMBOLS,
            "gbp_vcolor.o": _FS_SYMBOLS,
            "gbp_vsig.o": _FS_SYMBOLS,
            "gbp_vstatedump.o": _FS_SYMBOLS,
            "gbp_vcoldump.o": _FS_SYMBOLS,
            "gbp_time64.o": _FS_SYMBOLS,
            "gbp_avblock.o": _FS_SYMBOLS,
            "gbp_irq_service.o": _FS_SYMBOLS,
            "gbp_initirqa_probe.o": _FS_SYMBOLS,
            "hsp_backend.o": _FS_SYMBOLS,
            "hsp_backend_irq.o": _FS_SYMBOLS,
        },
        "main_must_call": ("hsp_backend_irq_transport_ext", "gbp_vstate_probe_run", "gbp_vcoldump_stream",
                           "sdlog_stream_open", "sdlog_save"),
        "main_must_not_call": ("hsp_backend_irq_transport", "hsp_backend_irq_transport_multi",
                               "hsp_backend_intmr_transport", "gbp_initirqa_probe_run", "gbp_initirqb_probe_run",
                               "gbp_initirq4_probe_run", "gbp_initirq_probe_run", "gbp_avsvc_probe_run",
                               "gbp_video_probe_run", "gbp_irq_service_ack", "gbp_vstatedump_stream"),
    },
    # GBP-VIDEO-004 (§V5). Everything the `color` profile pins about the service
    # path, plus the one architectural boundary this experiment introduces:
    # GX_ and VIDEO_ may appear in main.o and NOWHERE ELSE. That is §V5.7 turned
    # into a machine check — the display path lives in the POC, and no object
    # under src/gbp may reach the graphics pipeline.
    "stream": {
        "forbidden_objects": ("hsp_backend_irq_multi.o", "hsp_backend_intmr.o", "gbp_initirqb_probe.o",
                              "gbp_initirq4_probe.o", "gbp_init_irq_probe.o", "gbp_init_probe.o",
                              "gbp_avsvc_probe.o", "gbp_video_probe.o", "gbp_avdump.o", "gbp_avseq.o",
                              "gbp_avseqdump.o", "gbp_vcoldump.o"),
        "required_objects": ("hsp_backend_irq.o", "hsp_backend.o", "gbp_initirqa_probe.o", "gbp_irq_service.o",
                             "gbp_avblock.o", "gbp_time64.o", "gbp_vsig.o", "gbp_vstate.o",
                             "gbp_vstate_probe.o", "gbp_vstatedump.o", "gbp_vpix.o", "gbp_vqueue.o", "gbp_vpresent.o",
                             "gbp_vwitness.o", "gbp_vidxdump.o",
                             "gbp_crc32.o", "sdlog.o", "main.o"),
        "forbidden_symbols": ("IRQ_Free", "hsp_backend_irq_transport", "hsp_backend_irq_transport_multi",
                              "hsp_backend_intmr_transport", "hsp_backend_oneshot_isr_multi",
                              "gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run",
                              "gbp_initirq4_probe_run", "gbp_avsvc_probe_run", "gbp_video_probe_run",
                              "gbp_vcoldump_stream"),
        "forbidden_symbol_prefixes": ("ARQ_", "AR_", "AUDIO_", "ASND", "AESND", "GX_", "net_", "DSP_", "SI_", "SIO"),
        # The ONLY exemption in any profile, and it is the point of this one:
        # main.o owns the display path. Every other object still may not name GX_
        # or VIDEO_, which is how §V5.7's boundary is proved rather than asserted.
        "prefix_exempt_objects": {"main.o": ("GX_", "SI_")},
        "investigate_symbols": (),
        "symbol_callers": {"__UnmaskIrq": {"h_irq_unmask": 1},
                           "IRQ_Request": {"h_irq_install": 1, "h_irq_restore": 1},
                           "__MaskIrq": {"h_irq_mask": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
                           "gbp_avblock_read": {"gbp_vstate_probe_run": 2},
                           "gbp_irq_service_deliver_quiet": {"gbp_vstate_probe_run": 2, "gbp_irq_service_deliver": 1},
                           "gbp_irq_service_ack_write_postack": {"gbp_vstate_probe_run": 1, "gbp_irq_service_ack": 1},
                           "gbp_irq_service_deliver": {},
                           "gbp_irq_service_ack": {},
                           "gbp_vsig_block": {"gbp_vstate_probe_run": 1},
                           "gbp_vstate_block": {"gbp_vstate_probe_run": 1},
                           # §V5.7: the publish is ONE call site, in the service
                           # path, and nothing else in the runtime may publish.
                           "gbp_vqueue_publish": {"gbp_vstate_probe_run": 1},
                           # The ownership machine is reached from main.o only,
                           # and the callback calls exactly ONE function — which
                           # is the whole of the stream-0001 fix (§V5.26.2).
                           "gbp_vpresent_draw_done": {"on_draw_done": 1},
                           # §V5.46: `submit_ready` used to be inlined into its
                           # two callers, so the sites WERE {pump: 2, main: 1}.
                           # The disposition trace made it large enough that GCC
                           # stopped inlining it, which this rule caught. The
                           # property the rule exists for is unchanged and is now
                           # pinned in TWO places: the submit has one call site,
                           # and that site has exactly the same three callers as
                           # before. What still matters most is the caller that
                           # is ABSENT from both: gbp_vstate_probe_run.
                           "gbp_vpresent_submit": {"submit_ready": 1},
                           # NOT pinned: `submit_ready` is static, so calls to
                           # it inside main.o carry no relocation and this tool
                           # cannot see them. The property is preserved anyway --
                           # gbp_vpresent_submit has ONE site and it is not
                           # gbp_vstate_probe_run.
                           # §V5.46: the clock. It used to be read ONLY by the
                           # transport's 64-bit hook; the trace reads it at the
                           # take, the first slice, the conversion end, the
                           # submit, the decision and in the draw-done callback.
                           # Pinned exactly so a stray read is still a finding.
                           "gettime": {"h_ticks64": 1, "main": 2, "on_draw_done": 1,
                                       "pump": 3, "submit_ready": 2},
                           # The conversion is CONSUMER ONLY. The POC converts one
                           # TILE ROW per slice, so `pump` is the single call site
                           # and no object under src/gbp may call it at all —
                           # which is the half of §V5.7 that keeps pixels out of
                           # the service path.
                           # `gbp_vpix_frame` is the whole-frame helper the HOST tests use; on
                           # the target the POC converts a tile row at a time, so the
                           # linker drops the frame helper and `pump` is the only
                           # caller that ships. Both sites are named so the split is
                           # explicit rather than incidental.
                           "gbp_vpix_block": {"pump": 1, "gbp_vpix_frame": 1},
                           # (the gettime pin lives above, next to the submit
                           # site it was widened for -- a second key here would
                           # silently shadow it, which is how the last profile
                           # edit was lost)
                           # §V5.39.4: the witness rule is applied at exactly ONE
                           # place, in the service path, and nothing else in the
                           # runtime may reach the store. `gbp_vwitness_step` is
                           # a static inline, so the sites that survive are its
                           # bodies' calls out of gbp_vstate_probe_run.
                           # TWO sites each, and that is the assertion: the rule
                           # has exactly two orderings — place-then-close for the
                           # 48-block give-up, close-then-place for a boundary —
                           # and `gbp_vwitness_step` inlines both. Collapsing them
                           # into one would put a block in the wrong frame, so the
                           # count is pinned rather than left to drift.
                           "gbp_vwitness_stage": {"gbp_vstate_probe_run": 2},
                           "gbp_vwitness_place": {"gbp_vstate_probe_run": 2},
                           "gbp_vwitness_commit": {"gbp_vstate_probe_run": 1},
                           "gbp_vwitness_note_ticks": {"gbp_vstate_probe_run": 1},
                           # §V5.39.8: the sidecar is written from main.o and
                           # from nowhere else. A serializer reachable from the
                           # service path would be a filesystem call in the
                           # capture window, which is the thing being forbidden.
                           "gbp_vidxdump_stream": {"main": 1},
                           # §V5.46: the SECOND sidecar, written from the same
                           # place and after the same teardown. Both serializers
                           # are reachable from main and from nowhere else, and
                           # both are pinned so neither can drift into the
                           # capture window later.
                           "gbp_vdispdump_stream": {"main": 1},
                           "sdlog_stream_open": {"main": 2},
                           "sdlog_stream_write": {"sink_sd": 1},
                           "sdlog_save": {"main": 1}},
        "elf_required": ("gbp_vstate_probe_run", "gbp_vstate_report", "gbp_vstate_block", "gbp_vsig_block",
                         "gbp_vqueue_publish", "gbp_vqueue_take", "gbp_vqueue_commit", "gbp_vpix_block",
                         "gbp_vpresent_acquire", "gbp_vpresent_submit", "gbp_vpresent_draw_done",
                         "gbp_vpresent_xfb_target", "gbp_vpresent_shutdown", "GX_SetDrawDoneCallback",
                         # stream-0003: the storage diagnostic, the R1 assertion
                         # and the R8 latch must all SHIP, not merely compile.
                         "gbp_vstate_storage_fault", "gbp_vstate_configured_bytes",
                         "gbp_vqueue_pristine", "gbp_vpresent_invariant_failures",
                         # stream-0005: the witness retention, its bounded stop and
                         # its sidecar must SHIP, not merely compile.
                         "gbp_vwitness_stage", "gbp_vwitness_place", "gbp_vwitness_commit",
                         "gbp_vwitness_target_reached", "gbp_vwitness_store_full",
                         "gbp_vidxdump_stream", "gbp_vidxdump_layout",
                         "gbp_initirqa_run_cause", "gbp_initirqa_teardown", "gbp_regwrite_irq_u16",
                         "gbp_regwrite_control_byte", "hsp_backend_oneshot_isr_ext",
                         "hsp_backend_irq_transport_ext", "__UnmaskIrq", "__MaskIrq", "IRQ_Request",
                         "GX_Init", "GX_InitTexObj", "GX_LoadTexObj", "DCFlushRange"),
        "elf_forbidden": ("gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run",
                          "gbp_initirq4_probe_run", "gbp_avsvc_probe_run", "gbp_avdump_serialize",
                          "gbp_video_probe_run", "gbp_avseqdump_serialize", "gbp_vcoldump_stream",
                          "hsp_backend_intmr_transport", "hsp_backend_oneshot_isr_multi",
                          "hsp_backend_irq_transport_multi", "hsp_backend_irq_transport",
                          "ARQ_Init", "AR_Init", "AUDIO_Init", "ASND_Init", "net_init"),
        "irq_write_sites": {"gbp_initirqa_probe.o": 3, "gbp_irq_service.o": 1, "gbp_vstate_probe.o": 3},
        "control_write_sites": {"gbp_initirqa_probe.o": 2},
        "intsr_store_sites": {"h_write_intsr": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
        # The qualification state machine (§V5.44). It decides WHEN to start
        # measuring and must not be able to consult the measurement, so its
        # outward edges are enumerated rather than merely restricted.
        "object_may_only_reference": {
            "gbp_vwitness.o": ("memset", "__udivdi3"),
            # §V5.46: the disposition trace runs INSIDE the capture window and
            # inside the draw-done callback. Its outward edges are enumerated
            # for the same reason the witness's are: so a filesystem call, a
            # CRC or a decoder written later is a finding by default.
            "gbp_vdisp.o": ("memset",),
        },
        "object_must_not_reference": {
            "gbp_vstate_probe.o": _CAPTURE_SYMBOLS,
            "gbp_vstate.o": _CAPTURE_SYMBOLS,
            "gbp_vwitness.o": _CAPTURE_SYMBOLS,
            "gbp_vpix.o": _FS_SYMBOLS,
            "gbp_vqueue.o": _FS_SYMBOLS,
            "gbp_vpresent.o": _FS_SYMBOLS,
            "gbp_vsig.o": _CAPTURE_SYMBOLS,
            "gbp_vstatedump.o": _FS_SYMBOLS,
            "gbp_vidxdump.o": _FS_SYMBOLS,
            "gbp_vdispdump.o": _FS_SYMBOLS,   # post-teardown serializer: CRC is fine, the filesystem is not
            "gbp_time64.o": _FS_SYMBOLS,
            "gbp_avblock.o": _FS_SYMBOLS,
            "gbp_irq_service.o": _CAPTURE_SYMBOLS,
            "gbp_initirqa_probe.o": _FS_SYMBOLS,
            "hsp_backend.o": _FS_SYMBOLS,
            "hsp_backend_irq.o": _FS_SYMBOLS,
        },
        # The sidecar is OGBPIDXCAP1, written from main.o after the teardown
        # (§V5.39.8). The frozen OGBPSEQ1 and OGBPCOL1 writers stay untouched.
        "main_must_call": ("hsp_backend_irq_transport_ext", "gbp_vstate_probe_run", "sdlog_save",
                           "GX_Init", "GX_InitTexObj", "GX_LoadTexObj", "DCFlushRange",
                           "GX_SetDrawDoneCallback", "GX_SetDrawDone"),
        "main_must_not_call": ("hsp_backend_irq_transport", "hsp_backend_irq_transport_multi",
                               "hsp_backend_intmr_transport", "gbp_initirqa_probe_run", "gbp_initirqb_probe_run",
                               "gbp_initirq4_probe_run", "gbp_initirq_probe_run", "gbp_avsvc_probe_run",
                               "gbp_video_probe_run", "gbp_irq_service_ack", "gbp_vqueue_publish"),
    },
}
# the GBP-INIT-003A names, kept for callers that import them
FORBIDDEN_OBJECTS = PROFILES["003a"]["forbidden_objects"]
FORBIDDEN_SYMBOLS = PROFILES["003a"]["forbidden_symbols"]
INVESTIGATE_SYMBOLS = PROFILES["003a"]["investigate_symbols"]
ELF_REQUIRED = PROFILES["003a"]["elf_required"]
ELF_FORBIDDEN = PROFILES["003a"]["elf_forbidden"]
IRQ_WRITE_SITES = PROFILES["003a"]["irq_write_sites"]
CONTROL_WRITE_SITES = PROFILES["003a"]["control_write_sites"]

FUNC_RE = re.compile(r"^[0-9a-f]+ <([^>]+)>:\s*$")
INSN_RE = re.compile(r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{2} ){4}\s*(\S+)\s*(.*)$")
RELOC_RE = re.compile(r"^\s*([0-9a-f]+): (R_PPC_\w+)\s+(\S+)")
STORE_MNEMONICS = ("stw", "sth", "stb", "stwu", "sthu", "stbu", "stwx", "sthx", "stbx", "stwux", "sthux", "stbux",
                   "stwbrx", "sthbrx", "stmw", "stfs", "stfd", "stfsu", "stfdu", "stfsx", "stfdx")
NO_GPR_WRITE = ("cmpw", "cmpwi", "cmplw", "cmplwi", "cmpd", "cmpdi", "cmpld", "cmpldi", "mtlr", "mtctr", "mtcrf", "mtspr",
                "mtmsr", "mtsr", "sync", "isync", "eieio", "dcbf", "dcbi", "dcbst", "dcbz", "icbi", "nop", "b", "bl",
                "blr", "bctr", "bctrl", "bdnz", "bdz", "beq", "bne", "blt", "bgt", "ble", "bge", "beq+", "bne+", "blt+",
                "bgt+", "ble+", "bge+", "beq-", "bne-", "blt-", "bgt-", "ble-", "bge-", "bns", "bso", "twi", "tw", "sc",
                "rfi", "crclr", "crset", "crxor", "creqv", "cror", "crand", "crnor", "crandc", "crorc", "crnand", "mcrf")
PI_INTSR = 0xCC003000
PI_INTMR = 0xCC003004


def parse_objdump(text):
    """Returns (functions: {name: [items]}) where items are ('insn', addr, mnemonic, operands) or ('reloc', addr, type, symbol)."""
    funcs = {}
    cur = None
    for line in text.splitlines():
        m = FUNC_RE.match(line)
        if m:
            cur = m.group(1)
            funcs[cur] = []
            continue
        if cur is None:
            continue
        m = RELOC_RE.match(line)
        if m:
            funcs[cur].append(("reloc", int(m.group(1), 16), m.group(2), m.group(3)))
            continue
        m = INSN_RE.match(line)
        if m:
            funcs[cur].append(("insn", int(m.group(1), 16), m.group(2), m.group(3).strip()))
    return funcs


def reloc_symbols(funcs):
    out = {}
    for name, items in funcs.items():
        for it in items:
            if it[0] == "reloc":
                out.setdefault(it[3], []).append(name)
    return out


def _imm(s):
    s = s.strip()
    return int(s, 16) if s.lower().startswith(("0x", "-0x")) else int(s)


COND_BRANCH_BASES = {"beq", "bne", "blt", "bgt", "ble", "bge", "bns", "bso", "bnl", "bng", "bnu", "bun", "bdz", "bdnz",
                     "bdzt", "bdzf", "bdnzt", "bdnzf", "bt", "bf", "bc"}
VOLATILE_GPRS = ("r0",) + tuple("r%d" % i for i in range(3, 13))


def _branch_target(ops):
    """Offset printed by objdump as the branch target ("98 <f+0x98>", "cr7,98 <f+0x98>"), else None."""
    if not ops:
        return None
    tgt = ops.split(",")[-1].strip().split()
    if not tgt:
        return None
    try:
        return int(tgt[0], 16)
    except ValueError:
        return None


def _apply(regs, mn, ops, has_reloc):
    """Register state after one non-branch instruction (a new dict); a relocated immediate is unknown."""
    regs = dict(regs)
    parts = [p.strip() for p in ops.split(",")] if ops else []
    try:
        if mn == "lis" and len(parts) == 2:
            if has_reloc:
                regs.pop(parts[0], None)
            else:
                regs[parts[0]] = (_imm(parts[1]) & 0xFFFF) << 16
        elif mn == "li" and len(parts) == 2:
            if has_reloc:
                regs.pop(parts[0], None)
            else:
                regs[parts[0]] = _imm(parts[1]) & 0xFFFFFFFF
        elif mn == "ori" and len(parts) == 3:
            if parts[1] in regs and not has_reloc:
                regs[parts[0]] = regs[parts[1]] | (_imm(parts[2]) & 0xFFFF)
            else:
                regs.pop(parts[0], None)
        elif mn == "oris" and len(parts) == 3:
            if parts[1] in regs and not has_reloc:
                regs[parts[0]] = regs[parts[1]] | ((_imm(parts[2]) & 0xFFFF) << 16)
            else:
                regs.pop(parts[0], None)
        elif mn in ("addi", "addic") and len(parts) == 3:
            if parts[1] in regs and not has_reloc:
                regs[parts[0]] = (regs[parts[1]] + _imm(parts[2])) & 0xFFFFFFFF
            else:
                regs.pop(parts[0], None)
        elif mn == "addis" and len(parts) == 3:
            if parts[1] in regs and not has_reloc:
                regs[parts[0]] = (regs[parts[1]] + (_imm(parts[2]) << 16)) & 0xFFFFFFFF
            else:
                regs.pop(parts[0], None)
        elif mn == "mr" and len(parts) == 2:
            if parts[1] in regs:
                regs[parts[0]] = regs[parts[1]]
            else:
                regs.pop(parts[0], None)
        elif mn in STORE_MNEMONICS:
            if mn.endswith("u") or mn.endswith("ux"):                  # update forms write the base register
                m = re.search(r"\((r\d+)\)", ops)
                if m:
                    regs.pop(m.group(1), None)
                elif len(parts) == 3:
                    regs.pop(parts[1], None)
        elif mn in NO_GPR_WRITE:
            pass
        elif parts and re.match(r"^r\d+$", parts[0]):
            regs.pop(parts[0], None)                                    # unknown value from here on
    except ValueError:
        if parts and re.match(r"^r\d+$", parts[0]):
            regs.pop(parts[0], None)
    return regs


def track_registers(insns, reloc_offsets=()):
    """insns: [(offset, mnemonic, operands)] of one function in listing order. Returns, per
    instruction, the dict of GPR values known on entry to it — a forward data-flow pass over the
    function's control-flow graph: a block reached from several places keeps only the values every
    predecessor agrees on, loops iterate to a fixpoint, calls (bl/bctrl) clobber the volatile GPRs
    r0 and r3–r12, and an immediate carrying a relocation is unknown. None marks an instruction the
    analysis never reached (dead code)."""
    n = len(insns)
    if n == 0:
        return []
    off_to_i = {off: i for i, (off, _, _) in enumerate(insns)}
    relocs = set(reloc_offsets)
    state = [None] * n
    state[0] = {}

    def meet(a, b):
        if a is None:
            return dict(b)
        return {r: v for r, v in a.items() if r in b and b[r] == v}

    for _round in range(64):
        changed = False
        for i in range(n):
            s = state[i]
            if s is None:
                continue
            off, mn, ops = insns[i]
            base = mn.rstrip("+-")
            succ = []
            if base in ("blr", "bctr", "rfi", "sc"):
                out = s
            elif base in ("b", "ba"):
                out = s
                t = _branch_target(ops)
                if t in off_to_i:
                    succ.append(off_to_i[t])
            elif base in ("bl", "bla", "bctrl", "blrl"):
                out = dict(s)
                for r in VOLATILE_GPRS:
                    out.pop(r, None)
                succ.append(i + 1)
            elif base in COND_BRANCH_BASES or (base.startswith("b") and _branch_target(ops) is not None):
                out = s
                succ.append(i + 1)
                t = _branch_target(ops)
                if t in off_to_i:
                    succ.append(off_to_i[t])
            else:
                out = _apply(s, mn, ops, off in relocs or (off + 2) in relocs)
                succ.append(i + 1)
            for t in succ:
                if t >= n:
                    continue
                new = meet(state[t], out)
                if new != state[t]:
                    state[t] = new
                    changed = True
        if not changed:
            break
    return state


def store_ea_and_value(regs, mn, ops):
    """(effective address, stored value) of a store instruction under the known registers; None when unknown."""
    parts = [p.strip() for p in ops.split(",")] if ops else []
    ea = None
    m = re.search(r"(-?\d+)\((r\d+)\)", ops)
    try:
        if m and m.group(2) in regs:
            ea = (regs[m.group(2)] + int(m.group(1))) & 0xFFFFFFFF
        elif not m and len(parts) == 3 and parts[1] in regs and parts[2] in regs:   # indexed form
            ea = (regs[parts[1]] + regs[parts[2]]) & 0xFFFFFFFF
    except ValueError:
        ea = None
    value = regs.get(parts[0]) if parts else None
    return ea, value


def pi_stores(funcs):
    """Store instructions whose effective address is PI INTMR or PI INTSR, under
    the register values track_registers() proves at each store. Returns
    (intmr_hits, intsr_hits) as lists of (function, addr, mnemonic, operands)."""
    intmr, intsr = [], []
    for name, items in funcs.items():
        insns = [(it[1], it[2], it[3]) for it in items if it[0] == "insn"]
        relocs = {it[1] for it in items if it[0] == "reloc"}
        states = track_registers(insns, relocs)
        for (addr, mn, ops), regs in zip(insns, states):
            if regs is None or mn not in STORE_MNEMONICS:
                continue
            ea, _value = store_ea_and_value(regs, mn, ops)
            if ea == PI_INTMR:
                intmr.append((name, addr, mn, ops))
            elif ea == PI_INTSR:
                intsr.append((name, addr, mn, ops))
    return intmr, intsr


def intmr_stores(funcs):
    return pi_stores(funcs)[0]


def call_count(funcs, symbol):
    n = 0
    for items in funcs.values():
        for it in items:
            if it[0] == "reloc" and it[2] == "R_PPC_REL24" and it[3] == symbol:
                n += 1
    return n


def call_sites(funcs, symbol):
    """{function: number of branch-and-link relocations to `symbol`} inside one object."""
    out = {}
    for name, items in funcs.items():
        for it in items:
            if it[0] == "reloc" and it[2] == "R_PPC_REL24" and it[3] == symbol:
                out[name] = out.get(name, 0) + 1
    return out


def parse_nm(text):
    defined = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3:
            defined[parts[2]] = parts[1]
        elif len(parts) == 2:
            defined[parts[1]] = parts[0]
    return defined


def audit_dir(path, profile="003a"):
    prof = PROFILES[profile]
    findings = []
    report = {"profile": profile, "objects": [], "symbols": {}, "symbol_callers": {}, "intmr_stores": [], "intsr_stores": [],
              "intsr_store_sites": {}, "callsites": {}, "elf": {}}
    files = sorted(glob.glob(os.path.join(path, "*.objdump.txt")))
    if not files:
        findings.append("no *.objdump.txt in %s" % path)
        return findings, report
    objects = {}
    for f in files:
        obj = os.path.basename(f)[:-len(".objdump.txt")] + ".o"
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            objects[obj] = parse_objdump(fh.read())
        report["objects"].append(obj)
    for bad in prof["forbidden_objects"]:
        if bad in objects:
            findings.append("forbidden object linked: %s" % bad)
    for need in prof["required_objects"]:
        if need not in objects:
            findings.append("expected object missing: %s" % need)
    irq_sites_total = 0
    callers = {s: {} for s in prof["symbol_callers"]}
    intsr_sites = {}
    for obj, funcs in objects.items():
        syms = reloc_symbols(funcs)
        for s in prof["forbidden_symbols"]:
            if s in syms:
                findings.append("%s references %s (from %s)" % (obj, s, ", ".join(sorted(set(syms[s])))))
                report["symbols"].setdefault(obj, []).append(s)
        for s in prof["investigate_symbols"]:
            if s in syms:
                findings.append("%s references %s — investigate (from %s)" % (obj, s, ", ".join(sorted(set(syms[s])))))
                report["symbols"].setdefault(obj, []).append(s)
        # §V5.44.18 ALLOWLIST. A deny-list can only forbid the decoders that
        # exist today; the qualification state machine must be unable to reach
        # one that is written tomorrow. So the rule is inverted for it: name
        # everything it MAY reference and reject the rest. It currently reaches
        # memset and the compiler's 64-bit divide helper and nothing else, so
        # any new outward edge — a signature, a colour, a CRC, a decoder — is a
        # finding by default rather than by enumeration.
        allow = prof.get("object_may_only_reference", {}).get(obj)
        if allow is not None:
            for s in sorted(syms):
                if s.startswith(".text.") or s.startswith(".rodata."):
                    continue          # this object's own sections, not an outward edge
                if s not in allow:
                    findings.append("%s references %s — not in this object's allowlist (from %s)"
                                    % (obj, s, ", ".join(sorted(set(syms[s])))))
                    report["symbols"].setdefault(obj, []).append(s)
        for s_bad in prof.get("object_must_not_reference", {}).get(obj, ()):
            if s_bad in syms:
                findings.append("%s references %s — forbidden in this object's path (from %s)"
                                % (obj, s_bad, ", ".join(sorted(set(syms[s_bad])))))
                report["symbols"].setdefault(obj, []).append(s_bad)
        exempt = prof.get("prefix_exempt_objects", {}).get(obj, ())
        for pref in prof.get("forbidden_symbol_prefixes", ()):
            if pref in exempt:
                continue          # this object is ALLOWED this prefix, by design
            for s in sorted(syms):
                if s.startswith(pref):
                    findings.append("%s references %s (forbidden prefix %s; from %s)" % (obj, s, pref, ", ".join(sorted(set(syms[s])))))
                    report["symbols"].setdefault(obj, []).append(s)
        for s in prof["symbol_callers"]:
            for fn, n in call_sites(funcs, s).items():
                callers[s][fn] = callers[s].get(fn, 0) + n
            for fn in syms.get(s, []):
                callers[s].setdefault(fn, 0)          # a non-call relocation (address taken) counts as a caller with 0 calls
        intmr_hits, intsr_hits = pi_stores(funcs)
        for hit in intmr_hits:
            findings.append("%s stores to PI INTMR in %s at 0x%x: %s %s" % (obj, hit[0], hit[1], hit[2], hit[3]))
            report["intmr_stores"].append([obj] + [str(x) for x in hit])
        for hit in intsr_hits:
            report["intsr_stores"].append([obj] + [str(x) for x in hit])
            intsr_sites[hit[0]] = intsr_sites.get(hit[0], 0) + 1
        n_irq = call_count(funcs, "gbp_regwrite_irq_u16")
        n_ctl = call_count(funcs, "gbp_regwrite_control_byte")
        report["callsites"][obj] = {"gbp_regwrite_irq_u16": n_irq, "gbp_regwrite_control_byte": n_ctl}
        irq_sites_total += n_irq
        want = prof["irq_write_sites"].get(obj)
        if want is not None and n_irq != want:
            findings.append("%s calls gbp_regwrite_irq_u16 %d times (expected %d)" % (obj, n_irq, want))
        if want is None and n_irq:
            findings.append("%s calls gbp_regwrite_irq_u16 (%d) — only the probe may" % (obj, n_irq))
        want = prof["control_write_sites"].get(obj)
        if want is not None and n_ctl != want:
            findings.append("%s calls gbp_regwrite_control_byte %d times (expected %d)" % (obj, n_ctl, want))
        if want is None and n_ctl:
            findings.append("%s calls gbp_regwrite_control_byte (%d) — only the probe may" % (obj, n_ctl))
        if obj == "main.o":
            for s in prof["main_must_call"]:
                if s not in syms:
                    findings.append("main.o does not reference %s" % s)
            for s in prof["main_must_not_call"]:
                if s in syms:
                    findings.append("main.o references %s (from %s)" % (s, ", ".join(sorted(set(syms[s])))))
    for s, want in prof["symbol_callers"].items():
        got = callers[s]
        report["symbol_callers"][s] = dict(sorted(got.items()))
        if got != want:
            findings.append("%s call sites %s, expected exactly %s" % (s, json.dumps(dict(sorted(got.items()))), json.dumps(dict(sorted(want.items())))))
    report["intsr_store_sites"] = dict(sorted(intsr_sites.items()))
    if intsr_sites != prof["intsr_store_sites"]:
        findings.append("PI INTSR store sites %s, expected exactly %s" % (json.dumps(dict(sorted(intsr_sites.items()))),
                                                                          json.dumps(dict(sorted(prof["intsr_store_sites"].items())))))
    report["irq_write_sites_total"] = irq_sites_total
    nm_path = os.path.join(path, "elf.nm.txt")
    if os.path.isfile(nm_path):
        with open(nm_path, "r", encoding="utf-8", errors="replace") as fh:
            defined = parse_nm(fh.read())
        for s in prof["elf_required"]:
            report["elf"][s] = defined.get(s)
            if s not in defined:
                findings.append("ELF does not define %s" % s)
        for s in prof["elf_forbidden"]:
            report["elf"][s] = defined.get(s)
            if s in defined:
                findings.append("ELF defines %s (must not be linked)" % s)
        report["elf"]["__UnmaskIrq"] = defined.get("__UnmaskIrq")
    else:
        findings.append("elf.nm.txt missing")
    return findings, report


def format_report(findings, report):
    out = ["poc_audit: %d finding(s)" % len(findings), "profile: %s" % report.get("profile", "003a")]
    for f in findings:
        out.append("  FINDING " + f)
    out.append("objects: " + ", ".join(report["objects"]))
    for s, got in sorted(report.get("symbol_callers", {}).items()):
        out.append("call sites %s: %s" % (s, ", ".join("%s=%d" % kv for kv in sorted(got.items())) or "none"))
    for obj, c in sorted(report["callsites"].items()):
        if c["gbp_regwrite_irq_u16"] or c["gbp_regwrite_control_byte"]:
            out.append("callsites %s: gbp_regwrite_irq_u16=%d gbp_regwrite_control_byte=%d"
                       % (obj, c["gbp_regwrite_irq_u16"], c["gbp_regwrite_control_byte"]))
    out.append("irq write sites total: %d" % report.get("irq_write_sites_total", 0))
    out.append("intmr stores: %d" % len(report["intmr_stores"]))
    out.append("intsr stores (W1C acknowledge, allowed): %d%s" % (len(report["intsr_stores"]),
               " — " + ", ".join("%s:%s" % (h[0], h[1]) for h in report["intsr_stores"]) if report["intsr_stores"] else ""))
    for k, v in sorted(report["elf"].items()):
        out.append("elf %s: %s" % (k, "defined (%s)" % v if v else "absent"))
    if report["elf"].get("__UnmaskIrq") and report.get("profile", "003a") == "003a":
        out.append("note: __UnmaskIrq is defined by libogc2 and used by its own VIDEO/PAD/EXI setup; no POC object references it")
    return "\n".join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    path = argv[0]
    report_path = None
    as_json = False
    profile = "003a"
    i = 1
    while i < len(argv):
        if argv[i] == "--report" and i + 1 < len(argv):
            report_path = argv[i + 1]
            i += 2
        elif argv[i] == "--profile" and i + 1 < len(argv):
            profile = argv[i + 1]
            if profile not in PROFILES:
                print("unknown profile", profile, "(known: %s)" % ", ".join(sorted(PROFILES)), file=sys.stderr)
                return 2
            i += 2
        elif argv[i] == "--json":
            as_json = True
            i += 1
        else:
            print("unknown argument", argv[i], file=sys.stderr)
            return 2
    findings, report = audit_dir(path, profile)
    text = json.dumps({"findings": findings, "report": report}, indent=1) if as_json else format_report(findings, report)
    print(text)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(format_report(findings, report) + "\n")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
