#!/usr/bin/env python3
"""OGBPIDXCAP1: the C producer against the Python consumer, and the analyzer
adapter's refusal rules (HARDWARE_TESTS §V5.39.7, §V5.39.10).

The valuable tests here are the CROSS-LANGUAGE ones. A format is only frozen if
two independent implementations agree on it, so the sidecars these tests parse
are written by the real `src/gbp/gbp_vidxdump.c` — compiled, run, and handed to
`tools/vidxcap.py` — rather than by a Python model of it. A Python writer
checking a Python reader would prove nothing about the bytes the GameCube
produces.

The second group is about REFUSAL. A capture that stopped for the wrong reason,
overflowed its store or lost a record can be perfectly decodable and still be
the wrong evidence, and the adapter has to say so rather than let a plausible
sequence of frame IDs become a conclusion.
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import hostcc  # noqa: E402
import istim          # noqa: E402
import vidxcap        # noqa: E402
import vindex         # noqa: E402

SRC = os.path.join(ROOT, "src", "gbp")

GENERATOR = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_vwitness.h"
#include "gbp_vidxdump.h"

/* Writes ONE OGBPIDXCAP1 file built by the real runtime writer.
 *   argv[1] path  argv[2] records  argv[3] target  argv[4] capacity
 *   argv[5] stop_reason  argv[6] 1 = also mark the store as full
 *   argv[7] frame-id base: block b of record k encodes (base + k) via istim */
static uint16_t *store;
static struct gbp_vwitness_meta *meta;
static struct gbp_vwitness w;
static uint8_t chunk[GBP_VIDXDUMP_RECORD_SIZE];
static FILE *out;

static int sink(void *ctx, const uint8_t *d, uint32_t n)
{
    (void)ctx;
    return fwrite(d, 1u, n, out) == n ? 0 : -1;
}

int main(int argc, char **argv)
{
    struct gbp_vidxdump_info info;
    struct gbp_vwitness_meta m;
    uint32_t n, target, cap, k, b, i;
    uint64_t written = 0;
    long rc;
    if (argc < 8) return 2;
    n = (uint32_t)strtoul(argv[2], 0, 0);
    target = (uint32_t)strtoul(argv[3], 0, 0);
    cap = (uint32_t)strtoul(argv[4], 0, 0);
    store = calloc(cap, GBP_VWITNESS_FRAME_BYTES);
    meta = calloc(cap, sizeof *meta);
    if (!store || !meta) return 3;
    if (gbp_vwitness_init(&w, store, meta, cap, target)) return 4;
    for (k = 0; k < n; k++) {
        for (b = 0; b < GBP_VWITNESS_BLOCKS; b++) {
            uint16_t words[GBP_VWITNESS_WORDS];
            char line[512];
            if (!fgets(line, sizeof line, stdin)) return 5;
            for (i = 0; i < GBP_VWITNESS_WORDS; i++) {
                char *e;
                words[i] = (uint16_t)strtoul(i == 0 ? line : e, &e, 16);
                if (i == 0) e = line + 4;
            }
            /* re-parse properly: 54 hex words separated by spaces */
            {
                char *p = line;
                for (i = 0; i < GBP_VWITNESS_WORDS; i++)
                    words[i] = (uint16_t)strtoul(p, &p, 16);
            }
            memcpy(w.staged, words, sizeof words);
            w.staged_valid = 1u;
            w.blocks_staged++;
            if (gbp_vwitness_place(&w, b)) return 6;
        }
        memset(&m, 0, sizeof m);
        m.frame_index = k * 2u + 5u;
        m.blocks = 40u;
        m.flags = 0x0001u;
        m.completeness = 1u;
        m.t_first_block = 100000u + k * 675264u;
        m.t_last_block = m.t_first_block + 600000u;
        if (gbp_vwitness_commit(&w, &m) != 1) return 7;
    }
    if (argv[6][0] == '1') w.store_full = 1u;
    memset(&info, 0, sizeof info);
    info.tb_hz = 40500000u;
    info.stop_reason = (uint16_t)strtoul(argv[5], 0, 0);
    if (gbp_vidxdump_set_identity(&info, "GBP-VIDEO-004", "stream-0005",
                                  "gbp-video-stream-probe", "abc1234")) return 8;
    out = fopen(argv[1], "wb");
    if (!out) return 9;
    rc = gbp_vidxdump_stream(&info, &w, chunk, sizeof chunk, sink, 0, &written);
    fclose(out);
    return rc > 0 ? 0 : 10;
}
"""

STOP_WITNESS_TARGET = vidxcap.stop_reasons()["GBP_VSTATE_STOP_WITNESS_TARGET"]
STOP_SAFETY = vidxcap.stop_reasons()["GBP_VSTATE_STOP_SAFETY_BUDGET"]


class Producer:
    """Compiles the real writer once and drives it."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="opengbp-idxcap-")
        self.bin = os.path.join(self.tmp, "gen")
        csrc = os.path.join(self.tmp, "gen.c")
        with open(csrc, "w") as f:
            f.write(GENERATOR)
        self.have, self.ok, self.err = hostcc.compile_c(["-std=gnu11", "-O1", "-I", SRC, "-o", self.bin, csrc,
                                                         os.path.join(SRC, "gbp_vwitness.c"),
                                                         os.path.join(SRC, "gbp_vidxdump.c"),
                                                         os.path.join(SRC, "gbp_crc32.c")])

    def write(self, path, frames, target=None, cap=None,
              stop=STOP_WITNESS_TARGET, store_full=False):
        """`frames` is a list of 40 lists of 54 words."""
        n = len(frames)
        target = n if target is None else target
        cap = max(n, target) if cap is None else cap
        payload = "".join(" ".join("%04x" % w for w in blk) + "\n"
                          for fr in frames for blk in fr)
        r = subprocess.run([self.bin, path, str(n), str(target), str(cap),
                            str(stop), "1" if store_full else "0", "0"],
                           input=payload, capture_output=True, text=True)
        assert r.returncode == 0, "generator failed rc=%d %s" % (r.returncode, r.stderr)
        return path


PROD = Producer()


def frame_words(frame_id, status=0x7F, phase=0):
    """A whole OGBPIDX1 frame's canonical witness, from the frozen model."""
    return [istim.witness_words(frame_id, b, status, phase) for b in range(40)]


class SidecarRoundTrip(unittest.TestCase):
    def setUp(self):
        hostcc.require(self, PROD.have, PROD.ok, PROD.err)
        self.dir = tempfile.mkdtemp(prefix="opengbp-idxcap-t-")

    def path(self, name="cap.bin"):
        return os.path.join(self.dir, name)

    def test_the_c_writer_and_the_python_reader_agree_byte_for_byte(self):
        frames = [frame_words(0x100 + k) for k in range(4)]
        p = PROD.write(self.path(), frames)
        info = vidxcap.load(p)
        self.assertEqual(info["records_n"], 4)
        self.assertEqual(info["target_frames"], 4)
        self.assertEqual(info["build_id"], "stream-0005")
        self.assertEqual(info["test_id"], "GBP-VIDEO-004")
        self.assertEqual(info["app"], "gbp-video-stream-probe")
        self.assertEqual(info["commit"], "abc1234")
        self.assertEqual(info["witness_words"], 54)
        self.assertEqual(info["witness_blocks"], 40)
        self.assertEqual(info["strip_x0"], 1)
        self.assertEqual(info["strip_row"], 0)
        for k, rec in enumerate(info["records"]):
            self.assertEqual(rec["witness"], frames[k])
            self.assertEqual(rec["present"], (1 << 40) - 1)
            self.assertEqual(rec["blocks_captured"], 40)
            self.assertEqual(rec["frame_index"], k * 2 + 5)

    def test_the_declared_size_is_the_real_size(self):
        p = PROD.write(self.path(), [frame_words(1)])
        info = vidxcap.load(p)
        self.assertEqual(os.path.getsize(p), info["total_size"])
        self.assertEqual(info["total_size"],
                         vidxcap.HEADER_SIZE + vidxcap.RECORD_SIZE + vidxcap.FOOTER_SIZE)

    def test_bit15_survives_the_whole_path(self):
        """The one property no later step can recover: the analyzer splits bit 15
        offline, so the file has to have carried it."""
        frames = [frame_words(7)]
        frames[0][0] = [w | 0x8000 for w in frames[0][0]]
        p = PROD.write(self.path(), frames)
        info = vidxcap.load(p)
        self.assertTrue(all(w & 0x8000 for w in info["records"][0]["witness"][0]))
        self.assertEqual(info["records"][0]["witness"][0], frames[0][0])

    def test_every_single_byte_flip_is_refused(self):
        """Not a sample: every byte of a small file, one at a time."""
        p = PROD.write(self.path(), [frame_words(3)])
        with open(p, "rb") as f:
            good = bytearray(f.read())
        vidxcap.parse(bytes(good))          # the undamaged file parses
        accepted = []
        for i in range(len(good)):
            bad = bytearray(good)
            bad[i] ^= 0xFF
            try:
                vidxcap.parse(bytes(bad))
                accepted.append(i)
            except vidxcap.SidecarError:
                pass
        self.assertEqual(accepted, [], "bytes accepted after damage: %r" % accepted[:8])

    def test_a_short_file_is_refused(self):
        p = PROD.write(self.path(), [frame_words(3)])
        with open(p, "rb") as f:
            good = f.read()
        for n in (0, 8, vidxcap.HEADER_SIZE, len(good) - 1):
            with self.assertRaises(vidxcap.SidecarError):
                vidxcap.parse(good[:n])

    def test_the_stop_enum_is_read_from_the_runtime_header(self):
        """A tool that hard-codes a runtime enum drifts from it silently."""
        stops = vidxcap.stop_reasons()
        self.assertEqual(stops["GBP_VSTATE_STOP_NONE"], 0)
        self.assertIn("GBP_VSTATE_STOP_WITNESS_TARGET", stops)
        self.assertIn("GBP_VSTATE_STOP_WITNESS_STORE_FULL", stops)
        self.assertEqual(stops["GBP_VSTATE_STOP_WITNESS_STORE_FULL"],
                         stops["GBP_VSTATE_STOP_WITNESS_TARGET"] + 1)


class Admissibility(unittest.TestCase):
    """What the adapter REFUSES, which is the part that protects the claim."""

    def setUp(self):
        hostcc.require(self, PROD.have, PROD.ok, PROD.err)
        self.dir = tempfile.mkdtemp(prefix="opengbp-idxcap-u-")

    def path(self, name="cap.bin"):
        return os.path.join(self.dir, name)

    def frames(self, n, start=0x200):
        return [frame_words(start + k) for k in range(n)]

    def test_a_clean_target_stop_is_admissible(self):
        p = PROD.write(self.path(), self.frames(4))
        u = vidxcap.usability(vidxcap.load(p))
        self.assertTrue(u["usable_for_decisive_claim"], u["reasons"])
        self.assertEqual(u["reasons"], [])

    def test_a_store_full_capture_is_never_admissible(self):
        p = PROD.write(self.path(), self.frames(4), store_full=True)
        u = vidxcap.usability(vidxcap.load(p))
        self.assertFalse(u["usable_for_decisive_claim"])
        self.assertTrue(any("store_full" in r for r in u["reasons"]))

    def test_a_run_that_stopped_for_another_reason_is_not_admissible(self):
        p = PROD.write(self.path(), self.frames(4), stop=STOP_SAFETY)
        u = vidxcap.usability(vidxcap.load(p))
        self.assertFalse(u["usable_for_decisive_claim"])
        self.assertTrue(any("did not stop on the witness target" in r for r in u["reasons"]))

    def test_a_capture_short_of_its_target_is_not_admissible(self):
        p = PROD.write(self.path(), self.frames(3), target=8, cap=8)
        info = vidxcap.load(p)
        self.assertFalse(info["flags"] & vidxcap.FLAG_TARGET_REACHED)
        u = vidxcap.usability(info)
        self.assertFalse(u["usable_for_decisive_claim"])
        self.assertTrue(any("target was never reached" in r for r in u["reasons"]))

    def test_the_analyzer_adapter_forces_inconclusive_on_an_inadmissible_capture(self):
        """A contiguous ID sequence in a capture that stopped wrongly is still
        not a decisive result. The classification survives; the VERDICT does not."""
        p = PROD.write(self.path(), self.frames(6), stop=STOP_SAFETY)
        report, info, use = vindex.analyze_sidecar(p)
        self.assertEqual(report["observed_intact"], 6)
        self.assertEqual(report["verdict"], vindex.INCONCLUSIVE_CAPTURE)
        self.assertFalse(report["capture"]["usable_for_decisive_claim"])
        self.assertTrue(report["capture"]["refused_because"])
        # The per-frame work is untouched: the adapter adds a gate, it does not
        # edit what the core decided. 6 intact frames -> the trailing one is
        # excluded as uncertified (no later STATUS covers its own update), so the
        # decisive set is 5 frames and 4 transitions.
        self.assertEqual(len(report["decisive_transitions"]), 4)
        self.assertEqual(report["counts"].get(istim.OBSERVED_ID_CONTIGUOUS), 4)

    def test_the_analyzer_adapter_passes_a_clean_capture_through(self):
        p = PROD.write(self.path(), self.frames(6))
        report, info, use = vindex.analyze_sidecar(p)
        self.assertTrue(report["capture"]["usable_for_decisive_claim"])
        self.assertNotEqual(report["verdict"], vindex.INCONCLUSIVE_CAPTURE)
        self.assertEqual(report["observed_intact"], 6)
        self.assertEqual(report["capture"]["records"], 6)
        self.assertEqual(report["capture"]["records_all_40_blocks"], 6)
        self.assertEqual(report["capture"]["records_partial"], 0)

    def test_a_gap_in_the_ids_is_reported_as_a_gap(self):
        """The gap has to sit INSIDE the decisive set to be counted: the frozen
        contract excludes the trailing frame because no later STATUS certifies
        its own update, and that exclusion is not negotiable after the fact."""
        frames = [frame_words(i) for i in (0x300, 0x301, 0x305, 0x306)]
        p = PROD.write(self.path(), frames)
        report, _, _ = vindex.analyze_sidecar(p)
        self.assertEqual(report["counts"].get(istim.OBSERVED_ID_GAP), 1)
        self.assertEqual(report["counts"].get(istim.OBSERVED_ID_CONTIGUOUS), 1)
        self.assertEqual(report["first_decisive"], 0x300)
        self.assertEqual(report["last_decisive"], 0x305)

    def test_a_full_target_capture_yields_target_minus_two_transitions(self):
        """§17's expectation, checked at a size the test can afford and stated as
        an identity rather than a number: N intact frames give N-1 decisive
        frames and N-2 decisive transitions. At the shipped target of 2048 that
        is 2046 — expected, never pre-asserted; the run reports its real N."""
        n = 12
        p = PROD.write(self.path(), self.frames(n, start=0x400))
        report, _, _ = vindex.analyze_sidecar(p)
        self.assertEqual(report["observed_intact"], n)
        self.assertEqual(len(report["decisive_transitions"]), n - 2)
        self.assertEqual(report["counts"].get(istim.OBSERVED_ID_CONTIGUOUS), n - 2)
        self.assertEqual(vidxcap.WITNESS_BLOCKS * vidxcap.WITNESS_WORDS * 2, 4320)
        self.assertEqual(2048 - 2, 2046)

    def test_the_report_names_the_build_that_produced_it(self):
        p = PROD.write(self.path(), self.frames(2))
        report, _, _ = vindex.analyze_sidecar(p)
        self.assertEqual(report["capture"]["build_id"], "stream-0005")
        self.assertEqual(report["capture"]["commit"], "abc1234")

    def test_format_info_states_the_refusal_out_loud(self):
        p = PROD.write(self.path(), self.frames(2), stop=STOP_SAFETY)
        text = vidxcap.format_info(vidxcap.load(p))
        self.assertIn("decisive-claim ready False", text)
        self.assertIn("REFUSED", text)


class GeometryIsFrozen(unittest.TestCase):
    """The wire format did not change in this round, and these guards say so."""

    def test_the_python_constants_match_the_c_header(self):
        src = open(os.path.join(SRC, "gbp_vwitness.h")).read()
        self.assertIn("#define GBP_VWITNESS_WORDS       54u", src)
        self.assertIn("#define GBP_VWITNESS_BLOCKS      40u", src)
        self.assertIn("#define GBP_VWITNESS_STRIP_X0    1u", src)
        self.assertIn("#define GBP_VWITNESS_TARGET      2048u", src)
        self.assertEqual(vidxcap.WITNESS_WORDS, 54)
        self.assertEqual(vidxcap.WITNESS_BLOCKS, 40)
        self.assertEqual(vidxcap.RECORD_SIZE, 4368)
        self.assertEqual(vidxcap.WITNESS_BYTES, 4320)

    def test_the_canonical_witness_is_the_one_istim_defines(self):
        """The retention must extract exactly what the frozen model says the
        witness is — not a region that merely happens to contain it."""
        self.assertEqual(len(istim.witness_words(1, 0, 0x7F, 0)), vidxcap.WITNESS_WORDS)
        strip = list(istim.STRIP_L)
        self.assertEqual(len(strip), vidxcap.WITNESS_WORDS)
        self.assertEqual(strip[0], vidxcap.WITNESS_STRIP_X0)
        self.assertEqual(strip[-1], vidxcap.WITNESS_STRIP_X0 + vidxcap.WITNESS_WORDS - 1)
        self.assertEqual(vidxcap.WITNESS_STRIP_ROW, 0)

    def test_the_audited_budget_is_unchanged(self):
        self.assertEqual(2048 * 4320, 8847360)
        self.assertEqual(vidxcap.WITNESS_BYTES * 2048, 8847360)


if __name__ == "__main__":
    unittest.main()
