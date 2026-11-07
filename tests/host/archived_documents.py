"""Explicit adapter for legacy assertions against immutable document oracles."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from historical_documents import (  # noqa: E402,F401
    MANIFEST, REVISION, document_bytes, open_document, read_bytes, read_text,
)
