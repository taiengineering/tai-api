"""KECO 15149420 공식 API 계약 상수. CHEM-WO-DATA-KECO-002 / KECO-003.

데이터셋: https://www.data.go.kr/data/15149420/openapi.do
제공기관: 한국환경공단
"""
from __future__ import annotations

SOURCE_ID = "KECO_15149420"
SOURCE_DATASET_ID = "15149420"
SOURCE_CONTRACT_VERSION = "KECO_15149420_V1"
DATASET_URL = "https://www.data.go.kr/data/15149420/openapi.do"
PROVIDER = "한국환경공단"
BASE_URL = "https://apis.data.go.kr/B552584/kecoapi/ncissbstn"
OPERATION = "chemSbstnList"

# 환경변수명 — canonical data.go.kr 공유키 우선, legacy fallback 지원
CANONICAL_SERVICE_KEY_ENV = "DATA_GO_KR_SERVICE_KEY"
LEGACY_SERVICE_KEY_ENV = "KECO_API_SERVICE_KEY"

SERVICE_KEY_ENV = (
    CANONICAL_SERVICE_KEY_ENV,
    LEGACY_SERVICE_KEY_ENV,
)

# searchGubun 값 (국문명 코드 없음)
SEARCH_ENGLISH_NAME = "1"   # 영문명
SEARCH_CAS = "2"            # CAS번호
SEARCH_UNIQUE_NO = "3"      # 고유번호
ALLOWED_SEARCH_GUBUN = frozenset({"1", "2", "3"})

RETURN_TYPE_JSON = "JSON"
RETURN_TYPE_XML = "XML"

# 공식 성공 코드 (KECO Swagger evidence: 200 = 성공)
# EXPECTED: 200 / LIVE_WIRE 미확정 — Live Gate에서 확정
SUCCESS_RESULT_CODES = frozenset({"200"})

# GW 에러 코드 분류
RATE_LIMIT_DAILY_CODES = frozenset({"22"})
RATE_LIMIT_SECOND_CODES = frozenset({"23"})

# String constants for exact source_code comparison in sync.py
RATE_LIMIT_DAILY_CODE = "22"   # daily quota — stop_batch=True
RATE_LIMIT_SECOND_CODE = "23"  # per-second throttle — bounded backoff, stop_batch=False

RETRY_CODES = frozenset({"05", "22", "23"})
NON_RETRY_CODES = frozenset({"10", "12", "20", "29", "30", "31", "91", "93", "95", "97"})

# Error classification 레이블
ERROR_AUTH = "AUTH"
ERROR_VALIDATION = "VALIDATION"
ERROR_RATE_LIMIT = "RATE_LIMIT"
ERROR_TIMEOUT = "TIMEOUT"
ERROR_UPSTREAM = "UPSTREAM"
ERROR_UNKNOWN = "UNKNOWN"

DEFAULT_TIMEOUT_SECONDS = 25
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_PAGE_NO = 1
DEFAULT_NUM_OF_ROWS = 10

# Probe 하드 상한 (bulk collection 금지)
PROBE_MAX_CALLS = 3

# ─────────────────────────────────────────────────────────────
# KECO-003: Collection Runtime Constants
# ─────────────────────────────────────────────────────────────

# Run types for keco_ingestion_runs.run_type
RUN_TYPE_PREFLIGHT = "PREFLIGHT"
RUN_TYPE_INITIAL_BULK = "INITIAL_BULK"
RUN_TYPE_MANUAL_SINGLE = "MANUAL_SINGLE"
RUN_TYPE_RETRY = "RETRY"
RUN_TYPE_SCHEDULED_REFRESH = "SCHEDULED_REFRESH"

# Run types that participate in the atomic runtime lock (only one may be RUNNING at a time)
LOCK_RUNTIME_RUN_TYPES = (
    RUN_TYPE_INITIAL_BULK,
    RUN_TYPE_MANUAL_SINGLE,
    RUN_TYPE_RETRY,
    RUN_TYPE_SCHEDULED_REFRESH,
)

# Collection target
TARGET_TYPE_CAS = "CAS"

TARGET_STATUS_PENDING = "PENDING"
TARGET_STATUS_RUNNING = "RUNNING"
TARGET_STATUS_DONE = "DONE"
TARGET_STATUS_EMPTY = "EMPTY"
TARGET_STATUS_RETRY = "RETRY"
TARGET_STATUS_FAILED = "FAILED"
TARGET_STATUS_CONFLICT = "CONFLICT"

# Environment variable names for runtime config
REQUEST_BUDGET_ENV = "KECO_REQUEST_BUDGET"
REFRESH_INTERVAL_DAYS_ENV = "KECO_REFRESH_INTERVAL_DAYS"
REFRESH_BATCH_SIZE_ENV = "KECO_REFRESH_BATCH_SIZE"
STALE_RUNNING_MINUTES_ENV = "KECO_STALE_RUNNING_MINUTES"

# TAI safety defaults — NOT KECO source contract values
DEFAULT_REQUEST_BUDGET = 9000
DEFAULT_REFRESH_INTERVAL_DAYS = 30   # days between refresh cycles
DEFAULT_REFRESH_BATCH_SIZE = 50      # targets per scheduled refresh run
DEFAULT_STALE_RUNNING_MINUTES = 60   # stale RUNNING recovery threshold
DEFAULT_CLAIM_BATCH_SIZE = 100       # targets claimed per bulk batch

SYNC_PAGE_SIZE = 100                 # numOfRows per KECO API page request
MAX_PAGES_SAFETY_CAP = 50            # prevent infinite pagination loop

# Rate-limit backoff for code 23 (per-second throttle)
RATE_RETRY_MAX_ENV = "KECO_RATE_RETRY_MAX"
RATE_RETRY_BASE_SECONDS_ENV = "KECO_RATE_RETRY_BASE_SECONDS"
DEFAULT_RATE_RETRY_MAX = 3
DEFAULT_RATE_RETRY_BASE_SECONDS = 2.0
