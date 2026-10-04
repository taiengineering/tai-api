"""KECO 15149420 공식 API 계약 상수. CHEM-WO-DATA-KECO-002.

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

# 환경변수명 — 다른 키 fallback 금지
SERVICE_KEY_ENV = ("KECO_API_SERVICE_KEY",)

# searchGubun 값 (국문명 코드 없음)
SEARCH_ENGLISH_NAME = "1"   # 영문명
SEARCH_CAS = "2"            # CAS번호
SEARCH_UNIQUE_NO = "3"      # 고유번호
ALLOWED_SEARCH_GUBUN = frozenset({"1", "2", "3"})

RETURN_TYPE_JSON = "JSON"
RETURN_TYPE_XML = "XML"

# 공식 성공 코드 (KECO Swagger evidence: 200 = 성공)
SUCCESS_RESULT_CODES = frozenset({"200"})

# GW 에러 코드 분류
RATE_LIMIT_DAILY_CODES = frozenset({"22"})
RATE_LIMIT_SECOND_CODES = frozenset({"23"})

RETRY_CODES = frozenset({"05", "22", "23"})
NON_RETRY_CODES = frozenset({"10", "12", "20", "30", "31", "91", "93", "95", "97"})

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
