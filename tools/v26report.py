#!/usr/bin/env python3
"""
tools/v26report.py — game-0002's log -> the report tools/v26accept.py reads (GitHub Issue #113, Phase 6's
acceptance, second attempt, HARDWARE_TESTS §V26).

    tools/v26report.py <GBP-AUDIO-011 log> [--sidecar <l2 file>] [--json <out>]

`tools/v26accept.py` was frozen (f874cc6) before the image existed. This file makes the report it reads and is
frozen WITH the image, before any run. It IS tools/v25report.py's report -- `v25report.build`, imported and run
unchanged -- plus the fields §V26 adds:

  t_press                       LIVET t_press, the first A as gbp_alive records it (s2)
  video.before_frames           one [store index, t_first_block, t_last_block, t_next_first_block] per LIVEVBEF
                                line, in the order written (s6)
  video.before_listed           how many LIVEVBEF lines there are
  video.before_capped           LIVEVBEFN capped=1: more before-AI frames than the image lists
  video.episodes_close_max      the largest close_frame among the log's EPISODE records -- the start-up bound
                                the clause reads from the log itself (s3); null when there is none

It REFUSES (ValueError) a log whose LIVEVBEFN disagrees with its own LIVEVBEF lines or with LIVEVINC's
`before` (s6), and a log with no LIVEVBEFN at all: that is not a game-0002 log.

Standard library only. Reads a log (and checks a file exists); writes a JSON; decides nothing.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v22report  # noqa: E402
import v25report  # noqa: E402


def build(text, sidecar_path=None):
    report = v25report.build(text, sidecar_path)
    recs = v22report.records(text)
    kv = v22report._kv
    if "LIVEVBEFN" not in recs:
        raise ValueError("no LIVEVBEFN record: not a GBP-AUDIO-011 (game-0002) log")
    n = kv(recs["LIVEVBEFN"][0])
    lines = [kv(b) for b in recs.get("LIVEVBEF", [])]
    if [int(x["i"]) for x in lines] != list(range(len(lines))):
        raise ValueError("LIVEVBEF lines are not contiguous from 0")
    if int(n["listed"]) != len(lines):
        raise ValueError("LIVEVBEFN listed=%s but %d LIVEVBEF lines" % (n["listed"], len(lines)))
    if int(n["before"]) != report["video"]["before"]:
        raise ValueError("LIVEVBEFN before=%s but LIVEVINC before=%d" % (n["before"], report["video"]["before"]))
    capped, before = int(n["capped"]) == 1, int(n["before"])
    if (capped and not before > len(lines)) or (not capped and before != len(lines)):
        raise ValueError("LIVEVBEFN capped=%s disagrees with before=%d listed=%d" % (n["capped"], before, len(lines)))
    closes = [int(kv(m)["close_frame"]) for m in re.findall(r"^\d{6} EPISODE (.*)$", text, re.M)]
    t = kv(recs["LIVET"][0])
    report["t_press"] = int(t["t_press"], 16)
    report["video"].update(
        before_frames=[[int(x["idx"]), int(x["t_first"], 16), int(x["t_last"], 16), int(x["t_next"], 16)]
                       for x in lines],
        before_listed=len(lines), before_capped=capped,
        episodes_close_max=max(closes) if closes else None)
    return report


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    side = argv[argv.index("--sidecar") + 1] if "--sidecar" in argv else None
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        rep = build(f.read(), side)
    text = json.dumps(rep, indent=2, sort_keys=True)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
