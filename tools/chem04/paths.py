"""Local CHEM-04 artifact layout. Bulk files stay gitignored."""
from __future__ import annotations

from pathlib import Path

ROOT = Path("artifacts/chem04")
SECONDARY_SEED = ROOT / "secondary_seed"
OFFICIAL_CURRENT = ROOT / "official_current"
JOINS = ROOT / "joins"
MANIFESTS = ROOT / "manifests"
CHECKPOINTS = ROOT / "checkpoints"
CONTENT = ROOT / "content"
CONTENT_SOURCE = CONTENT / "source"
CONTENT_INDEXES = CONTENT / "indexes"
CONTENT_COVERAGE = CONTENT / "coverage"
CONTENT_QUEUES = CONTENT / "queues"
CONTENT_CHECKPOINTS = CONTENT / "checkpoints"
CONTENT_MANIFESTS = CONTENT / "manifests"
CONTENT_REPORTS = CONTENT / "reports"
DECISION = ROOT / "decision"
DECISION_RAW = DECISION / "live_raw"
DECISION_NORMALIZED = DECISION / "normalized"
DECISION_CHECKPOINTS = DECISION / "checkpoints"
DECISION_MANIFESTS = DECISION / "manifests"


def ensure_layout() -> None:
    for path in (
        SECONDARY_SEED,
        OFFICIAL_CURRENT,
        JOINS,
        MANIFESTS,
        CHECKPOINTS,
        CONTENT_SOURCE,
        CONTENT_INDEXES,
        CONTENT_COVERAGE,
        CONTENT_QUEUES,
        CONTENT_CHECKPOINTS,
        CONTENT_MANIFESTS,
        CONTENT_REPORTS,
        DECISION,
        DECISION_RAW,
        DECISION_NORMALIZED,
        DECISION_CHECKPOINTS,
        DECISION_MANIFESTS,
    ):
        path.mkdir(parents=True, exist_ok=True)
