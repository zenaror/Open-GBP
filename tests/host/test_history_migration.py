"""Issue #164: mapped identities preserve pins, trees and collision rejection."""
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import unittest
import frozen
import guards

class HistoryMigration(unittest.TestCase):
    def test_all_recorded_trees_and_recovery_are_exact(self):
        rows = json.loads((Path(guards.ROOT) / "docs/maintenance/ai-coauthor-2026-10-12.json").read_text())["mapping"]
        self.assertEqual(len(rows), 624)
        self.assertEqual(sum(len(r["removed"]) for r in rows), 587)
        subprocess.run(["python3", str(Path(guards.ROOT) / "tools/history_recover.py")], check=True, capture_output=True)
        for row in rows:
            trees = subprocess.check_output(["git", "-C", guards.ROOT, "rev-parse", row["old"] + "^{tree}", row["new"] + "^{tree}"]).splitlines()
            self.assertEqual(trees[0], trees[1])

    def test_original_pin_is_retained_and_collisions_still_fail(self):
        phrase = next(iter(frozen.BASES))
        original = frozen.BASES[phrase]
        self.assertEqual(frozen.base(phrase), original)
        with patch.object(frozen, "_matches", return_value=[original, original]):
            with self.assertRaisesRegex(AssertionError, "now matches 2 commits"):
                frozen.base(phrase)
        with patch.object(frozen, "_matches", return_value=["0" * 40]):
            with self.assertRaisesRegex(AssertionError, "but this module pins"):
                frozen.base(phrase)
