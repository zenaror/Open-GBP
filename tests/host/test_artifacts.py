"""
Build-artifact checks for poc/smoke-test.

These tests inspect what the Docker/devkitPPC build produced under
build/poc/smoke-test/. They are skipped (with an explicit reason) when the
build has not been run; `make test` at the repository root builds first.

Runs under pytest or `python3 -m unittest`.
"""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import dolinfo  # noqa: E402

POCS = ("smoke-test", "gbp-probe", "gbp-init-probe", "gbp-init-irq-probe", "gbp-init-irq-program-probe")
OUTDIR = os.path.join(ROOT, "build", "poc", "smoke-test")
ELF = os.path.join(OUTDIR, "smoke-test.elf")
DOL = os.path.join(OUTDIR, "smoke-test.dol")
DOL_UNPADDED = os.path.join(OUTDIR, "smoke-test.unpadded.dol")
BUILD_INFO = os.path.join(OUTDIR, "build-info.txt")

# libogc2 GameCube link layout: text begins just above the OS globals area.
EXPECTED_TEXT_BASE = 0x80003100


def read_build_info(path=BUILD_INFO):
    info = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                info[k] = v
    return info


@unittest.skipUnless(os.path.isdir(OUTDIR),
                     "build output missing; run `make build` first")
class SmokeTestArtifacts(unittest.TestCase):
    def test_elf_exists_and_is_powerpc(self):
        self.assertTrue(os.path.isfile(ELF), ELF)
        with open(ELF, "rb") as f:
            hdr = f.read(20)
        self.assertEqual(hdr[:4], b"\x7fELF")
        self.assertEqual(hdr[4], 1, "ELFCLASS32")
        self.assertEqual(hdr[5], 2, "ELFDATA2MSB (big-endian)")
        e_machine = int.from_bytes(hdr[18:20], "big")
        self.assertEqual(e_machine, 20, "EM_PPC")

    def test_dol_exists_and_parses(self):
        self.assertTrue(os.path.isfile(DOL), DOL)
        info = dolinfo.parse_dol_file(DOL)
        self.assertGreaterEqual(len(info.text_sections), 1)
        self.assertGreaterEqual(len(info.data_sections), 1)
        self.assertGreater(info.bss_size, 0)

    def test_dol_entry_and_layout(self):
        info = dolinfo.parse_dol_file(DOL)
        first_text = min(info.text_sections, key=lambda s: s.load_address)
        self.assertEqual(first_text.load_address, EXPECTED_TEXT_BASE)
        entry_sec = info.section_containing(info.entry_point)
        self.assertIsNotNone(entry_sec)
        self.assertEqual(entry_sec.kind, "text")
        # No two sections may overlap in memory.
        spans = sorted((s.load_address, s.end_address) for s in info.sections)
        for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0, "overlapping sections %x-%x / %x-%x" % (a0, a1, b0, b1))

    def test_final_dol_is_dolphin_loadable(self):
        # Dolphin 2606a rejects sections whose address/size are not 32-byte
        # multiples; the build pads elf2dol's output with tools/dolpad.py.
        info = dolinfo.parse_dol_file(DOL)
        self.assertTrue(info.dolphin_loadable,
                        [(s.kind, s.index, hex(s.size)) for s in info.unaligned_sections])
        self.assertTrue(os.path.isfile(DOL_UNPADDED), DOL_UNPADDED)
        raw = dolinfo.parse_dol_file(DOL_UNPADDED)
        # same code, same addresses, only sizes rounded up
        self.assertEqual(raw.entry_point, info.entry_point)
        self.assertEqual([s.load_address for s in raw.sections],
                         [s.load_address for s in info.sections])
        for a, b in zip(raw.sections, info.sections):
            self.assertLessEqual(a.size, b.size)
            self.assertLess(b.size - a.size, 32)

    def test_dol_is_small(self):
        # A hello-world class libogc2 program; guards against accidental bloat.
        size = os.path.getsize(DOL)
        self.assertLess(size, 2 * 1024 * 1024, "DOL unexpectedly large: %d bytes" % size)

    def test_build_info_matches_embedded_identity(self):
        self.assertTrue(os.path.isfile(BUILD_INFO), BUILD_INFO)
        info = read_build_info()
        for key in ("app", "build_id", "commit", "sha256_dol", "cc", "libogc2"):
            self.assertIn(key, info)
        self.assertEqual(info["app"], "smoke-test")
        self.assertRegex(info["build_id"], r"^smoke-\d{4}$")
        self.assertRegex(info["commit"], r"^([0-9a-f]{7,}(-dirty)?|unknown)$")

        marker = ("OPENGBP-IDENT app=%s build=%s commit=%s"
                  % (info["app"], info["build_id"], info["commit"])).encode("ascii")
        with open(DOL, "rb") as f:
            blob = f.read()
        self.assertIn(marker, blob, "identity marker not found in DOL")
        self.assertEqual(blob.count(b"OPENGBP-IDENT "), 1)

    def test_build_info_hash_matches_dol(self):
        import hashlib
        info = read_build_info()
        with open(DOL, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(info["sha256_dol"], digest)

    def test_gecko_protocol_strings_present(self):
        # The Dolphin runner keys on these literals; keep them in sync.
        with open(DOL, "rb") as f:
            blob = f.read()
        self.assertIn(b"OPENGBP-SMOKE READY ", blob)
        self.assertIn(b"OPENGBP-SMOKE HEARTBEAT n=", blob)

    def test_libogc_version_recorded(self):
        info = read_build_info()
        self.assertTrue(re.match(r"^libogc2 r\d+\.[0-9a-f]+$", info["libogc2"]), info["libogc2"])


@unittest.skipUnless(all(os.path.isdir(os.path.join(ROOT, "build", "poc", p)) for p in POCS),
                     "build output missing; run `make build` first")
class EveryPocArtifacts(unittest.TestCase):
    """Common checks for every POC: valid, Dolphin-loadable DOL, identity
    marker, hash, and the READY line prefix the Dolphin runner keys on."""

    def test_each_poc(self):
        for poc in POCS:
            out = os.path.join(ROOT, "build", "poc", poc)
            dol = os.path.join(out, poc + ".dol")
            info = dolinfo.parse_dol_file(dol)
            self.assertTrue(info.dolphin_loadable, poc)
            self.assertEqual(info.entry_point, 0x80003100, poc)
            bi = read_build_info(os.path.join(out, "build-info.txt"))
            self.assertEqual(bi["app"], poc)
            with open(dol, "rb") as f:
                blob = f.read()
            marker = ("OPENGBP-IDENT app=%s build=%s commit=%s" % (bi["app"], bi["build_id"], bi["commit"])).encode()
            self.assertIn(marker, blob, poc)
            prefix = {"smoke-test": b"OPENGBP-SMOKE READY ", "gbp-probe": b"OPENGBP-PROBE READY ",
                      "gbp-init-probe": b"OPENGBP-INIT READY ",
                      "gbp-init-irq-probe": b"OPENGBP-INITIRQ READY ",
                      "gbp-init-irq-program-probe": b"OPENGBP-INITIRQA READY "}[poc]
            self.assertIn(prefix, blob, poc)

    def test_probe_writes_only_documented_things(self):
        # The probe binary must not contain the strings of features it must not touch.
        dol = os.path.join(ROOT, "build", "poc", "gbp-probe", "gbp-probe.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertIn(b"GBP-PROBE-001", blob)
        self.assertIn(b"OPENGBP-PROBE READY ", blob)
        self.assertNotIn(b"libmobile", blob)

    def test_init_irq_probe_identity_and_records(self):
        # GBP-INIT-002: its own test id, its own gecko prefix, the record
        # kinds the log tooling and the fixture tests key on.
        dol = os.path.join(ROOT, "build", "poc", "gbp-init-irq-probe", "gbp-init-irq-probe.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertIn(b"GBP-INIT-002", blob)
        self.assertNotIn(b"GBP-INIT-001", blob)
        self.assertIn(b"OPENGBP-INITIRQ READY ", blob)
        for rec in (b"INITIRQ start ", b"INITIRQ end status=", b"IRQ install rc=", b"UNMASK t_unmask=",
                    b"HANDLER fired=", b"HANDLERPI intsr_before_ack=", b"CLEANUP performed=", b"MASK final intmr="):
            self.assertIn(rec, blob, rec)
        self.assertNotIn(b"libmobile", blob)

    def test_init_irq_program_probe_identity_and_records(self):
        # GBP-INIT-003A: its own test id and gecko prefix; the record kinds the
        # log tooling keys on; none of the GBP-INIT-002 interrupt-path records
        # (that probe module and hsp_backend_irq.c must not be linked); the
        # mandatory power-cycle banner.
        dol = os.path.join(ROOT, "build", "poc", "gbp-init-irq-program-probe", "gbp-init-irq-program-probe.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertIn(b"GBP-INIT-003A", blob)
        self.assertNotIn(b"GBP-INIT-002", blob)
        self.assertNotIn(b"GBP-INIT-001", blob)
        self.assertIn(b"OPENGBP-INITIRQA READY ", blob)
        for rec in (b"INITIRQA start ", b"INITIRQA end status=", b"IRQSHAPE tag=", b"IRQW ", b"layout=gbi-u16-replicated",
                    b"SNAP tag=", b"WINDOW tag=", b"REGION log_count_start=", b"TEARDOWN start", b"IRQSTOP pre ",
                    b"comment=startup-disc-stop-shadow", b"CLEANUP performed=", b"RESTORE control_restore_ok=",
                    b"WRITES control_written=", b"OBSERVED intsr13_seen=", b"format=attempted/completed",
                    b"DEVICE STATE UNCERTAIN", b"POWER CYCLE REQUIRED"):
            self.assertIn(rec, blob, rec)
        for rec in (b"IRQ install rc=", b"UNMASK t_unmask=", b"HANDLER fired=", b"HANDLERPI intsr_before_ack=",
                    b"MASK final intmr=", b"INITIRQ start ", b"INIT start "):
            self.assertNotIn(rec, blob, rec)
        self.assertNotIn(b"libmobile", blob)
        bi = read_build_info(os.path.join(ROOT, "build", "poc", "gbp-init-irq-program-probe", "build-info.txt"))
        self.assertEqual(bi["build_id"], "initirqa-0001")


if __name__ == "__main__":
    unittest.main()
