#!/usr/bin/env python3
"""OGBPIDX1 analyzer — the offline authority for the indexed stimulus.

It takes what a future runtime would preserve — for each captured frame, 40
blocks of 54 ORIGINAL consumed word16 from the canonical witness (STRIP-L, local
row 0) — and produces a structured verdict. It decodes; it never decides
anything online, and it never sees a ROM.

WHAT IT MAY AND MAY NOT CLAIM (HARDWARE_TESTS §V5.33.7)
  MAY    frame-ID sequence integrity, block composition integrity, block
         position integrity, between the first and last intact observed IDs
  MAY NOT pixel fidelity outside the strip; anything about frames before the
         first or after the last observed intact ID; any mechanism for a gap

The vocabulary is factual and "dropped frame" is not in it.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import istim  # noqa: E402

# the frozen classification names, re-exported so a caller need not reach into istim
OBSERVED_ID_CONTIGUOUS  = istim.OBSERVED_ID_CONTIGUOUS
OBSERVED_ID_GAP         = istim.OBSERVED_ID_GAP
OBSERVED_DUPLICATE_ID   = istim.OBSERVED_DUPLICATE_ID
OBSERVED_REORDER        = istim.OBSERVED_REORDER
UNRESOLVED_HALF_RANGE   = istim.UNRESOLVED_HALF_RANGE
MIXED_BLOCK_IDS         = istim.MIXED_BLOCK_IDS
MISPLACED_BLOCK_INDEX   = istim.MISPLACED_BLOCK_INDEX
INVALID_CANONICAL_STRIP = istim.INVALID_CANONICAL_STRIP
FRAME_OK                = istim.FRAME_OK

STIMULUS_INVALID = "STIMULUS_INVALID_FOR_DECISIVE_CLAIM"
OBSERVED_CONTIGUOUS = "OBSERVED_CONTIGUOUS"
OBSERVED_DISCONTINUITY = "OBSERVED_DISCONTINUITY"
INCONCLUSIVE_TOO_FEW = "INCONCLUSIVE_TOO_FEW_INTACT_FRAMES"


def analyze_frame(block_witnesses, prev_frame_id=None):
    """One captured frame.

    `block_witnesses`: 40 sequences of 54 consumed word16, in DELIVERY order.
    Returns a dict; `classification` is present only when `prev_frame_id` is
    given and this frame decoded intact.
    """
    if len(block_witnesses) != istim.BLOCKS:
        return {"outcome": INVALID_CANONICAL_STRIP, "reason": "block_count",
                "frame_id": None, "status": None,
                "mixed_block_ids": False, "misplaced_block_indices": [],
                "invalid_canonical_strips": list(range(len(block_witnesses))),
                "flag15": [], "classification": None}

    fr = istim.classify_frame(block_witnesses)
    blocks = fr["blocks"]

    invalid = [b for b, d in enumerate(blocks) if d["outcome"] != istim.CANONICAL_OK]
    misplaced = [b for b, d in enumerate(blocks)
                 if d["outcome"] == istim.CANONICAL_OK and not d["index_ok"]]
    ids = sorted({d["frame_id"] for d in blocks if d["outcome"] == istim.CANONICAL_OK})
    flag15 = [(b, i) for b, d in enumerate(blocks) for i in d.get("flag15_indices", [])]

    out = {
        "outcome": fr["outcome"],
        "frame_id": fr["frame_id"],
        "status": fr["status"],
        "fault": fr["fault"],
        "vmargin": fr["vmargin"],
        "id_valid": fr["outcome"] == FRAME_OK,
        "mixed_block_ids": fr["outcome"] == MIXED_BLOCK_IDS,
        "block_ids": ids,
        "misplaced_block_indices": misplaced,
        "invalid_canonical_strips": invalid,
        "invalid_reasons": {b: blocks[b].get("reason") for b in invalid},
        "flag15": flag15,
        "classification": None,
    }
    if out["id_valid"] and prev_frame_id is not None:
        out["classification"] = istim.classify_delta(prev_frame_id, out["frame_id"])
    return out


def analyze_run(frames):
    """`frames` is the ordered list of per-frame witness sets for a capture."""
    per_frame, prev = [], None
    for w in frames:
        a = analyze_frame(w, prev)
        per_frame.append(a)
        if a["id_valid"]:
            prev = a["frame_id"]

    classified = [istim.classify_frame(w) for w in frames]
    pop = istim.decisive_population(classified)
    intact = [a for a in per_frame if a["id_valid"]]

    report = {
        "frames": per_frame,
        "observed_total": len(per_frame),
        "observed_intact": len(intact),
        "first_observed": intact[0]["frame_id"] if intact else None,
        "last_observed": intact[-1]["frame_id"] if intact else None,
        "first_decisive": pop["decisive_frames"][0] if pop["decisive_frames"] else None,
        "last_decisive": pop["decisive_frames"][-1] if pop["decisive_frames"] else None,
        "edge_frames_excluded": pop["excluded"],
        "decisive_transitions": pop["decisive_transitions"],
        "fault_seen": pop["fault_seen"],
        "counts": {},
        "verdict": pop["verdict"],
    }
    for _, _, c in pop["decisive_transitions"]:
        report["counts"][c] = report["counts"].get(c, 0) + 1
    for a in per_frame:
        if not a["id_valid"]:
            report["counts"][a["outcome"]] = report["counts"].get(a["outcome"], 0) + 1
    if report["fault_seen"]:
        report["verdict"] = STIMULUS_INVALID
    return report


def format_report(r) -> str:
    L = []
    L.append("OGBPIDX1 analyzer report")
    L.append("  observed frames        %d (intact %d)" % (r["observed_total"], r["observed_intact"]))
    if r["first_observed"] is not None:
        L.append("  first/last observed    0x%06x .. 0x%06x" % (r["first_observed"], r["last_observed"]))
    if r["first_decisive"] is not None:
        L.append("  first/last decisive    0x%06x .. 0x%06x" % (r["first_decisive"], r["last_decisive"]))
    L.append("  decisive transitions   %d" % len(r["decisive_transitions"]))
    for k in sorted(r["counts"]):
        L.append("      %-24s %d" % (k, r["counts"][k]))
    L.append("  excluded from the decisive set:")
    for kind, why in r["edge_frames_excluded"]:
        L.append("      %-28s %s" % (kind, why))
    L.append("  stimulus fault seen    %s" % r["fault_seen"])
    L.append("  VERDICT                %s" % r["verdict"])
    L.append("")
    L.append("  This says nothing about frames before the first or after the last")
    L.append("  observed intact ID, and nothing about pixel fidelity outside the strip.")
    return "\n".join(L)


if __name__ == "__main__":
    print(__doc__)
