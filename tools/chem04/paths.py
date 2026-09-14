"""Local CHEM-04 artifact layout. Bulk files stay gitignored."""
from __future__ import annotations

from pathlib import Path

ROOT = Path("artifacts/chem04")
SECONDARY_SEED = ROOT / "secondary_seed"
OFFICIAL_CURRENT = ROOT / "official_current"
JOINS = ROOT / "joins"
MANIFESTS = ROOT / "manifests"
CHECKPOINTS = ROOT / "checkpoints"


def ensure_layout() -> None:
    for path in (SECONDARY_SEED, OFFICIAL_CURRENT, JOINS, MANIFESTS, CHECKPOINTS):
        path.mkdir(parents=True, exist_ok=True)
