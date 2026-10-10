"""EXT-037 계약 상수 — 화학안전원 화학물질안전정보 수집기.

API 원문: https://apis.data.go.kr/1480802/iciskischem/kischemlist
응답 형식: XML (resultCode "00" = 정상)
인증: DATA_GO_KR_SERVICE_KEY (공통 인증키 풀)
PK 필드명: dataNo (G1 probe 확인)
제공자: 1480802 (NICS — 국가화학물질정보시스템)
"""
from __future__ import annotations

SOURCE_ID = "EXT037_CHEMICAL_SAFETY"
ADAPTER_KEY = "ext037_chemical_safety"
DISPLAY_NAME = "화학안전원 화학물질안전정보"

BASE_URL = "https://apis.data.go.kr/1480802/iciskischem/kischemlist"
PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_ENV = "EXT037_PAGE_SIZE"
MAX_PAGES_SAFETY_CAP = 5000
REQUEST_BUDGET_DEFAULT = 500
REQUEST_BUDGET_ENV = "EXT037_REQUEST_BUDGET"

# Supabase table names
TABLE_SNAPSHOTS = "ext037_chemical_safety_snapshots"
TABLE_ITEMS = "ext037_chemical_safety_snapshot_items"

# Snapshot status values
SNAPSHOT_STAGING = "STAGING"
SNAPSHOT_COMPLETED = "COMPLETED"
SNAPSHOT_FAILED = "FAILED"

# XML field — G1 probe 확인
XML_ITEM_TAG = "item"
XML_FIELD_SOURCE_ID = "dataNo"
