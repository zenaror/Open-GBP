"""Negative controls for immutable oracles and the live-source boundary."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import archived_documents
import historical_documents as archive
import skip_ledger


class HistoricalDocuments(unittest.TestCase):
    def tearDown(self):
        archive._blob.cache_clear()

    def test_every_pinned_blob_is_available_and_matches(self):
        self.assertEqual(archive.REVISION, 'd358c5e75201dbc45798ab58507fd6c9623f2140')
        for path, digest in archive.MANIFEST['documents'].items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256(archive.document_bytes(path)).hexdigest(), digest)

    def test_digest_corruption_fails(self):
        with self.assertRaisesRegex(AssertionError, 'digest mismatch'):
            archive._blob('AGENTS.md', '0' * 64)

    def test_missing_revision_fails_without_skip(self):
        with patch.object(archive, 'REVISION', '0' * 40):
            with self.assertRaisesRegex(AssertionError, 'revision unavailable'):
                archive._blob('AGENTS.md', '0' * 64)

    def test_unlisted_archive_path_is_refused(self):
        with self.assertRaises(ValueError):
            archive.document_bytes('src/gbp.c')

    def test_oracle_is_read_only(self):
        with self.assertRaises(ValueError):
            archive.open_document(archive.ROOT / 'AGENTS.md', 'w')

    def test_live_source_and_external_namesake_remain_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'AGENTS.md'
            for content in ('first', 'changed'):
                path.write_text(content)
                self.assertEqual(archive.read_text(path), content)
        # A temporary non-oracle source inside the tree must also bypass Git.
        with tempfile.NamedTemporaryFile(dir=archive.ROOT / 'tests', suffix='.c') as tmp:
            tmp.write(b'changed current source'); tmp.flush()
            self.assertEqual(archive.read_bytes(tmp.name), b'changed current source')
        with self.assertRaises(FileNotFoundError):
            archive.read_bytes(archive.ROOT / 'src/nonexistent-public-source.c')

    def test_existing_local_capture_absence_spellings(self):
        for tag in ('run1', 'run2', 'run-1'):
            self.assertEqual(skip_ledger.classify('the %s capture is not on this machine' % tag)[0],
                             'LOCAL_ARTIFACT_ABSENT')
        self.assertIsNone(skip_ledger.classify('a new unknown absence'))
