"""tests/host/test_play_gba2_image.py -- GitHub Issue #158: poc/gbp-play-gba2, the GBA play image vehicle-0002 (GBP-PLAY-002), against the Issue's Authorised list.

vehicle-0002 is vehicle-0001's COPY plus ONE teardown block that writes STARTUP / STARTUPT / STARTUPV / STREAMINV / STREAMSELFTEST through src/gbp/gbp_startrec. Checked here:
  * EVERY structural test of vehicle-0001 (tests/host/test_play_gba_image.py) runs again on the copy -- the module is loaded a second time with its paths pointed at poc/gbp-play-gba2, so
    the session flow, the audio configuration, the plan, the stores and the declaration are held to the same text (the tests that pin vehicle-0001's own identity, slot and targets are
    not re-run: this file pins vehicle-0002's);
  * vehicle-0001's and the V28 image's sources are byte-identical to their pins (executed images: an image reproduces only at its own commit);
  * the source diff against vehicle-0001 holds ONLY the allowed hunks (the Issue's item 1, a-e);
  * the formatter's literals are the ten inline copies' (STARTUPV the nine-copy shape), with their argument casts; every record line fits the log line at its worst case;
  * REACHABILITY from main() (not a token grep): the formatter is called from main only, after the probe has returned, the draw-done callback is restored and the DMA callback is gone,
    outside `if (sync_started)`, and from nothing the pump / tap / DMA callback / draw-done handler / step hook reach; mutants of each property are caught;
  * the records main() can write after `keylog_rl = 0` are bounded, from the code's own loops and caps, below KEYLOG_TAIL_RESERVE (1280);
  * the identity, the Makefile targets, the audit profile `vehicle2`, and no Swiss row.
"""
import hashlib
import importlib.util
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import poc_audit  # noqa: E402
import test_v28_plans as tp  # noqa: E402

POC = os.path.join(ROOT, "poc", "gbp-play-gba2")
MAIN = os.path.join(POC, "source", "main.c")
MAKEFILE = os.path.join(POC, "Makefile")
V1 = os.path.join(ROOT, "poc", "gbp-play-gba")
V1_MAIN = os.path.join(V1, "source", "main.c")
V1_MAKEFILE = os.path.join(V1, "Makefile")
FORMATTER = os.path.join(ROOT, "src", "gbp", "gbp_startrec.c")
OUT = os.path.join(ROOT, "build", "poc", "gbp-play-gba2")
V1_OUT = os.path.join(ROOT, "build", "poc", "gbp-play-gba")
FORMATTERS = ("gbp_startrec_startup", "gbp_startrec_startupt", "gbp_startrec_startupv", "gbp_startrec_streaminv", "gbp_startrec_streamselftest")
HOT_ROOTS = ("pump", "live_tap", "live_dma_cb", "on_draw_done", "gbp_v28_step_hook")
TEN = ("gbp-audio-drain-probe", "gbp-audio-game", "gbp-audio-game2", "gbp-audio-live", "gbp-audio-split", "gbp-audio-sync", "gbp-audio-trace", "gbp-audio-window-probe",
       "gbp-play-session", "gbp-video-stream-probe")
TAGS = {"STARTUP": "gbp_startrec_startup", "STARTUPT": "gbp_startrec_startupt", "STARTUPV": "gbp_startrec_startupv", "STREAMINV": "gbp_startrec_streaminv",
        "STREAMSELFTEST": "gbp_startrec_streamselftest"}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def defs_of(src):
    return tp.function_defs(tp.strip_for_calls(src))


# ------------------------------------------------------------------------------------------------ vehicle-0001's structural tests, on the copy
def _load_v1_tests_on_the_copy():
    spec = importlib.util.spec_from_file_location("test_play_gba_image_on_gba2", os.path.join(HERE, "test_play_gba_image.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.POC, m.MAIN, m.MAKEFILE, m.OUT = POC, MAIN, MAKEFILE, OUT
    return m


_v1 = _load_v1_tests_on_the_copy()


class OnTheCopy_TheV28ImageIsUntouched(_v1.TheV28ImageIsUntouched):
    pass


class OnTheCopy_ThePlanAndTheStoresAreTheToolsArithmetic(_v1.ThePlanAndTheStoresAreTheToolsArithmetic):
    pass


class OnTheCopy_NoResearchMachineryIsLinkedOrReachable(_v1.NoResearchMachineryIsLinkedOrReachable):
    pass


class OnTheCopy_TheAudioIsConfiguredOnceAtT256A1(_v1.TheAudioIsConfiguredOnceAtT256A1):
    pass


class OnTheCopy_ThePhasesAreTimed(_v1.ThePhasesAreTimedAndNothingTheOperatorPressesMovesThem):
    pass


class OnTheCopy_EveryRecordTheDesignNamesIsWrittenAndReadable(_v1.EveryRecordTheDesignNamesIsWrittenAndReadable):
    pass


class OnTheCopy_TheDeclarationIsMadeAfterTheSession(_v1.TheDeclarationIsMadeAfterTheSessionAndNeverReachesTheCartridge):
    pass


class OnTheCopy_TheSessionFlowSurvivesTheCopy(_v1.TheSessionFlowSurvivesTheCopy):
    pass


class TheCopyIsTheRightOne(unittest.TestCase):
    def test_the_loaded_module_reads_the_copy(self):
        self.assertEqual(_v1.MAIN, MAIN)
        self.assertIn("gbp_startrec_startup", _v1.stripped(), "the re-run structural tests read poc/gbp-play-gba2, not vehicle-0001")


# ------------------------------------------------------------------------------------------------ the executed images stay frozen
class TheExecutedImagesAreUntouched(unittest.TestCase):
    def test_vehicle_0001_sources_are_their_pins(self):
        self.assertEqual(sha(V1_MAIN), "276abbe2ed673421204f11f92472e1074eb9f52c6ffb949929c6cd350566e7f6")
        self.assertEqual(sha(V1_MAKEFILE), "4122b4bead8fa79efbcba2e78649af9127757009e1d11f50b8491e07eac8ea44")
        self.assertEqual(sorted(os.listdir(os.path.join(V1, "source"))), ["main.c"])

    def test_the_v28_sources_are_their_pins(self):
        v28 = os.path.join(ROOT, "poc", "gbp-audio-v28")
        self.assertEqual(sha(os.path.join(v28, "source", "main.c")), "a821c331970cd11dd348c226c03c81999be990797cfc0bbc9ec43f06d40ec73b")
        self.assertEqual(sha(os.path.join(v28, "Makefile")), "4c6bfd1646d1f0197247463724f666a6f03e2f93816a754a6b330ced40affbf1")


# ------------------------------------------------------------------------------------------------ the diff against vehicle-0001: only the allowed hunks
def diff_hunks(a, b):
    import difflib
    al, bl = a.split("\n"), b.split("\n")
    sm = difflib.SequenceMatcher(a=al, b=bl, autojunk=False)
    return [(tag, al[i1:i2], bl[j1:j2], j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]


def header_end(text):
    """the index of the first `#include` line: the file's header comment is everything before it"""
    return next(i for i, l in enumerate(text.split("\n")) if l.startswith("#include"))


V1_HEADER = '    printf("\\n  Open-GBP " TEST_ID "  Issue #153, THE GBA PLAY IMAGE (NOT PHYSICALLY VALIDATED)\\n");'
V2_HEADER = '    printf("\\n  Open-GBP " TEST_ID "  Issue #158, THE GBA PLAY IMAGE vehicle-0002 (NOT PHYSICALLY VALIDATED)\\n");'


def classify_main_hunk(tag, old, new, j1, hdr_end):
    """-> the allowed category of one hunk of main.c, or None. A comment insertion is allowed ONLY inside the file's header comment (R4 of the
    review): every inserted line sits before the first #include of the new file."""
    if tag == "insert" and new and all(l.startswith(" *") or l.startswith("/*") for l in new) and j1 + len(new) <= hdr_end:
        return "header comment"
    if tag == "insert" and new == ['#include "gbp_startrec.h"']:
        return "include"
    if tag == "replace" and old == ['#define OPENGBP_APP_NAME "gbp-play-gba"'] and new == ['#define OPENGBP_APP_NAME "gbp-play-gba2"']:
        return "app name default"
    if tag == "replace" and old == [V1_HEADER] and new == [V2_HEADER]:
        return "screen header"
    if tag == "insert" and new:
        body = tp.code("\n".join(new))
        stmts = [s.strip() for s in re.split(r";", re.sub(r"[{}]", ";", body)) if s.strip()]
        calls = [s for s in stmts if not s.startswith("char srec[LOG_LINE_LEN]")]
        fmt_calls = [s for s in calls if re.match(r"gbp_startrec_\w+\(srec, sizeof srec,", s)]
        logs = [s for s in calls if s == 'ringlog_printf(&rl, "%s", srec)']
        if len(fmt_calls) == 5 and len(logs) == 5 and len(calls) == 10 and "char srec[LOG_LINE_LEN]" in body:
            return "the teardown block"
    return None


class TheDiffHoldsOnlyTheAllowedHunks(unittest.TestCase):
    def test_main_c(self):
        hunks = diff_hunks(read(V1_MAIN), read(MAIN))
        cats = []
        for tag, old, new, j1 in hunks:
            c = classify_main_hunk(tag, old, new, j1, header_end(read(MAIN)))
            self.assertIsNotNone(c, "a hunk the Issue does not allow:\n-%s\n+%s" % ("\n-".join(old), "\n+".join(new)))
            cats.append(c)
        self.assertEqual(sorted(cats), sorted(["header comment", "include", "app name default", "screen header", "the teardown block"]), cats)

    def test_a_hunk_outside_the_list_is_caught(self):
        """mutants: an instruction added to live_dma_cb, a changed constant, a sixth call in the block, a comment block inserted outside the header (R4)"""
        base = read(MAIN)
        for old, new in (("AUDIO_InitDMA((u32)(size_t)c, GBP_APLAY2_CHUNK_BYTES);\n}", "AUDIO_InitDMA((u32)(size_t)c, GBP_APLAY2_CHUNK_BYTES);\n    live_taps++;\n}"),
                         ("#define PLAY_SLICE_TILE_ROWS     1u", "#define PLAY_SLICE_TILE_ROWS     2u"),
                         ('        ringlog_printf(&rl, "%s", srec);\n    }\n', '        ringlog_printf(&rl, "%s", srec);\n        ringlog_printf(&rl, "%s", srec);\n    }\n'),
                         ("int main(void)\n{", "/*\n * a comment block slipped in below the header\n */\nint main(void)\n{"),
                         ("static void on_draw_done(void)\n", " * a stray comment line before a handler\nstatic void on_draw_done(void)\n")):
            self.assertIn(old, base)
            mutant = base.replace(old, new, 1)
            bad = [h for h in diff_hunks(read(V1_MAIN), mutant) if classify_main_hunk(h[0], h[1], h[2], h[3], header_end(mutant)) is None]
            self.assertTrue(bad, "the mutant %r was not caught" % new)

    def test_makefile(self):
        v1, v2 = read(V1_MAKEFILE).split("\n"), read(MAKEFILE).split("\n")
        self.assertEqual(len(v1) + 1, len(v2), "one comment line added at the top; every other line maps one to one")
        allowed = {"APP_NAME   := gbp-play-gba": "APP_NAME   := gbp-play-gba2", "BUILD_ID   ?= vehicle-0001": "BUILD_ID   ?= vehicle-0002"}
        for tag, old, new, _j1 in diff_hunks(read(V1_MAKEFILE), read(MAKEFILE)):
            for o, n in zip(old, new):
                if o.startswith("#") and n.startswith("#"):
                    continue
                if o in allowed:
                    self.assertEqual(n, allowed[o])
                elif o.startswith("GIT_DIRTY"):
                    self.assertEqual(n, o.replace("../../poc/gbp-play-gba ", "../../poc/gbp-play-gba2 "))
                elif o.startswith("SRCS :="):
                    self.assertEqual(n, o.replace("gbp_cartdecl.c ", "gbp_cartdecl.c gbp_startrec.c "))
                else:
                    self.fail("a Makefile line the Issue does not allow: %r -> %r" % (o, n))
            for extra in new[len(old):]:
                self.assertTrue(extra.startswith("#"), extra)


# ------------------------------------------------------------------------------------------------ the formatter: the ten copies' literals and casts, the widths
def literals_after(src, start):
    out, i = "", start
    while True:
        m = re.compile(r'\s*"((?:[^"\\]|\\.)*)"').match(src, i)
        if not m:
            return out, i
        out += m.group(1)
        i = m.end()


def copy_literals(path):
    src = read(path)
    got = {}
    for m in re.finditer(r"ringlog_printf\(\s*&?\w+,\s*(?=\")", src):
        lit, _ = literals_after(src, m.end())
        tag = lit.split(" ", 1)[0]
        if tag in TAGS:
            got.setdefault(tag, []).append(lit)
    return got


def formatter_literals():
    src = read(FORMATTER)
    d = tp.function_defs(tp.code(src))
    out = {}
    for tag, fn in TAGS.items():
        body = d[fn]
        m = re.search(r"snprintf\(out, cap,(?=\s*\")", body)
        lit, end = literals_after(body, m.end())
        args = body[end:body.rindex(")")]
        out[tag] = (lit, args)
    return out


def worst(lit):
    """the literal with every conversion at its widest: %s the longest mode name, %d 11, %lu 10, %llx 16, %llu 20"""
    return len(re.sub(r"%(llx|llu|lu|d|s)", lambda m: {"llx": "f" * 16, "llu": "9" * 20, "lu": "9" * 10, "d": "-" * 11, "s": "diagnostic"}[m.group(1)], lit))


class TheFormatterIsTheTenCopiesFormat(unittest.TestCase):
    def test_the_literals_equal_every_copy(self):
        mine = formatter_literals()
        for poc in TEN:
            got = copy_literals(os.path.join(ROOT, "poc", poc, "source", "main.c"))
            for tag in TAGS:
                self.assertEqual(len(got.get(tag, [])), 1, (poc, tag))
                if tag == "STARTUPV" and poc == "gbp-video-stream-probe":
                    self.assertIn("t_drawdone=%llx", got[tag][0], "the stream probe's own shape (V5.52)")
                    self.assertEqual(got[tag][0].replace(" t_drawdone=%llx", ""), mine[tag][0])
                    continue
                self.assertEqual(got[tag][0], mine[tag][0], (poc, tag))
        self.assertNotIn("t_drawdone", mine["STARTUPV"][0], "the nine-copy shape")

    def test_the_casts_are_the_copies(self):
        for tag, (lit, args) in formatter_literals().items():
            n_lu = len(re.findall(r"%lu", lit))
            n_ll = len(re.findall(r"%ll[xu]", lit))
            self.assertEqual(len(re.findall(r"\(unsigned long\)", args)), n_lu, tag)
            self.assertEqual(len(re.findall(r"\(unsigned long long\)", args)), n_ll, tag)

    def test_every_record_fits_the_log_line_at_its_worst_case(self):
        ring = read(os.path.join(ROOT, "src", "log", "ringlog.c"))
        self.assertIn("%06u ", ring)
        self.assertIn("#define LOG_LINE_LEN 256", read(MAIN))
        usable = 256 - len("000000 ") - 1
        self.assertEqual(usable, 248)
        widths = dict((tag, worst(lit)) for tag, (lit, _a) in formatter_literals().items())
        self.assertEqual(widths, {"STARTUP": 212, "STARTUPT": 234, "STARTUPV": 196, "STREAMINV": 130, "STREAMSELFTEST": 205})
        self.assertEqual(max(widths, key=widths.get), "STARTUPT")
        for tag, w in widths.items():
            self.assertLess(w, usable, tag)

    def test_the_object_references_nothing_but_snprintf(self):
        code = tp.code(read(FORMATTER))
        calls = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", code)) - set(FORMATTERS) - {"sizeof"}
        self.assertEqual(calls, {"snprintf"})
        self.assertEqual(re.findall(r"#include\s*[<\"]([^>\"]+)", read(FORMATTER)), ["gbp_startrec.h", "stdio.h"])


# ------------------------------------------------------------------------------------------------ A1: WHICH variables main() passes (the copies' expressions)
GAME2 = os.path.join(ROOT, "poc", "gbp-audio-game2", "source", "main.c")
CAST = re.compile(r"\((?:unsigned long long|unsigned long|uint64_t|uint32_t|int)\)")


def split_args(text):
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [a for a in out]


def norm(e):
    return re.sub(r"\s+", "", CAST.sub("", e))


def call_args(text, start):
    """the argument text of the call whose '(' is the first one at or after `start`"""
    i = text.index("(", start)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[i + 1:j]
    raise ValueError("unbalanced")


def main_formatter_args(src):
    """{tag: [normalised arguments]} of main()'s five formatter calls (the buffer and its size dropped)"""
    main = defs_of(src)["main"]
    out = {}
    for tag, fn in TAGS.items():
        m = re.search(r"\b%s\s*\(" % fn, main)
        args = [norm(a) for a in split_args(call_args(main, m.start()))]
        assert args[:2] == ["srec", "sizeofsrec"], args
        out[tag] = args[2:]
    return out


def copy_expressions():
    """{tag: [normalised arguments]} of the inline copy (poc/gbp-audio-game2/source/main.c:1374-1409), STARTUPV mapped onto the formatter's
    parameters: the copy's `have ? X : 0u` guards are the formatter's own, t_ho / c are the copy's locals, and its ticks expression is the
    formatter's (t_decision, t_control) pair."""
    src = tp.code(read(GAME2))
    out = {}
    for tag in TAGS:
        m = re.search(r'ringlog_printf\(&rl,\s*"%s ' % tag, src)
        parts = split_args(call_args(src, m.start()))           # [&rl, the (concatenated) literal, the arguments...]; no format holds a comma
        assert norm(parts[0]) == "&rl" and parts[1].strip().startswith('"%s ' % tag), parts[:2]
        out[tag] = [norm(x) for x in parts[2:]]
    # STARTUPV: the copy's locals and guards
    c = norm(re.search(r"const uint64_t c = ([^;]+);", src).group(1))
    t_ho = norm(re.search(r"const uint64_t t_ho = ([^;]+);", src).group(1))
    unwrap = lambda e: re.sub(r"^\(?first_real\.have\?(.+):0u\)?$", r"\1", e)
    v = out["STARTUPV"]
    assert v[5] == "((first_real.have&&t_ho>c)?t_ho-c:0u)", v[5]
    assert v[4] == "t_ho" and unwrap(t_ho) == "first_real.t_decision", (v[4], t_ho)
    out["STARTUPV"] = [v[0]] + [unwrap(x) for x in v[1:4]] + [unwrap(t_ho), c]
    return out


class MainPassesTheCopiesVariables(unittest.TestCase):
    """A1 of the central session's review: swapping first_real.t_take and first_real.t_convert_done in main()'s STARTUPV call passed every test.
    main()'s five argument lists, normalised (no casts, no spaces), must be the inline copy's expressions."""

    def test_the_five_argument_lists_are_the_copys(self):
        self.assertEqual(main_formatter_args(read(MAIN)), copy_expressions())
        self.assertEqual(copy_expressions()["STARTUPV"], ["first_real.have", "first_real.frame_index", "first_real.t_take", "first_real.t_convert_done",
                                                          "first_real.t_decision", "res.t_control_transform"])

    def test_swap_mutants_fail(self):
        base = read(MAIN)
        for old, new in (("first_real.t_take, first_real.t_convert_done", "first_real.t_convert_done, first_real.t_take"),
                         ("first_real.t_decision, res.t_control_transform", "res.t_control_transform, first_real.t_decision"),
                         ("present.invariant_failures, present.invariant_checks", "present.invariant_checks, present.invariant_failures"),
                         ("selftest_presents,\n                                    selftest_repeats", "selftest_repeats,\n                                    selftest_presents")):
            self.assertIn(old, base)
            self.assertNotEqual(main_formatter_args(base.replace(old, new, 1)), copy_expressions(), "the swap %r was not caught" % new)


# ------------------------------------------------------------------------------------------------ reachability: where the block is, what reaches it
def placement_problems(src):
    """[] when the five formatter calls are where the Issue puts them; otherwise what is wrong (used on the real main.c and on mutants)"""
    d = defs_of(src)
    probs = []
    hot = set()
    for r in HOT_ROOTS:
        hot |= tp.reachable_functions(d, r)
    for fn, body in d.items():
        for f in FORMATTERS:
            if re.search(r"\b%s\s*\(" % f, body):
                if fn != "main":
                    probs.append("%s calls %s" % (fn, f))
                if fn in hot:
                    probs.append("%s (reachable from the hot path) calls %s" % (fn, f))
    main = d.get("main", "")
    for f in FORMATTERS:
        n = len(re.findall(r"\b%s\s*\(" % f, main))
        if n != 1:
            probs.append("main calls %s %d times" % (f, n))
            continue
        i = main.index(f + "(")
        # the SESSION record is found by its arguments (the literals are blanked in the stripped text)
        for before in ("gbp_vstate_probe_run(", "GX_SetDrawDoneCallback(gx_prev_drawdone_cb);", "AUDIO_RegisterDMACallback(NULL);", "keylog_rl = 0;",
                       "session.holds_begun, gbp_vstate_stop_name(res.stop));"):
            k = main.find(before)
            if k < 0 or k > i:
                probs.append("%s is not after %s" % (f, before))
        j = main.find("if (sync_started) {")
        if j < 0 or j < i:
            probs.append("%s is not before (outside) `if (sync_started)`" % f)
        k = main.find("gbp_cartdecl_fmt(")
        if k < 0 or k < i:
            probs.append("%s is not before the declaration" % f)
        seg = main[main.index("gbp_vstate_probe_run("):i]
        if re.search(r"\breturn\b|\bexit\s*\(|\bgoto\b", seg):
            probs.append("a return / exit / goto between the probe and %s: the abort path could skip it" % f)
        depth = seg.count("{") - seg.count("}")
        if depth != 1:
            probs.append("%s is not in a block of its own at main's level (brace depth %d after the probe)" % (f, depth))
    # every formatter call is followed by its ringlog_printf
    if len(re.findall(r'ringlog_printf\(&rl, "", srec\)', main)) != 5:
        probs.append("not five ringlog_printf(&rl, \"%s\", srec) lines")
    return probs


class TheBlockIsWhereTheIssuePutsIt(unittest.TestCase):
    def test_the_real_main(self):
        self.assertEqual(placement_problems(read(MAIN)), [])

    def test_mutants_are_caught(self):
        base = read(MAIN)
        block_start = base.index("    /* ---- Issue #158 (vehicle-0002)")
        block_end = base.index("    }\n", base.index("gbp_startrec_streamselftest(srec")) + len("    }\n")
        block = base[block_start:block_end]
        without = base[:block_start] + base[block_end:]
        mutants = {
            "inside if (sync_started)": without.replace("    if (sync_started) {\n", "    if (sync_started) {\n" + block, 1),
            "before the probe": without.replace("    t_probe_enter = gettime();\n", "    t_probe_enter = gettime();\n" + block, 1),
            "before the draw-done callback is restored": without.replace("    GX_SetDrawDoneCallback(gx_prev_drawdone_cb);\n", block + "    GX_SetDrawDoneCallback(gx_prev_drawdone_cb);\n", 1),
            "called from the pump": base.replace("    input_step();\n    session_step();", "    input_step();\n    { char x[8]; gbp_startrec_streaminv(x, 8, 0u, 0u, 0u, 0u, 0u, 0u, 0); }\n    session_step();", 1),
            "called from the draw-done handler": base.replace("    (void)gbp_vpresent_draw_done(&present);", "    (void)gbp_vpresent_draw_done(&present);\n    { char x[8]; gbp_startrec_startup(x, 8, \"n\", 0, 0, 0u, 0, 0, 0u, 0u); }", 1),
            "a return before it": without.replace("    gx_callback_restored = 1;\n", "    gx_callback_restored = 1;\n    if (!sync_started) return 0;\n", 1).replace(
                "                   (unsigned long)session.holds_begun, gbp_vstate_stop_name(res.stop));\n", "                   (unsigned long)session.holds_begun, gbp_vstate_stop_name(res.stop));\n" + block, 1),
        }
        for name, m in mutants.items():
            self.assertNotEqual(m, base, name)
            self.assertTrue(placement_problems(m), "mutant not caught: %s" % name)


# ------------------------------------------------------------------------------------------------ the post-session record bound
def body_of_block(text, start):
    """the {...} block whose opening brace is the first one at or after `start`"""
    i = text.index("{", start)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    raise ValueError("unbalanced")


def post_session_bound(src):
    """-> (bound, breakdown): the records main() can write to the ringlog after `keylog_rl = 0;`, from the code's own loops and caps"""
    d = defs_of(src)
    main = d["main"]
    tail = main[main.index("keylog_rl = 0;"):]
    site = r"ringlog_printf\(&rl,"
    total_sites = len(re.findall(site, tail))
    under_cap = int(re.search(r"#define GBP_APLAY2_UNDER_CAP\s+(\d+)u", read(os.path.join(ROOT, "src", "audio", "gbp_aplay2.h"))).group(1))
    plans = read(os.path.join(ROOT, "src", "audio", "gbp_v28_plans.h"))
    count = int(re.search(r"GBP_V28_PLAY_GBA = \{\s*GBP_V28_PLAY_GBA_PHASES, (\d+)u,", plans).group(1))
    und = body_of_block(tail, tail.index("for (q = 0u; q < us.recorded; q++)"))
    back = body_of_block(tail, tail.index("for (j = 0u; j < V28_PLAN->count; j++)"))
    final = body_of_block(tail, tail.index("for (;;)"))
    n_und, n_back, n_final = (len(re.findall(site, b)) for b in (und, back, final))
    straight = total_sites - n_und - n_back - n_final
    phase_report = d["v28_phase_report"]
    loop = body_of_block(phase_report, phase_report.index("for (i = 0u; i < V28_PLAN->count; i++)"))
    n_phase = len(re.findall(r"ringlog_printf\(rl,", loop))
    calls_phase = len(re.findall(r"\bv28_phase_report\s*\(&rl\)", tail))
    # the final screen's line is the declaration, written once: inside `if (!decl_locked)`, which sets decl_locked first
    assert n_final == 1 and "decl_locked = 1;" in final and final.index("decl_locked = 1;") < final.index("ringlog_printf(&rl,")
    breakdown = {"straight-line sites": straight, "PLAYUND (<= GBP_APLAY2_UNDER_CAP)": n_und * under_cap,
                 "backstop SYNCPE + SYNCPH (x plan count)": n_back * count, "V28PHC + V28PHD (x plan count)": calls_phase * n_phase * count,
                 "CARTDECL (once)": n_final}
    return sum(breakdown.values()), breakdown


class ThePostSessionRecordsFitTheReserve(unittest.TestCase):
    def test_the_bound_is_under_keylog_tail_reserve(self):
        reserve = int(re.search(r"#define KEYLOG_TAIL_RESERVE (\d+)u", read(MAIN)).group(1))
        self.assertEqual(reserve, 1280, "the reserve is vehicle-0001's, not raised")
        bound, br = post_session_bound(read(MAIN))
        b1, _ = post_session_bound(read(V1_MAIN))
        self.assertEqual(bound - b1, 5, "the five new lines, and nothing else, on top of vehicle-0001's bound: %s" % br)
        self.assertEqual(bound, 92, br)
        self.assertLessEqual(bound, reserve, br)

    def test_a_record_added_in_a_loop_is_counted(self):
        m = read(MAIN).replace("            ringlog_printf(&rl, \"%s\", rec);\n        }\n            gbp_play_under_fmt_sum",
                               "            ringlog_printf(&rl, \"%s\", rec);\n            ringlog_printf(&rl, \"%s\", rec);\n        }\n            gbp_play_under_fmt_sum", 1)
        if m == read(MAIN):
            m = read(MAIN).replace("                ringlog_printf(&rl, \"%s\", rec);\n            }\n", "                ringlog_printf(&rl, \"%s\", rec);\n                ringlog_printf(&rl, \"%s\", rec);\n            }\n", 1)
        self.assertNotEqual(m, read(MAIN))
        self.assertEqual(post_session_bound(m)[0], post_session_bound(read(MAIN))[0] + 64)


# ------------------------------------------------------------------------------------------------ identity, build, Swiss, audit
class TheIdentityAndTheBuild(unittest.TestCase):
    def test_identity(self):
        m = read(MAIN)
        self.assertIn('#define TEST_ID "GBP-PLAY-002"', m, "the same test as vehicle-0001: the build id discriminates")
        self.assertIn('#define OPENGBP_APP_NAME "gbp-play-gba2"', m)
        mk = read(MAKEFILE)
        self.assertIn("APP_NAME   := gbp-play-gba2", mk)
        self.assertIn("BUILD_ID   ?= vehicle-0002", mk)
        self.assertIn("IDENT test=%s app=%s build=%s commit=%s libogc=%s", m)

    def test_dirty_sees_untracked_sources_of_this_poc(self):
        self.assertIn("git -C \"$(CURDIR)\" status --porcelain --untracked-files=normal -- ../../src ../../poc/gbp-play-gba2 ../../tools", read(MAKEFILE))

    def test_no_swiss_row_no_pin_no_export(self):
        tsv = read(os.path.join(ROOT, "tools", "swiss-layout.tsv"))
        self.assertNotIn("gbp-play-gba2", tsv)
        self.assertNotIn("vehicle2", tsv)
        self.assertNotRegex(tsv, r"(?m)^29\t")


class TheMakefileTargets(unittest.TestCase):
    def test_the_targets(self):
        mk = read(os.path.join(ROOT, "Makefile"))
        phony = re.search(r"^\.PHONY:.*$", mk, re.M).group(0) + " "
        for t in ("vehicle2", "vehicle2-audit", "vehicle2-dolphin"):
            self.assertIn(" %s " % t, phony)
        self.assertRegex(mk, r"(?m)^vehicle2:")
        self.assertRegex(mk, r"(?m)^vehicle2-dolphin:")
        self.assertIn("$(eval $(call ISR_COMPARE_TARGET,vehicle2-audit,$(VEHICLE2_OUT)))", mk)
        self.assertIn("$(eval $(call POC_AUDIT_RULE,$(VEHICLE2_OUT),vehicle2))", mk)
        self.assertIn("$(eval $(call ISR_RULE,$(VEHICLE2_OUT),ext,hsp_backend_oneshot_isr_ext,hsp_backend_irq))", mk)
        self.assertIn("$(eval $(call ISR_RULE,$(VEHICLE2_OUT),base,hsp_backend_oneshot_isr,hsp_backend_irq))", mk)
        self.assertIn("make --no-print-directory -C poc/gbp-play-gba2 clean; make --no-print-directory -C poc/gbp-play-gba2", mk)
        self.assertIn('-e GIT_DIRTY="$(VEHICLE2_GIT_DIRTY)"', mk)
        self.assertIn("git status --porcelain --untracked-files=normal -- src poc/gbp-play-gba2 tools", mk)
        self.assertIn("--expect 'OPENGBP-PLAY READY app=gbp-play-gba2 build=vehicle-0002'", mk)
        self.assertIn("'OPENGBP-PLAY RESULT status=abort_inconsistent stop=failure service=0 deliveries=0 restore=1'", mk)
        self.assertNotIn("gbp-play-gba2", re.search(r"^POCS\s*:=.*$", mk, re.M).group(0))
        self.assertIn("$(VEHICLE2_OUT)/gbp-play-gba2.elf: poc/gbp-play-gba2/Makefile", mk)
        self.assertIn("$(IN_CONTAINER) sh tools/audit_listings.sh $(VEHICLE2_OUT) gbp-play-gba2", mk)


class TheAudit(unittest.TestCase):
    def test_the_profile_is_vehicle_plus_the_formatter(self):
        p, v = poc_audit.PROFILES["vehicle2"], poc_audit.PROFILES["vehicle"]
        self.assertEqual(p["required_objects"], v["required_objects"] + ("gbp_startrec.o",))
        self.assertEqual(p["object_may_only_reference"]["gbp_startrec.o"], ("snprintf",))
        for f in FORMATTERS:
            self.assertIn(f, p["elf_required"])
            self.assertIn(f, p["main_must_call"])
            self.assertEqual(p["symbol_callers"][f], {"main": 1})
        for k in v:
            if k not in ("required_objects", "elf_required", "main_must_call", "symbol_callers", "object_may_only_reference"):
                self.assertEqual(p[k], v[k], k)
        for k, val in v["symbol_callers"].items():
            self.assertEqual(p["symbol_callers"][k], val, "vehicle's pinned call counts hold for vehicle-0002: %s" % k)

    def test_profile_vehicle2_on_the_listings(self):
        audit = os.path.join(OUT, "audit")
        if not os.path.isfile(os.path.join(audit, "elf.nm.txt")):
            self.skipTest("%s is not built in this checkout" % "gbp-play-gba2")
        self.assertEqual(poc_audit.audit_dir(audit, "vehicle2")[0], [])
        for other in ("live", "sync"):
            self.assertNotEqual(poc_audit.audit_dir(audit, other)[0], [], "the %s profile must FAIL this image" % other)

    def test_profile_vehicle2_fails_vehicle_0001(self):
        audit = os.path.join(V1_OUT, "audit")
        if not os.path.isfile(os.path.join(audit, "elf.nm.txt")):
            self.skipTest("%s is not built in this checkout" % "gbp-play-gba")
        f = poc_audit.audit_dir(audit, "vehicle2")[0]
        self.assertIn("expected object missing: gbp_startrec.o", f)

    def test_the_handlers_match_GBP_VIDEO_001(self):
        for arm in ("ext", "base"):
            path = os.path.join(OUT, "isr-audit-%s.txt" % arm)
            if not os.path.isfile(path):
                self.skipTest("%s is not built in this checkout" % "gbp-play-gba2")
            ref = os.path.join(ROOT, "build", "poc", "gbp-video-capture-probe", "isr-audit-%s.txt" % arm)
            if not os.path.isfile(ref):
                self.skipTest("%s is not built in this checkout" % "gbp-video-capture-probe")
            self.assertEqual(read(path), read(ref), arm)


if __name__ == "__main__":
    unittest.main()
