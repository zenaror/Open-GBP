#!/usr/bin/env python3
"""
probelog — parse Open-GBP device logs (OPENGBP-LOG v1, as written by
src/platform/sdlog.c or captured from USB Gecko "OPENGBP-PROBE LOG" lines)
and turn them into machine-readable data, replay fixtures and a
comparison against the Phase 2 expectations.

Usage:
    tools/probelog.py parse   <log>              JSON summary + records
    tools/probelog.py fixture <log> <out.gbpreplay> [--note "…"]   replay script for src/gbp/gbp_replay.c
    tools/probelog.py check   <log>              interpret TEST/RAW records (exit 1 on anomalies)

Record grammar (one per line, after the "NNNNNN " sequence prefix):
    KEY key=value key=value ...      values are hex/decimal/strings; data=<64 hex>
The parser keeps every raw block as bytes; interpretation lives in check().

GBP-INIT-003A records (gbp_initirqa_probe.c) map to the replay script as:
    IRQW  tag=A1|A2|STOP … rc= t_after=   ->  W <addr> <rc>  then  T <t_after>
    CTLW  … t_after=                       ->  W <addr> <rc>  then  T <t_after>
    SNAP  tag=EVENT ticks= … poll_intsr=   ->  T <ticks>  then  P p <poll_intsr>  (the poll that saw INTSR bit 13)
    WINDOW tag=A2 … t_end=                 ->  T <t_end>
Deadline loops replay with one time-base read per sample (the SNAP's own
`ticks`), so poll counters differ from the device run and are not part of
the comparison; nothing else is invented.

GBP-INIT-003B records (gbp_initirqb_probe.c) extend the GBP-INIT-002 rules:
    HANDLERPI intsr_at_entry= … intsr_after_w1c=   ->  the same "I u" fields as 002's
                                                       intsr_before_ack / intsr_after_ack
    HANDLERPI2 t_second= intsr_second= …           ->  five extra "I u" numbers
                                                       (intsr_before_w1c t_second intsr_second
                                                       intmr_second reentry_t), only when the
                                                       record exists (002 logs are unchanged)
    MAINPICLEANUP site=POSTACK performed=1 value=  ->  P a <value>  (the main-loop W1C, logged
                                                       before the write and before the
                                                       "PI tag=MAINCLEANUP" re-read)
    IRQ mask tag=MAIN|RETRY rc=ok                  ->  I m  (as 002; the WAIT time-base reads
                                                       precede the MAIN mask)
GBP-INIT-004 records (gbp_initirq4_probe.c) add, per cycle:
    PREPARE n= gen=                                ->  I p <gen>   (optional in the replay)
    REARM n= t_rearm=                              ->  T <t_rearm> (read before the IRQW tag=REARM-n write)
    SNAP tag=NEXTCAUSE-n … poll_intsr=             ->  T <ticks>, P p <poll_intsr> (the SNAP rule: the poll that saw bit 13)
    NEXTCAUSE n= found=0 … t_end=                  ->  T <t_end> (the poll loop's last time-base read, bound reached)
    the per-cycle UNMASK/HANDLER*/IRQW/SNAP records follow the rules above (the handler
    record search stops at the next UNMASK, so each "I u" carries its own cycle's record)
GBP-AV-SERVICE-001 records (gbp_avsvc_probe.c / gbp_avblock.c) add:
    AUDIOREAD / VIDEOREAD … attempted=1 addr= len= rc= t_start= t_end=
                                                   ->  T <t_start>, B <addr> <len> <rc> [<crc32>], T <t_end>
                                                       (the crc32 comes from the run's BLOCK kind= record when the
                                                       read completed; the bytes themselves live in the run's
                                                       "-blocks.bin" sidecar, never in the script)
    SVC / SVCEND / POSTDRAIN / POSTACKAV / PICLEAN / SERVICE / COUNTERS / BLOCK / BLOCKW / AVSVC
                                                   ->  no replay operation (the snapshots they summarize are
                                                       replayed by their own SNAP / PI / RAW records)
    REARM t_rearm= and NEXTCAUSE found=0 t_end=    ->  as the GBP-INIT-004 rules (no n= field)
"""
from __future__ import annotations

import json
import re
import sys

REC_RE = re.compile(r"^(?:(\d{6}) )?([A-Z][A-Z0-9]*)(?: (.*))?$")   # kinds may carry a digit (HANDLERPI2, A1, P0CHK)
KV_RE = re.compile(r"(\w+)=(\S+)")


def parse_lines(lines):
    """Yields dicts: {seq, kind, fields:{...}} for record lines; header
    key=value lines go to a dict returned separately."""
    header = {}
    records = []
    for raw in lines:
        s = raw.rstrip("\r\n")
        if s.startswith("OPENGBP-PROBE LOG "):
            s = s[len("OPENGBP-PROBE LOG "):]
        if not s or s.startswith("#"):
            continue
        m = REC_RE.match(s)
        if m and m.group(2) and (m.group(1) is not None or m.group(2).isupper()):
            seq, kind, rest = m.groups()
            if seq is None and "=" in kind:
                pass
            else:
                fields = dict(KV_RE.findall(rest or ""))
                toks = (rest or "").split()
                tag = toks[0] if toks and "=" not in toks[0] else None
                if "data" in fields and fields["data"] != "-":
                    try:
                        fields["data_bytes"] = bytes.fromhex(fields["data"])
                    except ValueError:
                        fields["data_bytes"] = None
                records.append({"seq": int(seq) if seq else None, "kind": kind, "tag": tag, "fields": fields})
                continue
        if "=" in s and " " not in s.split("=", 1)[0]:
            k, v = s.split("=", 1)
            header[k] = v
    return header, records


def parse_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse_lines(f.readlines())


def to_json(header, records):
    out = {"header": header, "records": []}
    for r in records:
        f = dict(r["fields"])
        if "data_bytes" in f:
            f["data_bytes"] = f["data_bytes"].hex() if f["data_bytes"] else None
        out["records"].append({"seq": r["seq"], "kind": r["kind"], "tag": r.get("tag"), "fields": f})
    return out


def _handler_record(records, start):
    """Fields of the HANDLER/HANDLERPI(/HANDLERPI2) records that follow
    index `start` (the values the physical handler left in its record), as
    the numbers of a replay "I u" line; zeros when the handler never ran.
    GBP-INIT-002 names (intsr_before_ack / intsr_after_ack) and GBP-INIT-003B
    names (intsr_at_entry / intsr_after_w1c) denote the same record fields.
    The five extended numbers are appended only when a HANDLERPI2 record
    exists (003B), so 002 logs produce the same nine-number line as before.
    The search stops at the next UNMASK record."""
    h = hp = hp2 = None
    for r in records[start + 1:]:
        if r["kind"] == "UNMASK":
            break
        if r["kind"] == "HANDLER" and h is None:
            h = r["fields"]
        elif r["kind"] == "HANDLERPI" and hp is None:
            hp = r["fields"]
        elif r["kind"] == "HANDLERPI2" and hp2 is None:
            hp2 = r["fields"]
    h = h or {}
    hp = hp or {}
    line = "%s %s %s %s %s %s %s %s %s" % (
        h.get("count", "0"), h.get("fired", "0"), h.get("t_entry", "0"),
        hp.get("intsr_before_ack", hp.get("intsr_at_entry", "00000000")), hp.get("intmr_at_entry", "00000000"),
        hp.get("intsr_after_ack", hp.get("intsr_after_w1c", "00000000")), hp.get("intmr_after_mask", "00000000"),
        hp.get("reentry_intsr", "00000000"), hp.get("reentry_intmr", "00000000"))
    if hp2 is not None:
        line += " %s %s %s %s %s" % (
            hp.get("intsr_before_w1c", "00000000"), hp2.get("t_second", "0"), hp2.get("intsr_second", "00000000"),
            hp2.get("intmr_second", "00000000"), hp2.get("reentry_t", "0"))
    return line


def _write_ticks_after(records, start):
    """Time-base value the probe read right after its experimental CONTROL
    write: the next SNAP record with since_write != 0 gives ticks - since_write."""
    for r in records[start:]:
        if r["kind"] == "SNAP" and r["fields"].get("since_write", "0") != "0":
            return int(r["fields"]["ticks"]) - int(r["fields"]["since_write"])
    return None


def _wait_lines(f, t_unmask):
    """Time-base values read at the end of the wait: the loop-exit read
    (only when the wait timed out) and t_wait_end."""
    t_end = t_unmask + int(f["wait_ticks"])
    out = []
    if f.get("timed_out") == "1":
        out.append("T %d" % t_end)                                   # loop: tnow = now() -> timeout
    out.append("T %d" % t_end)                                       # t_wait_end = now()
    return out


def _raw_crc_at(records, kind, t_start):
    """CRC-32 of the block a whole-block read produced, found by joining on the physical t_start of
    the transfer: `VBLK ... t_start=` for VIDEO, `ABLK ... t_start=` for AUDIO (GBP-VIDEO-001).
    Returns "" when no summary record carries a CRC for that transfer — which is the honest answer
    for an AUDIO drain whose payload was not preserved (only the first 8 and the last valid one are).
    A CRC is NEVER invented: a zero field means "not measured", not "the CRC is zero"."""
    want = "VBLK" if kind == "video" else "ABLK"
    for r in records:
        if r["kind"] == want and r["fields"].get("t_start") == str(t_start):
            c = r["fields"].get("crc32", "")
            if c and c != "00000000":
                return c
            return ""
    return ""


def _block_crc(records, kind):
    """crc32 of the completed block `kind` ("audio" / "video") from the run's BLOCK record, or None."""
    for r in records:
        if r["kind"] == "BLOCK" and r["fields"].get("kind") == kind and r["fields"].get("valid") == "1" and "crc32" in r["fields"]:
            return r["fields"]["crc32"]
    return None


def _cyc_fields(rec):
    """The slash-separated groups of a CYCU / CYCD / CYCR record, as {key: [parts]}."""
    out = {}
    for k, v in rec["fields"].items():
        out[k] = v.split("/") if "/" in v else [v]
    return out


def _is_verify(records, n):
    """True when cycle `n` is one of the verify cycles (its CYCU record says verify=1)."""
    for r in records:
        if r["kind"] == "CYCU" and r["fields"].get("n") == n:
            return r["fields"].get("verify") == "1"
    return False


def _vblk_crc(records, seq):
    """CRC-32 of the VIDEO block of sequence index `seq`, from its VBLK record (logged after
    the cycles); "" when the block did not complete."""
    for r in records:
        if r["kind"] == "VBLK" and r["fields"].get("seq") == seq and r["fields"].get("completed") == "1":
            return r["fields"].get("crc32", "")
    return ""


def _irq_addr(video_addr):
    """The IRQ register block address (base + 0xD00000) behind a VIDEO block address (base + 0x100000)."""
    return "%08x" % ((int(video_addr, 16) - (1 << 20)) + (0xD << 20))


def _cyc_record(records, start, n):
    """The "I u" argument list of lean cycle `n`, from its CYCH record (already in the
    order a replay line expects: count fired t_entry intsr_at_entry intmr_at_entry
    intsr_after_ack intmr_after_mask reentry_intsr reentry_intmr + the five extended fields)."""
    for r in records[start:]:
        if r["kind"] == "CYCH" and r["fields"].get("n") == n:
            return " ".join(r["fields"]["rec"].split(","))
    return None


def fixture(records, note=None):
    """Replay script: reproduces the transport calls the probe made, in
    order, so gbp_replay + the probe logic on the host reach the same
    result. Time-base values (T) and interrupt-path operations (I) are
    emitted only from records that carry them (GBP-INIT-002 logs and
    later); nothing is invented — a handler that never ran replays as a
    record of zeros, not as an interrupt. `note` (a string or a list of
    strings) is written as comment lines under the header, e.g. to mark
    a fixture generated from a synthetic (host mock) log."""
    lines = ["# generated by tools/probelog.py from a device log"]
    if note:
        for n in ([note] if isinstance(note, str) else note):
            lines.append("# " + n)
    t_unmask = None
    irq_addr = None                  # the IRQ register block address, taken from each CYCD record
    wait_done = False
    cleanup_emitted = set()          # indices of CLEANUP records whose "P a" was already placed
    for idx, r in enumerate(records):
        k, f, tag = r["kind"], r["fields"], r.get("tag")
        if k == "SNAP" and "ticks" in f:
            lines.append("T %s" % f["ticks"])                        # snapshot(): s->ticks = now()
            if "poll_intsr" in f:                                    # GBP-INIT-003A EVENT: the poll that triggered it
                lines.append("P p %s" % f["poll_intsr"])
        elif k == "IRQW" and "addr" in f:                            # GBP-INIT-003A: IRQ-register write, then t_after = now()
            lines.append("W %s %s" % (f["addr"], f["rc"]))
            if "t_after" in f:
                lines.append("T %s" % f["t_after"])
        elif k == "WINDOW" and f.get("tag") == "A2" and "t_end" in f:
            lines.append("T %s" % f["t_end"])                        # t_window_end = now()
        elif k == "IRQ" and tag == "install" and f.get("rc") == "ok":
            lines.append("I i %s" % f.get("old_handler", "null"))
        elif k == "IRQ" and tag == "mask" and f.get("rc") == "ok":
            # The probe reads the time base (loop exit, t_wait_end) BEFORE it
            # re-masks, but logs the mask record before the WAIT record:
            # emit the WAIT time-base values first.
            nxt = records[idx + 1] if idx + 1 < len(records) else None
            if nxt and nxt["kind"] == "WAIT" and t_unmask is not None:
                lines.extend(_wait_lines(nxt["fields"], t_unmask))
                wait_done = True
            lines.append("I m")
        elif k == "IRQ" and tag == "restore" and f.get("rc") == "ok":
            lines.append("I r")
        elif k == "UNMASK":
            t_unmask = int(f["t_unmask"])
            lines.append("T %d" % t_unmask)                          # t_unmask = now()
            lines.append("I u " + _handler_record(records, idx))     # __UnmaskIrq; handler record
            lines.append("T %s" % f["t_post"])                       # t_post = now()
        elif k == "WAIT" and t_unmask is not None:
            if not wait_done:
                lines.extend(_wait_lines(f, t_unmask))
            wait_done = False
        if k == "ARINFO" and "value" in f:
            if tag == "write":                                  # gbp_probe: write, then a separate read record
                lines.append("A w %s" % f["value"])
            elif tag == "exp":                                  # gbp_init_probe: write + readback in one record
                lines.append("A w %s" % f["value"])
                lines.append("A r %s" % f["value"])
            elif tag == "restore":
                lines.append("A w %s" % f["value"])
                if "readback" in f:                             # gbp_init_probe restore includes the readback
                    lines.append("A r %s" % f["readback"])
            elif f.get("rc", "ok") == "ok":
                lines.append("A r %s" % f["value"])
        elif k == "RAW":
            data = f.get("data", "-") if f.get("rc") == "ok" else ""
            lines.append(("R %s %s %s" % (f["addr"], f["rc"], data)).rstrip())
        elif k == "TESTW":
            lines.append("W %s %s" % (f.get("addr") or _hs_addr(records, r), f["rc"]))
        elif k == "TESTR":
            data = f.get("data", "-") if f.get("rc") == "ok" else ""
            lines.append(("R %s %s %s" % (f.get("addr") or _hs_addr(records, r), f["rc"], data)).rstrip())
        elif k == "CTLW":
            lines.append("W %s %s" % (f["addr"], f["rc"]))
            if "t_after" in f:                                       # GBP-INIT-003A: t_after = now() after every CONTROL write
                lines.append("T %s" % f["t_after"])
            elif f.get("tag") == "EXP":
                wt = _write_ticks_after(records, idx)
                if wt is not None:
                    lines.append("T %d" % wt)                        # write_ticks = now()
        elif k == "PI" and "intsr" in f:
            lines.append("P r %s %s" % (f["intsr"], f["intmr"]))
            if f.get("tag") == "CLEANUPCHK":
                # The single main-loop W1C happens right after this read and
                # before the "PI tag=CLEANUP" re-read; the CLEANUP record that
                # describes it is logged after both reads.
                for j in range(idx + 1, len(records)):
                    if records[j]["kind"] == "CLEANUP":
                        if records[j]["fields"].get("performed") == "1":
                            lines.append("P a %s" % records[j]["fields"]["value"])
                            cleanup_emitted.add(j)
                        break
        elif k == "INTMR" and tag in ("mask", "restore") and f.get("rc") == "ok":
            lines.append("P w %s" % (f.get("readback") or f.get("wanted") or f.get("value")))
        elif k == "MAINPICLEANUP" and f.get("performed") == "1" and "value" in f:   # GBP-INIT-003B main-loop W1C (POSTACK)
            lines.append("P a %s" % f["value"])
        elif k == "PREPARE" and "gen" in f:                                # GBP-INIT-004: generation published while masked
            lines.append("I p %s" % f["gen"])
        elif k == "REARM" and "t_rearm" in f:                              # GBP-INIT-004: time base read before the re-arm write
            lines.append("T %s" % f["t_rearm"])
        elif k == "NEXTCAUSE" and f.get("found") == "0" and "t_end" in f:  # GBP-INIT-004: the poll loop met its bound (last now())
            lines.append("T %s" % f["t_end"])
        elif k == "ADMIT" and "t_adm" in f and "prep_intsr" in f:   # GBP-VIDEO-001 verify cycle: the admission read, then PREPARE's PI read
            lines.append("T %s" % f["t_adm"])                         # t_adm = now()
            lines.append("P r %s %s" % (f["prep_intsr"], f["prep_intmr"]))   # the record reset itself consumes no line
        elif k == "CYCU" and f.get("verify") == "0":                  # GBP-VIDEO-001 lean cycle: admission, PREPARE, the unmask
            # (a verify cycle logs the same operations through its detailed AVSVC records, so its
            #  compact CYC* records are skipped here: they would emit every operation twice)
            g = _cyc_fields(r)
            if f.get("t_adm", "0") != "0":
                lines.append("T %s" % f["t_adm"])                     # t_adm = now() (absent in cycle 0)
                lines.append("P r %s %s" % (g["prep"][0], g["prep"][1]))
            lines.append("P r %s %s" % (g["pre"][0], g["pre"][1]))    # the pre-unmask PI read
            lines.append("T %s" % f["t_unmask"])
            rec = _cyc_record(records, idx, f["n"])
            if rec:
                lines.append("I u " + rec)
            lines.append("T %s" % f["t_post"])
            lines.append("P r %s %s" % (g["post"][0], g["post"][1]))  # the post-unmask PI read; the record polls consume no line
        elif k == "CYCW" and not _is_verify(records, f.get("n")):                                             # the bounded wait and the main re-mask
            g = _cyc_fields(r)
            if f.get("timed_out") == "1":
                lines.append("T %s" % f["t_wait_end"])                # the loop-exit now() that met the bound
            lines.append("T %s" % f["t_wait_end"])                    # t_wait_end = now()
            lines.append("I m")
            lines.append("P r %s %s" % (g["remask"][0], g["remask"][1]))
            if f.get("retry") == "1":
                lines.append("I m")
                lines.append("P r %s %s" % (g["remask"][0], g["remask"][1]))
        elif k == "CYCD" and not _is_verify(records, f.get("n")):                                             # the pending read (its "RAW READ-n" line precedes this record), the drains, the ACK
            g = _cyc_fields(r)
            lines.append("T %s" % f["t_read"])                        # t_read = now(), after the block read
            a, v, ack = g["a"], g["v"], g["ack"]
            if a[1] == "1":                                           # AUDIO attempted: t_start, one whole-block read, t_end
                lines.append("T %s" % a[5])
                # the AUDIO CRC is emitted ONLY when this drain's payload was preserved (the first 8
                # and the last valid one); audio_crc32 == 0 means "not measured" and must stay blank
                acrc = a[8] if (a[2] == "1" and a[8] != "00000000") else ""
                lines.append(("B %s %08x %s %s" % (a[9], 0x1000, a[3], acrc)).rstrip())
                lines.append("T %s" % a[6])
            if v[1] == "1":                                           # VIDEO attempted
                lines.append("T %s" % v[5])
                lines.append(("B %s %08x %s %s" % (v[8], 0x0F00, v[3], _vblk_crc(records, v[4]))).rstrip())
                lines.append("T %s" % v[6])
            irq_addr = _irq_addr(v[8])
            if ack[0] == "1":                                         # the ACK write, then t_after
                lines.append("W %s %s" % (irq_addr, "ok" if ack[1] == "1" else "backend"))
                lines.append("T %s" % ack[3])
        elif k == "CYCR" and not _is_verify(records, f.get("n")):                                             # PI clean, the re-arm, WAIT_NEXT
            g = _cyc_fields(r)
            pi, rearm, nxt = g["pi"], g["rearm"], g["next"]
            lines.append("P r %s %s" % (pi[0], pi[1]))                # the PICLEAN read
            if f.get("w1c") == "1":
                lines.append("P a 00002000")                          # the single main W1C, then the re-read
                lines.append("P r %s %s" % (f["after"], pi[1]))
            if rearm[0] == "1" and irq_addr:
                lines.append("T %s" % rearm[2])                       # t_rearm = now()
                lines.append("W %s %s" % (irq_addr, "ok" if rearm[1] == "1" else "backend"))
                lines.append("T %s" % rearm[3])
            if nxt[1] != "-":                                         # WAIT_NEXT: one poll answered by the recorded values
                lines.append("T %s" % nxt[2])
                if nxt[0] == "1":
                    lines.append("P p %s" % nxt[3])
        elif k == "NEXT" and "polls" in f:                             # GBP-VIDEO-001 verify cycle: WAIT_NEXT (nothing when REARMPOST already saw the cause)
            if f["polls"] != "0":
                lines.append("T %s" % f["t_next"])                     # the poll that ended the wait
                if f.get("observed") == "1":
                    lines.append("P p %s" % f["intsr"])
        elif k in ("AUDIOREAD", "VIDEOREAD") and f.get("attempted") == "1":  # one whole-block read, timed around the call
            kind = "audio" if k == "AUDIOREAD" else "video"
            crc = None
            if f.get("rc") == "ok":
                # GBP-AV-SERVICE-001 logs a BLOCK record per block; GBP-VIDEO-001 logs VBLK / ABLK
                # summaries instead, joined to this transfer by its physical t_start
                crc = _block_crc(records, kind) or _raw_crc_at(records, kind, f.get("t_start"))
            lines.append("T %s" % f["t_start"])
            lines.append(("B %s %08x %s %s" % (f["addr"], int(f["len"], 16), f["rc"], crc or "")).rstrip())
            lines.append("T %s" % f["t_end"])
        elif k == "CLEANUP" and f.get("performed") == "1" and idx not in cleanup_emitted:   # one INTSR W1C (no CLEANUPCHK record before it)
            lines.append("P a %s" % f["value"])
    return "\n".join(lines) + "\n"


def _hs_addr(records, rec):
    """Handshake records carry idx but not addr; derive base from the
    preceding MODE begin record."""
    base = None
    for r in records:
        if r is rec:
            break
        if r["kind"] == "MODE" and r["fields"].get("base"):
            base = int(r["fields"]["base"], 16)
    idx = int(rec["fields"].get("idx", "0"), 16)
    return "%08x" % ((base or 0) + (idx << 20))


def check(header, records):
    """Interpretation pass. Returns (findings:list[str], anomalies:int)."""
    findings = []
    anomalies = 0
    modes = {}
    for r in records:
        f = r["fields"]
        if r["kind"] == "TESTR" and f.get("rc") == "ok" and f.get("data_bytes"):
            d = f["data_bytes"]
            exp = int(f["expect"], 16)
            uniq = sorted(set(d))
            m = f.get("mode", "?")
            modes.setdefault(m, {"tests": 0, "all": 0, "b1f": 0, "layouts": set()})
            modes[m]["tests"] += 1
            if all(b == exp for b in d):
                modes[m]["all"] += 1
                modes[m]["layouts"].add("uniform")
            elif d[31] == exp:
                modes[m]["b1f"] += 1
                modes[m]["layouts"].add("byte1F-only:" + d.hex())
            else:
                modes[m]["layouts"].add("nomatch:" + d.hex())
            if len(uniq) > 2:
                findings.append("seq %s: TESTR mode=%s pattern=%s has %d distinct byte values" % (r["seq"], m, f.get("pattern"), len(uniq)))
        if r["kind"] == "RAW" and f.get("rc") != "ok":
            anomalies += 1
            findings.append("seq %s: RAW idx=%s rc=%s" % (r["seq"], f.get("idx"), f.get("rc")))
        if r["kind"] == "PROBE" and "restored=0" in " ".join("%s=%s" % kv for kv in f.items()):
            anomalies += 1
            findings.append("AR_INFO NOT restored")
    for m, s in sorted(modes.items()):
        findings.append("mode %s: %d handshakes, %d uniform inverse, %d byte1F-only; layouts=%s"
                        % (m, s["tests"], s["all"], s["b1f"], sorted(s["layouts"])))
    return findings, anomalies


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, path = argv[0], argv[1]
    header, records = parse_file(path)
    if cmd == "parse":
        print(json.dumps(to_json(header, records), indent=1))
        return 0
    if cmd == "fixture":
        if len(argv) < 3:
            print("fixture needs an output path", file=sys.stderr)
            return 2
        notes = [argv[i + 1] for i, a in enumerate(argv) if a == "--note" and i + 1 < len(argv)]
        with open(argv[2], "w", encoding="utf-8") as f:
            f.write(fixture(records, note=notes or None))
        print("wrote %s (%d records)" % (argv[2], len(records)))
        return 0
    if cmd == "check":
        findings, anomalies = check(header, records)
        for l in findings:
            print(l)
        print("anomalies=%d" % anomalies)
        return 1 if anomalies else 0
    print("unknown command", cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
