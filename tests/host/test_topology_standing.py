"""
tests/host/test_topology_standing.py — GitHub Issue #35 (2026-09-21): the topology
the Operator declared for RUN 16 / 17 / 18 after their ingestion, and the two
STANDING declarations.

Pinned: §V7.4.2 carries BBA PRESENT / Ethernet DISCONNECTED and the display chain
UNCHANGED as OPERATOR DECLARATIONS with his literal words, and KEEPS the history
(recorded as absent at ingestion, not inferred; declared afterwards, by this
route, under this Issue); the two standing declarations are recorded with their
stated duration, cited by future pre-registrations, never a licence to infer,
with the INCONCLUSIVE-on-that-item rule beside them; the per-run list reduces to
the cartridge / boot screen and the controller; §V7.4.4's TOPOLOGY reads PASS
with the history; the three struct fixtures' topology block carries the same
and nothing else in them moved; GBP-HW-266 has the dated addendum and no id was
minted; HANDOFF's "Do not rediscover" row and a do-not-assume bullet carry the
standing part; §V7.1–§V7.3 and §V7.4's results are the bytes of aaee492;
nothing under the forbidden paths moved.
"""
import json
import os
import re
import subprocess
import unittest

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FX = os.path.join(ROOT, "captures", "fixtures")
P = "hw-gamecube-gbp-2026-09-21-"
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
README = os.path.join(ROOT, "captures", "README.md")
BASE_COMMIT = "aaee492"     # origin/main before Issue #35
W_BBA = "BBA como sempre (presente mas nao conectado no cabo)"
W_CHAIN = "video inalterado e ira permanecer assim ate que eu anuncie o contrario"
W_BBA_STANDING = "BBA também permanecera presente e sem cabo, ate que seja solicitado para remover ou conectar o cabo"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "")


def git_show(path, commit=BASE_COMMIT):
    """Issue #83 (B): an absent COMMIT skips; a path missing from a commit that IS
    here fails, because that is a moved file and not an absent history."""
    return guards.show(commit, path)


def v74(text=None):
    t = read(HW) if text is None else text
    i = t.index("### V7.4 ")
    j = t.find("### V7.5 ", i)
    return t[i:] if j < 0 else t[i:j]


def part(n, text=None):
    t = v74(text)
    i = t.index("#### V7.4.%d " % n)
    j = t.find("#### V7.4.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


def struct(run):
    with open(os.path.join(FX, P + "idxcap-run%d-struct.json" % run), encoding="utf-8") as f:
        return json.load(f)


class TheDeclarationIsRecordedWithItsHistory(unittest.TestCase):
    def test_v7_4_2_carries_the_declared_items_the_words_and_the_history(self):
        p = plain(part(2))
        for tok in ("BBA / ETHERNET PRESENT / DISCONNECTED -- his words: \"%s\"" % W_BBA, "DISPLAY CHAIN UNCHANGED", "his words: \"video inalterado\"",
                    "OPERATOR DECLARATION, given AFTER the ingestion and relayed by the Orchestrator (Issue #35, 2026-09-21)",
                    "THE HISTORY, KEPT: at ingestion (Issue #33) no per-run declaration of these two items existed",
                    "RECORDED AS ABSENT, NOT INFERRED", "the declaration above replaced that note under Issue #35",
                    "TOPOLOGY only; nothing about the display is claimed; the join reads the FRAMES, not the screen"):
            self.assertIn(tok, p, tok)
        self.assertIn("what was not declared at ingestion, and the declaration that followed (Issue #35)", part(2).splitlines()[0])
        self.assertEqual(part(2).count("DECLARED\n"), 2, "the two items are marked DECLARED, in the style of §V7.2.2")

    def test_the_standing_declarations_have_their_words_their_duration_and_their_limits(self):
        p = plain(part(2))
        for tok in ("STANDING Two of these are STANDING declarations -- operator declarations WITH A STATED DURATION, in his words: DECLARATIONS display chain",
                    "display chain \"%s\"" % W_CHAIN, "BBA \"%s\"" % W_BBA_STANDING,
                    "They hold until he announces a change, like the hardware inventory (Issue #25)",
                    "a future pre-registration CITES them instead of asking", "NOT a licence to infer", "do NOT make the topology \"known\"",
                    "stays DECLARED, by him, until he says otherwise", "that run is INCONCLUSIVE on that item exactly as V7.1.4 says",
                    "What still MUST be declared per run: the cartridge and its boot screen, and the controller",
                    "has used both (RUN 14 / 15 / 17 the generic, RUN 16 / 18 the original), so it is never assumed"):
            self.assertIn(tok, p, tok)

    def test_the_topology_gate_reads_pass_with_the_history_and_the_record_row_follows(self):
        g = plain(part(4))
        for tok in ("TOPOLOGY PASS for the items declared", "BBA PRESENT / Ethernet DISCONNECTED and the display chain UNCHANGED, declared by the Operator after the ingestion (Issue #35",
                    "HISTORY: at ingestion these two were NOT DECLARED, the line read PASS* and they were recorded as absent, not inferred",
                    "The gate text is unchanged; the reading is stated here"):
            self.assertIn(tok, g, tok)
        self.assertNotIn("TOPOLOGY PASS* for", g)
        r = plain(part(10))
        self.assertIn("BBA / Ethernet / chain (declared) BBA PRESENT, no Ethernet cable; display chain UNCHANGED -- declared after the ingestion (Issue #35; STANDING, V7.4.2); at ingestion NOT DECLARED, recorded as absent, not inferred", r)
        intro = plain(v74().split("#### V7.4.1 ")[0])
        self.assertIn("were NOT declared for these runs at ingestion and were recorded as absent -- the Operator declared them afterwards, the same day, and the declaration replaced that note under Issue #35 with the history kept", intro.replace("—", "--"))
        self.assertIn("the display chain (declared unchanged under Issue #35; not part of the join)", plain(part(12)))

    def test_the_fixtures_carry_the_declaration_and_nothing_else_in_them_moved(self):
        for run in (16, 17, 18):
            with self.subTest(run=run):
                s = struct(run)
                tp = s["topology_declared_by_operator"]
                self.assertTrue(tp["bba_ethernet"].startswith("PRESENT / DISCONNECTED -- DECLARED by the Operator after the ingestion (Issue #35, 2026-09-21)"))
                self.assertIn(W_BBA, tp["bba_ethernet"])
                self.assertTrue(tp["display_chain"].startswith("UNCHANGED -- the chain of §V7.1.4 / §V6.24.3"))
                self.assertIn("DECLARED by the Operator after the ingestion (Issue #35", tp["display_chain"])
                sd = tp["standing_declarations"]
                self.assertEqual((sd["display_chain"]["words"], sd["bba"]["words"]), (W_CHAIN, W_BBA_STANDING))
                for tok in ("WITH A STATED DURATION", "never a licence to infer", "INCONCLUSIVE on that item", "CITE these instead of asking"):
                    self.assertIn(tok, sd["what"], tok)
                self.assertIn("the cartridge and its boot screen; the controller", sd["what_still_varies_per_run"])
                self.assertIn("RECORDED AS ABSENT, NOT INFERRED", tp["declaration_history"])
                self.assertIn("replaced that note under Issue #35", tp["declaration_history"])
                self.assertIn("HISTORY: at ingestion these two were NOT DECLARED", s["verdicts"]["shared_gates"]["TOPOLOGY"])
                self.assertIn("regenerated_for_issue_35", s["tools"])
                old = git_show("captures/fixtures/" + P + "idxcap-run%d-struct.json" % run)  # Issue #83 (B)
                o = json.loads(old)
                for k in ("bba_ethernet", "display_chain"):
                    self.assertTrue(o["topology_declared_by_operator"][k].startswith("NOT DECLARED"), "the base recorded the item as absent")
                o["topology_declared_by_operator"] = s["topology_declared_by_operator"]
                o["verdicts"]["shared_gates"]["TOPOLOGY"] = s["verdicts"]["shared_gates"]["TOPOLOGY"]
                o["tools"]["regenerated_for_issue_35"] = s["tools"]["regenerated_for_issue_35"]
                self.assertEqual(o, s, "every other section of the struct fixture is unchanged (the join, the verdicts, the records)")
        # the RUN 14 / RUN 15 records are history and untouched
        for run in (14, 15):
            self.assertIn("what still varies and must be declared per run: BBA and Ethernet state, the display chain, the cartridge and its boot screen, the controller",
                          struct(run)["topology_declared_by_operator"]["standing_note_for_future_pre_registrations"])


class TheRecordsAndTheFreeze(unittest.TestCase):
    def test_the_evidence_row_has_the_dated_addendum_and_no_id_was_minted(self):
        ev = read(EVIDENCE)
        b266 = ev[ev.index("### GBP-HW-266 "):ev.index("### GBP-HW-267 ")]
        self.assertIn("recorded as ABSENT,\nnot inferred", b266, "the history kept")
        self.assertIn("**2026-09-21, Issue #35 (declared after the ingestion; the note above kept as\nhistory):**", b266)
        for tok in (W_BBA, W_CHAIN, W_BBA_STANDING, "WITH A STATED DURATION", "NOT a licence to infer", "INCONCLUSIVE on that item", "no new id"):
            self.assertIn(tok, plain(b266), tok)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 321)   # 272: Issue #46 (the CONTROL bit 0x02 split, FACT for the split / HYPOTHESIS for the cause)   # 285…294: Issue #62 (RUN 30 ingested, §V8.13)   # 295…300: Issue #67 (RUN 31 ingested, §V9.15); 301…302: #67's validation (the rate/layout split, U-GBP-039's probe); 303…307: #72, RUN 32; 308…311: #78, RUN 33 and RUN 34; 312: #79, duty()'s mechanism; 313: #80, the H-PWM decode; 314…316: #82, the block structure and the drain (§V18); 317: #84, the start-up stall invariance; 318: #90, RUN 36; 319…321: #91, RUN 37 (§V19.11)   # 318: Issue #90 (RUN 36 ingested, the output path heard: §V21.9)   # 319…321: Issue #91 (RUN 37 ingested: D1, D2, QUESTION A; §V19.14)

    def test_the_handoff_carries_the_standing_declarations_where_a_pre_registration_will_meet_them(self):
        h = read(HANDOFF)
        row = [l for l in h.splitlines() if l.startswith("| **The console and the Game Boy Player are the same two units in every run of this project**")]
        self.assertEqual(len(row), 1)
        r = row[0]
        for tok in ("Two STANDING declarations (2026-09-21, Issue #35", W_CHAIN, W_BBA_STANDING, "WITH A STATED DURATION", "never a licence to infer",
                    "do not make the topology \"known\"", "INCONCLUSIVE on that item (§V7.1.4)",
                    "What still varies and MUST be declared per run: the cartridge and its boot screen, and the controller", "so it is never assumed",
                    "GBP-HW-261, GBP-HW-266", "§V7.2.2, §V7.4.2"):
            self.assertIn(tok, r, tok)
        self.assertNotIn("MUST be declared per run: BBA and Ethernet state", r)
        p = plain(h)
        for tok in ("- That the topology is known. It is DECLARED", "issue 35",   # the trail's `next` moved on with Issue #34
                    "at ingestion recorded absent, not inferred; history kept"):
            self.assertIn(tok, p, tok)
        self.assertIn("Issue #35", plain(read(README)))
        d = read(DEVLOG)
        # Issue #46 (2026-09-22): bounded to the Issue #35 entry. It ran to END OF FILE, so the sentinel below
        # fired on GBP-HW-272, minted by a later checkpoint and named in a later entry.
        e = d[d.rindex("## 2026-09-21 — Issue #35"):]
        e = e[:e.index("\n## ", 1)] if "\n## " in e[1:] else e
        for tok in (W_CHAIN, "WITH A STATED DURATION", "never a licence to infer", "No hardware; no code", "Issue #34 (the acceptance run) not started"):
            self.assertIn(tok, plain(e), tok)
        self.assertNotRegex(e, r"GBP-HW-27[2-9]")

    def test_v7_1_to_v7_3_and_v7_4s_results_are_the_bytes_of_the_base(self):
        old = git_show("docs/research/HARDWARE_TESTS.md")  # Issue #83 (B): absent COMMIT skips, absent PATH fails
        new = read(HW)
        self.assertEqual(new[new.index("### V7.1 "):new.index("### V7.4 ")], old[old.index("### V7.1 "):old.index("### V7.4 ")])
        self.assertEqual(old[:old.index("\n## V7 ")], new[:new.index("\n## V7 ")])
        old_head = [l for l in old.splitlines() if l.startswith("## V7 ")][0]
        new_head = [l for l in new.splitlines() if l.startswith("## V7 ")][0]
        self.assertTrue(new_head.startswith(old_head), "the chapter heading only grows (Issue #34 appended the RUN 19 / RUN 20 clause)")
        # the results: every part of §V7.4 except the ones the Issue names (the intro, 2, 4, 10, 11, 12) is byte-identical
        for n in (1, 3, 5, 6, 7, 8, 9):
            self.assertEqual(part(n, new), part(n, old), "V7.4.%d untouched" % n)
        self.assertEqual(part(11, new).replace("declared under Issue #35 with that history", "").count("recorded as absent"), 1)

    def test_nothing_under_the_forbidden_paths_changed(self):
        if not guards.base_available(BASE_COMMIT):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE_COMMIT)
        changed = guards.changed_since(BASE_COMMIT, ["src", "poc", "tools", "Makefile", "stimulus", "docs/protocol", "docs/hardware"])   # Issue #29: tracked AND untracked, one implementation
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
        # Issue #48 (2026-09-22) promoted the cartridge-sensing bits into the consolidated hardware pages:
        # the rows carried the references' usage only while the Keypad rows beside them carried their
        # hardware history, so they understated 36 runs. Statuses were COPIED from EVIDENCE, none changed.
        changed = changed - {"docs/hardware/GBS-DOL.md", "docs/hardware/ARCHITECTURE.md"}
        # Issue #46 (2026-09-22): the REGISTERS.md row for CONTROL bit 0x02 now separates the references' USAGE (C)
        # from this project's own measurement (F) from the causal reading (H), citing GBP-HW-272
        changed = changed - {"docs/protocol/REGISTERS.md"}
        # Issue #39 (2026-09-21) built the playable image: the session end in the service-path module (tests/host/test_play_image.py pins it), a new POC, its audit profile and its Swiss slot
        # Issue #95 (2026-09-24) promoted Phase 6 into docs/protocol/AUDIO.md (new), indexed it in README.md,
        # and corrected the stale audio rows its reconciliation sweep found (REGISTERS.md, INITIALIZATION.md,
        # ARCHITECTURE.md, GBS-DOL.md) as wording that cites EVIDENCE. Documentation only; no status moved.
        changed = changed - {"docs/protocol/AUDIO.md", "docs/protocol/README.md", "docs/protocol/INITIALIZATION.md",
                             "docs/protocol/REGISTERS.md", "docs/hardware/ARCHITECTURE.md", "docs/hardware/GBS-DOL.md"}
        self.assertTrue(changed <= {"src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_session.c", "src/gbp/gbp_session.h", "poc/gbp-play-session/Makefile", "poc/gbp-play-session/source/main.c", "tools/poc_audit.py", "tools/swiss-layout.tsv", "Makefile"}, "changed against the base: " + " ".join(sorted(changed)))
        changed2 = guards.changed_since(BASE_COMMIT, ["captures/fixtures"])   # Issue #29: tracked AND untracked, one implementation
        # Issue #81 (2026-09-23): RUN 33 / RUN 34's raw audio sidecars, versioned as replay fixtures
        # (captures/README.md); the first fixtures since RUN 18, and they touch none of the above.
        changed2 = changed2 - {"captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz",
                               "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz",
                               # Issue #90: RUN 36's console log, byte for byte (§V21.9)
                               "captures/fixtures/hw-gamecube-gbp-2026-09-23-aout-0002-run36.log",
                               # Issue #91: RUN 37's console log, byte for byte (§V19.14)
                               "captures/fixtures/hw-gamecube-gbp-2026-09-23-drain-0001-run37.log"}
        self.assertTrue(changed2 <= {"captures/fixtures/" + P + "idxcap-run%d-struct.json" % n for n in (16, 17, 18)}, " ".join(sorted(changed2)))
        # the guard's blind spot (Issue #29): untracked files are invisible to git diff -- none may exist under these paths


if __name__ == "__main__":
    unittest.main()
