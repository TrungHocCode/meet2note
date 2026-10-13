"""meet2note pipeline — core domain (root, ADR-0005).

P3 surface: ingest → extract → resolve → verify → export → cli.
"""

from __future__ import annotations

from . import extract, export, ingest, resolve, verify  # noqa: F401

__all__ = ["ingest", "extract", "resolve", "verify", "export"]