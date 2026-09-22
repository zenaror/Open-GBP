"""
tests/host/test_input_keylog.py — Issue #27 (GBP-KEY-009): the per-change KEYPAD
word record in stream-0015, and GBP-KEY-008's repair (the ENVINPUT split).

Pinned: the ONE format of the "KEY" line lives in gbp_input.h and fits the
248-character ringlog payload at the WORST case of every conversion (derived,
not eyeballed); it is emitted from the pump slot right after the write it
describes, never from the ISR or the service path, through the transport's
clock (no gettime); a refresh never produces an event; the bound keeps
KEYLOG_TAIL_RESERVE lines free for the post-run records (counted here) so
`dropped` cannot rise, and the surplus is counted, never silent; the KEYLOG
summary exists; the descriptor and the policy are byte-identical to the
candidate that ran (0ff8355); BUILD_ID is stream-0015, not executed, not
staged; nothing frozen moved. Nothing here runs a program.
"""
import os
import re
import subprocess
import unittest

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")
POC_MAKE = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "Makefile")
INPUT_H = os.path.join(ROOT, "src", "gbp", "gbp_input.h")
INPUT_C = os.path.join(ROOT, "src", "gbp", "gbp_input.c")
UNIT = os.path.join(ROOT, "tests", "unit", "test_gbp_input.c")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
BASE = "2498709"                # origin/main before Issue #27
CANDIDATE_RAN = "0ff8355"       # stream-0014, RUN 14 / RUN 15: the descriptor and the policy must be its bytes
ALLOWED = {"src/gbp/gbp_input.c", "src/gbp/gbp_input.h", "poc/gbp-video-stream-probe/source/main.c",
           "poc/gbp-video-stream-probe/Makefile"}
PAYLOAD_MAX = 248
WIDTH = {"lu": 10, "ld": 11, "u": 10, "d": 11, "llu": 20, "lld": 20, "llx": 16, "lx": 8, "x": 8}
SPEC = re.compile(r"%(?:(\d+)\$)?([-+ #0]*)(\d+)?(?:\.(\d+))?(hh|h|ll|l|z|t|j)?([diouxXeEfgGcsp%])")
STREAM15_SHA = "dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49"   # stream-0015 @ da06500, 514 880 B; built in the project image at the clean commit (Issue #27)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def strip_comments(src):
    return re.sub(r"//[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", src, flags=re.S))


def git(*a):
    r = subprocess.run(["git", "-C", ROOT] + list(a), capture_output=True, text=True)
    return None if r.returncode != 0 else r.stdout


def body_of(src, fn):
    m = re.search(r"^(?:static )?[^\n;]*\b%s\s*\(" % fn, src, re.M)
    i = src.index("{", m.start())
    d, j = 0, i
    while True:
        d += src[j] == "{"
        d -= src[j] == "}"
        if d == 0:
            return src[i:j + 1]
        j += 1


def key_format():
    m = re.search(r'#define GBP_INPUT_EVENT_FMT "((?:[^"\\]|\\.)*)"', read(INPUT_H))
    return m.group(1)


def worst_case(fmt, s_width):
    total, pos = 0, 0
    for m in SPEC.finditer(fmt):
        total += m.start() - pos
        pos = m.end()
        length, conv, width = m.group(5) or "", m.group(6), m.group(3)
        if conv == "%":
            total += 1
            continue
        if conv == "s":
            total += s_width
            continue
        w = WIDTH[length + conv]
        if width and width.isdigit():
            w = max(w, int(width))
        total += w
    return total + len(fmt) - pos


def descriptor_and_policy(src):
    src = strip_comments(src)
    d = re.search(r"GBP_KEYPAD_DESCRIPTOR\s*=\s*\{\s*\{([^}]*)\}\s*,\s*(\d+)\s*\}", src)
    p = re.search(r"GBP_INPUT_POLICY_DEFAULT\s*=\s*\{(.*?)\};", src, re.S)
    return ([int(x) for x in d.group(1).split(",")], int(d.group(2)), re.sub(r"\s+", " ", p.group(1)))


class TheFormatIsOneAndFits(unittest.TestCase):
    def test_the_format_fits_the_payload_at_the_worst_case_of_every_conversion(self):
        fmt = key_format()
        self.assertTrue(fmt.startswith("KEY n=%lu act=%s keys=%04x word=%04x t_poll=%llx t_attempt=%llx t_done=%llx xfer=%lu rc=%s"))
        # the two %s are vocabularies: the action names and the transport status names, the longest 7 characters
        names = re.findall(r'return "([a-z?]+)";', body_of(read(INPUT_C), "gbp_input_action_name"))
        status = re.findall(r'return "([a-z?]+)";', read(os.path.join(ROOT, "src", "gbp", "gbp_transport.c")).split("gbp_status_name")[1].split("}")[0])
        self.assertEqual(sorted(names), ["?", "change", "first", "none", "refresh", "retry"])
        self.assertEqual(max(len(n) for n in names + status), 7)
        w = worst_case(fmt, 7)
        self.assertLessEqual(w, PAYLOAD_MAX, "KEY worst case %d > %d" % (w, PAYLOAD_MAX))
        self.assertLessEqual(w, int(re.search(r"#define GBP_INPUT_EVENT_RENDER_MAX (\d+)u", read(INPUT_H)).group(1)))
        self.assertEqual(w, 158)   # derived: 4 + 12 + 5+7 + 6+8 + 6+8 + 8+16 + 11+16 + 8+16 + 6+10 + 4+7
        self.assertEqual(read(INPUT_H).count("#define GBP_INPUT_EVENT_FMT "), 1)
        self.assertEqual(strip_comments(read(MAIN)).count("GBP_INPUT_EVENT_FMT"), 1, "one emission point, the macro, no copy of the format")

    def test_the_render_and_the_bound_are_covered_by_the_unit_test(self):
        u = read(UNIT)
        for tok in ("test_events_through_the_mock", "gbp_input_event_render(&e, buf, sizeof buf)", "len <= 248", "gbp_input_keylog_admit(960u, 1024u, 64u) == 0",
                    "GBP_INPUT_WRITE_REFRESH);\n    CHECK(in.events_recorded == 1u && in.event.pending == 0u)"):
            self.assertIn(tok, u, tok)


class TheEmissionPointAndTheBound(unittest.TestCase):
    def setUp(self):
        self.src = strip_comments(read(MAIN))

    def test_emitted_from_the_pump_slot_after_the_write_never_from_the_service_path(self):
        s = self.src
        self.assertEqual(s.count("ringlog_printf(keylog_rl, GBP_INPUT_EVENT_FMT, GBP_INPUT_EVENT_ARGS(&e))"), 1)
        step = body_of(s, "input_step")
        self.assertIn("act = gbp_input_step(&in_state, t, &s, t_poll);", step)
        self.assertLess(step.index("gbp_input_note_step_ticks("), step.index("keylog_emit(t)"))
        self.assertIn("act == GBP_INPUT_WRITE_FIRST || act == GBP_INPUT_WRITE_CHANGE || act == GBP_INPUT_WRITE_RETRY", step)
        self.assertNotIn("REFRESH", step)
        pump = body_of(s, "pump")
        first = [l.strip() for l in pump[pump.index("(void)user;") + len("(void)user;"):].splitlines() if l.strip()][0]
        self.assertEqual(first, "input_step();", "the input step is still the first statement of the slot")
        self.assertEqual(pump.count("gettime("), 5, "the stream audit's gettime pins of pump() are unchanged")
        emit = body_of(s, "keylog_emit")
        self.assertNotIn("gettime(", emit)
        self.assertIn("t->ticks(t->ctx)", emit)
        self.assertIn("gbp_input_take_event(&in_state, &e)", emit)
        for fn in ("gbp_irq_service.c", "gbp_vstate_probe.c", "gbp_vqueue.c", "gbp_vwitness.c", "gbp_vdisp.c", "gbp_vfull.c", "gbp_vvi.c"):
            body = read(os.path.join(ROOT, "src", "gbp", fn))
            self.assertNotIn("keylog", body, fn)
            self.assertNotIn("gbp_input", body, fn)
        arm, run, disarm = s.index("keylog_rl = &rl;"), s.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"), s.index("keylog_rl = 0;")
        self.assertLess(s.index("in_transport = &t;"), arm)
        self.assertLess(arm, run)
        self.assertLess(run, disarm)
        self.assertLess(s.index("in_transport = 0;"), disarm)

    def test_the_reserve_covers_the_post_run_records_and_the_surplus_is_counted(self):
        s = self.src
        reserve = int(re.search(r"#define KEYLOG_TAIL_RESERVE (\d+)u", s).group(1))
        after = s[s.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"):]
        post_run = after.count("ringlog_printf(&rl,")
        self.assertGreaterEqual(reserve, post_run + 8, "reserve %d, post-run records %d" % (reserve, post_run))
        self.assertLess(reserve, 128)
        self.assertIn("#define LOG_LINES 1024", s)
        self.assertIn("gbp_input_keylog_admit((uint32_t)keylog_rl->count, (uint32_t)keylog_rl->capacity, KEYLOG_TAIL_RESERVE)", s)
        emit = body_of(s, "keylog_emit")
        self.assertIn("keylog_lost++", emit)
        self.assertIn("keylog_truncated++", emit)
        # the summary record, once, after INPUTT, with the accounting a reader needs
        self.assertEqual(s.count('ringlog_printf(&rl, "KEYLOG '), 1)
        self.assertLess(s.index('"INPUTT write_ticks='), s.index('"KEYLOG events='))
        m = re.search(r'ringlog_printf\(&rl, "(KEYLOG [^"]*)"', s)
        for f in ("events=", "emitted=", "lost=", "truncated=", "overwritten=", "reserve=", "emit_ticks="):
            self.assertIn(f, m.group(1))
        self.assertLessEqual(worst_case(m.group(1), 0), PAYLOAD_MAX)
        self.assertIn("events=%lu emitted=%lu lost=%lu", s[s.index("OPENGBP-STREAM INPUT selftest="):][:400])

    def test_a_refresh_never_produces_an_event(self):
        c = strip_comments(read(INPUT_C))
        step = body_of(c, "gbp_input_step") if re.search(r"^static [^\n;]*\bgbp_input_step\s*\(", c, re.M) else c[c.index("enum gbp_input_action gbp_input_step("):]
        self.assertIn("if (act != GBP_INPUT_WRITE_REFRESH) {", step)
        self.assertIn("in->events_recorded++;", step)
        self.assertIn("if (e->pending) in->events_overwritten++;", step)


class NothingElseMoved(unittest.TestCase):
    def test_the_descriptor_and_the_policy_are_the_bytes_of_the_candidate_that_ran(self):
        old = git("show", "%s:src/gbp/gbp_input.c" % CANDIDATE_RAN)
        if old is None:
            self.skipTest("the candidate commit is not available in this checkout")
        self.assertEqual(descriptor_and_policy(read(INPUT_C)), descriptor_and_policy(old))
        bits, pressed, _ = descriptor_and_policy(read(INPUT_C))
        self.assertEqual((bits[:8], bits[8], bits[9], pressed), (list(range(8)), 9, 8, 1), "R -> bit 9, L -> bit 8, 1 = pressed: kept (U-GBP-010 closed AS-ASSIGNED)")

    def test_build_id_stream_0015_not_executed_not_staged(self):
        m = read(POC_MAKE)
        self.assertIsNotNone(re.search(r"^BUILD_ID\s*:=\s*stream-0015$", m, re.M))
        c = re.sub(r"\s+", " ", m.replace("\n# ", " "))
        for tok in ("stream-0015 is stream-0014 plus TWO logging changes and nothing else", "ONE \"KEY\" ringlog line", "ENVINPUT + ENVINPUT2",
                    "NOT PHYSICALLY EXECUTED; no run is pre-registered for it; not staged"):
            self.assertIn(tok, c, tok)
        self.assertIn("stream-0014 is stream-0013 plus the INPUT PATH", m, "the history of the build ids stays")

    def test_the_candidate_if_built_is_clean_and_is_the_pinned_one(self):
        info = os.path.join(ROOT, "build", "poc", "gbp-video-stream-probe", "build-info.txt")
        if not os.path.exists(info):
            self.skipTest("no build metadata on this host")
        t = read(info)
        if "build_id=stream-0015" not in t:
            self.skipTest("the tree builds a different stream candidate")
        if "commit=da06500" not in t:
            # a later code checkpoint (Issue #39 changed the service-path module) rebuilds the stream probe at ITS commit;
            # that artifact is not the candidate, whose identity is da06500's. The staged copy is what the runs used.
            self.skipTest("the stream-0015 artifact on this host was rebuilt at another commit; the candidate is da06500's")
        self.assertNotIn("-dirty", t)
        if STREAM15_SHA is None:
            self.skipTest("the candidate's identity is pinned by the docs checkpoint")
        self.assertIn("sha256_dol=" + STREAM15_SHA, t)

    def test_only_the_four_files_of_issue_27_moved_under_the_frozen_paths(self):
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)
        changed = guards.changed_since(BASE, ["src", "poc", "tools", "Makefile", "stimulus", "captures/fixtures", "docs/protocol", "docs/hardware"])   # Issue #29: tracked AND untracked, one implementation
        # Issue #50 (2026-09-22) made §V7.6.11's frozen verdicts executable BEFORE RUN 21 / RUN 22's logs
        # existed: tools/v7611.py recomputes them and is exercised on SYNTHETIC vectors only, so the
        # ingestion cannot tune the constructions to the data. It reads no run and changes nothing.
        changed = changed - {"tools/v7611.py"}
        # Issue #58 (2026-09-22) pre-registered Phase 6's first physical run (§V8, GBP-AUDIO-001) and made its
        # three-model predictions executable BEFORE any build or log existed: tools/v8audio.py is exercised on
        # SYNTHETIC vectors only, reads no run, authorises nothing and promotes nothing.
        changed = changed - {"tools/v8audio.py"}
        # Issue #29 (2026-09-21) added the promotion sweep tool; it reads the pages and judges nothing, and
        # Issue #44 (2026-09-22) hardened the staging tool against destroying a frozen slot: the manifest gained a frozen_sha256 column
        changed = changed - {"tools/reconcile.py", "tools/swiss_export.py", "tools/swiss-layout.tsv"}
        changed = changed
        # Issue #28 (2026-09-21) corrected docs/protocol/INPUT.md's "GBP-KEY-009; recorded, not implemented" on its
        # date, in its own commit, and appended the RUN 17 / RUN 18 pre-registration (§V7.3) after §V7.2; the
        # chapter heading grew; §V7.1 and §V7.2 stay the bytes of this checkpoint's base
        # ... and Issue #33 (2026-09-21) ingested RUN 16 / 17 / 18: fixtures added, the consolidated pages promoted (tests/host/test_run17.py pins them)
        allowed = ALLOWED | {"docs/protocol/INPUT.md", "docs/protocol/REGISTERS.md", "docs/protocol/INITIALIZATION.md", "docs/hardware/GBS-DOL.md",
                             "docs/hardware/ARCHITECTURE.md"} | {p for p in changed if re.search(r"^captures/fixtures/.*-run1[678]-", p)}
        # Issue #39 (2026-09-21) built the playable image: the session end in the service-path module (tests/host/test_play_image.py pins it), a new POC, its audit profile and its Swiss slot
        allowed |= {"src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_session.c", "src/gbp/gbp_session.h", "poc/gbp-play-session/Makefile", "poc/gbp-play-session/source/main.c", "tools/poc_audit.py", "tools/swiss-layout.tsv", "Makefile"}
        self.assertTrue(changed <= allowed, "changed beyond the input and logging modules: %s" % sorted(changed - allowed))
        old = git("show", "%s:docs/research/HARDWARE_TESTS.md" % BASE)
        new = read(HW)
        old_head = old[old.index("\n## V7 "):].splitlines()[1]
        new_head = [l for l in new.splitlines() if l.startswith("## V7 ")][0]
        self.assertTrue(new_head.startswith(old_head), "the chapter heading grows, it does not change")
        self.assertEqual(new[new.index("### V7.1 "):new.index("### V7.3 ")].rstrip("\n"), old[old.index("### V7.1 "):].rstrip("\n"),
                         "§V7.1 and §V7.2 untouched")


if __name__ == "__main__":
    unittest.main()
