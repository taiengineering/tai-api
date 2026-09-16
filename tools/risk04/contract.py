"""WO-RISK-04 seed review constants. MODEL D and RISK-03 kinds are not revisited."""

from tools.risk02.contract import C_SHA256
from tools.risk03.contract import (
    B_IDENTITY,
    B_LEAF_OCCURRENCE_SUM,
    B_PATH_IDENTITIES,
    B_RAW_ROWS,
    C_OCCURRENCE,
    C_UNIQUE,
    SOURCE_NODE_KIND_TO_CANONICAL,
)
from tools.risk02.contract import A_NODES, SOURCE_CIC_W, SOURCE_KALIS, SOURCE_KOSHA

REVIEW_STATUSES = ("UNREVIEWED", "REVIEW_READY", "HOLD", "REJECT_CANDIDATE")
FORBIDDEN_GENERATOR_STATUSES = ("ACTIVE", "APPROVED")
BATCH_MAX = 100
BATCH_KIND_CAP = 50
SECTOR_HINT = "CONSTRUCTION"
PROPOSED_ORIGIN_TYPE = "PROMOTED_FROM_SOURCE"
SOURCE_INGEST_ORDER = (
    "risk_sources",
    "risk_snapshots",
    "risk_source_nodes",
    "risk_records",
    "risk_snapshot_memberships",
)
CANONICAL_INGEST_ORDER = (
    "risk_canonical_nodes",
    "risk_canonical_node_sectors",
    "risk_source_mappings",
)
REQUIRED_TABLES = SOURCE_INGEST_ORDER + CANONICAL_INGEST_ORDER
C_FILE_SHA256 = C_SHA256
A_NODE_COUNT = A_NODES
B_PROPOSAL_NODES = B_PATH_IDENTITIES
C_TASK_NODES = 761

assert SOURCE_CIC_W and SOURCE_KOSHA and SOURCE_KALIS
assert SOURCE_NODE_KIND_TO_CANONICAL
assert B_IDENTITY == "HOLD"
assert B_LEAF_OCCURRENCE_SUM == 626
assert C_UNIQUE == 30696
assert C_OCCURRENCE == 47559
assert B_RAW_ROWS == 626
