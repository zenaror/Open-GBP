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
    # Issue #88: the third pinned slot, which this dict had not carried
    "14-audio": ("c3281a8c1382a1136a881c5548ef8238d69fa7862861d66741310b3d1f5f9c54", HW,
                 "stream-0016 @ 04121fe, staged under Hardware Issue #61; RUN 33, 34 and 35 executed it"),
    # 2026-09-23: the one sitting the Operator decided on (§V19.12, §V21.4)
    "15-drain": ("4c80ab8a34d9260793e036beda513a9a23be86d04c61c0d653c6f79fc7333884", HW,
                 "drain-0001 @ 897ea6c, GBP-AUDIO-005, staged for its first run"),
    "16-aout": ("161492325661ffc63288c33712dcf7be98554828581e3d8e4564d0381b13ba90", HW,
                "aout-0001 @ 2f14028, AOUT-HW-001, staged for its first run"),
}

# Issue #83, pattern H: A RECORD THAT CERTIFIES ITSELF.
#
# build/swiss/INDEX.txt is written by the same `make swiss` that writes the slots, so a
# slot agreeing with INDEX.txt proves only that the export was self-consistent. For the
# two slots above the documents carry the hash, so the check has an outside authority.
# 11-color does NOT: the image that was PHYSICALLY EXECUTED is recorded (§V4.10) and the
# slot on this host is a later rebuild, whose hash appears in no document at all.
#
# So the property that can be checked, and is, is the one §V3.28's own IDENTITY WARNING
# states: a rebuilt DOL must never be mistaken for the tested artifact. Either the slot
# IS the executed image, or INDEX.txt names a commit that is NOT the executed one.
#
# slot -> (sha256 of the image physically executed, the document, its commit, its size)
EXECUTED = {
    "11-color": ("d3c1f09efb105a0027d3bc596528448c579a234cbbe8306469d7f1222cbf29c1", HW, "39f1980", 442592),
    # Issue #88 (2026-09-23): the same property for every slot whose record carries the executed
    # image's hash and commit. On that date slots 01-11 all held rebuilds exported at 7d7a6d8; a
    # record that writes the hash abbreviated ("head…tail") is matched in that form, and a size the
    # record does not carry is None.
    "10-vstate": ("b0ed33f06e257d1e775d382f86116a59b756d90b528c0be3f233e086d00597c5", HANDOFF, "b017e38", None),
    "09-video": ("856d3e91…fd65", HW, "6930dde", None),
}


def same_image(got, want):
    """`want` is a full hash, or the abbreviated head…tail form a record writes."""
    if "…" in want:
        head, tail = want.split("…")
        return got.startswith(head) and got.endswith(tail)
    return got == want

# the preserved originals, whose hashes the documents carry in full
# file under build/archive/ -> (sha256, the document that names it, size, what it is)
ARCHIVE = {
    "gbp-video-stream-probe-stream-0013-7d7a6d8.dol":
        ("5391c3fe962dc4b2f4e493f3846ac7407ded064c58f5d4bb583a51e5a725dd79", HW, 506496,
         "stream-0013 @ 7d7a6d8, the image RUN 12 and RUN 13 executed, preserved before stream-0014 was staged"),
    "gbp-video-stream-probe-stream-0014-0ff8355.dol":
        ("ef76a170c10d335e62c017e53f74c60e410e44f5ce2fbca6774ab43c68ec0b9c", HANDOFF, 513152,
         "stream-0014 @ 0ff8355, the image RUN 14 / RUN 15 executed, preserved under Hardware Issue #32"),
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
    """The rows of build/swiss/INDEX.txt, read by the exporter's OWN row pattern (Issue #88
    added the STATUS column; one pattern, so the reader and the writer cannot drift)."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import swiss_export
    rows = {}
    for line in read(INDEX).splitlines():
        m = swiss_export.INDEX_ROW_RE.match(line)
        if m:
            rows[m.group(1)] = {"test_id": m.group(2), "build_id": m.group(3), "commit": m.group(4),
                                "size": int(m.group(5)), "sha256": m.group(6), "status": m.group(7),
                                "source": m.group(8)}
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

    def test_the_preserved_archives_are_the_documented_bytes(self):
        """Issue #83 (H). build/archive/ was pinned by NOTHING: the ledger's stated cover for
        the identity skips is test_staged_artifacts.py, and it did not reach the archive at
        all. The hash must be in the document whether or not the file is on this host, so the
        first half of this test never skips."""
        for name, (want, doc, size, what) in sorted(ARCHIVE.items()):
            self.assertIn(want, read(doc),
                          "%s's hash is not in %s any more; the records moved and this test did not"
                          % (name, os.path.relpath(doc, ROOT)))
        present = [n for n in ARCHIVE if os.path.isfile(os.path.join(ROOT, "build", "archive", n))]
        if not present:
            self.skipTest("no preserved archive is in this checkout (build/ is not versioned)")
        for name in sorted(present):
            want, _doc, size, what = ARCHIVE[name]
            p = os.path.join(ROOT, "build", "archive", name)
            self.assertEqual((os.path.getsize(p), sha256(p)), (size, want),
                             "THE PRESERVED ORIGINAL %s IS NOT THE IMAGE THE RECORDS NAME (%s)" % (name, what))

    def test_a_rebuilt_slot_is_never_mistaken_for_the_executed_image(self):
        """Issue #83 (H), the self-certifying half. 11-color's only authority is INDEX.txt,
        written by the same export that wrote the slot. What an outside record does fix is the
        image that was PHYSICALLY EXECUTED, so the checkable property is §V3.28's own identity
        warning: the staged bytes are either that image, or INDEX.txt names a different commit.
        A re-export that kept the executed commit's name on different bytes fails here."""
        slots = staged_slots(SWISS)
        rows = index_rows()
        for slot, (want, doc, commit, size) in sorted(EXECUTED.items()):
            self.assertIn(want, read(doc), "%s's EXECUTED identity left %s" % (slot, os.path.relpath(doc, ROOT)))
            if slot not in slots:
                continue
            got = sha256(slots[slot])
            if same_image(got, want):
                if size is not None:
                    self.assertEqual(os.path.getsize(slots[slot]), size)
                continue
            self.assertIn(slot, rows, "slot %s is staged, is NOT the executed image, and INDEX.txt does not "
                                      "record what it is" % slot)
            if rows[slot].get("status"):
                self.assertEqual(rows[slot]["status"], "UNPINNED-COPY",
                                 "build/swiss/%s is NOT the executed image, yet INDEX.txt marks it %s"
                                 % (slot, rows[slot]["status"]))
            self.assertNotEqual(rows[slot]["commit"], commit,
                                "build/swiss/%s holds bytes that are NOT the executed image (%s), yet INDEX.txt "
                                "still names the commit that was executed (%s). A rebuilt DOL must never carry "
                                "the tested artifact's identity (§V3.28)." % (slot, got[:12], commit))

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
