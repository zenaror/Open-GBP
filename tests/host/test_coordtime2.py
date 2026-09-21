"""
tests/host/test_coordtime2.py — the coord-0002 timing proof on its exact
generated image (tools/coordtime.py, profile coord-0002; HARDWARE_TESTS §V6.23,
GitHub Issue #13), and the promise that the coord-0001 analysis of §V6.22 did
not move when the second profile was added.

The gates of Issue #13, each pinned: every entry digit 0..9 makes the next
VBlank; the worst entry PREPARE stays at least 50 000 cycles below the
conservative minimum budget; ordinary, steady and exit PREPARE are below it;
no class is inside the uncertainty band; the PUBLISH model reads the same
VMARGIN classes as the unchanged output work; the entry path performs zero
GamePak ROM reads; the witness/CRC path is cycle-invariant with respect to the
payload -- shown on the four real RUN 12 entry tuples (480/0x36, 960/0x27,
1440/0x26, 1920/0x26) and on alternates. The identities of the canonical ROM
and of its delivery image are pinned; nothing here runs on hardware.
"""
import hashlib
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import coordtime as ct  # noqa: E402

FX = os.path.join(ROOT, "captures", "fixtures")
ROM2 = os.path.join(FX, "stimulus-coord-0002-canonical.gba")
ROM1 = os.path.join(FX, "stimulus-coord-0001-canonical.gba")
BUILT2 = os.path.join(ROOT, "build", "stimulus", "agb-coord2", "agb-coord2.gba")
DELIVERY2 = os.path.join(ROOT, "build", "physical", "agb-coord2-cart.gba")
COORD2_SHA = "319dacb759dd2f78b420691a896387b727accf5d9483f152a6a096865c95093f"
COORD2_SIZE = 3620
DELIVERY2_SHA = "276ad987c4cd0cefc7d7c532b86a7f5c336cf6603a32509f80f17aac9a56f700"
SAFETY_MARGIN = 50_000
RUN12_ENTRIES = [(480, 0x36), (960, 0x27), (1440, 0x26), (1920, 0x26)]      # FRAME_ID / STATUS carried in those frames (§V6.22.7)
_C = {}


def rom2():
    if "rom2" not in _C:
        _C["rom2"] = ct.load_rom(ROM2)
    return _C["rom2"]


def res2():
    if "res2" not in _C:
        _C["res2"] = ct.analyse(rom2())
        _C["b2"] = ct.budget(_C["res2"])
    return _C["res2"], _C["b2"]


def model2():
    if "m2" not in _C:
        _C["m2"] = ct.Model(rom2())
    return _C["m2"]


class TheIdentity(unittest.TestCase):
    def test_the_fixture_is_the_frozen_coord_0002_canonical_rom(self):
        with open(ROM2, "rb") as f:
            data = f.read()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (COORD2_SIZE, COORD2_SHA))
        self.assertIs(ct.profile_of(data), ct.COORD2)
        self.assertEqual(ct.COORD2.name, "coord-0002")

    def test_the_rom_carries_no_glyph_table_payload(self):
        """80 000 B of tables would be visible in the ROM size; the tables are EWRAM NOLOAD."""
        self.assertEqual(COORD2_SIZE - ct.COORD1.rom_size, 124)
        off, img = ct.iwram_image(rom2())
        self.assertEqual((off, len(img)), (0x910, 0x504))
        self.assertEqual(rom2()[0x900:0x90A], bytes([0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F]))

    def test_the_built_rom_if_present_is_the_fixture(self):
        if not os.path.exists(BUILT2):
            self.skipTest("coord-0002 not built here (make stimulus-coord2)")
        with open(BUILT2, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), COORD2_SHA)

    def test_the_delivery_image_if_present_differs_only_in_the_logo_area(self):
        if not os.path.exists(DELIVERY2):
            self.skipTest("delivery image not derived here (tools/gbaderive.py)")
        with open(DELIVERY2, "rb") as f:
            d = f.read()
        self.assertEqual((len(d), hashlib.sha256(d).hexdigest()), (COORD2_SIZE, DELIVERY2_SHA))
        self.assertEqual(d[0xC0:], rom2()[0xC0:])
        diff = [i for i in range(0xC0) if d[i] != rom2()[i]]
        self.assertTrue(diff and 0x04 <= min(diff) and max(diff) <= 0x9F, "only the 156-byte logo area may differ")


class ThePublishModelIsTheSameOutputWork(unittest.TestCase):
    def test_the_three_calibrated_classes_read_the_same_vmargin(self):
        r, _ = res2()
        p = r["publish"]
        self.assertEqual(p["ordinary (strips only)"]["cycles"], 16799)                                   # identical to coord-0001
        self.assertEqual(p["exit (strips + digit erase + squares erase)"]["cycles"], 35657)             # identical to coord-0001
        self.assertEqual(p["steady (strips + squares)"]["cycles"], 17522)                                # identical to coord-0001
        self.assertEqual(p["entry (strips + digit paint + squares)"]["cycles"], 34974)                   # +320: the row pointer is loaded per row
        for k, exp in (("ordinary (strips only)", 54), ("entry (strips + digit paint + squares)", 39), ("exit (strips + digit erase + squares erase)", 39)):
            self.assertEqual(227 - int(ct.VBLANK_FIRST + p[k]["cycles"] / ct.LINE_CYCLES), exp, k)
        self.assertEqual((p["entry (strips + digit paint + squares)"]["dma_count"], p["entry (strips + digit paint + squares)"]["dma_units"]), (248, 6680))
        self.assertEqual(p["entry (strips + digit paint + squares)"]["dma_cycles"], ct.analyse(ct.load_rom(ROM1))["publish"]["entry (strips + digit paint + squares)"]["dma_cycles"])


class TheTimingGates(unittest.TestCase):
    def test_the_budget_and_its_band(self):
        _, b = res2()
        self.assertEqual((b["frame_cycles"], b["publish"], b["tail"], b["react"], b["poll_iteration"]), (280896, 16799, 232, 6, 24))
        self.assertEqual((b["min"], b["max"]), (263835, 263859))
        b_pf = ct.budget(ct.analyse(rom2(), ct.Timing(rom_code_s=2)))
        self.assertEqual((b_pf["min"], b_pf["max"]), (263935, 263951))
        self.assertLessEqual(b_pf["max"] - b["min"], 120)

    def test_every_entry_digit_0_to_9_makes_the_next_vblank_with_the_safety_margin(self):
        r, b = res2()
        entries = {d: r["prepare"]["entry digit %d" % d if d else "entry digit 0 (k=10)"]["cycles"] for d in range(10)}
        self.assertEqual(set(entries.values()), {86972}, "the entry PREPARE no longer depends on the digit")
        worst = max(entries.values())
        self.assertLess(worst, b["min"])
        self.assertGreaterEqual(b["min"] - worst, SAFETY_MARGIN)
        self.assertEqual(b["min"] - worst, 176863)
        for d, c in entries.items():
            self.assertLess(c + b["poll_iteration"], b["min"], d)     # even one poll late

    def test_ordinary_steady_and_exit_are_below_the_minimum_budget_and_nothing_is_in_the_band(self):
        r, b = res2()
        for name, c in ((k, v["cycles"]) for k, v in r["prepare"].items()):
            self.assertLess(c, b["min"], name)
            self.assertFalse(b["min"] <= c <= b["max"], name)
        p = r["prepare"]
        self.assertEqual((p["ordinary (k>=1, 40<phase<480)"]["cycles"], p["exit (phase 40)"]["cycles"]), (77905, 77914))
        self.assertEqual((p["steady (phase 1)"]["cycles"], p["steady (phase 39)"]["cycles"]), (86827, 86443))

    def test_the_entry_path_performs_zero_rom_reads_and_builds_nothing(self):
        r, _ = res2()
        for name, v in r["prepare"].items():
            self.assertEqual(v["access"]["rom_r"], 0, name)
            self.assertEqual(v["access"]["ewram_w16"], 0, name)          # nothing is built in any PREPARE class
        e = r["prepare"]["entry digit 1"]["access"]
        self.assertEqual(e["ewram_r16"], 400)                             # the squares' erase words only (all unlit at phase 0)
        self.assertEqual((r["prepare"]["entry digit 1"]["op_digit"], r["prepare"]["entry digit 1"]["op_sq"]), (1, 1))

    def test_every_class_leaves_the_flags_publish_reads(self):
        r, _ = res2()
        p = r["prepare"]
        self.assertEqual((p["ordinary (k>=1, 40<phase<480)"]["op_digit"], p["ordinary (k>=1, 40<phase<480)"]["op_sq"]), (0, 0))
        self.assertEqual((p["steady (phase 1)"]["op_digit"], p["steady (phase 1)"]["op_sq"]), (0, 1))
        self.assertEqual((p["exit (phase 40)"]["op_digit"], p["exit (phase 40)"]["op_sq"]), (2, 2))

    def test_the_tail_wraps_the_schedule_where_coord_0002_keeps_it(self):
        r, _ = res2()
        t = r["tail"]["entry (schedule wrap)"]
        self.assertEqual((t["phase_after"], t["k_after"], t["instructions"]), (0, 1, 46))
        self.assertEqual(r["tail"]["ordinary"]["phase_after"], 201)


class ThePayloadCannotMoveAnEntryAcrossTheGate(unittest.TestCase):
    """The strip loops use conditional moves, never branches on bit values: the
    PREPARE cost is a function of the frame class alone. Shown on the actual RUN 12
    entry tuples and on alternates, for both images."""

    ALTERNATES = [(0, 0x00), (0xFFFFFF, 0xFF), (12345, 0x7F), (480, 0x80), (1920, 0x18), (0x800000, 0x36)]

    def test_coord_0002_entry_cost_is_identical_for_the_real_and_alternate_payloads(self):
        m = model2()
        for k, d in ((1, 1), (2, 2), (3, 3), (4, 4)):
            fid, st = RUN12_ENTRIES[k - 1]
            self.assertEqual(m.prepare(fid, st, 0, k, d)["cycles"], 86972, (fid, st))
        for fid, st in self.ALTERNATES:
            for k, d in ((1, 1), (7, 7), (10, 0)):
                self.assertEqual(m.prepare(fid, st, 0, k, d)["cycles"], 86972, (fid, st, k))
        for fid, st in self.ALTERNATES:
            self.assertEqual(m.prepare(fid, st, 200, 1, 1)["cycles"], 77905, (fid, st))

    def test_coord_0001_entry_costs_are_also_payload_invariant_which_the_v6_22_analysis_assumed(self):
        m1 = ct.Model(ct.load_rom(ROM1))
        for (k, d), exp in zip(((1, 1), (2, 2), (3, 3), (4, 4)), (287787, 261723, 260043, 287179)):
            fid, st = RUN12_ENTRIES[k - 1]
            self.assertEqual(m1.prepare(fid, st, 0, k, d)["cycles"], exp, (fid, st))
            self.assertEqual(m1.prepare(0xFFFFFF, 0xFF, 0, k, d)["cycles"], exp)
            self.assertEqual(m1.prepare(0, 0x00, 0, k, d)["cycles"], exp)


class TheHistoricalCoord0001ReplayIsUnchanged(unittest.TestCase):
    def test_the_v6_22_numbers(self):
        rom1 = ct.load_rom(ROM1)
        self.assertIs(ct.profile_of(rom1), ct.COORD1)
        r, b = ct.analyse(rom1), None
        b = ct.budget(r)
        self.assertEqual((b["min"], b["max"]), (263839, 263863))
        p = r["prepare"]
        self.assertEqual([p["entry digit %d" % d]["cycles"] for d in (1, 2, 3, 4)], [287787, 261723, 260043, 287179])
        self.assertEqual([p["entry digit %d" % d]["cycles"] for d in (5, 6, 7, 8, 9)], [261723, 268219, 277643, 271467, 265643])
        self.assertEqual(p["entry digit 0 (k=10)"]["cycles"], 280683)     # the one row added by Issue #13 (digit 0 would also have missed); every earlier number is untouched
        self.assertEqual((p["ordinary (k>=1, 40<phase<480)"]["cycles"], p["steady (phase 1)"]["cycles"], p["exit (phase 40)"]["cycles"]), (77917, 86824, 77919))
        pub = r["publish"]
        self.assertEqual([pub[k]["cycles"] for k in ("ordinary (strips only)", "entry (strips + digit paint + squares)", "steady (strips + squares)", "exit (strips + digit erase + squares erase)")],
                         [16799, 34654, 17522, 35657])
        rows = ct.sensitivity(rom1, ws_values=(2,), rom_n_values=(4,))
        self.assertEqual(rows[0]["pattern"], "M--M")

    def test_the_two_profiles_are_immutable_and_distinct(self):
        self.assertEqual(ct.COORD1.rom_sha256, "90343b64eda9602c173364171637cd1068f265c385464361b40ec073b11f0a1f")
        self.assertEqual(ct.COORD2.rom_sha256, COORD2_SHA)
        self.assertEqual(ct.PROFILES[ct.COORD1.rom_sha256].publish_addr, 0x0300047C)
        self.assertEqual(ct.PROFILES[ct.COORD2.rom_sha256].publish_addr, 0x03000348)
        self.assertEqual(ct.ROM_SHA256, ct.COORD1.rom_sha256)


if __name__ == "__main__":
    unittest.main()
