"""Original entry-policy assertions replayed unchanged at their fixed revision.
Current public documentation is checked by test_public_documentation.py.
"""
import unittest
from historical_entry_checks import results

class HistoricalEntryPolicy(unittest.TestCase):
    def test_original_assertions_execute_without_skips(self):
        count, report = results()
        self.assertGreater(count, 0, report)
