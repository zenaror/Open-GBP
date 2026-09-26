#!/usr/bin/env python3
"""
tools/v123frame.py — GitHub Issue #123: what one 256-byte slice of an AUDIO block holds, read as eight stride-8
streams, and which update grid each archived capture's level follows. DESCRIPTIVE, host-side, on archived bytes; it
decides nothing and names nothing it has not counted.

    tools/v123frame.py [--json <out>]

THE READING. A 4 096-byte block is sixteen 256-byte slices; a slice is 32 GROUPS of 8 bytes. STREAM j of a slice is
byte j of every group -- bytes j, j + 8, ..., j + 248 -- read most significant bit first: 256 bits. Nothing here claims
that a stream bit is a moment in time: that is U-GBP-041's question (slices uniform in time), still a HYPOTHESIS. The
streams are a READING of the bytes, chosen because it is the one that makes the structure simple; every property below
is counted, not assumed.

WHAT IT COUNTS, per capture:
  pairs       stream 1 == stream 3 and stream 5 == stream 7 in every slice?  Call them A (1 = 3) and B (5 = 7)
  superset    every even stream a bit-superset of its odd partner (0 of 1, 2 of 3, 4 of 5, 6 of 7)?
  one pulse   each odd stream exactly ONE contiguous run of ones per slice?
  even runs   per even stream, the slices where it holds MORE than one run of ones (its extras away from the pulse)
  rise        the first one-bit of stream 1: its position, per slice
  identity    the slice's one-bit count == 4 wA + 4 wB + extras, with wA, wB the ones in A and B and the extras the
              even-stream bits their odd partner lacks
  A vs B      how often A == B; how often |wA - wB| <= 1 (what a value split into two halves allows), and the largest
  grid        (wA, wB) equal inside each slice pair (2p, 2p + 1)? where A or B changes between adjacent slices of a
              block, on an EVEN boundary (between pairs) or an ODD one (inside a pair)
  rest        (wA, wB) in the captures' control windows (awin sidecars only: they mark them)
  flat        the blocks whose sixteen slice counts spread by at most tools/v18block.py's FLAT_SPREAD (3 bits), and
              how many of them hold (wA, wB) constant across the sixteen slices
  mid / side  per slice, (wA + wB) / 2 and (wA - wB) / 2: the side's share of the two's AC energy -- what a decode
              that sums A and B (today's) cannot keep, IF A and B are two output sides (a HYPOTHESIS)
THE DETECTOR the counts give, descriptive: the share of slice pairs whose two (wA, wB) differ. Zero means the level
followed a 512-cycle grid in that capture; well above zero, a 256-cycle grid -- under U-GBP-041, 32 768 against 65 536
updates a second. A capture whose level never changes cannot show either, and the tool says so.

INPUTS. RUN 33 and RUN 34 (stimulus ROM tones, versioned). RUN 43's raw window (a commercial game's output,
captures/local only, never versioned): the tool prints AGGREGATES of it and nothing else, and skips it when absent.

Standard library only; reads the captures, writes the JSON it is asked to.
"""
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import awinparse  # noqa: E402
import awrparse  # noqa: E402
import v18block  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FXD = os.path.join(ROOT, "captures", "fixtures")
CAPTURES = {
    "RUN33": ("awin", os.path.join(FXD, "hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz")),
    "RUN34": ("awin", os.path.join(FXD, "hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz")),
    "RUN43": ("awr", os.path.join(ROOT, "captures", "local", "GBP-AUDIO-012_sync-0001-run43-awr.bin")),
}
BLOCK, SLICE, GROUP = 4096, 256, 8
PC = [bin(i).count("1") for i in range(256)]


def streams(sl):
    """The eight stride-8 streams of a 256-byte slice, each as a 256-bit integer (MSB of the first byte first)."""
    return [int.from_bytes(sl[j::GROUP], "big") for j in range(GROUP)]


def runs_of_ones(x, nbits=256):
    """(number of maximal runs of one-bits, index of the first one-bit counted from the most significant end)."""
    s = format(x, "0%db" % nbits)
    n = 0
    prev = "0"
    for c in s:
        if c == "1" and prev == "0":
            n += 1
        prev = c
    first = s.find("1")
    return n, first


def slice_record(sl):
    st = streams(sl)
    a, b = st[1], st[5]
    count = sum(PC[x] for x in sl)
    wa, wb = bin(a).count("1"), bin(b).count("1")
    extras = sum(bin(st[e] & ~st[e + 1]).count("1") for e in (0, 2, 4, 6))
    runs = [runs_of_ones(st[o]) for o in (1, 3, 5, 7)]
    return {"pairs": st[1] == st[3] and st[5] == st[7],
            "superset": all(st[e] & st[e + 1] == st[e + 1] for e in (0, 2, 4, 6)),
            "one_pulse": all(r[0] == 1 for r in runs),
            "rise": runs[0][1], "wa": wa, "wb": wb, "a_eq_b": a == b,
            "identity": count == 4 * wa + 4 * wb + extras, "extras": extras, "count": count,
            "even_runs": [runs_of_ones(st[e])[0] for e in (0, 2, 4, 6)]}


def load(kind, path):
    """[(window kind or None, [blocks])] for the capture."""
    if kind == "awin":
        with gzip.open(path) as f:
            data = f.read()
        header, anchors, off = awinparse.parse(data)
        wins = awinparse.windows(data, header, anchors, off)
        return [(awinparse.KIND.get(a["kind"], str(a["kind"])), w) for a, w in zip(anchors, wins)]
    with open(path, "rb") as f:
        data = f.read()
    header, blocks = awrparse.parse(data)[:2]
    return [(None, blocks)]


def analyse_capture(kind, path):
    out = {"slices": 0, "pairs": 0, "superset": 0, "one_pulse": 0, "identity": 0, "a_eq_b": 0,
           "rise": {}, "pair_equal": 0, "pair_n": 0, "change_even": 0, "change_odd": 0,
           "rest": {}, "extras_max": 0, "wa_min": 256, "wa_max": 0,
           "even_multi_run": {"0": 0, "2": 0, "4": 0, "6": 0}, "flat": 0, "flat_ab_constant": 0,
           "ab_within_1": 0, "ab_max": 0,
           "_m": [0.0, 0.0], "_s": [0.0, 0.0]}
    for wkind, blocks in load(kind, path):
        for blk in blocks:
            recs = [slice_record(blk[i * SLICE:(i + 1) * SLICE]) for i in range(BLOCK // SLICE)]
            counts = [r["count"] for r in recs]
            if max(counts) - min(counts) <= v18block.FLAT_SPREAD:
                out["flat"] += 1
                out["flat_ab_constant"] += int(len(set((r["wa"], r["wb"]) for r in recs)) == 1)
            for r in recs:
                out["slices"] += 1
                for k in ("pairs", "superset", "one_pulse", "identity", "a_eq_b"):
                    out[k] += int(r[k])
                out["rise"][str(r["rise"])] = out["rise"].get(str(r["rise"]), 0) + 1
                out["extras_max"] = max(out["extras_max"], r["extras"])
                for e, n in zip(("0", "2", "4", "6"), r["even_runs"]):
                    out["even_multi_run"][e] += int(n > 1)
                out["wa_min"] = min(out["wa_min"], r["wa"])
                out["wa_max"] = max(out["wa_max"], r["wa"])
                out["ab_within_1"] += int(abs(r["wa"] - r["wb"]) <= 1)
                out["ab_max"] = max(out["ab_max"], abs(r["wa"] - r["wb"]))
                mid, side = (r["wa"] + r["wb"]) / 2.0, (r["wa"] - r["wb"]) / 2.0
                out["_m"][0] += mid
                out["_m"][1] += mid * mid
                out["_s"][0] += side
                out["_s"][1] += side * side
                if wkind == "control":
                    key = "%d,%d" % (r["wa"], r["wb"])
                    out["rest"][key] = out["rest"].get(key, 0) + 1
            for p in range(0, len(recs), 2):
                out["pair_n"] += 1
                out["pair_equal"] += int((recs[p]["wa"], recs[p]["wb"]) == (recs[p + 1]["wa"], recs[p + 1]["wb"]))
            for k in range(1, len(recs)):
                if (recs[k]["wa"], recs[k]["wb"]) != (recs[k - 1]["wa"], recs[k - 1]["wb"]):
                    out["change_odd" if k % 2 else "change_even"] += 1
    n = float(out["slices"])
    ac_m = out["_m"][1] - out["_m"][0] ** 2 / n
    ac_s = out["_s"][1] - out["_s"][0] ** 2 / n
    out["side_share"] = ac_s / (ac_m + ac_s) if ac_m + ac_s > 0 else None
    del out["_m"], out["_s"]
    out["mid_pair_share"] = 1.0 - out["pair_equal"] / float(out["pair_n"]) if out["pair_n"] else None
    changes = out["change_even"] + out["change_odd"]
    out["grid"] = ("no level change" if changes == 0 else
                   "512-cycle (pair) grid" if out["change_odd"] == 0 else "256-cycle (slice) grid")
    return out


def analyse():
    res = {}
    for name, (kind, path) in CAPTURES.items():
        res[name] = analyse_capture(kind, path) if os.path.isfile(path) else None
    return res


def main(argv):
    res = analyse()
    for name, r in res.items():
        if r is None:
            print("%s: absent in this checkout (captures/local is ignored)" % name)
            continue
        n = r["slices"]
        print("%s: %d slices; A=1=3 & B=5=7 %d; supersets %d; one pulse per odd stream %d; identity %d; A==B %d; "
              "rise at %s; wA %d..%d; extras <= %d" % (name, n, r["pairs"], r["superset"], r["one_pulse"],
                                                        r["identity"], r["a_eq_b"], r["rise"], r["wa_min"],
                                                        r["wa_max"], r["extras_max"]))
        print("   pairs with equal (wA,wB): %d of %d (mid-pair share %.4f); changes on even / odd boundaries %d / %d: %s"
              % (r["pair_equal"], r["pair_n"], r["mid_pair_share"], r["change_even"], r["change_odd"], r["grid"]))
        print("   side share of the (mid, side) AC energy: %s" % ("%.4f" % r["side_share"] if r["side_share"] is not None
                                                                  else "none (no AC energy)"))
        print("   even streams with more than one run of ones, slices: %s; flat blocks %d, (wA, wB) constant in %d"
              % (r["even_multi_run"], r["flat"], r["flat_ab_constant"]))
        print("   |wA - wB| <= 1 in %d slices; the largest %d" % (r["ab_within_1"], r["ab_max"]))
        if r["rest"]:
            print("   control windows (wA,wB): %s" % r["rest"])
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(res, f, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
