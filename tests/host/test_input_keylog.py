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
        old = guards.show(CANDIDATE_RAN, "src/gbp/gbp_input.c")  # Issue #83 (B): absent COMMIT skips, absent PATH fails
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
        # Issue #65 (2026-09-22) BUILT stimulus/agb-tone (tone-0001), §V9's two-frequency stimulus: a new
        # stimulus ROM beside the four the family already had. It touches no runtime path, no image and no
        # slot; §V9.14 records its identity and tests/host/test_agb_tone.py runs its own code on the host.
        changed = changed - {"stimulus/agb-tone/Makefile", "stimulus/agb-tone/source/main.c"}
        # Issue #70 (2026-09-22) BUILT stimulus/agb-sweep (sweep-0001), §V11's TWO-AXIS stimulus: a new
        # stimulus ROM beside the five the family now has, and agb-tone is NOT touched (a test pins it
        # byte-identical). It touches no runtime path, no image and no slot; §V11.15 records its
        # identity and tests/host/test_agb_sweep.py runs its own code on the host.
        changed = changed - {"stimulus/agb-sweep/Makefile", "stimulus/agb-sweep/source/main.c"}
        # Issue #64 (2026-09-22) pre-registered agb-tone (§V9) and made its constructions executable BEFORE
        # the ROM exists: tools/v9tone.py is exercised on SYNTHETIC vectors only, reads no run, authorises
        # nothing and promotes nothing.
        changed = changed - {"tools/v9tone.py"}
        # Issue #69 (2026-09-22) pre-registered the amplitude sweep (§V11) and froze its constructions
        # BEFORE stimulus/agb-sweep exists: tools/v11sweep.py runs on SYNTHETIC vectors only, reads no
        # run, authorises nothing and promotes nothing. It is the fourth outing of the same discipline.
        changed = changed - {"tools/v11sweep.py"}
        # Issue #74 (2026-09-23) added tools/geckorx.py, the HOST receiver for the Operator's Pico
        # Gecko. It reads a serial port and writes bytes to a file; it touches no image, no POC and
        # no runtime path, and CLAUDE.md §14 forbids anything coming to depend on the device.
        changed = changed - {"tools/geckorx.py"}
        # Issue #75 (2026-09-23) pre-registered U-GBP-038's separator (§V13) and froze its
        # construction BEFORE the run: tools/v13sep.py runs on SYNTHETIC vectors only, borrows
        # v11sweep's classifier unchanged, reads no run and authorises nothing.
        changed = changed - {"tools/v13sep.py"}
        # §V14 (2026-09-23) froze the METHOD of RUN 34's measurement before the run:
        # tools/v14repeat.py contains no gate, reproduces §V11.16.7 exactly, reads no run.
        changed = changed - {"tools/v14repeat.py"}
        # Issue #79 (2026-09-23): tools/v16bitgate.py, QUESTION V repaired at bit resolution and
        # QUESTION L, frozen forward only; it imports v11sweep and edits nothing.
        changed = changed - {"tools/v16bitgate.py"}
        # Issue #80 (2026-09-23): tools/v17pred.py (the predictions, frozen first) and
        # tools/v17decode.py (the H-PWM decoder); they read the captures and touch no image.
        changed = changed - {"tools/v17pred.py", "tools/v17decode.py"}
        # Issue #81 (2026-09-23): the AUDIO decode as runtime code -- src/audio/ (the decoder, the
        # replay backend, the 125/16 resampler and its generated table), its generator
        # tools/gen_aresamp.py, and RUN 33 / RUN 34's raw sidecars versioned as fixtures. Host-tested
        # only: no image links src/audio/, and no POC, slot or runtime path changed.
        changed = changed - {"src/audio/gbp_adec.c", "src/audio/gbp_adec.h", "src/audio/gbp_asrc.c",
                             "src/audio/gbp_asrc.h", "src/audio/gbp_aresamp.c", "src/audio/gbp_aresamp.h",
                             "src/audio/gbp_aresamp_coef.h", "tools/gen_aresamp.py", "captures/README.md",
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz",
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz",
                             # Issue #90: RUN 36's console log, byte for byte (§V21.9)
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-aout-0002-run36.log",
                             # Issue #91: RUN 37's console log, byte for byte (§V19.14)
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-drain-0001-run37.log"}
        # Issue #82 (2026-09-23): tools/v18block.py, what one AUDIO block contains, measured on the
        # versioned fixtures (§V18). Descriptive, no gate; it reads captures and touches no image.
        changed = changed - {"tools/v18block.py"}
        # Issue #84 (2026-09-23): tools/v19drain.py, §V19's three gates, FROZEN BEFORE the run
        # (GBP-AUDIO-005). Synthetic vectors only; it reads no capture and authorises nothing.
        changed = changed - {"tools/v19drain.py"}
        # Issue #92 (2026-09-23): tools/v22accept.py, §V22's gates (Phase 6's acceptance), FROZEN
        # BEFORE the POC exists. Synthetic vectors only; it reads no capture and authorises nothing.
        changed = changed - {"tools/v22accept.py"}
        # Issue #92: Phase 6's acceptance image and its chain -- poc/gbp-audio-live, src/audio/gbp_alive.*
        # and gbp_aplay.* (host-tested: tests/unit, tests/host/test_alive_chain.py), and the report
        # builder frozen with it. No earlier image, path or module changed.
        changed = changed - {"poc/gbp-audio-live/Makefile", "poc/gbp-audio-live/source/main.c",
                             "src/audio/gbp_alive.c", "src/audio/gbp_alive.h", "src/audio/gbp_aplay.c",
                             "src/audio/gbp_aplay.h", "tools/v22report.py"}
        # Issue #84: src/audio/gbp_adrain.* -- GBP-AUDIO-005's phase machine and coverage
        # counter, host-tested only (tests/unit/test_gbp_adrain.c). No image links it yet.
        changed = changed - {"src/audio/gbp_adrain.c", "src/audio/gbp_adrain.h"}
        # Issue #84 (2026-09-23) BUILT GBP-AUDIO-005's image, drain-0001 (§V19.11 A4.1): play-0001 plus
        # the drain's period decoder (src/audio/gbp_aperiod.*, host-tested), the POC that carries it, and
        # tools/v19report.py, the log -> report builder frozen before the run. The service path gains two
        # optional hooks, NULL in every earlier build (tests/unit/test_gbp_video_state.c proves the operation
        # stream identical), and tests/host/test_drain_image.py diffs the image against play-0001.
        changed = changed - {"poc/gbp-audio-drain-probe/Makefile", "poc/gbp-audio-drain-probe/source/main.c",
                             "src/audio/gbp_aperiod.c", "src/audio/gbp_aperiod.h", "tools/v19report.py"}
        # Issue #87 (2026-09-23) restored `make build` at HEAD: since #59 the service module references the
        # AUDIO window, so these four POCs link gbp_awin.c the way they link gbp_vwitness.c, cfg.awin NULL.
        # No executed artifact is rebuilt or relabelled; tests/host/test_poc_link_closure.py keeps the class
        # from recurring unobserved.
        changed = changed - {"poc/gbp-play-session/Makefile", "poc/gbp-video-stream-probe/Makefile",
                             "poc/gbp-video-state-probe/Makefile", "poc/gbp-video-color-probe/Makefile"}
        # Issue #86 (2026-09-23) BUILT AOUT-HW-001, the OUTPUT-PATH image (not a GBP audio test): the
        # listening sequence (src/audio/gbp_alisten.*, bit-identical to the #80/#81 reference on RUN 33,
        # tests/host/test_audio_listen.py) and the POC that plays it through the AI. No GBP code is linked
        # into it (the `aout` audit profile), and no runtime path, image or slot changed.
        changed = changed - {"src/audio/gbp_alisten.c", "src/audio/gbp_alisten.h",
                             "poc/audio-output-replay/Makefile", "poc/audio-output-replay/source/main.c",
                             "poc/audio-output-replay/source/fixture_embed.S",
                             # §V21.6: aout-0002's sealed play order, drawn and committed before the code
                             "poc/audio-output-replay/source/aout_order.h"}
        # Issue #62 (2026-09-22) ingested RUN 30 and needed two READERS that did not exist: awinparse.py,
        # a strict parser for the OGBPAW1 sidecar, and tprime.py, §V7.9's decision rule. Both only read and
        # report; the VERDICT constructions stay in tools/v8audio.py, which tests/host/test_run30.py diffs
        # against the commit that wrote it.
        changed = changed - {"tools/awinparse.py", "tools/tprime.py"}
        # Issue #59 (2026-09-22) BUILT the image §V8 needs: the AUDIO window and its OGBPAW1 sidecar
        # (src/gbp/gbp_awin*, host-testable, no libogc) and the POC that carries them, stream-0016. The
        # service path gains ONE optional config field and ONE call after the AUDIO drain and its commit;
        # no device operation is added, removed or reordered (tests/host/test_awin_image.py diffs it).
        changed = changed - {"src/gbp/gbp_awin.c", "src/gbp/gbp_awin.h",
                             "src/gbp/gbp_awindump.c", "src/gbp/gbp_awindump.h",
                             "poc/gbp-audio-window-probe/Makefile",
                             "poc/gbp-audio-window-probe/source/main.c"}
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
        # Issue #95 (2026-09-24) promoted Phase 6 into docs/protocol/AUDIO.md (new), indexed it in README.md,
        # and corrected the stale audio rows its reconciliation sweep found (REGISTERS.md, INITIALIZATION.md,
        # ARCHITECTURE.md, GBS-DOL.md) as wording that cites EVIDENCE. Documentation only; no status moved.
        changed = changed - {"docs/protocol/AUDIO.md", "docs/protocol/README.md", "docs/protocol/INITIALIZATION.md",
                             "docs/protocol/REGISTERS.md", "docs/hardware/ARCHITECTURE.md", "docs/hardware/GBS-DOL.md"}
        # Issue #96 (2026-09-24) swept the consolidated set for pages disagreeing with the record:
        # VIDEO.md gained a pointer to AUDIO.md, docs/hardware/README.md its missing AUDIO.md entry.
        changed = changed - {"docs/protocol/VIDEO.md", "docs/hardware/README.md"}
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
