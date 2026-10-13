"""meet2note pipeline — core domain (root, ADR-0005).

P2 surface: ingest → extract → resolve → verify → cli.
"""

from __future__ import annotations

from . import extract, ingest, resolve, verify  # noqa: F401

__all__ = ["ingest", "extract", "resolve", "verify"]