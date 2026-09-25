#!/usr/bin/env python3
"""
tools/vevents.py — GitHub Issue #120: how fast the video state model's EVENT STORE fills, what fills it, and what
session length a store of a given size permits. DESCRIPTIVE; a capacity fact, never a gate.

    tools/vevents.py <log> [<log> ...] [--cap <records>] [--json <out>]

WHAT FILLS THE STORE (src/gbp/gbp_vstate.c, read, not assumed). Every event is one 64-byte record appended by
gbp_vstate_event(); nothing is overwritten, and once the store is full each further event is DROPPED and counted
(`events_dropped`), and the probe stops the run as `event_store_cap`. The producers:
  * the EPISODE path (run_episodes / open_episode / close_episode, reached from close_frame for CLEAN frames only):
    while an episode is open, every CLEAN closed frame emits one `episode_stabilising` -- the candidate repeated
    (stable_count + 1) or changed (back to 1). The frame that opens an episode emits `episode_open` IN PLACE of a
    stabilising event; the episode then adds `episode_stable` when the candidate has repeated GBP_VSTATE_N_STABLE = 3
    times, and `episode_close` (stable, or capped at GBP_VSTATE_EPISODE_MAX_FRAMES = 60). An UNCLEAN frame while an
    episode is open (incomplete, a region anomaly, the frame that clears a resync) lengthens the episode
    (close_frame's `else if (s->episode_open)` branch, `ep->frames++`) and appends NO event unless it caps the
    episode. So a picture that keeps changing emits about ONE EVENT PER CLEAN FRAME, not one per episode; the
    episode path's ceiling is a run of 3-frame stable episodes: open, stabilising, stabilising + stable + close =
    5 events per 3 frames. It bounds the episode path only: the one-off events and one `predicate_disagreement` per
    disagreeing block come on top.
  * the frame path: `incomplete_interval` per incomplete frame, `resync` once per region anomaly run, `cap_reached`;
  * the block path: `predicate_disagreement`, one per disagreeing BLOCK (up to 40 a frame);
  * the probe's own: capture start, baseline, stop, teardown.
The semantic READ disagreements (READDISAGREE*) append NO event (HARDWARE_TESTS.md, GBP-VIDEO-002-R3).

WHAT IT READS from each log, in the ringlog form `NNNNNN TAG k=v ...`: EVENTS (n, dropped, store_full), CLOCKS
(tb_hz, capture_start), CLOCKSEC (capture_s), FRAMECAP (frames, incomplete, resync), STRUCTURED (episodes, stable,
unstable), PREDICATES (disagreements), and the printed EV lines -- the first 128 and the last 64 events, the rest
omitted from the log (EVGAP). The rates:
  mean       n / capture_s, and n / frames (events per closed frame)
  head/tail  over the printed EV lines' own instants and frame indices, with their types counted
  permits    cap / rate: the capture a store of `cap` records lasts at the measured mean, at one event per frame at
             59.727 Hz (GBP-HW-282's reading), and at the episode path's ceiling of 5/3 per frame; and the design
             comment's assumed 4 events/s, beside them, for what it claimed

Standard library only; reads the logs it is given, writes the JSON it is asked to.
"""
import json
import re
import sys

FRAME_HZ = 59.727             # the measured frame rate (HARDWARE_TESTS.md; RUN 41 / RUN 42)
EPISODE_CEILING = 5.0 / 3.0   # events per frame: a run of 3-frame stable episodes
DESIGN_ASSUMED = 4.0          # events/s, the comment `~4 events/s is the ceiling assumed` (poc/*/source/main.c)
CAP = 16384                   # PLAY_EVENT_RECORDS of play-0001 .. sync-0001

REC = re.compile(r"^\d{6} (\S+) (.*)$")
EV = re.compile(r"^\d{6} EV seq=(\d+) t=([0-9a-f]+) type=(\S+) f=(\d+) ep=([0-9a-f]+)")


class VeventsError(Exception):
    pass


def kv(rest):
    out = {}
    for tok in rest.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out.setdefault(k, v)
    return out


def parse(text):
    recs, evs = {}, []
    for line in text.splitlines():
        m = EV.match(line)
        if m:
            evs.append({"seq": int(m.group(1)), "t": int(m.group(2), 16), "type": m.group(3),
                        "f": int(m.group(4)), "ep": int(m.group(5), 16)})
            continue
        m = REC.match(line)
        if m and m.group(1) in ("EVENTS", "CLOCKS", "CLOCKSEC", "FRAMECAP", "STRUCTURED", "PREDICATES") \
                and m.group(1) not in recs:
            recs[m.group(1)] = kv(m.group(2))
    for tag in ("EVENTS", "CLOCKS", "CLOCKSEC", "FRAMECAP", "STRUCTURED"):
        if tag not in recs:
            raise VeventsError("no %s record" % tag)
    return recs, evs


def stretch(evs, t0, tb):
    if len(evs) < 2:
        return None
    types = {}
    for e in evs:
        types[e["type"]] = types.get(e["type"], 0) + 1
    dt = (evs[-1]["t"] - evs[0]["t"]) / float(tb)
    df = evs[-1]["f"] - evs[0]["f"]
    return {"seq": [evs[0]["seq"], evs[-1]["seq"]], "t_s": [(evs[0]["t"] - t0) / float(tb), (evs[-1]["t"] - t0) / float(tb)],
            "frames": [evs[0]["f"], evs[-1]["f"]], "per_s": (len(evs) - 1) / dt if dt > 0 else None,
            "per_frame": (len(evs) - 1) / float(df) if df > 0 else None, "types": dict(sorted(types.items()))}


def analyse(text, cap=CAP):
    recs, evs = parse(text)
    E, C, CS, F, ST = (recs[k] for k in ("EVENTS", "CLOCKS", "CLOCKSEC", "FRAMECAP", "STRUCTURED"))
    n, frames = int(E["n"]), int(F["frames"])
    tb, t0 = int(C["tb_hz"]), int(C["capture_start"], 16)
    cap_s = float(CS["capture_s"])
    head = [e for e in evs if e["seq"] <= 128]
    tail = [e for e in evs if e["seq"] > 128]
    mean_s = n / cap_s if cap_s > 0 else None
    out = {"n": n, "dropped": int(E["dropped"]), "store_full": int(E["store_full"]), "capture_s": cap_s,
           "frames": frames, "incomplete": int(F.get("incomplete", 0)), "resync": int(F.get("resync", 0)),
           "episodes": int(ST["episodes"]), "stable": int(ST["stable"]), "unstable": int(ST["unstable"]),
           "disagreements": int(recs["PREDICATES"]["disagreements"]) if "PREDICATES" in recs else None,
           "per_s": mean_s, "per_frame": n / float(frames) if frames else None,
           "head": stretch(head, t0, tb), "tail": stretch(tail, t0, tb), "cap": cap}
    if evs and tail and head and tail[0]["seq"] > head[-1]["seq"] + 1:
        a, b = head[-1], tail[0]
        dt = (b["t"] - a["t"]) / float(tb)
        out["omitted"] = {"events": b["seq"] - a["seq"], "s": dt, "frames": b["f"] - a["f"],
                          "per_s": (b["seq"] - a["seq"]) / dt if dt > 0 else None,
                          "per_frame": (b["seq"] - a["seq"]) / float(b["f"] - a["f"]) if b["f"] > a["f"] else None}
    out["permits_s"] = {"measured": cap / mean_s if mean_s else None,
                        "one_per_frame": cap / FRAME_HZ,
                        "episode_ceiling": cap / (EPISODE_CEILING * FRAME_HZ),
                        "design_assumed": cap / DESIGN_ASSUMED}
    # A LOWER BOUND on the frames inside an open episode. Each `episode_open` / `episode_stabilising` record is one
    # distinct clean frame inside an episode, so frames inside an episode >= those records in the store >= the store
    # minus UPPER bounds on every other kind: `episode_stable` <= stable, `episode_close` <= episodes, and the rest
    # <= capture start (1) + the baseline's own events (all in the head once `baseline_valid` is there) + one
    # `incomplete_interval` per incomplete frame and per 48-block interval before the first boundary + one `resync`
    # per region anomaly + one `episode_store_full` + one per predicate disagreement + stop and teardown (3).
    # Unclean frames inside an episode add frames and no record, so there is no upper bound here.
    ht = out["head"]["types"] if out["head"] else {}
    base = None
    if ht.get("baseline_valid"):
        base = sum(ht.get(k, 0) for k in ("baseline_candidate", "baseline_valid", "early_candidate"))
    need = ("anomaly_region", "pre_boundary")
    if base is None or any(k not in F for k in need) or "not_preserved" not in ST or out["disagreements"] is None:
        out["episode_frames_at_least"] = None
    else:
        other = (1 + base + out["incomplete"] + int(F["pre_boundary"]) // 48 + int(F["anomaly_region"])
                 + (1 if int(ST["not_preserved"]) else 0) + out["disagreements"] + 3)
        out["episode_frames_at_least"] = {"records": n - out["stable"] - out["episodes"] - other, "other_at_most": other}
    return out


def main(argv):
    rest = list(argv[1:])
    out_path, cap = None, CAP
    if "--json" in rest:
        j = rest.index("--json")
        out_path = rest[j + 1]
        del rest[j:j + 2]
    if "--cap" in rest:
        j = rest.index("--cap")
        cap = int(rest[j + 1])
        del rest[j:j + 2]
    res = {}
    for path in rest:
        with open(path, encoding="utf-8", errors="replace") as f:
            r = analyse(f.read(), cap)
        res[path] = r
        print("%s: %d events (dropped %d, full %d) over %.3f s and %d frames: %.2f/s, %.4f/frame; episodes %d "
              "(stable %d); %d records permit %.1f s at this rate, %.1f s at one per frame, %.1f s at the episode "
              "ceiling, %.0f s at the design's assumed %.0f/s"
              % (path, r["n"], r["dropped"], r["store_full"], r["capture_s"], r["frames"], r["per_s"] or 0,
                 r["per_frame"] or 0, r["episodes"], r["stable"], cap, r["permits_s"]["measured"] or 0,
                 r["permits_s"]["one_per_frame"], r["permits_s"]["episode_ceiling"], r["permits_s"]["design_assumed"],
                 DESIGN_ASSUMED))
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(res, f, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
