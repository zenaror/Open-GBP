#!/usr/bin/env python3
"""tools/v28syncpe.py -- GitHub Issue #128 section 7 / #129/#130: the SYNCPE/SYNCPH grammar's own
parser, so the SD log's phase-edge stream can be read back the same way poc/gbp-audio-v28's own
main.c writes it (its file header carries the grammar; this module is the ingestion side).

    SYNCPE p=<n> edge=<start|end> t=<tick> why=<reason>
    SYNCPH phase=<n> t_start=<tick> t_end=<tick> ended=<0|1> reason=<reason>

`why`/`reason` is one of: none, complete, cap, session, z, probe. `t`/`t_start`/`t_end` are hex
64-bit ticks (the ringlog's own %llx convention, no leading 0x). Standard library only.
"""
import re
import sys

WHY_VALUES = ("none", "complete", "cap", "session", "z", "probe")

# A real ringlog line carries a leading six-digit sequence number (tools/v28budget.py's own rec():
# `r"^\d{6} %s (.*)$"`) before the tag -- optional here so a bare tag (as a test fixture, or a
# tag already split off by the caller) still parses.
_SYNCPE = re.compile(r"^(?:\d+\s+)?SYNCPE\s+p=(\d+)\s+edge=(start|end)\s+t=([0-9a-fA-F]+)\s+why=(\w+)\s*$")
_SYNCPH = re.compile(r"^(?:\d+\s+)?SYNCPH\s+phase=(\d+)\s+t_start=([0-9a-fA-F]+)\s+t_end=([0-9a-fA-F]+)\s+ended=([01])\s+reason=(\w+)\s*$")


def parse_syncpe(line):
    """{'p': int, 'edge': 'start'|'end', 't': int, 'why': str}, or None if `line` is not a SYNCPE
    line -- INCLUDING one that otherwise matches the grammar but carries a `why` outside
    WHY_VALUES (a damaged or truncated physical-hardware log must not parse as if it were valid,
    CLAUDE.md §11's "malformed data" case: `main.c`'s own `syncpe_why()` is a closed switch that can
    never emit one, but the reader must not assume the writer -- or the bytes in between -- agree)."""
    m = _SYNCPE.match(line.strip())
    if not m or m.group(4) not in WHY_VALUES:
        return None
    return {"p": int(m.group(1)), "edge": m.group(2), "t": int(m.group(3), 16), "why": m.group(4)}


def parse_syncph(line):
    """{'phase': int, 't_start': int, 't_end': int, 'ended': bool, 'reason': str}, or None --
    including an out-of-vocabulary `reason` (see parse_syncpe()'s own comment)."""
    m = _SYNCPH.match(line.strip())
    if not m or m.group(5) not in WHY_VALUES:
        return None
    return {"phase": int(m.group(1)), "t_start": int(m.group(2), 16), "t_end": int(m.group(3), 16),
            "ended": m.group(4) == "1", "reason": m.group(5)}


def parse(text):
    """Every SYNCPE and SYNCPH line in `text`, in order, each tagged 'kind'."""
    out = []
    for line in text.splitlines():
        e = parse_syncpe(line)
        if e is not None:
            e["kind"] = "SYNCPE"
            out.append(e)
            continue
        h = parse_syncph(line)
        if h is not None:
            h["kind"] = "SYNCPH"
            out.append(h)
    return out


def main(argv):
    if len(argv) != 2:
        print("usage: v28syncpe.py <log-file>", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        recs = parse(f.read())
    for r in recs:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
