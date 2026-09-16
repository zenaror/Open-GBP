"""
Build-artifact checks for poc/smoke-test.

These tests inspect what the Docker/devkitPPC build produced under
build/poc/smoke-test/. They are skipped (with an explicit reason) when the
build has not been run; `make test` at the repository root builds first.

Runs under pytest or `python3 -m unittest`.
"""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import dolinfo  # noqa: E402

POCS = ("smoke-test", "gbp-probe", "gbp-init-probe", "gbp-init-irq-probe", "gbp-init-irq-program-probe", "gbp-init-irq-deliver-probe",
        "gbp-init-irq-service-probe", "gbp-av-service-probe",
        "gbp-video-capture-probe")
OUTDIR = os.path.join(ROOT, "build", "poc", "smoke-test")
ELF = os.path.join(OUTDIR, "smoke-test.elf")
DOL = os.path.join(OUTDIR, "smoke-test.dol")
DOL_UNPADDED = os.path.join(OUTDIR, "smoke-test.unpadded.dol")
BUILD_INFO = os.path.join(OUTDIR, "build-info.txt")

# libogc2 GameCube link layout: text begins just above the OS globals area.
EXPECTED_TEXT_BASE = 0x80003100


def read_build_info(path=BUILD_INFO):
    info = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                info[k] = v
    return info


@unittest.skipUnless(os.path.isdir(OUTDIR),
                     "build output missing; run `make build` first")
class SmokeTestArtifacts(unittest.TestCase):
    def test_elf_exists_and_is_powerpc(self):
        self.assertTrue(os.path.isfile(ELF), ELF)
        with open(ELF, "rb") as f:
            hdr = f.read(20)
        self.assertEqual(hdr[:4], b"\x7fELF")
        self.assertEqual(hdr[4], 1, "ELFCLASS32")
        self.assertEqual(hdr[5], 2, "ELFDATA2MSB (big-endian)")
        e_machine = int.from_bytes(hdr[18:20], "big")
        self.assertEqual(e_machine, 20, "EM_PPC")

    def test_dol_exists_and_parses(self):
        self.assertTrue(os.path.isfile(DOL), DOL)
        info = dolinfo.parse_dol_file(DOL)
        self.assertGreaterEqual(len(info.text_sections), 1)
        self.assertGreaterEqual(len(info.data_sections), 1)
        self.assertGreater(info.bss_size, 0)

    def test_dol_entry_and_layout(self):
        info = dolinfo.parse_dol_file(DOL)
        first_text = min(info.text_sections, key=lambda s: s.load_address)
        self.assertEqual(first_text.load_address, EXPECTED_TEXT_BASE)
        entry_sec = info.section_containing(info.entry_point)
        self.assertIsNotNone(entry_sec)
        self.assertEqual(entry_sec.kind, "text")
        # No two sections may overlap in memory.
        spans = sorted((s.load_address, s.end_address) for s in info.sections)
        for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0, "overlapping sections %x-%x / %x-%x" % (a0, a1, b0, b1))

    def test_final_dol_is_dolphin_loadable(self):
        # Dolphin 2606a rejects sections whose address/size are not 32-byte
        # multiples; the build pads elf2dol's output with tools/dolpad.py.
        info = dolinfo.parse_dol_file(DOL)
        self.assertTrue(info.dolphin_loadable,
                        [(s.kind, s.index, hex(s.size)) for s in info.unaligned_sections])
        self.assertTrue(os.path.isfile(DOL_UNPADDED), DOL_UNPADDED)
        raw = dolinfo.parse_dol_file(DOL_UNPADDED)
        # same code, same addresses, only sizes rounded up
        self.assertEqual(raw.entry_point, info.entry_point)
        self.assertEqual([s.load_address for s in raw.sections],
                         [s.load_address for s in info.sections])
        for a, b in zip(raw.sections, info.sections):
            self.assertLessEqual(a.size, b.size)
            self.assertLess(b.size - a.size, 32)

    def test_dol_is_small(self):
        # A hello-world class libogc2 program; guards against accidental bloat.
        size = os.path.getsize(DOL)
        self.assertLess(size, 2 * 1024 * 1024, "DOL unexpectedly large: %d bytes" % size)

    def test_build_info_matches_embedded_identity(self):
        self.assertTrue(os.path.isfile(BUILD_INFO), BUILD_INFO)
        info = read_build_info()
        for key in ("app", "build_id", "commit", "sha256_dol", "cc", "libogc2"):
            self.assertIn(key, info)
        self.assertEqual(info["app"], "smoke-test")
        self.assertRegex(info["build_id"], r"^smoke-\d{4}$")
        self.assertRegex(info["commit"], r"^([0-9a-f]{7,}(-dirty)?|unknown)$")

        marker = ("OPENGBP-IDENT app=%s build=%s commit=%s"
                  % (info["app"], info["build_id"], info["commit"])).encode("ascii")
        with open(DOL, "rb") as f:
            blob = f.read()
        self.assertIn(marker, blob, "identity marker not found in DOL")
        self.assertEqual(blob.count(b"OPENGBP-IDENT "), 1)

    def test_build_info_hash_matches_dol(self):
        import hashlib
        info = read_build_info()
        with open(DOL, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(info["sha256_dol"], digest)

    def test_gecko_protocol_strings_present(self):
        # The Dolphin runner keys on these literals; keep them in sync.
        with open(DOL, "rb") as f:
            blob = f.read()
        self.assertIn(b"OPENGBP-SMOKE READY ", blob)
        self.assertIn(b"OPENGBP-SMOKE HEARTBEAT n=", blob)

    def test_libogc_version_recorded(self):
        info = read_build_info()
        self.assertTrue(re.match(r"^libogc2 r\d+\.[0-9a-f]+$", info["libogc2"]), info["libogc2"])


@unittest.skipUnless(all(os.path.isdir(os.path.join(ROOT, "build", "poc", p)) for p in POCS),
                     "build output missing; run `make build` first")
def elf_loads(path):
    """PT_LOAD segments of a 32-bit big-endian ELF as (offset, vaddr, filesz, memsz)."""
    import struct
    with open(path, "rb") as f:
        elf = f.read()
    e_phoff = struct.unpack(">I", elf[0x1C:0x20])[0]
    e_phentsize, e_phnum = struct.unpack(">HH", elf[0x2A:0x2E])
    out = []
    for i in range(e_phnum):
        p = elf[e_phoff + i * e_phentsize: e_phoff + (i + 1) * e_phentsize]
        p_type, p_offset, p_vaddr, _p_paddr, p_filesz, p_memsz, _f, _a = struct.unpack(">8I", p)
        if p_type == 1:
            out.append((p_offset, p_vaddr, p_filesz, p_memsz))
    return elf, out


@unittest.skipUnless(os.path.isdir(OUTDIR), "build output missing; run `make build` first")
class EveryPocSectionMap(unittest.TestCase):
    """DOL sections against the ELF program headers, for every POC: the loaded payload is exactly the
    ELF's file-backed bytes; the only bytes a DOL section adds are tools/dolpad.py's zero padding, which
    may extend into the BSS start (the runtime zeroes BSS after the load: libogc2 ogc_crt0.S memsets
    __bss_start..__bss_end) but never over another loaded section; every section lives in MEM1."""

    def test_loaded_bytes_never_overlap_bss_except_zero_padding(self):
        import struct
        for poc in POCS:
            dol_path = os.path.join(ROOT, "build", "poc", poc, poc + ".dol")
            elf_path = os.path.join(ROOT, "build", "poc", poc, poc + ".elf")
            if not (os.path.isfile(dol_path) and os.path.isfile(elf_path)):
                continue
            info = dolinfo.parse_dol_file(dol_path)
            with open(dol_path, "rb") as f:
                dol = f.read()
            elf, loads = elf_loads(elf_path)
            bss_lo, bss_hi = info.bss_address, info.bss_address + info.bss_size
            self.assertGreater(info.bss_size, 0, poc)
            self.assertEqual(info.entry_point, 0x80003100, poc)
            for s in info.sections:
                self.assertTrue(0x80003100 <= s.load_address and s.end_address <= 0x81800000, (poc, s.kind, s.index))
                self.assertEqual(s.load_address % 32, 0, (poc, s.kind))
                self.assertEqual(s.size % 32, 0, (poc, s.kind))
                payload = dol[s.file_offset:s.file_offset + s.size]
                # every ELF file-backed byte inside this section is reproduced verbatim
                backed = bytearray(s.size)
                for off, vaddr, filesz, _memsz in loads:
                    lo, hi = max(vaddr, s.load_address), min(vaddr + filesz, s.end_address)
                    if lo < hi:
                        self.assertEqual(payload[lo - s.load_address:hi - s.load_address], elf[off + (lo - vaddr):off + (hi - vaddr)], (poc, s.kind))
                        for i in range(lo - s.load_address, hi - s.load_address):
                            backed[i] = 1
                # the bytes the DOL adds (padding) are zero, and a file-backed byte is never inside BSS
                for i, b in enumerate(backed):
                    a = s.load_address + i
                    if not b:
                        self.assertEqual(payload[i], 0, (poc, s.kind, hex(a)))
                    else:
                        self.assertFalse(bss_lo <= a < bss_hi, (poc, s.kind, hex(a)))
            # no two DOL sections overlap; the BSS never overlaps a file-backed range
            spans = sorted((s.load_address, s.end_address) for s in info.sections)
            for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
                self.assertLessEqual(a1, b0, (poc, hex(a0), hex(a1), hex(b0), hex(b1)))
            for _off, vaddr, filesz, _memsz in loads:
                if filesz:
                    self.assertTrue(vaddr + filesz <= bss_lo or vaddr >= bss_hi, (poc, hex(vaddr), hex(filesz)))
            # the ELF BSS segment is the DOL BSS
            nobits = [(vaddr, memsz) for _o, vaddr, filesz, memsz in loads if filesz == 0 and memsz]
            self.assertEqual(nobits, [(bss_lo, info.bss_size)], poc)


class EveryPocArtifacts(unittest.TestCase):
    """Common checks for every POC: valid, Dolphin-loadable DOL, identity
    marker, hash, and the READY line prefix the Dolphin runner keys on."""

    def test_each_poc(self):
        for poc in POCS:
            out = os.path.join(ROOT, "build", "poc", poc)
            dol = os.path.join(out, poc + ".dol")
            info = dolinfo.parse_dol_file(dol)
            self.assertTrue(info.dolphin_loadable, poc)
            self.assertEqual(info.entry_point, 0x80003100, poc)
            bi = read_build_info(os.path.join(out, "build-info.txt"))
            self.assertEqual(bi["app"], poc)
            with open(dol, "rb") as f:
                blob = f.read()
            marker = ("OPENGBP-IDENT app=%s build=%s commit=%s" % (bi["app"], bi["build_id"], bi["commit"])).encode()
            self.assertIn(marker, blob, poc)
            prefix = {"smoke-test": b"OPENGBP-SMOKE READY ", "gbp-probe": b"OPENGBP-PROBE READY ",
                      "gbp-init-probe": b"OPENGBP-INIT READY ",
                      "gbp-init-irq-probe": b"OPENGBP-INITIRQ READY ",
                      "gbp-init-irq-program-probe": b"OPENGBP-INITIRQA READY ",
                      "gbp-init-irq-deliver-probe": b"OPENGBP-INITIRQB READY ",
                      "gbp-init-irq-service-probe": b"OPENGBP-INITIRQ4 READY ", "gbp-av-service-probe": b"OPENGBP-AVSVC READY ",
                      "gbp-video-capture-probe": b"OPENGBP-VIDEO READY "}[poc]
            self.assertIn(prefix, blob, poc)

    def test_probe_writes_only_documented_things(self):
        # The probe binary must not contain the strings of features it must not touch.
        dol = os.path.join(ROOT, "build", "poc", "gbp-probe", "gbp-probe.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertIn(b"GBP-PROBE-001", blob)
        self.assertIn(b"OPENGBP-PROBE READY ", blob)
        self.assertNotIn(b"libmobile", blob)

    def test_init_irq_probe_identity_and_records(self):
        # GBP-INIT-002: its own test id, its own gecko prefix, the record
        # kinds the log tooling and the fixture tests key on.
        dol = os.path.join(ROOT, "build", "poc", "gbp-init-irq-probe", "gbp-init-irq-probe.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertIn(b"GBP-INIT-002", blob)
        self.assertNotIn(b"GBP-INIT-001", blob)
        self.assertIn(b"OPENGBP-INITIRQ READY ", blob)
        for rec in (b"INITIRQ start ", b"INITIRQ end status=", b"IRQ install rc=", b"UNMASK t_unmask=",
                    b"HANDLER fired=", b"HANDLERPI intsr_before_ack=", b"CLEANUP performed=", b"MASK final intmr="):
            self.assertIn(rec, blob, rec)
        self.assertNotIn(b"libmobile", blob)

    def test_init_irq_program_probe_identity_and_records(self):
        # GBP-INIT-003A: its own test id and gecko prefix; the record kinds the
        # log tooling keys on; none of the GBP-INIT-002 interrupt-path records
        # (that probe module and hsp_backend_irq.c must not be linked); the
        # mandatory power-cycle banner.
        dol = os.path.join(ROOT, "build", "poc", "gbp-init-irq-program-probe", "gbp-init-irq-program-probe.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertIn(b"GBP-INIT-003A", blob)
        self.assertNotIn(b"GBP-INIT-002", blob)
        self.assertNotIn(b"GBP-INIT-001", blob)
        self.assertIn(b"OPENGBP-INITIRQA READY ", blob)
        for rec in (b"INITIRQA start ", b"INITIRQA end status=", b"IRQSHAPE tag=", b"IRQW ", b"layout=gbi-u16-replicated",
                    b"SNAP tag=", b"WINDOW tag=", b"REGION log_count_start=", b"TEARDOWN start", b"IRQSTOP pre ",
                    b"comment=startup-disc-stop-shadow", b"CLEANUP performed=", b"RESTORE control_restore_ok=",
                    b"WRITES control_written=", b"OBSERVED intsr13_seen=", b"format=attempted/completed",
                    b"DEVICE STATE UNCERTAIN", b"POWER CYCLE REQUIRED"):
            self.assertIn(rec, blob, rec)
        for rec in (b"IRQ install rc=", b"UNMASK t_unmask=", b"HANDLER fired=", b"HANDLERPI intsr_before_ack=",
                    b"MASK final intmr=", b"INITIRQ start ", b"INIT start "):
            self.assertNotIn(rec, blob, rec)
        self.assertNotIn(b"libmobile", blob)
        bi = read_build_info(os.path.join(ROOT, "build", "poc", "gbp-init-irq-program-probe", "build-info.txt"))
        self.assertEqual(bi["build_id"], "initirqa-0001")

    def test_init_irq_deliver_probe_identity_and_records(self):
        # GBP-INIT-003B: its own test id and gecko prefix; the 003A stage records (reused module) plus the
        # delivery-stage records the log tooling keys on; none of the GBP-INIT-001/002 probe records nor
        # the 002 handler field names; the mandatory power-cycle banner; build id initirqb-0001.
        dol = os.path.join(ROOT, "build", "poc", "gbp-init-irq-deliver-probe", "gbp-init-irq-deliver-probe.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertIn(b"GBP-INIT-003B", blob)
        for tid in (b"GBP-INIT-003A", b"GBP-INIT-002", b"GBP-INIT-001"):
            self.assertNotIn(tid, blob, tid)
        self.assertIn(b"OPENGBP-INITIRQB READY ", blob)
        self.assertIn(b"OPENGBP-INITIRQB LOG ", blob)
        # since GBP-INIT-004 the cycle records are formatted by the shared service module with a "%s" cycle field
        # (empty for 003B: the log lines are unchanged, pinned by the physical fixture), so the format strings in the
        # binary carry the placeholder
        for rec in (b"INITIRQB start ", b"INITIRQB end status=", b"INITIRQA start ", b"CAUSE t_event=", b"IRQ install rc=",
                    b"PREUNMASK%s ok=", b"UNMASK%s t_unmask=", b"IRQ mask tag=MAIN%s rc=", b"WAIT%s fired=", b"HANDLER%s fired=",
                    b"HANDLERPI%s intsr_at_entry=", b"HANDLERPI2%s t_second=", b"DELIVERY%s fired=", b"PREACK%s intsr13=", b"ACK%s before=",
                    b"POSTACK%s intsr13=", b"MAINPICLEANUP%s site=POSTACK performed=", b"IRQW ", b"layout=gbi-u16-replicated",
                    b"comment=startup-disc-stop-shadow", b"CLEANUP performed=", b"IRQ restore rc=", b"MASK final intmr=",
                    b"ACKS ack=", b"RESTOREB handler_installed=", b"WRITES control_written=", b"format=attempted/completed",
                    b"DEVICE STATE UNCERTAIN", b"POWER CYCLE REQUIRED", b"install_point=after_latched_cause"):
            self.assertIn(rec, blob, rec)
        for rec in (b"HANDLERPI intsr_before_ack=", b"INITIRQ start ", b"INIT start ", b"INTMR mask ", b"INTMR restore "):
            self.assertNotIn(rec, blob, rec)
        self.assertNotIn(b"libmobile", blob)
        bi = read_build_info(os.path.join(ROOT, "build", "poc", "gbp-init-irq-deliver-probe", "build-info.txt"))
        self.assertEqual(bi["build_id"], "initirqb-0001")

    def test_init_irq_service_probe_identity_and_records(self):
        # GBP-INIT-004: its own test id and gecko prefix; the 003A stage records (reused module), the per-cycle
        # service records (shared module, " n=" field / "-n" tags), the 004 records; none of the other probes'
        # test ids, records or handler symbols' strings; the mandatory power-cycle banner; build id initirq4-0001.
        dol = os.path.join(ROOT, "build", "poc", "gbp-init-irq-service-probe", "gbp-init-irq-service-probe.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertIn(b"GBP-INIT-004", blob)
        for tid in (b"GBP-INIT-003B", b"GBP-INIT-003A", b"GBP-INIT-002", b"GBP-INIT-001"):
            self.assertNotIn(tid, blob, tid)
        self.assertIn(b"OPENGBP-INITIRQ4 READY ", blob)
        self.assertIn(b"OPENGBP-INITIRQ4 LOG ", blob)
        for rec in (b"INITIRQ4 start max_cycles=", b"INITIRQ4 policy handler=installed_once", b"INITIRQ4 end status=",
                    b"INITIRQA start ", b"CAUSE n=0 t_cause=", b"IRQ install rc=", b"MULTI install expected_gen=",
                    b"CYCLE n=%u start", b"PREPARE n=%u gen=%u rc=", b"PREUNMASK%s ok=", b"PREUNMASK4 n=", b"UNMASK%s t_unmask=",
                    b"IRQ mask tag=MAIN%s rc=", b"WAIT%s fired=", b"HANDLER%s fired=", b"HANDLERPI%s intsr_at_entry=",
                    b"HANDLERPI2%s t_second=", b"DELIVERY%s fired=", b"HANDLER4 n=", b"PREACK%s intsr13=", b"ACK%s before=",
                    b"POSTACK%s intsr13=", b"MAINPICLEANUP%s site=POSTACK performed=", b"PICLEAN n=", b"BOUNDARY n=",
                    b"REARM n=%u t_rearm=", b"REARMPOST n=", b"NEXTCAUSE n=%u found=1", b"NEXTCAUSE n=%u found=0 timed_out=1",
                    b"TEARDOWN4 variant=", b"CYCLES requested=", b"TIMING n=", b"MULTI expected_gen=", b"RESTORE4 handler_installed=",
                    b"IRQW ", b"layout=gbi-u16-replicated", b"comment=startup-disc-stop-shadow", b"CLEANUP performed=",
                    b"IRQ restore rc=", b"MASK final intmr=", b"WRITES control_written=", b"format=attempted/completed",
                    b"DEVICE STATE UNCERTAIN", b"POWER CYCLE REQUIRED", b"NOT A PHYSICAL CANDIDATE"):
            self.assertIn(rec, blob, rec)
        for rec in (b"INITIRQB start ", b"INITIRQ start ", b"INIT start ", b"INTMR mask ", b"INTMR restore ",
                    b"install_point=after_latched_cause", b"HANDLERPI intsr_before_ack="):
            self.assertNotIn(rec, blob, rec)
        self.assertNotIn(b"libmobile", blob)
        bi = read_build_info(os.path.join(ROOT, "build", "poc", "gbp-init-irq-service-probe", "build-info.txt"))
        self.assertEqual(bi["build_id"], "initirq4-0001")

    def test_av_service_probe_identity_and_records(self):
        # GBP-AV-SERVICE-001: its own test id and gecko prefix; the 003A stage records (reused module), the 003B
        # delivery / ACK records (shared module, empty cycle field), the service records, the block records, the
        # sidecar name; none of the other probes' test ids, records or the multi-cycle handler's strings; the
        # mandatory power-cycle banner; build id avsvc-0001; no framebuffer/GX/audio-output/network string.
        dol = os.path.join(ROOT, "build", "poc", "gbp-av-service-probe", "gbp-av-service-probe.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertIn(b"GBP-AV-SERVICE-001", blob)
        for tid in (b"GBP-INIT-004", b"GBP-INIT-003B", b"GBP-INIT-003A", b"GBP-INIT-002", b"GBP-INIT-001"):
            self.assertNotIn(tid, blob, tid)
        self.assertIn(b"OPENGBP-AVSVC READY ", blob)
        self.assertIn(b"OPENGBP-AVSVC LOG ", blob)
        self.assertIn(b"OPENGBP-AVSVC SAVEBLOCKS rc=", blob)
        for rec in (b"AVSVC start t_delivery_ms=", b"AVSVC blocks audio_idx=", b"AVSVC policy handler=003b_ext_installed_once",
                    b"AVSVC end status=", b"INITIRQA start ", b"CAUSE t_event=", b"IRQ install rc=", b"PREUNMASK%s ok=", b"PREUNMASKAV av=",
                    b"UNMASK%s t_unmask=", b"IRQ mask tag=MAIN%s rc=", b"WAIT%s fired=", b"HANDLER%s fired=", b"HANDLERPI%s intsr_at_entry=",
                    b"HANDLERPI2%s t_second=", b"DELIVERY%s fired=", b"SVC start pending=", b"ack_source=PRESVC", b"SVC abort reason=bulk_read_unavailable",
                    b"AUDIOREAD", b"VIDEOREAD", b"SVCEND drain=", b"POSTDRAIN observation_only=1", b"ACK%s before=", b"POSTACK%s intsr13=",
                    b"MAINPICLEANUP%s site=POSTACK performed=", b"POSTACKAV boundary=", b"requirement=none", b"PICLEAN intsr=",
                    b"REARM t_rearm=", b"after=drain_ack_pi_clean", b"REARMPOST t=", b"NEXTCAUSE found=1 immediate=", b"delivered=0",
                    b"NEXTCAUSE found=0 timed_out=1", b"TEARDOWNAV variant=", b"SERVICE pass pending=", b"SERVICE rearm relatch_postdrain=",
                    b"COUNTERS unmasks=", b"BLOCK kind=", b"BLOCKW kind=", b"gbi_frame_start=", b"TIMING cause_to_isr=", b"RESTOREAV handler_installed=",
                    b"IRQW ", b"layout=gbi-u16-replicated", b"comment=startup-disc-stop-shadow", b"CLEANUP performed=", b"IRQ restore rc=",
                    b"MASK final intmr=", b"WRITES control_written=", b"format=attempted/completed", b"DEVICE STATE UNCERTAIN",
                    b"POWER CYCLE REQUIRED", b"NOT A PHYSICAL CANDIDATE", b"-blocks.bin", b"OGBPBLK1", b"OGBPEND1", b"NEVER delivered"):
            self.assertIn(rec, blob, rec)
        for rec in (b"INITIRQ4 start ", b"INITIRQB start ", b"INITIRQ start ", b"INIT start ", b"INTMR mask ", b"INTMR restore ",
                    b"PREPARE n=", b"MULTI install expected_gen=", b"TEARDOWN4 variant=", b"CYCLE n=", b"hsp_backend_oneshot_isr_multi",
                    b"anomaly_source_not_cleared", b"install_point=after_latched_cause", b"HANDLERPI intsr_before_ack=",
                    b"GX_Init", b"AUDIO_Init", b"ASND_Init", b"ARQ_Init", b"libmobile", b"net_init"):
            self.assertNotIn(rec, blob, rec)
        bi = read_build_info(os.path.join(ROOT, "build", "poc", "gbp-av-service-probe", "build-info.txt"))
        self.assertEqual(bi["build_id"], "avsvc-0001")

    def test_video_capture_probe_identity_and_records(self):
        # GBP-VIDEO-001: its own test id and gecko prefix; the 003A stage records (reused module), the 003B
        # delivery records (shared module), the repeated-service records, the compact per-cycle records, the
        # boundary and matrix records, the sequence sidecar name and magic; none of the other probes' test
        # ids or records, no AVSVC record or v2 sidecar magic; the mandatory power-cycle banner; build id
        # video-0001; no framebuffer/GX/audio-output/network string.
        dol = os.path.join(ROOT, "build", "poc", "gbp-video-capture-probe", "gbp-video-capture-probe.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertIn(b"GBP-VIDEO-001", blob)
        for tid in (b"GBP-AV-SERVICE-001", b"GBP-INIT-004", b"GBP-INIT-003B", b"GBP-INIT-003A", b"GBP-INIT-002", b"GBP-INIT-001"):
            self.assertNotIn(tid, blob, tid)
        self.assertIn(b"OPENGBP-VIDEO READY ", blob)
        self.assertIn(b"OPENGBP-VIDEO LOG ", blob)
        self.assertIn(b"OPENGBP-VIDEO SAVESEQ rc=", blob)
        for rec in (b"VIDEO start target=", b"VIDEO masks ack_or=", b"VIDEO blocks audio_idx=",
                    b"VIDEO policy handler=003b_ext_installed_once", b"VIDEO policy2 admission=before_unmask",
                    b"VIDEO end status=", b"INITIRQA start ", b"CAUSE t_event=", b"IRQ install rc=",
                    b"PREUNMASK%s ok=", b"PREUNMASKAV av=", b"UNMASK%s t_unmask=", b"WAIT%s fired=", b"HANDLER%s fired=",
                    b"ADMIT n=", b"PREPARE n=", b"SVC n=", b"AUDIOREAD", b"VIDEOREAD", b"PICLEAN ", b"REARM n=",
                    b"REARMPOST n=", b"NEXT n=", b"CYCU n=", b"CYCW n=", b"CYCH n=", b"CYCD n=", b"CYCR n=",
                    b"VBLK seq=", b"ABLK cyc=", b"BOUNDARIES ", b"BPOS", b"BINT", b"ADMISSION t0=", b"MATRIX service=",
                    b"reference_content=offline", b"COUNTERS unmasks=", b"TIMING first_cause_to_isr=",
                    b"RESTOREVIDEO handler_installed=", b"TEARDOWNVIDEO variant=", b"IRQW ", b"layout=gbi-u16-replicated",
                    b"CLEANUP performed=", b"IRQ restore rc=", b"MASK final intmr=", b"-seq.bin", b"OGBPSEQ1", b"OGBPEND1",
                    b"POWER CYCLE REQUIRED", b"NOT A PHYSICAL CANDIDATE", b"never delivered"):
            self.assertIn(rec, blob, rec)
        for rec in (b"OGBPBLK1", b"AVSVC start ", b"SVC start pending=", b"TEARDOWNAV variant=", b"SERVICE pass pending=",
                    b"INITIRQ4 start ", b"INITIRQB start ", b"INITIRQ start ", b"INIT start ", b"INTMR mask ",
                    b"MULTI install expected_gen=", b"TEARDOWN4 variant=", b"CYCLE n=", b"hsp_backend_oneshot_isr_multi",
                    b"GX_Init", b"AUDIO_Init", b"ASND_Init", b"ARQ_Init", b"libmobile", b"net_init"):
            self.assertNotIn(rec, blob, rec)
        bi = read_build_info(os.path.join(ROOT, "build", "poc", "gbp-video-capture-probe", "build-info.txt"))
        self.assertEqual(bi["build_id"], "video-0001")


if __name__ == "__main__":
    unittest.main()
