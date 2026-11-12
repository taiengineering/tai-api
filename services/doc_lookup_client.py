"""services/doc_lookup_client.py — DOC 추출 결과 역조회 내부 클라이언트.

B2-03: doc_log_id 기반 기존·중복 문서 추출 결과 조회.
기존 doc_digitize_client.py의 서비스 인증 방식(X-Service-Key / X-Source-System) 재사용.

현재 상태 — DOC 엔드포인트 미활성화:
  DOC_LOOKUP_URL 미설정 → DocLookupError(code='endpoint_not_active') 발생.
  DOC /lookup 엔드포인트는 별도 Owner 활성화 승인 후 등록됨.

Markdown 결과 주의:
  extraction_format='md' → MAP-02용 DocExtractionEnvelope JSON이 아님.
  'md' 결과 수신 시 runDocMap2() 자동 실행 금지 (B2-04).
  MAP-02 실행은 'json' 형식 확인 + RuleSnapshot + GroupingConfig 보유 후에만 가능.

DOC 내부 오류 메시지·인증정보는 호출 측에 노출하지 않음.
타임아웃 후 자동 재전송 금지 — DOC에서 처리 중일 수 있음.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_ENV_LOOKUP_URL = "DOC_LOOKUP_URL"   # DOC /lookup 엔드포인트 URL (별도 활성화 승인 필요)
_ENV_KEY        = "TAI_SERVICE_KEY"  # 기존 doc_digitize_client.py와 동일
_SOURCE         = "tai"


# ── 결과 모델 ──────────────────────────────────────────────────────────────────

@dataclass
class DocLookupResult:
    doc_log_id: str
    status: str  # FOUND | NOT_FOUND | EXTRACTION_REF_MISSING | EXTRACTION_NOT_AVAILABLE | …
    extraction_storage_ref: Optional[str] = None
    # 'md' = Markdown(현재 운영) | 'json' = DocExtractionEnvelope(MAP-02 대상)
    # None = 형식 미확인
    extraction_format: Optional[str] = None


@dataclass
class DocLookupContentResult:
    doc_log_id: str
    status: str   # FOUND | NOT_FOUND | EXTRACTION_REF_MISSING | EXTRACTION_NOT_AVAILABLE | …
    content: Optional[str] = None  # Markdown 텍스트 — status=FOUND 시에만 존재


# ── 오류 계층 ──────────────────────────────────────────────────────────────────

class DocLookupError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code   = code
        self.detail = detail


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _get_lookup_config() -> tuple[str, str]:
    url = os.environ.get(_ENV_LOOKUP_URL, "").strip()
    key = os.environ.get(_ENV_KEY, "").strip()
    if not url:
        raise DocLookupError(
            code="endpoint_not_active",
            detail=f"{_ENV_LOOKUP_URL} 미설정 — DOC 역조회 엔드포인트 별도 활성화 승인 필요",
        )
    if not key:
        raise DocLookupError(
            code="config_missing",
            detail=f"{_ENV_KEY} 미설정 — DOC 연결 불가",
        )
    return url, key


_VALID_STATUSES: frozenset[str] = frozenset({
    "FOUND",
    "NOT_FOUND",
    "TENANT_MISMATCH",
    "SOURCE_SYSTEM_MISMATCH",
    "EXTRACTION_REF_MISSING",
    "EXTRACTION_NOT_AVAILABLE",
    "LOOKUP_BACKEND_UNAVAILABLE",
})
_VALID_FORMATS: frozenset[str] = frozenset({"md", "json"})


def _parse_lookup_body(body: dict, doc_log_id: str) -> DocLookupResult:
    """HTTP 200 조회 응답 → DocLookupResult 변환.

    - 정의된 7개 상태값만 허용.
    - FOUND: extraction_storage_ref(비공백) + extraction_format(md|json) 필수.
    - 비-FOUND: extraction_storage_ref 전달 금지.
    """
    if not isinstance(body, dict):
        raise DocLookupError("unexpected_response", "DOC 역조회 응답이 JSON 객체가 아님")

    status = body.get("status")
    if not isinstance(status, str) or not status.strip():
        raise DocLookupError("unexpected_response", "DOC 역조회 응답 status 필드 누락")
    if status not in _VALID_STATUSES:
        raise DocLookupError("unexpected_response", f"DOC 역조회 응답 알 수 없는 상태: {status}")

    if status == "FOUND":
        ref = body.get("extraction_storage_ref")
        if not isinstance(ref, str) or not ref.strip():
            raise DocLookupError(
                "unexpected_response",
                "DOC FOUND 응답에 extraction_storage_ref 없거나 비어 있음",
            )
        fmt = body.get("extraction_format")
        if fmt not in _VALID_FORMATS:
            raise DocLookupError(
                "unexpected_response",
                f"DOC FOUND 응답 extraction_format 유효하지 않음: {fmt}",
            )
        return DocLookupResult(
            doc_log_id=doc_log_id,
            status=status,
            extraction_storage_ref=ref,
            extraction_format=fmt,
        )

    # 비-FOUND 상태 — 참조값 전달 금지
    return DocLookupResult(doc_log_id=doc_log_id, status=status)


# ── 공개 API ──────────────────────────────────────────────────────────────────

async def lookup_extraction(
    *,
    doc_log_id: str,
    company_id: str,
    timeout: float = 30.0,
) -> DocLookupResult:
    """DOC 추출 결과 역조회 — doc_log_id 기반.

    Args:
        doc_log_id:  DOC에서 발급한 문서 처리 ID
        company_id:  TAI 서버에서 검증한 회사 ID (DOC tenant_id)
        timeout:     응답 대기 최대 초 — 초과 시 DocLookupError, 재전송 금지

    Returns:
        DocLookupResult — status=FOUND 시 extraction_storage_ref·format 포함

    Raises:
        DocLookupError(code='endpoint_not_active'):  DOC_LOOKUP_URL 미설정
        DocLookupError(code='config_missing'):       TAI_SERVICE_KEY 미설정
        DocLookupError(code='auth_failed'):          DOC 서비스 키 불일치
        DocLookupError(code='connection_timeout'):   타임아웃
        DocLookupError(code='connection_error'):     네트워크 오류
        DocLookupError(code='backend_error'):        DOC 5xx
        DocLookupError(code='unexpected_response'):  응답 파싱 실패
    """
    base_url, service_key = _get_lookup_config()
    url = base_url.rstrip("/") + f"/lookup/{doc_log_id}"

    headers = {
        "X-Source-System": _SOURCE,
        "X-Service-Key":   service_key,
        "X-Tenant-Id":     company_id,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
    except httpx.TimeoutException as exc:
        raise DocLookupError("connection_timeout", "DOC 역조회 응답 시간 초과") from exc
    except httpx.RequestError as exc:
        raise DocLookupError(
            "connection_error",
            f"DOC 역조회 연결 실패: {type(exc).__name__}",
        ) from exc

    # DOC 403 = 서비스 키 불일치 — TAI 사용자 권한 오류가 아닌 연동 실패
    if resp.status_code == 403:
        log.error("[doc_lookup] 서비스 키 불일치 — HTTP 403 (DOC_LOOKUP_URL=%s)", base_url)
        raise DocLookupError("auth_failed", "DOC 역조회 인증 실패 — TAI_SERVICE_KEY 확인 필요")

    if resp.status_code >= 500:
        log.error("[doc_lookup] DOC 서버 오류 HTTP %s", resp.status_code)
        raise DocLookupError("backend_error", f"DOC 역조회 서버 오류 (HTTP {resp.status_code})")

    try:
        body = resp.json()
    except Exception:
        raise DocLookupError("unexpected_response", "DOC 역조회 응답 파싱 실패")

    if resp.status_code != 200:
        raise DocLookupError(
            "unexpected_response",
            f"DOC 역조회 HTTP {resp.status_code}",
        )

    return _parse_lookup_body(body, doc_log_id)


async def lookup_extraction_content(
    *,
    doc_log_id: str,
    company_id: str,
    timeout: float = 30.0,
) -> DocLookupContentResult:
    """DOC 추출 결과 콘텐츠 조회 — doc_log_id 기반 Markdown 텍스트 반환.

    Args:
        doc_log_id:  DOC에서 발급한 문서 처리 ID
        company_id:  TAI 서버에서 검증한 회사 ID (DOC tenant_id)
        timeout:     응답 대기 최대 초

    Returns:
        DocLookupContentResult — status=FOUND 시 content(Markdown) 포함

    Raises:
        DocLookupError(code='endpoint_not_active'):  DOC_LOOKUP_URL 미설정
        DocLookupError(code='config_missing'):       TAI_SERVICE_KEY 미설정
        DocLookupError(code='auth_failed'):          DOC 서비스 키 불일치
        DocLookupError(code='connection_timeout'):   타임아웃
        DocLookupError(code='connection_error'):     네트워크 오류
        DocLookupError(code='backend_error'):        DOC 5xx
        DocLookupError(code='unexpected_response'):  응답 파싱 실패
    """
    base_url, service_key = _get_lookup_config()
    url = base_url.rstrip("/") + f"/lookup/{doc_log_id}/content"

    headers = {
        "X-Source-System": _SOURCE,
        "X-Service-Key":   service_key,
        "X-Tenant-Id":     company_id,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
    except httpx.TimeoutException as exc:
        raise DocLookupError("connection_timeout", "DOC 콘텐츠 조회 응답 시간 초과") from exc
    except httpx.RequestError as exc:
        raise DocLookupError(
            "connection_error",
            f"DOC 콘텐츠 조회 연결 실패: {type(exc).__name__}",
        ) from exc

    if resp.status_code == 403:
        log.error("[doc_lookup/content] 서비스 키 불일치 — HTTP 403 (DOC_LOOKUP_URL=%s)", base_url)
        raise DocLookupError("auth_failed", "DOC 콘텐츠 조회 인증 실패 — TAI_SERVICE_KEY 확인 필요")

    if resp.status_code >= 500:
        log.error("[doc_lookup/content] DOC 서버 오류 HTTP %s", resp.status_code)
        raise DocLookupError("backend_error", f"DOC 콘텐츠 조회 서버 오류 (HTTP {resp.status_code})")

    try:
        body = resp.json()
    except Exception:
        raise DocLookupError("unexpected_response", "DOC 콘텐츠 조회 응답 파싱 실패")

    if resp.status_code != 200:
        raise DocLookupError("unexpected_response", f"DOC 콘텐츠 조회 HTTP {resp.status_code}")

    if not isinstance(body, dict):
        raise DocLookupError("unexpected_response", "DOC 콘텐츠 조회 응답이 JSON 객체가 아님")

    status = body.get("status")
    if not isinstance(status, str) or status not in _VALID_STATUSES:
        raise DocLookupError("unexpected_response", f"DOC 콘텐츠 조회 응답 상태 유효하지 않음: {status}")

    if status == "FOUND":
        content = body.get("content")
        if not isinstance(content, str):
            raise DocLookupError("unexpected_response", "DOC FOUND 콘텐츠 응답에 content 필드 없음")
        return DocLookupContentResult(doc_log_id=doc_log_id, status=status, content=content)

    return DocLookupContentResult(doc_log_id=doc_log_id, status=status)
