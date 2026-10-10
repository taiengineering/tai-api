"""EXT-132 계약 상수 — 소방청 위험물안전관리 수집기.

API 원문: https://apis.data.go.kr/1661000/materialInfoSvc/getMaterialList
응답 형식: XML
인증: DATA_GO_KR_SERVICE_KEY (공통 인증키 풀)
페이지 크기: 초기값 10, 실제 최대 미검증(UNVERIFIED)
"""
from __future__ import annotations

SOURCE_ID = "EXT132_HAZARDOUS_MATERIAL"
ADAPTER_KEY = "ext132_hazardous_material"
DISPLAY_NAME = "소방청 위험물안전관리"

BASE_URL = "https://apis.data.go.kr/1661000/materialInfoSvc/getMaterialList"
PAGE_SIZE_DEFAULT = 10          # UNVERIFIED: actual API max not confirmed
PAGE_SIZE_ENV = "EXT132_PAGE_SIZE"
MAX_PAGES_SAFETY_CAP = 5000     # hard upper bound; actual record count unknown
REQUEST_BUDGET_DEFAULT = 500
REQUEST_BUDGET_ENV = "EXT132_REQUEST_BUDGET"

# Supabase table names
TABLE_SNAPSHOTS = "ext132_hazardous_material_snapshots"
TABLE_ITEMS = "ext132_hazardous_material_snapshot_items"

# Snapshot status values
SNAPSHOT_STAGING = "STAGING"
SNAPSHOT_COMPLETED = "COMPLETED"
SNAPSHOT_FAILED = "FAILED"

# XML field mapping (source key → local field name)
# Field names are UNVERIFIED until first sample response observed
XML_ITEM_TAG = "item"
XML_FIELD_SOURCE_ID = "chemicalno"   # unique key per WO-001A-R2 spec
