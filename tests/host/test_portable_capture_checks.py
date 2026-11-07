"""Portable history checks keep the original assertions and reject missing support."""
import artifacts
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import key_order_fixtures as key
import test_run21_run22 as runs
import test_staged_artifacts as staged


class KeyOrderExcerpts(unittest.TestCase):
    def test_each_public_excerpt_is_pinned_and_required(self):
        entries = key.manifest()['runs']
        self.assertEqual(set(entries), {'21', '22', '25', '26'})
        for number, entry in entries.items():
            n = int(number)
            with self.subTest(run=n):
                self.assertEqual((entry['source_sha256'], entry['source_bytes']), runs.HASHES[n])
                text = key.read_excerpt(n)
                self.assertTrue(text)
                if n in (21, 22):
                    self.assertEqual(len(text.splitlines()), 1)

    def test_optional_originals_reproduce_exact_excerpts(self):
        entries = key.manifest()['runs']
        sources = {key.ROOT / entry['source']: (int(n), entry) for n, entry in entries.items()}
        for original in artifacts.any_of(self, list(sources),
                                        'no local archive on this host (captures/local is ignored)'):
            n, entry = sources[original]
            raw = original.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry['source_sha256'])
            self.assertEqual(key.extract(raw, n), key.read_excerpt(n).encode())

    def test_missing_public_excerpt_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(key.FIXTURES / 'manifest.json', tmp)
            with patch.object(key, 'FIXTURES', Path(tmp)):
                with self.assertRaises(FileNotFoundError):
                    key.read_excerpt(25)

    def test_changed_public_excerpt_fails(self):
        entry = key.manifest()['runs']['25']
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(key.FIXTURES / 'manifest.json', tmp)
            raw = (key.FIXTURES / entry['file']).read_bytes()
            (Path(tmp) / entry['file']).write_bytes(b'X' + raw[1:])
            with patch.object(key, 'FIXTURES', Path(tmp)):
                with self.assertRaisesRegex(AssertionError, 'integrity mismatch'):
                    key.read_excerpt(25)


class StagingBoundary(unittest.TestCase):
    def test_empty_staging_has_no_index_but_still_checks_recorded_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(staged, 'SWISS', tmp), patch.object(staged, 'INDEX', str(Path(tmp) / 'INDEX.txt')):
                self.assertEqual(staged.index_rows(), {})
                test = staged.TheStagedImagesAreWhatTheRecordsName('test_a_rebuilt_slot_is_never_mistaken_for_the_executed_image')
                result = unittest.TestResult(); test.run(result)
                self.assertEqual((result.failures, result.errors, result.skipped), ([], [], []))

    def test_staged_bytes_without_an_index_are_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / '11-color'; slot.mkdir(); (slot / 'boot.dol').write_bytes(b'rebuilt')
            with patch.object(staged, 'SWISS', tmp), patch.object(staged, 'INDEX', str(Path(tmp) / 'INDEX.txt')):
                with self.assertRaises(FileNotFoundError):
                    staged.index_rows()

    def test_rebuilt_bytes_claiming_the_executed_commit_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / '11-color'; slot.mkdir(); (slot / 'boot.dol').write_bytes(b'rebuilt')
            with patch.object(staged, 'SWISS', tmp), patch.object(staged, 'index_rows', return_value={
                '11-color': {'status': 'UNPINNED-COPY', 'commit': staged.EXECUTED['11-color'][2]}}):
                test = staged.TheStagedImagesAreWhatTheRecordsName('test_a_rebuilt_slot_is_never_mistaken_for_the_executed_image')
                result = unittest.TestResult(); test.run(result)
                self.assertEqual(len(result.failures), 1)
                self.assertEqual(result.errors, [])
