"""Scenario generator: health-metric descriptors -> precomputed scenario buffer.

Submodules
----------
- ``descriptors``  : health-metric dimensions/levels (mood, hunger, sleep, ...)
- ``references``   : curated peer-reviewed reference registry (Zotero-first)
- ``mapping``      : descriptor -> engine-free-parameter physiological mapping
- ``db``           : DuckDB schema + population + query methods
- ``zotero``       : local Zotero library enrichment (optional)
"""

from __future__ import annotations

__version__ = "0.1.1"

from scenariogen import descriptors, mapping, references  # noqa: E402,F401
from scenariogen import db  # noqa: E402,F401
from scenariogen import zotero  # noqa: E402,F401

__all__ = ["descriptors", "mapping", "references", "db", "zotero", "__version__"]