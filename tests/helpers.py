"""Test helpers. Fixtures are real HTTP responses captured 2026-09-08/09, stored gzipped."""
import gzip
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def fixture(name):
    """Return the decompressed text of tests/fixtures/<name>.gz."""
    path = os.path.join(HERE, "fixtures", name + ".gz")
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        return f.read()
