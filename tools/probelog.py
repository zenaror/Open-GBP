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
"""
from __future__ import annotations

import json
import re
import sys

REC_RE = re.compile(r"^(?:(\d{6}) )?([A-Z]+)(?: (.*))?$")
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
    """Fields of the HANDLER/HANDLERPI records that follow index `start`
    (the values the physical handler left in its record), as the nine
    numbers of a replay "I u" line; zeros when the handler never ran."""
    h = hp = None
    for r in records[start:]:
        if r["kind"] == "HANDLER" and h is None:
            h = r["fields"]
        elif r["kind"] == "HANDLERPI" and hp is None:
            hp = r["fields"]
        if h and hp:
            break
    h = h or {}
    hp = hp or {}
    return "%s %s %s %s %s %s %s %s %s" % (
        h.get("count", "0"), h.get("fired", "0"), h.get("t_entry", "0"),
        hp.get("intsr_before_ack", "00000000"), hp.get("intmr_at_entry", "00000000"),
        hp.get("intsr_after_ack", "00000000"), hp.get("intmr_after_mask", "00000000"),
        hp.get("reentry_intsr", "00000000"), hp.get("reentry_intmr", "00000000"))


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
