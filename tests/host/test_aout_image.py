"""
tests/host/test_aout_image.py — GitHub Issue #86: the OUTPUT-PATH image
(poc/audio-output-replay, AOUT-HW-001, aout-0001), pinned to what it claims.

An output-path test, not a Game Boy Player audio test. What makes that claim
true is what the image LINKS and DOES, so those are what is pinned:
  * no Game Boy Player code at all -- transport, HSP backend, service path,
    register writes -- by the image's own SRCS and by the `aout` audit profile
    run on the real listings (both directions);
  * the fixture it plays is RUN 33's, by the same size and CRC the records carry,
    and it refuses anything else;
  * the screen never shows a frequency: the Operator's ears are the check;
  * the DOLPHIN FLOW variant (the fixture linked in) exists only under EMBED=1,
    with its own build id and its own output directory, and the console image
    cannot become it by accident.
The samples themselves are pinned by tests/host/test_audio_listen.py.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
POC = os.path.join(ROOT, "poc", "audio-output-replay")
MAIN = os.path.join(POC, "source", "main.c")
MAKEFILE = os.path.join(POC, "Makefile")
EMBED_S = os.path.join(POC, "source", "fixture_embed.S")
AUDIT = os.path.join(ROOT, "tools", "poc_audit.py")
OUT = os.path.join(ROOT, "build", "poc", "audio-output-replay")
PLAY_OUT = os.path.join(ROOT, "build", "poc", "gbp-play-session")
README = os.path.join(ROOT, "captures", "README.md")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def define(src, name):
    m = re.search(r"^#define\s+%s\s+(\S+)" % re.escape(name), src, re.M)
    assert m, name
    return m.group(1)


def srcs():
    return re.search(r"^SRCS := (.*)$", read(MAKEFILE), re.M).group(1).split()


class ItIsNotAGameBoyPlayerImage(unittest.TestCase):

    def test_the_test_id_is_not_a_gbp_family(self):
        self.assertEqual(define(read(MAIN), "TEST_ID"), '"AOUT-HW-001"')
        self.assertNotIn("GBP-AUDIO", define(read(MAIN), "TEST_ID"))

    def test_no_gbp_source_is_linked(self):
        s = set(srcs())
        self.assertEqual(s, {"main.c", "opengbp_ident.c", "ringlog.c", "sdlog.c", "gbp_alisten.c", "gbp_adec.c",
                             "gbp_asrc.c", "gbp_aresamp.c", "gbp_awindump.c", "gbp_awin.c", "gbp_crc32.c"})
        for bad in ("hsp_backend.c", "hsp_backend_irq.c", "gbp_transport.c", "gbp_vstate_probe.c",
                    "gbp_regwrite.c", "gbp_initirqa_probe.c", "gbp_detect.c", "gbp_input.c"):
            self.assertNotIn(bad, s)

    def test_main_names_no_gbp_device_call(self):
        m = read(MAIN)
        for bad in ("hsp_backend", "gbp_transport", "gbp_vstate", "gbp_regwrite", "IRQ_Request", "__UnmaskIrq"):
            self.assertNotIn(bad, m)
        self.assertIn("OUTPUT PATH TEST -- NOT a Game Boy Player audio test. The GBP is not touched.", m)


class ItPlaysRun33AndNothingElse(unittest.TestCase):

    def test_the_fixture_identity_is_the_records(self):
        m = read(MAIN)
        self.assertEqual(define(m, "AOUT_FIXTURE_BYTES"), "5243788u")
        self.assertEqual(define(m, "AOUT_FIXTURE_CRC"), "0xD3DBD9A6u")
        r = read(README)
        self.assertIn("raw sidecar `logs/run33/GBP-AUDIO-001_stream-0016-audio.bin` **5 243 788 B", r)
        self.assertIn("RUN 33              crc=d3dbd9a6", read(HW))

    def test_it_refuses_a_file_that_is_not_run_33(self):
        m = flat(read(MAIN))
        self.assertIn("info.total_crc32 != AOUT_FIXTURE_CRC", m)
        self.assertIn("(unsigned long)got != AOUT_FIXTURE_BYTES", m)
        self.assertIn("Nothing was played. START = exit", m)

    def test_the_output_is_the_ai_at_32_khz(self):
        m = read(MAIN)
        self.assertIn("AUDIO_SetDSPSampleRate(AI_SAMPLERATE_32KHZ);", m)
        self.assertEqual(define(m, "AOUT_RATE"), "32000u")
        self.assertEqual(int(define(m, "AOUT_CHUNK_FRAMES").rstrip("u")) * 4 % 32, 0)


class TheScreenNeverShowsAFrequency(unittest.TestCase):

    def test_the_frequencies_reach_the_log_only(self):
        m = read(MAIN)
        uses = [l for l in m.splitlines() if "TONE_HZ" in l]
        self.assertTrue(uses)
        for l in uses:
            self.assertFalse(re.search(r"\bprintf\(", l), l)
        body = m[m.index("int main(void)"):]
        for hz in ("128 Hz", "512 Hz", "256 Hz", "1024 Hz"):
            self.assertNotIn(hz, body)
        self.assertIn("TONE 1 of 4", body)


class TheDolphinVariantCannotBeTheConsoleImage(unittest.TestCase):

    def test_embedding_is_gated_and_renamed(self):
        mk = read(MAKEFILE)
        self.assertIn("EMBED ?= 0", mk)
        self.assertIn("BUILD_ID   := aout-0001-dolphin", mk)
        self.assertIn("OUTDIR  := $(ROOT)/build/poc/$(APP_NAME)$(if $(filter 1,$(EMBED)),-dolphin,)", mk)
        self.assertNotIn("fixture_embed", " ".join(srcs()))              # not in the console list
        self.assertIn("ifeq ($(EMBED),1)\nSRCS += fixture_embed.S\nendif", mk)
        self.assertIn(".incbin \"run33-audio.bin\"", read(EMBED_S))

    def test_the_embedded_loader_exists_only_under_the_flag(self):
        m = read(MAIN)
        i, j, k = m.index("#ifdef AOUT_EMBEDDED"), m.index("#else"), m.index("#endif", m.index("#else"))
        self.assertIn("aout_embedded_fixture", m[i:j])
        self.assertNotIn("aout_embedded_fixture", m[j:k])
        self.assertIn("fatMountSimple", m[j:k])
        self.assertIn("DOLPHIN FLOW BUILD", m[i:j])


class ThePreRegistrationStatesTheScopeFirst(unittest.TestCase):
    """§V21: the scope is said before anything else, and the gate is frozen before the run."""

    def part(self):
        t = read(HW)
        i = t.index("\n## V21 — AOUT-HW-001")
        j = t.find("\n## V22 ", i)
        return t[i:] if j < 0 else t[i:j]

    def test_the_scope_leads(self):
        p = flat(self.part())
        first = p[:p.index("### V21.1")]
        self.assertIn("an OUTPUT-PATH test, NOT a Game Boy Player audio test", first)
        self.assertIn("a PASS here is NOT Phase 6's acceptance.", first)
        self.assertIn("The Game Boy Player is not touched.", first)

    def test_the_gate_is_the_operators_ears_and_is_frozen(self):
        p = flat(self.part())
        self.assertIn("\"up, down, up\"", p)
        self.assertIn("PASS four distinct pitches AND \"up, down, up\"", p)
        self.assertIn("A frozen counter is not an audio result.", p)
        # the expected pattern follows from the schedule: 128 -> 512 up, -> 256 down, -> 1024 up
        hz = (128, 512, 256, 1024)
        self.assertEqual(["up" if b > a else "down" for a, b in zip(hz, hz[1:])], ["up", "down", "up"])

    def test_dolphin_is_named_as_not_evidence(self):
        self.assertIn("Dolphin's audio is not evidence of anything", flat(self.part()))


class TheGateIsFrozen(unittest.TestCase):
    """§V21 as committed at 2f14028 is the start of §V21 now: the gate was written before the
    candidate existed, and anything later is appended, never edited in."""

    def test_v21_is_the_frozen_text_at_its_start(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import frozen
        then = frozen.source("Issue #86 -- §V21 pre-registers AOUT-HW-001", "docs/research/HARDWARE_TESTS.md")
        i = then.index("\n## V21 — AOUT-HW-001")
        frozen_part = then[i:]
        now = read(HW)
        j = now.index("\n## V21 — AOUT-HW-001")
        self.assertTrue(now[j:].startswith(frozen_part.rstrip("\n")), "§V21 was edited after it was frozen")


class TheAuditDiscriminatesBothWays(unittest.TestCase):

    def _run(self, out_dir, profile):
        if not os.path.exists(os.path.join(out_dir, "audit", "elf.nm.txt")):
            self.skipTest("%s is not built in this checkout" % out_dir)
        r = subprocess.run([sys.executable, AUDIT, os.path.join(out_dir, "audit"), "--profile", profile],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_aout_passes_this_image(self):
        rc, out = self._run(OUT, "aout")
        self.assertEqual(rc, 0, out[:2000])
        self.assertIn("0 finding(s)", out)

    def test_aout_fails_a_gbp_image(self):
        rc, out = self._run(PLAY_OUT, "aout")
        self.assertNotEqual(rc, 0)
        self.assertIn("forbidden object linked: hsp_backend.o", out)

    def test_play_fails_this_image(self):
        rc, out = self._run(OUT, "play")
        self.assertNotEqual(rc, 0)


def flat(s):
    return re.sub(r"\s+", " ", s)


if __name__ == "__main__":
    unittest.main()
