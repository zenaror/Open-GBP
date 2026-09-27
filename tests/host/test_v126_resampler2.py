"""tests/host/test_v126_resampler2.py -- GitHub Issue #126, Round B: tools/gen_aresamp2.py's table is the object
GBP-HW-351 settled, reshaped, never rederived.

What is proved here:
  * the reshape is checked against TWO different things: once by regenerating the header and diffing it byte for
    byte (mirroring tests/host/test_audio_runtime.py's own check on gen_aresamp.py -- this catches a transcription
    slip confined to gen_aresamp2.py's own table()/render()), and once against a GENUINELY independent construction:
    tools/v123chain.py's prototype() builds the same Kaiser-windowed sinc from its own raw float definition (a
    different code path, sharing no call with tools/v124taps.kernel()'s already-shaped, already-quantized output),
    and each phase's row is required to correlate with the released Q15 table at > 0.9999 (worst measured: 125
    phases, min 0.99999999). CORRECTED CLAIM (review round, #126): an EARLIER version of this second check called
    v124taps.kernel() a second time with the identical arguments and applied the byte-for-byte identical index
    expression gen_aresamp2.table() uses -- so it shared kernel()'s own centre/normalization/quantization AND the
    index formula with the code under test, and would have reproduced any error in either identically, not caught
    it. The v123chain.prototype()-based check below has no such shared code path;
  * the ratio is exact (125 * 65536 == 256 * 32000);
  * every phase sums to exactly 32768 (also covered generically by test_resampler_tables.py; pinned here too since
    it is the property the whole design rests on).
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_aresamp2  # noqa: E402
import v123chain  # noqa: E402

HEADER = os.path.join(ROOT, "src", "audio", "gbp_aresamp2_coef.h")


class TheCommittedHeader(unittest.TestCase):
    def test_regenerating_reproduces_it_byte_for_byte(self):
        with open(HEADER, encoding="utf-8") as f:
            committed = f.read()
        self.assertEqual(gen_aresamp2.render(), committed)

    def test_the_ratio_is_exact(self):
        self.assertEqual(gen_aresamp2.L * gen_aresamp2.IN_RATE, gen_aresamp2.M * gen_aresamp2.OUT_RATE)
        self.assertEqual((gen_aresamp2.L, gen_aresamp2.M, gen_aresamp2.TAPS), (125, 256, 16))

    def test_every_phase_sums_to_exactly_32768(self):
        for row in gen_aresamp2.table():
            self.assertEqual(sum(row), 1 << gen_aresamp2.Q)


class TheReshapeMatchesAnIndependentConstruction(unittest.TestCase):
    """v123chain.prototype() builds the same 16-tap/L=125 Kaiser-windowed sinc from its own raw float definition
    (n in -1000..1000, t = n / L, DC gain L) -- a code path that shares nothing with tools/v124taps.kernel()'s
    already-shaped, already-quantized construction that gen_aresamp2.table() reshapes. A shared error in kernel()'s
    centre, normalization or Q15 quantization, or in the index formula both files would then share, cannot hide
    behind this check the way it could behind calling kernel() a second time with the same arguments."""

    RAW = None

    @classmethod
    def setUpClass(cls):
        cls.RAW = v123chain.prototype(16, 4.0, fin=65536, cutoff=16000, L=125)
        cls.n0 = (len(cls.RAW) - 1) // 2

    def raw_row(self, p):
        half = 16 // 2
        return [self.RAW[self.n0 + 125 * (half - 1 - m) + p] for m in range(16)]

    def test_every_phase_correlates_with_the_released_table(self):
        # the raw kernel is float and un-quantized (Q15 rounding/residue-folding differ), so exact equality is not
        # the right check; a normalized correlation isolates a formula/index/centre error from quantization noise
        worst = 1.0
        for p, row in enumerate(gen_aresamp2.table()):
            raw = self.raw_row(p)
            num = sum(a * b for a, b in zip(row, raw))
            den = (sum(a * a for a in row) ** 0.5) * (sum(b * b for b in raw) ** 0.5)
            corr = num / den if den else 0.0
            worst = min(worst, corr)
            self.assertGreater(corr, 0.9999, p)
        self.assertGreater(worst, 0.999999, "worst-phase correlation, quoted in DEVLOG")

    def test_disagrees_when_the_mapping_is_wrong(self):
        # the check is not vacuous: a phase shift by one must be caught
        right = gen_aresamp2.table()
        wrong = [right[(p + 1) % 125] for p in range(125)]
        worst = 1.0
        for p in range(125):
            raw = self.raw_row(p)
            row = wrong[p]
            num = sum(a * b for a, b in zip(row, raw))
            den = (sum(a * a for a in row) ** 0.5) * (sum(b * b for b in raw) ** 0.5)
            worst = min(worst, num / den if den else 0.0)
        self.assertLess(worst, 0.9999)


if __name__ == "__main__":
    unittest.main()
