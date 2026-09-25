"""tests/host/test_v27report.py -- tools/v27report.py, the SD log of the latency round turned into the report
tools/v27accept.py reads (GitHub Issue #117). Synthetic logs only: the builder is proved on constructions before the
image exists, its refusals reached one by one, and its output fed to the frozen gate end to end.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v27accept  # noqa: E402
import v27report as r  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frozen  # noqa: E402

SEED = 0x9E3779B9


def hx(v):
    return "%x" % v


def lines(secs, kinds, answers, seed=SEED, deep=2048, shallow=512):
    """A synthetic GBP-AUDIO-012 log: `secs` seconds of Phase 1 alternating the two arms every 30 s."""
    gen = r.schedule_from_seed(seed)
    if kinds is None:
        kinds = gen["schedule"]
    out = ["# OPENGBP-LOG v1", "test_id=GBP-AUDIO-012", "build_id=sync-0001", "commit=abcdef0",
           "lines=999 dropped=0 truncated=0", "# --- records ---"]
    n = [0]

    def rec(tag, body):
        out.append("%06d %s %s" % (n[0], tag, body))
        n[0] += 1

    rec("IDENT", "test=GBP-AUDIO-012 app=gbp-audio-sync build=sync-0001 commit=abcdef0 libogc=x")
    rec("SYNCCFG", "deep=%d shallow=%d floor=384 mute=18 step_mute=4 p2_lo=384 p2_hi=3584 p2_step=128 p3_start=384 "
                   "p3_step=32 p3_dwell_s=6 p3_bisect=2" % (deep, shallow))
    rec("SYNCCFG2", "p3_min=128 cap_p1=300 cap_p2=240 cap_p3=180 cap_session=720 real=12 null=6 settling_s=2 awr_blocks=640 "
                    "cfg_faults=0")
    rec("SYNCCFG3", "p3_confirm_s=60 prompt_bound_s=45")
    rec("LIVE", "phase=done control_ok=1 gave_up=0 windows=2 press_before_prompt=0 presses_a=1")
    t0 = 0x1000000000
    rec("LIVET", "tb_hz=40500000 t0=%s t_accept=%s t_press=%s t_origin=%s t_end=%s"
        % (hx(t0), hx(t0 + 5 * 40500000), hx(t0 + 9 * 40500000), hx(t0 + 10 * 40500000), hx(t0 + 730 * 40500000)))
    rec("SYNCSEED", "seed=%08x initial=%s" % (seed, gen["initial"]))
    rec("SYNCSCHED", "n=18 kinds=%s" % ",".join(k[0] for k in kinds))
    rec("SYNCP2CFG", "starts=%s dirs=%s" % (",".join(str(s) for s in gen["p2_starts"]),
                                             ",".join(d[5] for d in gen["p2_dirs"])))
    origin = t0 + 10 * 40500000
    level = deep if gen["initial"] == "DEEP" else shallow
    tsw = origin + 3 * 40500000
    for i, k in enumerate(kinds):
        nxt = level if k == "NULL" else (shallow if level == deep else deep)
        discard = max(0, level - nxt)
        pause = (nxt - level + 127) // 128 if nxt > level else 0
        rec("SYNCSW", "seq=%d kind=%s from=%d to=%d t=%s discard=%d pause=%d" % (i, k, level, nxt, hx(tsw), discard, pause))
        if answers and answers[i]:
            rec("SYNCANS", "seq=%d answer=%s t=%s" % (i, answers[i], hx(tsw + 2 * 40500000)))
        rec("SYNCTX", "seq=%d done=1 mech=ROTATE mute=18 rot=%d res=%d late=%d unmasked=0 topped=0"
            % (i, 6 if nxt > level else 18, (i % 5) * 20 - 40, 1 if i % 6 == 0 else 0))
        level = nxt
        tsw += 15 * 40500000
    rec("SYNCPH", "phase=1 t_start=%s t_end=%s ended=complete" % (hx(origin + 3 * 40500000), hx(tsw)))
    rec("SYNCP2", "seq=0 kind=START from=%d to=1024 t=%s" % (level, hx(tsw)))
    rec("SYNCSET", "seq=0 start=1024 dir=D steps=4 target=512 t=%s" % hx(tsw + 40500000))
    rec("SYNCSET", "seq=1 start=2560 dir=S steps=15 target=640 t=%s" % hx(tsw + 2 * 40500000))
    rec("SYNCSET", "seq=2 start=640 dir=D steps=1 target=512 t=%s" % hx(tsw + 3 * 40500000))
    rec("SYNCPH", "phase=2 t_start=%s t_end=%s ended=complete" % (hx(tsw), hx(tsw + 4 * 40500000)))
    # §V27.14's descent: 384..160 hold (the DUP fires), 128 fails (dup 0, starved), the bisection to width 2 --
    # 144 fails, 152, 148, 146 hold -- then the 60 s hold at 144, which sees its underrun 47 s in
    t3 = tsw + 5 * 40500000
    depths = [(t, "STEP", 60, 0, 0) for t in (384, 352, 320, 288, 256, 224, 192, 160)] + [
        (128, "STEP", 0, 40, 0), (144, "BISECT", 0, 12, 0), (152, "BISECT", 50, 0, 0), (148, "BISECT", 45, 0, 0),
        (146, "BISECT", 30, 0, 0)]
    for j, (t, kind, dup, starved, und) in enumerate(depths):
        rec("SYNCDEPTH", "n=%d kind=%s target=%d fill16=%d underruns=%d overflow=0 dup=%d drop=0 lost=30 starved=%d "
                         "t_start=%s t_end=%s partial=0" % (j, kind, t, (t - 20) * 16, und, dup, starved,
                                                            hx(t3 + 6 * j * 40500000), hx(t3 + 6 * (j + 1) * 40500000)))
        rec("SYNCDEPTH2", "n=%d starved=%d ready_in=4 ready_out=%d fill_in=%d fill_out=%d fill_n=3"
            % (j, starved, 3 if starved else 4, t, t - 20))
    j = len(depths)
    rec("SYNCDEPTH", "n=%d kind=CONFIRM target=144 fill16=1600 underruns=1 overflow=0 dup=0 drop=0 lost=30 starved=900 "
                     "t_start=%s t_end=%s partial=0" % (j, hx(t3 + 6 * j * 40500000), hx(t3 + (6 * j + 47) * 40500000)))
    rec("SYNCDEPTH2", "n=%d starved=900 ready_in=4 ready_out=0 fill_in=144 fill_out=10 fill_n=3" % j)
    rec("SYNCPH", "phase=3 t_start=%s t_end=%s ended=complete" % (hx(tsw + 4 * 40500000), hx(tsw + 70 * 40500000)))
    # per-second arrays: 3 s of phase 0, then Phase 1 alternating arms every 30 s, mute at each switch second
    cols = {"counts": [], "fill16": [], "target": [], "phase": [], "mute": [], "settling": [], "underruns": [],
            "overflow": []}
    cur = deep if gen["initial"] == "DEEP" else shallow
    for s in range(secs):
        if s < 3:
            ph, mute, settling = 0, 0, 0
        else:
            ph = 1
            k = (s - 3) % 15
            if k == 0 and s > 3:
                cur = shallow if cur == deep else deep
            mute = 1 if k == 0 else 0
            settling = 1 if k in (1, 2) else 0
        fill = cur - 30 if not mute else 0
        for name, v in (("counts", 4090), ("fill16", fill * 16), ("target", cur), ("phase", ph), ("mute", mute),
                        ("settling", settling), ("underruns", 0), ("overflow", 0)):
            cols[name].append(v)
    tags = {"counts": "SYNCSECC", "fill16": "SYNCSECF", "target": "SYNCSECT", "phase": "SYNCSECP", "mute": "SYNCSECM",
            "settling": "SYNCSECS", "underruns": "SYNCSECU", "overflow": "SYNCSECO"}
    for name, tag in tags.items():
        for k in range(0, secs, 16):
            rec(tag, "from=%d %s=%s" % (k, name, ",".join(str(v) for v in cols[name][k:k + 16])))
    rec("SYNCC", "underruns=4 overflow=0 silences=0 mute_handed=320 dup=1000 drop=5 produced=20000 handed=19990")
    rec("SYNCC2", "discarded=300 starved_steps=10 lost=600 blocks_in=2900 ring_discarded=7000 counter_faults=0 sec_overflow=0")
    rec("SYNCREF", "switch_unanswered=1 switch_mute=2 switch_exhausted=0 switch_phase=0 answer=3 step_mute=0 step_end=1 "
                   "step_phase=0 step_value=0 confirm=0")
    rec("SYNCAWR", "blocks=640 cap=640 t_arm=%s t_first=%s t_last=%s faults=0 ignored=0 seen=640 state=3"
        % (hx(origin), hx(origin + 100), hx(origin + 6300000)))
    rec("SYNCAWRC", "copy_min=1200 copy_max=1500 copy_sum=800000 copy_n=640")
    rec("SYNCTXA", "begun=40 completed=40 faults=0 rotate=21 lates=0 unmasked=0 res=-40..40 converted=2 shorts=0 "
                   "short_max=0 trim_max=130 trim_sum=900")
    rec("SYNCP3", "pending=0 drained=0 refused_depth_done=0 depths=14 overflow=0")
    rec("SYNCEND", "reason=session t=%s secs=%d phase=4 plans=40 cs=60 acted=55 z=0 cs_dead=1 cs_busy=2 preempts=0 "
                   "stop=session_end"
        % (hx(origin + 720 * 40500000), secs))
    out.append("# --- end --- dropped=0")
    return "\n".join(out) + "\n"


def predicted_answers(kinds, initial):
    level = 2048 if initial == "DEEP" else 512
    out = []
    for k in kinds:
        if k == "NULL":
            out.append("SAME")
        else:
            nxt = 512 if level == 2048 else 2048
            out.append("LESS" if nxt < level else "MORE")
            level = nxt
    return out


class TheGenerator(unittest.TestCase):
    def test_shape_and_determinism(self):
        for seed in (SEED, 1, 0xFFFFFFFF, 12345):
            g = r.schedule_from_seed(seed)
            self.assertEqual((g["schedule"].count("REAL"), g["schedule"].count("NULL"), g["schedule"][0]),
                             (12, 6, "REAL"), seed)
            self.assertEqual(g, r.schedule_from_seed(seed))
            self.assertEqual(len(g["p2_starts"]), 3)
            for s in g["p2_starts"]:
                self.assertTrue(384 <= s <= 3584 and (s - 384) % 128 == 0, s)
            self.assertTrue(all(d in ("LEFT_DEEPER", "LEFT_SHALLOWER") for d in g["p2_dirs"]))
        self.assertNotEqual(r.schedule_from_seed(1)["schedule"], r.schedule_from_seed(2)["schedule"])

    def test_the_runtimes_own_vector(self):
        """tests/unit/test_gbp_async.c pins this vector as the C module's output for seed 0x9E3779B9."""
        g = r.schedule_from_seed(0x9E3779B9)
        self.assertEqual((g["initial"], "".join(k[0] for k in g["schedule"]), g["p2_starts"], g["p2_dirs"]),
                         ("SHALLOW", "RNRNRRNRRRNRRRRRNN", [2560, 1280, 1024], ["LEFT_DEEPER"] * 3))
        self.assertEqual(r.schedule_from_seed(0), r.schedule_from_seed(1))
        c = open(os.path.join(ROOT, "tests", "unit", "test_gbp_async.c"), encoding="utf-8").read()
        self.assertIn("RNRNRRNRRRNRRRRRNN", c)

    def test_xorshift_is_the_projects(self):
        import v24accept
        for x in (1, 0x9E3779B9, 0xDEADBEEF):
            self.assertEqual(r._xorshift32(x), v24accept._xorshift32(x))


class TheBuilder(unittest.TestCase):
    def test_a_complete_log_builds_and_the_frozen_gate_confirms(self):
        g = r.schedule_from_seed(SEED)
        text = lines(200, None, predicted_answers(g["schedule"], g["initial"]))
        rep = r.build(text)
        self.assertEqual((rep["test_id"], rep["build_id"], rep["commit"]), ("GBP-AUDIO-012", "sync-0001", "abcdef0"))
        self.assertEqual(rep["assign"]["seed"], SEED)
        self.assertEqual(rep["assign"]["schedule"], g["schedule"])
        self.assertEqual(len(rep["switches"]), 18)
        self.assertTrue(all(s["answer"] for s in rep["switches"]))
        self.assertEqual(len(rep["seconds"]), 200)
        self.assertEqual(rep["seconds"][3]["mute"], True)
        self.assertEqual(rep["seconds"][4]["settling"], True)
        self.assertEqual(rep["seconds"][10]["fill"], (rep["seconds"][10]["target"] - 30))
        self.assertEqual(rep["cfg"]["caps"], {"p1": 300, "p2": 240, "p3": 180, "session": 720})
        self.assertEqual(rep["awr"]["blocks"], 640)
        self.assertEqual(rep["end"], {"reason": "session", "t": rep["press"]["t_origin"] + 720 * 40500000,
                                      "secs": 200, "cs_busy": 2, "preempts": 0})
        a = v27accept.evaluate(rep)
        self.assertEqual((a["phase1"]["verdict"], a["phase1"]["D"], a["M"]["M1"], a["M"]["M2"]),
                         ("CONFIRMS", 12, "PASS", "PASS"))
        self.assertEqual((a["phase2"]["verdict"], a["phase3"]["verdict"], a["phase3"]["interval"]),
                         ("MEASURED", "MEASURED", [144, 146]))
        self.assertEqual((a["phase3"]["confirm"]["verdict"], a["phase3"]["confirm"]["length_s"]), ("OBSERVED", 47.0))
        # §V27.15: every switch's transition, as the executor carried it out
        self.assertTrue(all(s["tx"]["masked"] for s in rep["switches"]))      # late ones included: contiguous
        self.assertTrue(any(s["tx"]["late"] for s in rep["switches"]))
        self.assertEqual(rep["executor"]["residue_min"], -40)
        self.assertEqual(rep["cfg"]["mute_chunks"], 18)
        self.assertEqual(rep["cfg"]["p3_confirm_s"], 60)

    def test_the_transition_plans_in_the_log(self):
        g = r.schedule_from_seed(SEED)
        rep = r.build(lines(60, None, None))
        for s in rep["switches"]:
            if s["kind"] == "NULL":
                self.assertEqual((s["discard"], s["pause"], s["from"]), (0, 0, s["to"]))
            elif s["to"] < s["from"]:
                self.assertEqual((s["discard"], s["pause"]), (1536, 0))
            else:
                self.assertEqual((s["discard"], s["pause"]), (0, 12))
        self.assertTrue(all(s["answer"] is None for s in rep["switches"]))
        self.assertEqual(v27accept.evaluate(rep)["phase1"]["verdict"], "INCONCLUSIVE")

    def test_refusals(self):
        g = r.schedule_from_seed(SEED)
        good = lines(40, None, None)
        with self.assertRaises(ValueError):                         # a schedule the seed does not generate
            r.build(good.replace("kinds=%s" % ",".join(k[0] for k in g["schedule"]),
                                 "kinds=%s" % ",".join(k[0] for k in reversed(g["schedule"]))))
        with self.assertRaises(ValueError):                         # a non-contiguous per-second array
            r.build(good.replace("SYNCSECC from=16", "SYNCSECC from=17"))
        with self.assertRaises(ValueError):                         # an answer for a switch never made
            r.build(good.replace("# --- end", "000999 SYNCANS seq=40 answer=MORE t=1\n# --- end"))
        with self.assertRaises(ValueError):                         # no SYNCCFG
            r.build("\n".join(l for l in good.splitlines() if " SYNCCFG " not in l))
        with self.assertRaises(ValueError):                         # half a configuration
            r.build("\n".join(l for l in good.splitlines() if " SYNCCFG2 " not in l))
        with self.assertRaises(ValueError):                         # the refusals' line missing
            r.build("\n".join(l for l in good.splitlines() if " SYNCREF " not in l))
        with self.assertRaises(ValueError):                         # a truncated record somewhere: refused
            r.build(good.replace("lines=999 dropped=0 truncated=0", "lines=999 dropped=0 truncated=1"))
        with self.assertRaises(ValueError):                         # a dropped record somewhere: refused
            r.build(good.replace("lines=999 dropped=0 truncated=0", "lines=999 dropped=1 truncated=0"))
        with self.assertRaises(ValueError):                         # no header at all
            r.build(good.replace("lines=999 dropped=0 truncated=0\n", ""))
        with self.assertRaises(ValueError):                         # too few seconds for SYNCEND
            r.build(good.replace("secs=40", "secs=41"))

    def test_a_log_whose_session_never_started_is_refused_with_that_cause(self):
        """The A press never came (no_origin) or came after the prompt's bound (prompt_expired): the image writes
        SYNCEND secs=0 and no session record; the builder refuses naming the cause, never 'not a log'."""
        for reason in ("no_origin", "prompt_expired"):
            out = ["# OPENGBP-LOG v1", "test_id=GBP-AUDIO-012", "build_id=sync-0001", "commit=abcdef0",
                   "lines=9 dropped=0 truncated=0", "# --- records ---",
                   "000000 IDENT test=GBP-AUDIO-012 app=gbp-audio-sync build=sync-0001 commit=abcdef0 libogc=x",
                   "000001 SYNCCFG deep=2048 shallow=512 floor=384 mute=18 step_mute=4 p2_lo=384 p2_hi=3584 p2_step=128 "
                   "p3_start=384 p3_step=32 p3_dwell_s=6 p3_bisect=2",
                   "000002 SYNCCFG2 p3_min=128 cap_p1=300 cap_p2=240 cap_p3=180 cap_session=720 real=12 null=6 "
                   "settling_s=2 awr_blocks=640 cfg_faults=0",
                   "000002 SYNCCFG3 p3_confirm_s=60 prompt_bound_s=45",
                   "000003 LIVE phase=prompt control_ok=1 gave_up=0 windows=0 press_before_prompt=0 presses_a=0",
                   "000004 LIVET tb_hz=40500000 t0=1000000000 t_accept=100c1d7000 t_press=0 t_origin=0 t_end=0",
                   "000005 SYNCEND reason=%s t=1010000000 secs=0 phase=0 plans=0 cs=0 acted=0 z=0 cs_dead=0 stop=session_end"
                   % reason, "# --- end --- dropped=0"]
            with self.assertRaisesRegex(ValueError, "session never started .*reason=%s" % reason):
                r.build("\n".join(out) + "\n")

    def test_the_vocabulary_the_image_writes(self):
        """ended=null is JSON null; the end reason is one the image emits; the drain rows ride beside the depths;
        a dwell with no whole second behind fill16 reports no fill; prompt_bound_s reaches cfg."""
        kinds = r.schedule_from_seed(SEED)["schedule"]
        good = lines(730, kinds, predicted_answers(kinds, r.schedule_from_seed(SEED)["initial"]))
        rep = r.build(good)
        self.assertEqual(rep["end"]["reason"], "session")
        self.assertEqual(rep["cfg"]["prompt_bound_s"], 45)
        d128 = [d for d in rep["descent"] if d["target"] == 128][0]
        self.assertEqual((d128["starved"], d128["ready_in"], d128["ready_out"], d128["fill_in"], d128["fill_out"],
                          d128["fill_n"]), (40, 4, 3, 128, 108, 3))
        self.assertIsNotNone(d128["fill_mean"])
        cut = good.replace("\n# --- end", "\n999990 SYNCDEPTH n=20 kind=BISECT target=140 fill16=0 underruns=1 overflow=0 "
                                            "dup=0 drop=0 lost=0 starved=3 t_start=3 t_end=4 partial=1\n999991 SYNCDEPTH2 "
                                            "n=20 starved=3 ready_in=3 ready_out=2 fill_in=140 fill_out=120 fill_n=0\n# --- end")
        d140 = [d for d in r.build(cut)["descent_unfinished"] if d["target"] == 140][0]   # cut: observes nothing
        self.assertIsNone(d140["fill_mean"])
        nul = good.replace("SYNCPH phase=3 t_start=", "SYNCPH phase=3 ended=null t_start=").replace(" ended=complete", "", 0)
        import re
        nul = re.sub(r"(SYNCPH phase=3 ended=null t_start=\S+ t_end=\S+) ended=complete", r"\1", nul)
        self.assertIsNone(r.build(nul)["phases"]["p3"]["ended"])

    def test_a_cut_dwell_observes_nothing(self):
        """A dwell cut before its end observes neither holding nor failing (§V27.14's predicate is over the whole
        dwell): both go to `descent_unfinished`. Review round 3: the old rule kept a cut row that 'failed' --
        dup 0 over 20 ms is only no DUP yet -- and a cut 20 ms into 146 made (144, 146] a confident (146, 148]."""
        kinds = r.schedule_from_seed(SEED)["schedule"]
        good = lines(730, kinds, predicted_answers(kinds, r.schedule_from_seed(SEED)["initial"]))
        cut_hold = ("SYNCDEPTH n=21 kind=BISECT target=150 fill16=2048 underruns=0 overflow=0 dup=30 drop=0 lost=0 "
                    "starved=0 t_start=1 t_end=2 partial=1")
        cut_fail = ("SYNCDEPTH n=22 kind=BISECT target=140 fill16=1900 underruns=0 overflow=0 dup=0 drop=0 lost=0 "
                    "starved=5 t_start=3 t_end=4 partial=1")
        text = good.replace("\n# --- end", "\n999990 %s\n999991 %s\n# --- end" % (cut_hold, cut_fail))
        rep = r.build(text)
        # 150 was cut after its DUP fired: it HAS held (dup never decreases) and stays; 140 was cut with dup 0:
        # no DUP yet, it observes nothing
        self.assertEqual([d["target"] for d in rep["descent_unfinished"]], [140])
        self.assertNotIn(140, [d["target"] for d in rep["descent"]])
        self.assertIn(150, [d["target"] for d in rep["descent"]])
        self.assertTrue(all(d["partial"] == 0 or d["dup"] > 0 or d["kind"] == "CONFIRM" for d in rep["descent"]))
        self.assertEqual(r.build(good)["descent_unfinished"], [])
        # the round-3 case end to end: 146 cut 20 ms in (dup 0, starved 52) leaves the bracket where the whole
        # dwells put it
        cut146 = good.replace("\n# --- end", "\n999992 SYNCDEPTH n=23 kind=BISECT target=146 fill16=2000 underruns=0 "
                                                "overflow=0 dup=0 drop=0 lost=0 starved=52 t_start=5 t_end=6 partial=1\n# --- end")
        a = v27accept.evaluate(r.build(cut146))["phase3"]
        self.assertEqual((a["verdict"], a["interval"]), ("MEASURED", [144, 146]))

    def test_a_pending_depth_is_refused_and_the_end_keeps_its_counts(self):
        kinds = r.schedule_from_seed(SEED)["schedule"]
        good = lines(730, kinds, predicted_answers(kinds, r.schedule_from_seed(SEED)["initial"]))
        rep = r.build(good)
        self.assertEqual((rep["end"]["cs_busy"], rep["end"]["preempts"]), (2, 0))
        self.assertEqual(rep["p3"]["depths"], 14)
        with self.assertRaisesRegex(ValueError, "never reported"):
            r.build(good.replace("SYNCP3 pending=0", "SYNCP3 pending=1"))

    def test_an_unblinded_log_builds_with_no_assignment(self):
        good = lines(40, None, None)
        rep = r.build("\n".join(l for l in good.splitlines() if " SYNCSEED " not in l))
        self.assertIsNone(rep["assign"])
        self.assertEqual(v27accept.evaluate(rep)["phase1"]["verdict"], "VOID")

    def test_the_cli(self):
        g = r.schedule_from_seed(SEED)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.log")
            with open(p, "w") as f:
                f.write(lines(50, None, predicted_answers(g["schedule"], g["initial"])))
            out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v27report.py"), p, "--json",
                                  os.path.join(d, "r.json")], capture_output=True, text=True, timeout=60)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("GBP-AUDIO-012 / sync-0001 / abcdef0: 50 seconds, 18 switches (18 answered), 3 settings, "
                          "14 depths, assignment present, awr 640 blocks", out.stdout)
            with open(os.path.join(d, "r.json")) as f:
                self.assertEqual(json.load(f)["end"]["secs"], 50)



class TheBuilderIsNotEditedAfterTheImage(unittest.TestCase):
    """Frozen with the image, before any run: the builder is byte-identical to its commit."""
    KEY = "Issue #117 -- v27report, the latency round's SD log"

    def test_the_tool_is_byte_identical_to_its_freeze(self):
        then = frozen.source(self.KEY, "tools/v27report.py")
        then = then.decode("utf-8") if isinstance(then, bytes) else then
        with open(os.path.join(ROOT, "tools", "v27report.py"), encoding="utf-8") as f:
            self.assertEqual(then, f.read())

if __name__ == "__main__":
    unittest.main()
