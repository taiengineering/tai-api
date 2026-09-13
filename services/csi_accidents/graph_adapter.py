"""CSI Graph eligibility helper. Production Graph write path stays closed."""
from __future__ import annotations

GRAPH_WRITES_OPEN = False
KOSHA_ACCIDENT_SOURCE = "KOSHA"
CSI_SOURCE = "CSI"


def is_csi_content_id(content_id: str) -> bool:
    return content_id.startswith("CSI:")


def graph_eligible(*, snapshot_status: str, identity_status: str, latest_completed: bool) -> bool:
    return (
        latest_completed
        and snapshot_status == "COMPLETED"
        and identity_status == "READY"
    )
