"""tests/host/test_v123_records.py -- GitHub Issue #123: the records of the muffling round, against the tools and
against what the records said before it.

What is held here, each checked, not assumed:
  * ON TOP, NEVER REWRITTEN. In EVIDENCE, UNKNOWNS, RESEARCH_METHOD, HARDWARE_TESTS and the DEVLOG, every block of
    c68b44a (origin/main when #123's records were written) -- the preamble, and the text under every heading of
    levels 1 to 4, repeated ids included -- is still there, in order, and still STARTS with its heading and body of
    then; AUDIO.md's table rows grow only inside their cells and its other lines only at their ends. New blocks may
    appear anywhere between the old ones and any block may grow at its end: nothing here asks for whole-file
    equality, and a later Issue's amendment on top passes.
  * THE NEW ENTRIES are GBP-HW-347..350 and U-GBP-047/048, in order after the base's last, with the statuses their
    headings claim; the Orchestrator's withdrawal of the pair premise is quoted verbatim where the records carry it.
  * THE 0.125 s CUSHION IS PROVISIONAL wherever it is recorded: AUDIO.md §6, GBP-HW-343, U-GBP-045, U-GBP-046,
    §V27.20.13 and #121's DEVLOG entry, each dated and naming #123.
  * THE METHOD RULE the round produced is in docs/RESEARCH_METHOD.md, and the comment that credited §V22.4 with the
    one-correction rule is gone from src/audio/gbp_aplay.c.
  * THE FIGURES ARE THE TOOLS'. GBP-HW-347's tone columns and GBP-HW-350's budget are formatted from
    tools/v123frame.py's and tools/v123chain.py's own output, so a record that drifted from the data fails here.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import guards  # noqa: E402
import v123chain  # noqa: E402
import v123frame  # noqa: E402

BASE = "c68b44a2abd7a27a242680068ea310387f2b7df2"     # origin/main when #123's records were written
EV = "docs/research/EVIDENCE.md"
UN = "docs/research/UNKNOWNS.md"
HT = "docs/research/HARDWARE_TESTS.md"
AUDIO = "docs/protocol/AUDIO.md"
METHOD = "docs/RESEARCH_METHOD.md"
DEVLOG = "docs/research/DEVLOG.md"
APLAY_C = "src/audio/gbp_aplay.c"
PROV = "**2026-09-25 (GitHub Issue #123), on top: the adopted cushion is PROVISIONAL.**"
WITHDRAWAL = ("the conclusion held only for the tones, and I generalised it from documentation to a case the "
              "documentation does not cover")
NEW_EV = (("GBP-HW-347", "an AUDIO slice read as eight stride-8 streams"),
          ("GBP-HW-348", "the level's update grid differs by capture"),
          ("GBP-HW-349", "\"at most one correction per chunk\" has no recorded reason"),
          ("GBP-HW-350", "what a native decode would cost the chain"))
NEW_UN = (("U-GBP-047", "are streams A and B of an AUDIO slice the AGB's two output sides"),
          ("U-GBP-048", "why every slice of the tone ROMs holds one pulse per 256 cycles"))


def now(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def then(path):
    b = guards.show(BASE, path)
    return b.decode("utf-8") if isinstance(b, bytes) else b


def flat(s):
    return " ".join(s.split())


def entries(text, head_re):
    """{id: (heading line, body)} for every entry whose heading matches head_re (group 1 the id); a body runs to the
    next such heading."""
    heads = list(re.finditer(head_re, text, re.M))
    out = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out[m.group(1)] = (m.group(0), text[m.end():end])
    return out, [m.group(1) for m in heads]


EV_HEAD = r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) .*$"
UN_HEAD = r"^#{2,3} (U-(?:GBP|ENV)-\d{3}) .*$"


def base_body(body):
    """A base body without the trailing blank lines and entry separator: what must still START the body now."""
    b = body.rstrip("\n")
    if b.endswith("\n---"):
        b = b[:-4].rstrip("\n")
    return b


def blocks(text):
    """[(heading line, body)] in order: the preamble (heading ""), then every heading of levels 1 to 4 with the text
    up to the next such heading."""
    heads = list(re.finditer(r"^#{1,4} .*$", text, re.M))
    out = [("", text[:heads[0].start()] if heads else text)]
    for i, m in enumerate(heads):
        out.append((m.group(0), text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]))
    return out


def walk_on_top(tc, path):
    """Every block of the base, in order, is found now under a heading that starts with its heading, and its body
    now starts with its body of then (less the trailing blank lines and separator). Returns the blocks checked."""
    old, new = blocks(then(path)), blocks(now(path))
    j = 0
    for h0, b0 in old:
        while j < len(new) and not new[j][0].startswith(h0):
            j += 1
        tc.assertLess(j, len(new), "%s: the block %r is gone or its heading changed" % (path, h0[:70]))
        tc.assertTrue(new[j][1].startswith(base_body(b0)),
                      "%s: the text under %r changed above its end" % (path, h0[:70]))
        j += 1
    return len(old)


def section(text, head_re):
    """From a heading to the next heading of the same or a higher level."""
    m = re.search(head_re, text, re.M)
    level = len(m.group(0)) - len(m.group(0).lstrip("#"))
    n = re.search(r"^#{1,%d} " % level, text[m.end():], re.M)
    return text[m.start():m.end() + n.start() if n else len(text)]


class OnTopNeverRewritten(unittest.TestCase):
    def test_every_block_of_then_starts_its_block_now(self):
        for path, least in ((EV, 440), (UN, 50), (METHOD, 25), (HT, 1300), (DEVLOG, 380)):      # the base's: 447 54 26 1397 387
            self.assertGreater(walk_on_top(self, path), least, path)

    def check_new_ids(self, path, head_re, new):
        """The base's ids are still there in order (a subsequence: later Issues may mint ids anywhere, as #27 did in
        its family's section), and #123's come once each, in order, after the base's last."""
        old_ids = [m.group(1) for m in re.finditer(head_re, then(path), re.M)]
        now_ids = [m.group(1) for m in re.finditer(head_re, now(path), re.M)]
        j = 0
        for eid in old_ids:
            while j < len(now_ids) and now_ids[j] != eid:
                j += 1
            self.assertLess(j, len(now_ids), "%s: %s is gone or out of order" % (path, eid))
            j += 1
        last = j - 1                                            # where the base's last id sits now
        at = [now_ids.index(e) for e, _ in new]
        self.assertEqual(at, sorted(at))
        self.assertGreater(at[0], last)
        heads = dict((m.group(1), m.group(0)) for m in re.finditer(head_re, now(path), re.M))
        for eid, lead in new:
            self.assertEqual(now_ids.count(eid), 1, eid)
            self.assertTrue(heads[eid].split(" — ", 1)[1].startswith(lead), eid)

    def test_the_new_evidence_entries(self):
        self.check_new_ids(EV, EV_HEAD, NEW_EV)

    def test_the_new_unknowns(self):
        self.check_new_ids(UN, UN_HEAD, NEW_UN)

    def test_audio_md_rows_grow_only_inside_their_cells(self):
        old, new = then(AUDIO), now(AUDIO)
        # in order: each row of then is found at or after the previous one's place, as a row of the same width whose
        # every cell starts with its cell of then (new rows and new tables of any width may sit between)
        rows = [l.split(" | ") for l in new.splitlines() if l.startswith("| ")]
        n = j = 0
        for line in old.splitlines():
            if not line.startswith("| "):
                continue
            cells = line.split(" | ")
            while j < len(rows) and not (len(rows[j]) == len(cells) and
                                         all(b.startswith(a.rstrip(" |")) for a, b in zip(cells, rows[j]))):
                j += 1
            self.assertLess(j, len(rows), "the row %r is gone or was rewritten" % line[:60])
            j += 1
            n += 1
        self.assertGreater(n, 20)
        # every other line of then still starts a line now, in order
        lines = new.splitlines()
        j = 0
        for line in old.splitlines():
            if not line.strip() or line.startswith("| "):
                continue
            while j < len(lines) and not lines[j].startswith(line):
                j += 1
            self.assertLess(j, len(lines), line[:60])
            j += 1

    def test_the_new_rule_sits_before_the_hardware_test_requests(self):
        m = now(METHOD)
        self.assertLess(m.index("\n### A consequence is not finished"), m.index("\n## Hardware test requests"))


class TheNewEntries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = entries(now(EV), EV_HEAD)[0]
        cls.un = entries(now(UN), UN_HEAD)[0]

    def test_the_statuses_the_headings_claim(self):
        h = dict((e, flat(self.ev[e][0])) for e, _ in NEW_EV)
        self.assertIn("FACT (counted, three captures)", h["GBP-HW-347"])
        self.assertIn("are HYPOTHESES", h["GBP-HW-347"])
        self.assertIn("LEAD against FACT, unresolved", h["GBP-HW-348"])
        self.assertIn("FACT (records and code)", h["GBP-HW-349"])
        self.assertIn("FACT (the measured anchors); INFERENCE (everything native)", h["GBP-HW-350"])

    def test_the_withdrawal_is_quoted_verbatim(self):
        self.assertIn(WITHDRAWAL, flat(self.ev["GBP-HW-348"][1]))
        self.assertIn(WITHDRAWAL, flat(section(now(DEVLOG), r"^## 2026-09-25 — Issue #123: .*$")))

    def test_the_code_each_claim_touches_is_named(self):
        b347 = flat(self.ev["GBP-HW-347"][1])
        self.assertIn("gbp_adec_popcount()", b347)
        self.assertIn("knowingly unchanged", b347)
        b349 = flat(self.ev["GBP-HW-349"][1])
        self.assertIn("A rule with a citation nobody followed back is indistinguishable from a rule with a reason", b349)
        self.assertIn("gbp_aplay_set_corrections(p, k)", b349)
        self.assertIn("No image sets k > 1.", b349)

    def test_the_unknowns_name_their_cheap_tests(self):
        self.assertIn("READS SOUNDBIAS", self.un["U-GBP-048"][1])
        self.assertIn("the Game Boy Player itself raises the resolution", self.un["U-GBP-048"][1])
        self.assertIn("routes a PSG channel to ONE side only", self.un["U-GBP-047"][1])
        for eid in ("U-GBP-012", "U-GBP-043"):
            self.assertIn("**2026-09-25 (GitHub Issue #123), on top.**", self.un[eid][1], eid)


class TheCushionIsProvisional(unittest.TestCase):
    def test_every_record_of_the_adoption_carries_the_note(self):
        ev = entries(now(EV), EV_HEAD)[0]
        un = entries(now(UN), UN_HEAD)[0]
        places = {"GBP-HW-343": ev["GBP-HW-343"][1],
                  "U-GBP-045": un["U-GBP-045"][1],
                  "U-GBP-046": un["U-GBP-046"][1],
                  "§V27.20.13": section(now(HT), r"^#{2,5} §?V27\.20\.13\b.*$"),
                  "#121": section(now(DEVLOG), r"^## 2026-09-25 — Issue #121: .*$")}
        for where, text in places.items():
            self.assertEqual(text.count(PROV), 1, where)
        row = [l for l in now(AUDIO).splitlines() if l.startswith("| The cushion (`TARGET`) |")]
        self.assertEqual(len(row), 1)
        self.assertIn("**Provisional since 2026-09-25 (Issue #123):**", row[0])

    def test_the_note_says_why(self):
        for path in (EV, UN, HT, DEVLOG):
            for m in re.finditer(re.escape(PROV) + r"[^\n]*(?:\n[^\n]+)*", now(path)):
                self.assertIn("a finer decode costs processing, which is latency", flat(m.group(0)), path)


class TheMethodAndTheComment(unittest.TestCase):
    def test_the_rule_is_in_the_method(self):
        s = flat(section(now(METHOD), r"^### A consequence is not finished until the code it touches is named.*$"))
        self.assertIn("(2026-09-25, GitHub Issue #123)", s)
        self.assertIn("the claim is not finished until that code is named in it", s)
        self.assertIn("A rule with a citation nobody followed back is indistinguishable from a rule with a reason.", s)
        m = now(METHOD)
        self.assertLess(m.index("### A consequence is not finished"), m.index("\n## Hardware test requests"))

    def test_the_comment_no_longer_credits_v22_4(self):
        c = now(APLAY_C)
        self.assertNotIn("§V22.4: at most one counted correction per chunk", c)
        self.assertIn("§V22.4 makes a correction a COUNTED event", c)


class TheFiguresAreTheTools(unittest.TestCase):
    def test_gbp_hw_347s_tone_columns(self):
        body = entries(now(EV), EV_HEAD)[0]["GBP-HW-347"][1]
        r = dict((n, v123frame.analyse_capture(*v123frame.CAPTURES[n])) for n in ("RUN33", "RUN34"))

        def grp(n):
            return "{:,}".format(n).replace(",", " ")

        def columns(label):
            line = [l for l in body.splitlines() if l.startswith(label + "  ")]
            self.assertEqual(len(line), 1, label)
            return re.split(r"\s{2,}", line[0].strip())[1:3]          # RUN 33's and RUN 34's
        for label, key in (("slices", "slices"), ("stream 1 == 3 and 5 == 7", "pairs"),
                           ("each odd stream one run of ones", "one_pulse"),
                           ("even stream a superset of its odd", "superset"),
                           ("count == 4 wA + 4 wB + extras", "identity"), ("A == B", "a_eq_b")):
            self.assertEqual(columns(label), [grp(r["RUN33"][key]), grp(r["RUN34"][key])], label)
        self.assertEqual(columns("wA"), ["%d..%d" % (r[n]["wa_min"], r[n]["wa_max"]) for n in ("RUN33", "RUN34")])
        self.assertEqual(columns("the run of ones starts at bit"),
                         ["%s (all)" % list(r[n]["rise"])[0] for n in ("RUN33", "RUN34")])
        self.assertEqual(columns("extras per slice"), ["<= 3", "<= 3"])
        self.assertEqual(columns("control windows (wA, wB)"),
                         ["%s (all)" % ",".join(list(r[n]["rest"])[0].split(",")) for n in ("RUN33", "RUN34")])
        self.assertEqual(columns("side's share of (mid, side) AC"),
                         ["%g" % r[n]["side_share"] for n in ("RUN33", "RUN34")])
        self.assertEqual(columns("even stream 0 > one run of ones"),
                         [grp(r[n]["even_multi_run"]["0"]) for n in ("RUN33", "RUN34")])
        self.assertEqual(columns("even streams 2 / 4 / 6 > one run"),
                         [" / ".join(grp(r[n]["even_multi_run"][e]) for e in "246") for n in ("RUN33", "RUN34")])
        self.assertEqual(columns("flat blocks, (wA, wB) constant"),
                         ["%s of %s" % (grp(r[n]["flat_ab_constant"]), grp(r[n]["flat"])) for n in ("RUN33", "RUN34")])
        for n in ("RUN33", "RUN34"):
            self.assertLessEqual(r[n]["extras_max"], 3)
            self.assertEqual(len(r[n]["rise"]), 1)
            self.assertEqual(len(r[n]["rest"]), 1)

    def test_gbp_hw_350s_budget(self):
        body = flat(entries(now(EV), EV_HEAD)[0]["GBP-HW-350"][0] + entries(now(EV), EV_HEAD)[0]["GBP-HW-350"][1])
        a = v123chain.analyse()
        p, m = a["production_today"], a["model"]
        n16, n32 = m["native"]["65536_N16_ch2"], m["native"]["65536_N32_ch2"]

        def grp(x):
            return "{:,}".format(int(round(x))).replace(",", " ")
        want = ["%.1f ticks a push" % p["per_push"], "%s a chunk" % grp(p["chunk_8push"]),
                "%.2f %% of the CPU" % (100 * p["cpu_share"]),
                "%s ticks a chunk, %.2f %% of the CPU" % (grp(n16["ticks"]), 100 * n16["cpu"]),
                "%s ticks, %.2f %%" % (grp(n32["ticks"]), 100 * n32["cpu"]),
                "%d calls, a nominal refill of ~%.1f ms, AHEAD 1 / 2 margin %.1f / %.1f ms"
                % (n16["calls_at_todays_length"], n16["refill_ms"], n16["margin_ms"]["1"], n16["margin_ms"]["2"]),
                "%d calls, ~%.1f ms, %.1f / %.1f ms"
                % (n32["calls_at_todays_length"], n32["refill_ms"], n32["margin_ms"]["1"], n32["margin_ms"]["2"]),
                "(today: 16 calls, ~%.1f ms)" % m["today_refill_ms"],
                "16 taps: scaled ~%.1f ms, margin %.1f / %.1f ms; additive ~%.1f ms, %.1f / %.1f ms"
                % tuple(x for f in ("worst_scaled", "worst_additive") for x in
                        (n16["refill_forms_ms"][f], n16["margin_forms_ms"][f]["1"], n16["margin_forms_ms"][f]["2"])),
                "32 taps: scaled ~%.1f ms, margin %.1f / %.1f ms; additive ~%.1f ms, %.1f / %.1f ms"
                % tuple(x for f in ("worst_scaled", "worst_additive") for x in
                        (n32["refill_forms_ms"][f], n32["margin_forms_ms"][f]["1"], n32["margin_forms_ms"][f]["2"])),
                "today: scaled ~%.1f ms, additive ~%.1f ms" % (m["today_refill_forms_ms"]["worst_scaled"],
                                                              m["today_refill_forms_ms"]["worst_additive"]),
                "(6.12 ms against a nominal 4.23: x %.3f, + %.2f ms)" % (m["refill_basis"]["ratio_max"],
                                                                      m["refill_basis"]["excess_max_ms"]),
                "margin of %.1f / %.1f ms on the nominal refill but %.1f / %.1f ms on the largest refill RUN 40 measured"
                % (n16["margin_ms"]["1"], n32["margin_ms"]["1"], n16["margin_forms_ms"]["worst_scaled"]["1"],
                   n32["margin_forms_ms"]["worst_scaled"]["1"]),
                "calibration %.3f" % m["calibration"],
                "%s a block today (the popcount, 4 a byte); %s per slice per stream"
                % (grp(m["decode_instr_per_block"]["today"]), grp(m["decode_instr_per_block"]["per_channel_slice"])),
                "%s today; %s stereo per slice" % (grp(m["values_per_s"]["today"]),
                                                  grp(m["values_per_s"]["native_stereo"]))]
        f16 = a["filters"]["65536_N16_b5.65"]
        want.append("16 taps: %.1f dB rejection folding into 0..5 256 Hz, %.3f ms delay (today %.3f ms)"
                    % (f16["fp"]["5256"][1], f16["delay_ms"], a["filters"]["today_4096_N16"]["delay_ms"]))
        for w in want:
            self.assertIn(w, body)


if __name__ == "__main__":
    unittest.main()
