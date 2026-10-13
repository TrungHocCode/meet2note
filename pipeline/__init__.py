"""meet2note pipeline — core domain (root, ADR-0005).

P1 surface: ingest → extract → verify → cli.
"""

from __future__ import annotations

from . import extract, ingest, verify  # noqa: F401

__all__ = ["ingest", "extract", "verify"]