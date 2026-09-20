"""
tests/host/test_coordtime.py — the coord-0001 cycle model (tools/coordtime.py,
HARDWARE_TESTS §V6.22, GBP-VID-034; GitHub Issue #12).

Three layers, each pinned: (1) the interpreter's ARM semantics and the GBATEK
cycle rules on hand-assembled sequences; (2) the frozen ROM copy in
captures/fixtures (byte-identical to the RUN 12 stimulus, 90343b64…) and what
the model computes from it — PUBLISH calibrated against the three hardware
VMARGIN values of RUN 12, the entry budget, the cost of every frame class, the
M--M verdict for the four RUN 12 entries and the access counts that explain
the ordering; (3) the versioned RUN 12 structural fixture, read back to show
that the two duplicates sit exactly where the model puts the two missed
VBlanks (479 -> 479 -> 480, 1919 -> 1919 -> 1920) and nowhere else. Nothing
here touches hardware, the stimulus source or a frozen analyzer.
"""
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import coordtime as ct  # noqa: E402

ROM = os.path.join(ROOT, "captures", "fixtures", "stimulus-coord-0001-canonical.gba")
STRUCT = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-20-idxcap-run12-struct.json")
_C = {}


def rom():
    if "rom" not in _C:
        _C["rom"] = ct.load_rom(ROM)
    return _C["rom"]


def res():
    if "res" not in _C:
        _C["res"] = ct.analyse(rom())
        _C["b"] = ct.budget(_C["res"])
    return _C["res"], _C["b"]


def struct():
    if "s" not in _C:
        with open(STRUCT) as f:
            _C["s"] = json.load(f)
    return _C["s"]


def mem(rom_bytes=None, **timing):
    return ct.Mem(rom_bytes if rom_bytes is not None else bytes(0x1000), ct.Timing(**timing))


def run(m, addr, words, **regs):
    for i, w in enumerate(words):
        m.write(addr + 4 * i, 32, w, count=False)
    c = ct.CPU(m)
    for k, v in regs.items():
        c.r[int(k[1:])] = v
    c.r[14], c.r[15] = ct.SENTINEL, addr
    c.run()
    return c


class TheInterpreterAndItsCycleRules(unittest.TestCase):
    def test_alu_ldr_str_and_the_ewram_costs(self):
        m = mem()
        m.write(0x02000010, 32, 0xDEADBEEF)
        c = run(m, 0x03000000, [0xE0810002, 0xE2503001, 0xE5954000, 0xE1C640B0, 0xE12FFF1E], r1=5, r2=7, r5=0x02000010, r6=0x02000020)
        self.assertEqual((c.r[0], c.r[3], c.r[4], m.read(0x02000020, 16)), (12, 11, 0xDEADBEEF, 0xBEEF))
        self.assertEqual(c.cycles, 1 + 1 + (1 + 6 + 1) + (3 + 1))      # ALU 1S; LDR 1S+1N(EWRAM32)+1I; STRH 1N(EWRAM16)+1N(code)

    def test_conditional_false_costs_one_s_and_a_taken_branch_three(self):
        c = run(mem(), 0x03000100, [0xE3500000, 0x03A01001, 0x13A01002, 0xEA000000, 0xE3A02007, 0xE12FFF1E], r0=0)
        self.assertEqual((c.r[1], c.r[2], c.cycles), (1, 0, 1 + 1 + 1 + 3))

    def test_push_pop_costs(self):
        c = run(mem(), 0x03000200, [0xE92D4030, 0xE8BD4030, 0xE12FFF1E], r4=9, r5=8, r13=0x03007F00)
        self.assertEqual((c.r[13], c.cycles), (0x03007F00, (2 + 2) + (3 + 1 + 1)))

    def test_a_rom_byte_read_from_iwram_code_costs_the_waitcnt_n_access(self):
        r = bytearray(0x1000)
        r[0x758] = 0x5B
        c = run(mem(bytes(r)), 0x03000300, [0xE59F3008, 0xE5D33000, 0xE12FFF1E, 0, 0x08000758])
        self.assertEqual((c.r[3], c.cycles), (0x5B, (1 + 1 + 1) + (1 + 4 + 1)))
        c = run(mem(bytes(r), rom_n=5), 0x03000300, [0xE59F3008, 0xE5D33000, 0xE12FFF1E, 0, 0x08000758])
        self.assertEqual(c.cycles, (1 + 1 + 1) + (1 + 5 + 1))

    def test_shifter_carry_and_register_shift_internal_cycle(self):
        c = run(mem(), 0x03000400, [0xE1B000A1, 0xE12FFF1E], r1=3)          # movs r0, r1, lsr #1
        self.assertEqual((c.r[0], c.C, c.cycles), (1, 1, 1))
        c = run(mem(), 0x03000400, [0xE1A00231, 0xE12FFF1E], r1=8, r2=2)    # mov r0, r1, lsr r2 : 1S + 1I
        self.assertEqual((c.r[0], c.cycles), (2, 2))

    def test_dma_costs_per_region(self):
        m = mem()
        m.write(0x040000D4, 32, 0x03000970)
        m.write(0x040000D8, 32, 0x06000000)
        m.write(0x040000DC, 32, 0x8400001C)
        self.assertEqual(m.dma_cycles, 1 + 2 + 27 * (1 + 2) + 2)             # 28 x 32-bit, IWRAM -> VRAM
        m.write(0x040000D4, 32, 0x02000000)
        m.write(0x040000DC, 32, 0x84000019)
        self.assertEqual(m.dma_cycles, 86 + (6 + 2 + 24 * (6 + 2) + 2))      # 25 x 32-bit, EWRAM -> VRAM

    def test_rom_code_fetch_costs_are_bounded_by_the_two_prefetch_assumptions(self):
        t = ct.Timing()
        self.assertEqual((t.code(0x03000000, True), t.code(0x03000000, False)), (1, 1))
        self.assertEqual((t.code(0x08000000, True), t.code(0x08000000, False)), (4, 6))
        self.assertEqual(ct.Timing(rom_code_s=2).code(0x08000000, True), 2)


class TheFrozenRom(unittest.TestCase):
    def test_the_fixture_is_the_run_12_stimulus_byte_for_byte(self):
        with open(ROM, "rb") as f:
            data = f.read()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (ct.ROM_SIZE, ct.ROM_SHA256))
        self.assertEqual(struct()["stimulus"]["canonical_sha256"], ct.ROM_SHA256)
        with self.assertRaises(ValueError):
            ct.load_rom(STRUCT)

    def test_the_iwram_image_is_where_the_frozen_link_put_it(self):
        off, img = ct.iwram_image(rom())
        self.assertEqual((off, len(img)), (0x768, 0x630))                  # LMA 0x08000768, .iwram 1584 B
        self.assertEqual(img[:8], ct.PREPARE_HEAD)
        self.assertEqual(img[0x47C:0x47C + 8], ct.PUBLISH_HEAD)
        self.assertEqual(rom()[0x758:0x762], bytes([0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F]))   # seg_of_digit in ROM


class ThePublishCalibration(unittest.TestCase):
    """The DMA path shares the memory timing with PREPARE; RUN 12 measured where
    three kinds of PUBLISH ended (VMARGIN 54 / 39 / 38-39)."""

    def test_the_three_hardware_vmargins_are_reproduced(self):
        r, _ = res()
        p = r["publish"]
        end = {k: ct.VBLANK_FIRST + v["cycles"] / ct.LINE_CYCLES for k, v in p.items()}
        self.assertEqual(p["ordinary (strips only)"]["cycles"], 16799)
        self.assertEqual(p["entry (strips + digit paint + squares)"]["cycles"], 34654)
        self.assertEqual(p["exit (strips + digit erase + squares erase)"]["cycles"], 35657)
        self.assertEqual(227 - int(end["ordinary (strips only)"]), 54)
        self.assertEqual(227 - int(end["entry (strips + digit paint + squares)"]), 39)
        self.assertAlmostEqual(end["exit (strips + digit erase + squares erase)"], 188.94, places=2)   # the 188 / 189 knife-edge
        self.assertEqual((p["ordinary (strips only)"]["dma_count"], p["ordinary (strips only)"]["dma_units"]), (160, 4480))
        self.assertEqual((p["entry (strips + digit paint + squares)"]["dma_count"], p["entry (strips + digit paint + squares)"]["dma_units"]), (248, 6680))

    def test_only_two_ewram_wait_states_reproduce_the_entry_vmargin(self):
        for ws, expect in ((1, 43), (2, 39), (3, 36)):
            m = ct.Model(rom(), ct.Timing(ewram_ws=ws))
            self.assertEqual(227 - int(ct.VBLANK_FIRST + m.publish(1, 1)["cycles"] / ct.LINE_CYCLES), expect, ws)


class ThePrepareModel(unittest.TestCase):
    def test_the_entry_budget_and_its_declared_band(self):
        _, b = res()
        self.assertEqual(b["frame_cycles"], 280896)
        self.assertEqual((b["publish"], b["tail"], b["react"], b["poll_iteration"]), (16799, 228, 6, 24))
        self.assertEqual((b["min"], b["max"]), (263839, 263863))
        r_pf = ct.analyse(rom(), ct.Timing(rom_code_s=2))
        b_pf = ct.budget(r_pf)
        self.assertEqual((b_pf["min"], b_pf["max"]), (263937, 263953))
        self.assertLessEqual(b_pf["max"] - b["min"], 120, "the whole declared uncertainty of the budget is about a tenth of a line")

    def test_the_tail_wraps_the_schedule_exactly_once_on_an_entry_frame(self):
        r, _ = res()
        t = r["tail"]["entry (schedule wrap)"]
        self.assertEqual((t["phase_after"], t["k_after"]), (0, 1))
        self.assertEqual(r["tail"]["ordinary"]["phase_after"], 201)

    def test_every_frame_class_sets_the_flags_publish_will_read(self):
        r, _ = res()
        p = r["prepare"]
        self.assertEqual((p["ordinary (k>=1, 40<phase<480)"]["op_digit"], p["ordinary (k>=1, 40<phase<480)"]["op_sq"]), (0, 0))
        self.assertEqual((p["steady (phase 1)"]["op_digit"], p["steady (phase 1)"]["op_sq"]), (0, 1))
        self.assertEqual((p["exit (phase 40)"]["op_digit"], p["exit (phase 40)"]["op_sq"]), (2, 2))
        for d in range(1, 10):
            self.assertEqual((p["entry digit %d" % d]["op_digit"], p["entry digit %d" % d]["op_sq"]), (1, 1), d)

    def test_the_four_run_12_entries_read_m_dash_dash_m(self):
        r, b = res()
        e = {d: r["prepare"]["entry digit %d" % d]["cycles"] for d in range(1, 10)}
        self.assertEqual((e[1], e[2], e[3], e[4]), (287787, 261723, 260043, 287179))
        self.assertGreater(e[1], b["max"])
        self.assertGreater(e[4], b["max"])
        self.assertLess(e[2], b["min"])
        self.assertLess(e[3], b["min"])
        self.assertGreaterEqual(e[4] - b["max"], 23000)          # the duplicates: over by a fifth of a frame's VBlank-to-VBlank slack
        self.assertGreaterEqual(b["min"] - e[2], 2000)           # the non-duplicates: under by 0.8 % / 1.5 % -- the stated weakest margin
        self.assertGreaterEqual(b["min"] - e[3], 3700)
        self.assertEqual(e[5], e[2], "digit 5 mirrors digit 2's segment pattern cost")
        for d in (6, 7, 8, 9):
            self.assertGreater(e[d], b["max"], d)                  # falsifiable for a future run that retains k >= 6

    def test_no_other_frame_class_comes_within_a_third_of_the_budget(self):
        r, b = res()
        for name in ("ordinary (k>=1, 40<phase<480)", "pre-glyph (k=0)", "steady (phase 1)", "steady (phase 39)", "exit (phase 40)"):
            self.assertLess(r["prepare"][name]["cycles"], b["min"] // 3, name)
        self.assertEqual(r["prepare"]["ordinary (k>=1, 40<phase<480)"]["cycles"], 77917)

    def test_the_access_counts_explain_the_ordering(self):
        r, _ = res()
        a = {d: r["prepare"]["entry digit %d" % d]["access"] for d in (1, 2, 3, 4)}
        for d in (1, 2, 3, 4):
            self.assertEqual((a[d]["rom_r8"], a[d]["ewram_w16"]), (3840, 4000), d)              # one ROM byte per glyph pixel; every row word written
            self.assertEqual(a[d]["ewram_r16"], ct.unlit_pixels(d) + 160 + 400, d)                # unlit pixels + the guard columns + the (all unlit) squares
        self.assertEqual([ct.unlit_pixels(d) for d in (1, 2, 3, 4)], [3200, 2240, 2240, 2592])

    def test_the_sensitivity_sweep_keeps_the_pattern_at_the_calibrated_terms(self):
        rows = ct.sensitivity(rom(), ws_values=(2,), rom_n_values=(3, 4))
        for row in rows:
            self.assertTrue(row["calibrated"])
            self.assertEqual(row["pattern"], "M--M")
        row5 = ct.sensitivity(rom(), ws_values=(2,), rom_n_values=(5,))[0]
        self.assertEqual(row5["pattern"], "MMMM", "one extra ROM wait state per pixel would have duplicated every entry -- RUN 12 did not")


class TheRun12FixtureAgreesWithTheModel(unittest.TestCase):
    def test_duplicates_sit_exactly_before_the_two_predicted_entries_and_nowhere_else(self):
        recs = struct()["records"]
        ids = [x["frame_id"] for x in recs]
        dup = [(recs[i]["frame_index"], ids[i]) for i in range(len(ids) - 1) if ids[i + 1] == ids[i]]
        self.assertEqual(dup, [(761, 479), (2202, 1919)])
        r, b = res()
        predicted = [k for k in (1, 2, 3, 4) if r["prepare"]["entry digit %d" % k]["cycles"] >= b["max"]]
        self.assertEqual([480 * k - 1 for k in predicted], [479, 1919])
        for k in (1, 2, 3, 4):
            i = ids.index(480 * k)
            self.assertEqual(ids[i - 2:i + 2], [480 * k - 2, 480 * k - 1, 480 * k, 480 * k + 1] if k in (2, 3) else [480 * k - 1, 480 * k - 1, 480 * k, 480 * k + 1], k)

    def test_the_status_transitions_are_the_publish_classes_the_model_costs(self):
        recs = struct()["records"]
        trans = [(x["frame_id"], recs[i - 1]["status"], x["status"]) for i, x in enumerate(recs) if i and x["status"] != recs[i - 1]["status"]]
        self.assertEqual(trans, [(481, 0x36, 0x27), (1001, 0x27, 0x26)])   # after publish(480) = entry paint; after publish(1000) = exit erase
        self.assertTrue(all((x["status"] & 0x80) == 0 for x in recs))

    def test_fault_cannot_see_a_prepare_side_miss(self):
        """RQ2: the latch brackets publish_frame only (vc0 is read after both wait
        loops), so the miss leaves STATUS untouched -- both duplicate records carry
        the same STATUS as their neighbours, FAULT clear."""
        recs = {x["frame_index"]: x for x in struct()["records"]}
        self.assertEqual((recs[761]["status"], recs[762]["status"], recs[763]["status"]), (0x36, 0x36, 0x36))
        self.assertEqual((recs[2202]["status"], recs[2203]["status"], recs[2204]["status"]), (0x26, 0x26, 0x26))


if __name__ == "__main__":
    unittest.main()
