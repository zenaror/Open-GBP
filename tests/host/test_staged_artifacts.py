"""
tests/host/test_staged_artifacts.py — what is STAGED is what the records name
(GitHub Issue #29, the third instance's answer).

WHY THIS FILE EXISTS. `build/swiss/NN-slot/boot.dol` and its copy on the
Operator's SD are the files a physical run actually boots. Until now the suite
checked the identities of things in `build/poc/`, and those checks SKIP as soon
as a later checkpoint rebuilds a POC at its own commit — which is precisely the
moment a staged image could be disturbed. On 2026-09-21 five such guards went
quiet in the same commit that made the risk possible, and a person, not the
suite, verified that `12-stream` still held `stream-0015`.

THE RULE HERE IS THE OPPOSITE ONE: when something IS staged, this test checks
it and FAILS if it cannot. It skips only when there is nothing staged at all,
which is a "nothing to check", not a "cannot check".

WHAT IT CHECKS
  * every staged slot hashes to what `build/swiss/INDEX.txt` recorded for it,
    and every recorded row has its slot: the export is self-consistent, so a
    slot rewritten by a later build cannot sit there unnoticed;
  * slots the RECORDS freeze — `12-stream` = `stream-0015` (Hardware Issue #32;
    §V7.6.5 requires it untouched) and `13-play` = `play-0001` (§V7.6.8) —
    hash to the documented value, AND that value is quoted from the documents
    in the same run, so this test and the records cannot drift apart;
  * the same, on the SD, when the SD is mounted on this host.

WHAT IT DOES NOT DO. It does not build, export, copy or repair anything, and it
never writes to `build/swiss/` or to the SD. A mismatch is reported, never
fixed: a staged artifact that differs from its record is a finding for a person.
"""
import hashlib
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SWISS = os.path.join(ROOT, "build", "swiss")
INDEX = os.path.join(SWISS, "INDEX.txt")
SD = "/media/rafael/SD_GC/Open-GBP"
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")

# slot -> (sha256 the records name, the document that names it, what it is)
FROZEN = {
    "12-stream": ("dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49", HW,
                  "stream-0015 @ da06500, staged under Hardware Issue #32; RUN 16/17/18 executed it and §V7.6.5 "
                  "requires it untouched"),
    "13-play": ("d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de", HW,
                "play-0001 @ 2e48ca7, staged under Hardware Issue #43 for RUN 21 / RUN 22 (§V7.6.8)"),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def index_rows():
    rows = {}
    for line in read(INDEX).splitlines():
        m = re.match(r"^(\S+)\s+\|\s+(\S+)\s+\|\s+(\S+)\s+\|\s+(\S+)\s+\|\s+(\d+)\s+\|\s+([0-9a-f]{64})\s+\|\s+(\S+)\s*$", line)
        if m:
            rows[m.group(1)] = {"test_id": m.group(2), "build_id": m.group(3), "commit": m.group(4),
                                "size": int(m.group(5)), "sha256": m.group(6), "source": m.group(7)}
    return rows


def staged_slots(base):
    if not os.path.isdir(base):
        return {}
    out = {}
    for d in sorted(os.listdir(base)):
        dol = os.path.join(base, d, "boot.dol")
        if os.path.isfile(dol):
            out[d] = dol
    return out


class TheStagedImagesAreWhatTheRecordsName(unittest.TestCase):
    def test_every_staged_slot_holds_what_the_records_name(self):
        slots = staged_slots(SWISS)
        if not slots:
            self.skipTest("nothing is staged under build/swiss, so no staged artifact can be disturbed")
        # an index is not optional once something is staged: without it nothing can be verified, and
        # "cannot verify" is a failure here, not a skip
        self.assertTrue(os.path.isfile(INDEX),
                        "%d slot(s) are staged and build/swiss/INDEX.txt is missing: what is on the card cannot be "
                        "verified against anything. Re-export or restore the index." % len(slots))
        rows = index_rows()
        self.assertTrue(rows, "build/swiss/INDEX.txt parses to no rows; the staged slots cannot be verified")
        for slot, dol in sorted(slots.items()):
            self.assertIn(slot, rows, "slot %s is staged but is not in INDEX.txt" % slot)
            got, want = sha256(dol), rows[slot]["sha256"]
            self.assertEqual(got, want, "STAGED SLOT %s DIFFERS FROM WHAT THE EXPORT RECORDED.\n"
                                        "  on disk  %s\n  INDEX    %s (%s @ %s)\n"
                                        "This is the file a physical run boots. Do not re-export to make this pass: "
                                        "find out which image is there." % (slot, got, want, rows[slot]["build_id"], rows[slot]["commit"]))
            self.assertEqual(os.path.getsize(dol), rows[slot]["size"], slot)
        for slot in rows:
            self.assertIn(slot, slots, "INDEX.txt records slot %s but nothing is staged there" % slot)

    def test_the_frozen_slots_hash_to_the_documented_value(self):
        slots = staged_slots(SWISS)
        if not slots:
            self.skipTest("nothing is staged under build/swiss, so no staged artifact can be disturbed")
        for slot, (want, doc, what) in sorted(FROZEN.items()):
            # the test may not drift from the records: the hash must be quoted in the document that freezes it
            self.assertIn(want, read(doc), "%s's frozen hash is not in %s any more; the records moved and this test "
                                           "did not" % (slot, os.path.relpath(doc, ROOT)))
            if slot not in slots:
                continue          # not staged here; the slot that IS staged is checked above
            got = sha256(slots[slot])
            self.assertEqual(got, want, "STAGED SLOT %s IS NOT THE IMAGE THE RECORDS NAME (%s).\n"
                                        "  on disk  %s\n  records  %s" % (slot, what, got, want))

    def test_the_sd_carries_the_same_images(self):
        if not os.path.isdir(SD):
            self.skipTest("the SD is not mounted on this host (%s); nothing staged there can be checked" % SD)
        slots = staged_slots(SD)
        self.assertTrue(slots, "the SD is mounted at %s and holds no slot with a boot.dol" % SD)
        local = staged_slots(SWISS)
        for slot, dol in sorted(slots.items()):
            got = sha256(dol)
            if slot in FROZEN:
                want, _doc, what = FROZEN[slot]
                self.assertEqual(got, want, "THE SD'S %s IS NOT THE IMAGE THE RECORDS NAME (%s): %s" % (slot, what, got))
            if slot in local:
                self.assertEqual(got, sha256(local[slot]),
                                 "the SD's %s differs from build/swiss/%s: the card and the local staging disagree" % (slot, slot))

    def test_no_console_log_is_left_on_the_sd_before_a_run(self):
        """§V7.6.8's SD-state gate, checked where the file would be."""
        if not os.path.isdir(SD):
            self.skipTest("the SD is not mounted on this host (%s); nothing staged there can be checked" % SD)
        leftovers = [f for f in os.listdir(SD) if f.lower().endswith(".log")]
        self.assertEqual(leftovers, [], "a console log is on the SD before a run: %s. §V7.6.8: MOVE IT ASIDE, never "
                                        "delete it, and report it; it is a previous run's artifact." % leftovers)


if __name__ == "__main__":
    unittest.main()
