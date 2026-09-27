"""tests/host/test_v124route.py -- tools/v124route.py, the pre-registered predictions for
`agb-route`'s two open questions (U-GBP-047, U-GBP-048), pinned on SYNTHETIC data (no real
capture exists yet -- this is the tool the Orchestrator asked to be pinned BEFORE the capture
is read).

Synthetic (wA, wB) values are injected directly into 256-byte slices via streams 1 and 5 (the
same bytes tools/v123frame.py's slice_record() reads), so this file proves the ARITHMETIC the
already-frozen predictions state, not anything about real hardware.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v124route  # noqa: E402
import v11sweep  # noqa: E402
import awinparse  # noqa: E402

SLICE = 256
BLOCK = 4096


def make_slice(wa, wb):
    """A 256-byte slice whose stream 1 (A) has exactly `wa` one-bits and stream 5 (B) exactly
    `wb`, both packed at the most-significant end -- everything else zero."""
    sl = bytearray(SLICE)

    def pack(stream_index, ones):
        v = ((1 << ones) - 1) << (256 - ones) if ones else 0
        b = v.to_bytes(32, "big")
        for k in range(32):
            sl[stream_index + 8 * k] = b[k]

    pack(1, wa)
    pack(5, wb)
    return bytes(sl)


def make_block(wa, wb):
    return b"".join(make_slice(wa, wb) for _ in range(BLOCK // SLICE))


def make_window(n_blocks, wa, wb):
    return [make_block(wa, wb) for _ in range(n_blocks)]


def make_anchor(kind, keys=0, closed=True):
    return {"kind": kind, "keys": keys, "flags": awinparse.F_CLOSED if closed else 0}


ONSET = v11sweep.ONSET_SLICE_BLOCKS
STEADY_BLOCKS = 10
PRESS_BLOCKS = ONSET + STEADY_BLOCKS


def route_scenario(press_wa_values, press_wb_values, control_wa=128, control_wb=128,
                    press_keys=0x0001, n_control=1, n_press=4, closed=True):
    anchors = [make_anchor(0, closed=closed) for _ in range(n_control)]
    windows = [make_window(1, control_wa, control_wb) for _ in range(n_control)]
    for wa, wb in zip(press_wa_values, press_wb_values):
        anchors.append(make_anchor(1, keys=press_keys, closed=closed))
        windows.append(make_window(PRESS_BLOCKS, wa, wb))
    # pad/truncate to n_press if the caller wants an inadmissible window count
    while len(anchors) - n_control < n_press:
        anchors.append(make_anchor(1, keys=press_keys, closed=closed))
        windows.append(make_window(PRESS_BLOCKS, 128, 128))
    return anchors, windows


class QuestionStereo(unittest.TestCase):
    def test_route_left_prediction_holds_when_wa_moves_and_wb_pins(self):
        r = v124route.question_stereo(*route_scenario([140, 150, 160, 170], [128, 129, 127, 128]), variant="left")
        self.assertTrue(r["admissible"])
        self.assertEqual(r["wa_class"], "MOVED")
        self.assertEqual(r["wb_class"], "PINNED")
        self.assertTrue(r["prediction_holds"])

    def test_route_right_prediction_holds_when_wb_moves_and_wa_pins(self):
        r = v124route.question_stereo(*route_scenario([128, 129, 127, 128], [90, 100, 110, 120]), variant="right")
        self.assertTrue(r["admissible"])
        self.assertEqual(r["wa_class"], "PINNED")
        self.assertEqual(r["wb_class"], "MOVED")
        self.assertTrue(r["prediction_holds"])

    def test_the_same_data_fails_the_other_variant_s_prediction(self):
        anchors, windows = route_scenario([140, 150, 160, 170], [128, 129, 127, 128])
        left = v124route.question_stereo(anchors, windows, variant="left")
        right = v124route.question_stereo(anchors, windows, variant="right")
        self.assertTrue(left["prediction_holds"])
        self.assertFalse(right["prediction_holds"], "wA moving is route-left's own prediction, not route-right's")

    def test_both_sides_moving_comparably_is_indeterminate_not_stereo(self):
        r = v124route.question_stereo(*route_scenario([140, 150, 160, 170], [90, 100, 110, 120]), variant="left")
        self.assertTrue(r["admissible"])
        self.assertFalse(r["separated"], "the 131072 Hz rival predicts both sides keep varying comparably")
        self.assertEqual(r["wb_class"], "INDETERMINATE")
        self.assertEqual(r["wa_class"], "INDETERMINATE")
        self.assertFalse(r["prediction_holds"])

    def test_neither_side_moving_is_indeterminate_not_stereo(self):
        r = v124route.question_stereo(*route_scenario([128, 129, 128, 127], [128, 127, 129, 128]), variant="left")
        self.assertTrue(r["admissible"])
        self.assertFalse(r["separated"])
        self.assertEqual(r["wa_class"], "INDETERMINATE")
        self.assertFalse(r["prediction_holds"])

    def test_crosstalk_on_the_silent_side_is_still_pinned_relative_to_a_moving_side(self):
        """Amendment (a), Orchestrator review of Issue #130: a fixed absolute threshold (the
        original PIN_TOLERANCE = 2) would misclassify this as MOVED and give a false negative
        for stereo, because the control windows (both sides silent) cannot show what crosstalk
        from an ACTIVE side does to a nominally silent one. wB here deviates by 3 (crosstalk),
        clearly small relative to wA's own ~30 -- the relative classifier still calls it PINNED."""
        r = v124route.question_stereo(*route_scenario([158, 148, 138, 128], [125, 126, 124, 125]), variant="left")
        self.assertTrue(r["admissible"])
        self.assertTrue(r["separated"])
        self.assertEqual(r["wb_class"], "PINNED")
        self.assertEqual(r["wa_class"], "MOVED")
        self.assertTrue(r["prediction_holds"])
        self.assertGreater(r["deviation_wb"], 2.0, "the crosstalk deviation must exceed the old absolute tolerance")

    def test_only_route_left_or_route_right_are_pre_registered(self):
        with self.assertRaises(ValueError):
            v124route.question_stereo(*route_scenario([128] * 4, [128] * 4), variant="both")

    def test_a_wrong_axis_is_inadmissible(self):
        r = v124route.question_stereo(*route_scenario([140, 150, 160, 170], [128] * 4, press_keys=0x0002),
                                       variant="left")
        self.assertFalse(r["admissible"])
        self.assertEqual(r["axis"], "V")

    def test_a_mixed_axis_is_inadmissible_and_names_every_refusal(self):
        anchors, windows = route_scenario([140, 150, 160, 170], [128] * 4)
        anchors[2]["keys"] = 0x0002          # the third press pressed B, not A
        r = v124route.question_stereo(anchors, windows, variant="left")
        self.assertFalse(r["admissible"])
        self.assertEqual(r["axis"], "MIXED")
        self.assertTrue(r["refusals"])

    def test_the_wrong_window_count_is_inadmissible(self):
        r = v124route.question_stereo(*route_scenario([140, 150, 160], [128, 128, 128], n_press=3),
                                       variant="left")
        self.assertFalse(r["admissible"])

    def test_a_window_that_never_closed_is_inadmissible(self):
        r = v124route.question_stereo(*route_scenario([140, 150, 160, 170], [128] * 4, closed=False),
                                       variant="left")
        self.assertFalse(r["admissible"])

    def test_the_run_s_own_control_window_is_reported_not_substituted(self):
        r = v124route.question_stereo(*route_scenario([140, 150, 160, 170], [128, 129, 127, 128],
                                                        control_wa=131, control_wb=126), variant="left")
        self.assertTrue(r["admissible"])
        self.assertEqual(r["control_wa"], 131.0)
        self.assertEqual(r["control_wb"], 126.0)
        # the pin/move decision is against the frozen REST_WIDTH (128), not against this run's own
        # control reading, even though the control reading differs slightly from it here:
        self.assertEqual(r["wb_class"], "PINNED")


class QuestionBias(unittest.TestCase):
    def test_bits_14_15_zero_holds_the_prediction(self):
        r = v124route.question_bias(0x0200, entry_ok=1)
        self.assertTrue(r["admissible"])
        self.assertEqual(r["resolution_bits_14_15"], 0)
        self.assertTrue(r["prediction_holds"])

    def test_any_nonzero_resolution_breaks_the_model(self):
        for bad in (0x4000, 0x8000, 0xC000):
            r = v124route.question_bias(bad, entry_ok=1)
            self.assertTrue(r["admissible"])
            self.assertGreater(r["resolution_bits_14_15"], 0)
            self.assertFalse(r["prediction_holds"], "%#06x must break the model" % bad)

    def test_resolution_decodes_all_four_values(self):
        self.assertEqual(v124route.question_bias(0x0000, 1)["resolution_bits_14_15"], 0)
        self.assertEqual(v124route.question_bias(0x4000, 1)["resolution_bits_14_15"], 1)
        self.assertEqual(v124route.question_bias(0x8000, 1)["resolution_bits_14_15"], 2)
        self.assertEqual(v124route.question_bias(0xC000, 1)["resolution_bits_14_15"], 3)

    def test_a_missing_entry_marker_is_inadmissible(self):
        r = v124route.question_bias(0x0200, entry_ok=0)
        self.assertFalse(r["admissible"])

    def test_an_out_of_range_value_raises(self):
        with self.assertRaises(ValueError):
            v124route.question_bias(0x10000, entry_ok=1)


if __name__ == "__main__":
    unittest.main()
