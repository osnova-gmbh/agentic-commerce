"""Make every package of this repository importable for the end-to-end tests.

The tests need the third-party dependencies and the Cogit cohort installed (the wheels
vendored under packages/cogit-finance/vendor/wheels), nothing else: sources are read
straight from the repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_SOURCES = [
    REPO / "packages" / "cogit-finance-seams" / "src",
    REPO / "packages" / "cogit-messaging-shim" / "src",
    *sorted((REPO / "modules").glob("*/src")),
    *sorted((REPO / "apps").glob("*/src")),
    REPO / "packages" / "cogit-finance" / "src",
    *sorted((REPO / "agents").glob("*/src")),
    Path(__file__).resolve().parent,
]
for source in _SOURCES:
    if source.is_dir() and str(source) not in sys.path:
        sys.path.insert(0, str(source))
