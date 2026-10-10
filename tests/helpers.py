"""Test helpers.

Fixtures are real HTTP responses captured in September 2026 and stored gzipped. Page captures
(YouTube, X timelines, GitHub trending) go through fixtures/minimize.py before they are
committed, which keeps only the block the parser reads and blanks the requester's address and
visitor ids. test_fixtures_clean.py fails if a raw capture slips in.
"""
import gzip
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def fixture(name):
    """Return the decompressed text of tests/fixtures/<name>.gz."""
    path = os.path.join(HERE, "fixtures", name + ".gz")
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        return f.read()
