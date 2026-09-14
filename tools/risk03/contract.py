"""WO-RISK-03 frozen canonical and mapping constants. MODEL D is not revisited."""

from tools.risk02.contract import (
    B_ROWS,
    C_RAW_ROWS,
    C_UNIQUE_CONTENT,
    SOURCE_CIC_W,
    SOURCE_KALIS,
    SOURCE_KOSHA,
)

PHYSICAL_MODEL_DECISION = "NEW_RISK_CANONICAL"
INSTANCE_VS_CANONICAL = "PASS"

EXISTING_PROCESS_TASK_OBJECTS = (
    ("companies", "INSTANCE", "tenant root"),
    ("factories", "INSTANCE", "사업장"),
    ("factory_process", "INSTANCE", "factory-scoped registered process"),
    ("construction_sites", "INSTANCE", "site"),
    ("construction_site_processes", "INSTANCE", "site-scoped process row"),
    ("construction_works", "INSTANCE", "PTW / work occurrence"),
    ("inspection_sets", "INSTANCE", "factory inspection set"),
    ("work_schedules", "INSTANCE", "factory inspection schedule"),
    ("runtime_task", "INSTANCE", "tenant/facility obligation execution"),
    ("task_candidate", "INSTANCE", "factory-scoped legal compiler draft"),
    ("risk_assessments", "INSTANCE", "SaaS 위험성평가 document"),
    ("ksic_process_map", "SECTOR_SOURCE_MASTER", "manufacturing KSIC process map"),
    ("kcsc_process_master", "SECTOR_SOURCE_MASTER", "KCSC construction process"),
    ("kcsc_work_master", "SECTOR_SOURCE_MASTER", "KCSC work items"),
    ("risk_source_nodes", "SOURCE_NATIVE", "A/B/C source taxonomy, not TAI canonical"),
    ("risk_records", "SOURCE_CONTENT", "KALIS content linked to C TASK nodes"),
)

NODE_KINDS = ("PROCESS", "TASK")
CANONICAL_STATUSES = ("DRAFT", "ACTIVE", "RETIRED")
ORIGIN_TYPES = ("TAI_NATIVE", "PROMOTED_FROM_SOURCE", "MERGED_FROM_REVIEWED_SOURCES")
SECTOR_EXAMPLES = ("BUILDING", "MANUFACTURING", "CONSTRUCTION")

MAPPING_TYPES = (
    "EXACT_EQUIVALENT",
    "PARENT_CHILD",
    "BROADER_THAN",
    "NARROWER_THAN",
    "POSSIBLE_RELATED",
    "NO_MATCH",
    "AMBIGUOUS",
)
MAPPING_STATUSES = ("PROPOSED", "APPROVED", "REJECTED", "HOLD")
MAPPING_METHODS = ("EXACT_PATH", "EXACT_NAME", "MANUAL_REVIEW")
CANDIDATE_CLASSES = (
    "EXACT_PATH_CANDIDATE",
    "EXACT_NAME_CANDIDATE",
    "AMBIGUOUS",
    "UNMATCHED",
)
CONSUMER_ELIGIBLE_STATUS = "APPROVED"

SOURCE_NODE_KIND_TO_CANONICAL = {
    "W_ROOT": "PROCESS",
    "W_MID": "PROCESS",
    "W_LEAF": "PROCESS",
    "PROJECT_KIND": "PROCESS",
    "WORK_TYPE": "PROCESS",
    "DETAIL_PROCESS": "TASK",
    "WORK_BIG": "PROCESS",
    "WORK_MID": "PROCESS",
    "TASK": "TASK",
}

B_IDENTITY = "HOLD"
B_PATH_IDENTITIES = 620
B_LEAF_OCCURRENCE_SUM = 626
C_UNIQUE = C_UNIQUE_CONTENT
C_OCCURRENCE = C_RAW_ROWS
B_RAW_ROWS = B_ROWS

# Synthetic fixture IDs. Not production seed. Not source-derived.
FIXTURE_PROCESS_ID = "aaaaaaaa-1111-4111-8111-000000000001"
FIXTURE_TASK_ID = "bbbbbbbb-2222-4222-8222-000000000002"
FIXTURE_TASK_ALT_ID = "cccccccc-3333-4333-8333-000000000003"

assert SOURCE_CIC_W and SOURCE_KOSHA and SOURCE_KALIS
