"""services/doc_digitize_client.py — DOC /digitize httpx 클라이언트.

TAI → DOC 단방향 변환 요청 전용.
환경변수 미설정 시 즉시 raise (fail-closed).
타임아웃 후 자동 재전송 금지 — DOC 처리가 완료됐을 수 있음.
DOC 내부 오류 메시지·인증정보는 호출 측에 노출하지 않음.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_ENV_URL = "DOC_ENGINE_URL"
_ENV_KEY = "TAI_SERVICE_KEY"
_SOURCE  = "tai"


# ── 결과 모델 ──────────────────────────────────────────────────────────────────

@dataclass
class DocDigitizeResult:
    doc_log_id: str
    duplicate: bool
    primitive_id: Optional[str] = None
    v1_status: Optional[str] = None
    v2_status: Optional[str] = None
    file_hash: Optional[str] = None
    file_size_bytes: Optional[int] = None
    storage_ref: Optional[str] = None
    storage_warning: Optional[str] = None


# ── 오류 계층 ──────────────────────────────────────────────────────────────────

class DocDigitizeError(Exception):
    def __init__(self, stage: str, reason: str, http_status: Optional[int] = None):
        super().__init__(reason)
        self.stage       = stage
        self.reason      = reason
        self.http_status = http_status


class DocConnectionError(DocDigitizeError):
    """네트워크·타임아웃 오류 — http_status 없음."""
    def __init__(self, reason: str):
        super().__init__(stage="connection", reason=reason, http_status=None)


class DocConfigError(DocDigitizeError):
    """환경변수 미설정 — http_status 없음."""
    def __init__(self, reason: str):
        super().__init__(stage="config", reason=reason, http_status=None)


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _get_config() -> tuple[str, str]:
    url = os.environ.get(_ENV_URL, "").strip()
    key = os.environ.get(_ENV_KEY, "").strip()
    if not url:
        raise DocConfigError(f"{_ENV_URL} 미설정 — DOC 연결 불가")
    if not key:
        raise DocConfigError(f"{_ENV_KEY} 미설정 — DOC 연결 불가")
    return url, key


def _parse_200_body(body: dict) -> DocDigitizeResult:
    """HTTP 200 응답 구조 검증 및 DocDigitizeResult 변환.

    ok·doc_log_id·primitive_id(신규) 필수 검증.
    검증 실패 시 DocDigitizeError("internal") — KeyError·TypeError 비전파.
    """
    # ok: true 필수 — false이거나 없으면 성공 아님
    if body.get("ok") is not True:
        raise DocDigitizeError("internal", "DOC 200 응답 ok 필드가 true가 아님", 200)

    doc_log_id = body.get("doc_log_id")
    if not isinstance(doc_log_id, str) or not doc_log_id.strip():
        raise DocDigitizeError("internal", "DOC 200 응답에 doc_log_id 없음 또는 형식 오류", 200)

    if body.get("duplicate"):
        return DocDigitizeResult(doc_log_id=doc_log_id, duplicate=True)

    # 신규 처리: primitive_id 필수·비공백 문자열
    primitive_id = body.get("primitive_id")
    if not isinstance(primitive_id, str) or not primitive_id.strip():
        raise DocDigitizeError("internal", "DOC 200 응답 primitive_id 없음 또는 형식 오류", 200)

    return DocDigitizeResult(
        doc_log_id=doc_log_id,
        duplicate=False,
        primitive_id=primitive_id,
        v1_status=body.get("v1_status"),
        v2_status=body.get("v2_status"),
        file_hash=body.get("file_hash"),
        file_size_bytes=body.get("file_size_bytes"),
        storage_ref=body.get("storage_ref"),
        storage_warning=body.get("storage_warning"),
    )


# ── 공개 API ──────────────────────────────────────────────────────────────────

async def digitize(
    file_bytes: bytes,
    original_filename: str,
    company_id: str,
    document_input_mode: Optional[str] = None,
    factory_id: Optional[str] = None,
    timeout: float = 60.0,
) -> DocDigitizeResult:
    """DOC POST /digitize 호출 → DocDigitizeResult 반환.

    Args:
        file_bytes:            파일 원본 바이트
        original_filename:     원본 파일명 (확장자 포함)
        company_id:            TAI 서버에서 검증한 회사 ID (DOC tenant_id)
        document_input_mode:   파일 입력 방식 힌트 (digital|scan|unsure) — None이면 미전송
        factory_id:            TAI에서 검증한 사업장 ID — 비-None 시 X-Factory-Id 헤더 포함
        timeout:               응답 대기 최대 초 — 초과 시 DocConnectionError, 재전송 금지

    Returns:
        DocDigitizeResult — duplicate=True이면 doc_log_id 외 필드는 None

    Raises:
        DocConfigError:      DOC_ENGINE_URL·TAI_SERVICE_KEY 미설정
        DocConnectionError:  네트워크 오류·타임아웃
        DocDigitizeError:    DOC 측 처리 실패 (422/502/500 등)
    """
    base_url, service_key = _get_config()
    url = base_url.rstrip("/") + "/digitize"

    headers = {
        "X-Source-System": _SOURCE,
        "X-Service-Key":   service_key,
        "X-Tenant-Id":     company_id,
    }
    if factory_id is not None:
        headers["X-Factory-Id"] = factory_id

    post_kwargs: dict = {
        "headers": headers,
        "files":   {"file": (original_filename, file_bytes)},
    }
    if document_input_mode is not None:
        post_kwargs["data"] = {"document_input_mode": document_input_mode}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, **post_kwargs)
    except httpx.TimeoutException as exc:
        raise DocConnectionError("DOC 응답 시간 초과") from exc
    except httpx.RequestError as exc:
        raise DocConnectionError(f"DOC 연결 실패: {type(exc).__name__}") from exc

    # DOC 403 = 서비스 키 불일치 → TAI 사용자 권한 오류가 아닌 연동 실패
    if resp.status_code == 403:
        log.error("[doc_digitize] 서비스 키 불일치 — HTTP 403 (DOC_ENGINE_URL=%s)", base_url)
        raise DocDigitizeError(
            stage="connection",
            reason="DOC 서비스 인증 실패 — TAI_SERVICE_KEY 확인 필요",
            http_status=403,
        )

    try:
        body = resp.json()
    except Exception:
        raise DocDigitizeError(
            stage="internal",
            reason="DOC 응답 파싱 실패",
            http_status=resp.status_code,
        )

    if resp.status_code == 200:
        if not isinstance(body, dict):
            raise DocDigitizeError("internal", "DOC 200 응답이 JSON 객체가 아님", 200)
        return _parse_200_body(body)

    # 오류 단계 매핑 — DOC 실제 stage 필드 우선, 없으면 HTTP 코드로 추정
    # body가 비객체(배열 등)이면 .get() 호출 불가 → isinstance 선행 확인
    if resp.status_code == 422:
        stage = body.get("stage", "v1") if isinstance(body, dict) else "v1"
    elif resp.status_code == 502:
        stage = "extraction"
    else:
        stage = "internal"

    raise DocDigitizeError(
        stage=stage,
        reason=f"DOC 처리 실패 (HTTP {resp.status_code})",
        http_status=resp.status_code,
    )
