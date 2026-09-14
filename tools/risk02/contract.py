"""WO-RISK-02 frozen source catalog constants. MODEL D roles are not revisited."""

SOURCE_CIC_W = "CIC_W"
SOURCE_KOSHA = "KOSHA_CONSTRUCTION_PROCESS"
SOURCE_KALIS = "KALIS_RISK_PROFILE"

ROLE_A = "REFERENCE_CLASSIFICATION"
ROLE_B = "USEFUL_BRIDGE"
ROLE_C = "RISK_CONTEXT_SOURCE"

C_HEADERS = (
    "시설물분류(대)",
    "시설물분류(중)",
    "시설물분류(소)",
    "공종분류(대)",
    "공종분류(중)",
    "위험발생객체분류(대)",
    "위험발생객체분류(중)",
    "위험발생위치분류(대)",
    "위험발생위치코드(중)",
    "위험발생위치분류(중)",
    "위험발생위치분류(소)",
    "작업프로세스명",
    "물적피해",
    "인적피해",
    "사고원인",
    "사고가능성",
    "사고심각성",
    "설계단계",
    "시공단계",
)

B_HEADERS = ("번호", "공사종류", "공종명", "세부공정명")

A_SHA256 = "bef821019cd32ad9512f865d179852652d1f7aa9536be41b68c6e403fe0baa29"
B_SHA256 = "8e98fbb66d9e152a03425338d27fc738172cdf6dd5d46a36e7a5a06d80012b91"
C_SHA256 = "399dbe64dcf1b5d1445fd51e968070dd26e0a40583f8e0afc5e9219839c958c8"

C_RAW_ROWS = 47559
C_UNIQUE_CONTENT = 30696
C_DUPLICATE_GROUPS = 5730
C_DUPLICATE_EXTRAS = 16863
B_ROWS = 626
A_NODES = 1722

C_PORTAL_ROW_FIELD = 41239
C_LEGACY_PROSE_COUNT = 55546
C_CURRENT_PROSE = "approximately 47000"

HASH_JOIN = "\u241f"
