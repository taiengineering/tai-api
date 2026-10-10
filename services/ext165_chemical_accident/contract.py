"""EXT-165 계약 상수 — 화학물질안전원 화학사고 수집기.

API 원문: https://apis.data.go.kr/1480802/iciscsc/csclist
응답 형식: XML
인증: DATA_GO_KR_SERVICE_KEY (공통 인증키 풀)
페이지 크기: 초기값 10, 실제 최대 미검증(UNVERIFIED)
선택 파라미터: yyyy (연도 필터, 예: "2024")
"""
from __future__ import annotations

SOURCE_ID = "EXT165_CHEMICAL_ACCIDENT"
ADAPTER_KEY = "ext165_chemical_accident"
DISPLAY_NAME = "화학물질안전원 화학사고"

BASE_URL = "https://apis.data.go.kr/1480802/iciscsc/csclist"
PAGE_SIZE_DEFAULT = 10          # UNVERIFIED: actual API max not confirmed
PAGE_SIZE_ENV = "EXT165_PAGE_SIZE"
MAX_PAGES_SAFETY_CAP = 5000
REQUEST_BUDGET_DEFAULT = 500
REQUEST_BUDGET_ENV = "EXT165_REQUEST_BUDGET"

# Supabase table names
TABLE_SNAPSHOTS = "ext165_chemical_accident_snapshots"
TABLE_ITEMS = "ext165_chemical_accident_snapshot_items"

# Snapshot status values
SNAPSHOT_STAGING = "STAGING"
SNAPSHOT_COMPLETED = "COMPLETED"
SNAPSHOT_FAILED = "FAILED"

# XML field — unique key per WO-001A-R2 spec
# Field name UNVERIFIED until first sample response observed
XML_ITEM_TAG = "item"
XML_FIELD_SOURCE_ID = "dataNo"
