"""OBJ-01 KNOT-3B COMMIT B — worker inspection submission service.

Worker PWA 제출을 원자적 생성 RPC(fn_create_worker_inspection_record) 한 번으로
변환하는 순수 서비스 계층. base/results/creation-receipt/journal 직접 INSERT 는
하지 않으며 MAX(revision) 도 읽지 않는다. 모든 쓰기는 RPC 안에서 한 트랜잭션으로
일어난다.

책임:
  - submitted_at 정규화(필수; 잘못된 ISO-8601 → WORKER_SUBMISSION_TIMESTAMP_INVALID)
  - submission_id = UUID5(고정 namespace, 정체성 = schedule_ref + 정규화 phone + submitted_at)
    * 정체성이 같으면 항상 같은 submission_id (오프라인 재전송 멱등의 앵커)
  - request_hash = SHA-256(정규 의미 페이로드) — 정체성이 같아도 내용이 바뀌면 hash 는 바뀐다
  - RPC 정확히 1회 호출 후 typed 결과/에러 변환

FORBIDDEN: safety_inspections / safety_inspection_results /
safety_inspection_creation_receipt / safety_inspection_record_journal /
safety_inspection_command_receipt 직접 INSERT, MAX(revision) 조회.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# 고정 namespace (변경 금지 — 변경 시 과거 제출의 submission_id 정체성이 깨진다)
WORKER_SUBMISSION_NAMESPACE = uuid.UUID("6f6b3a1e-0e2a-5c7d-9b4f-1a2b3c4d5e6f")

RPC_NAME = "fn_create_worker_inspection_record"
DEFAULT_SOURCE = "WORKER_PWA"

# RPC 가 돌려주는 error code 중 라우터에서 409 로 매핑할 충돌 코드
CONFLICT_ERROR_CODES = frozenset({
    "SUBMISSION_ID_REUSE_CONFLICT",
    "INSPECTION_ALREADY_EXISTS_FOR_SCHEDULE",
    "FACTORY_MISMATCH",
})


class WorkerSubmissionError(Exception):
    """서비스/RPC 계약 위반을 표현하는 typed 에러."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    @property
    def is_conflict(self) -> bool:
        return self.code in CONFLICT_ERROR_CODES


def normalize_phone(raw: Optional[str]) -> str:
    """숫자만 남긴다(하이픈/공백/괄호 제거). None → ''."""
    if not raw:
        return ""
    return re.sub(r"\D", "", str(raw))


def normalize_submitted_at(raw: Any) -> datetime:
    """submitted_at 을 tz-aware UTC datetime 으로 정규화한다. 필수값.

    허용: datetime, ISO-8601 문자열('Z' 포함). tz 없으면 UTC 로 간주.
    실패 → WORKER_SUBMISSION_TIMESTAMP_INVALID.
    """
    if raw is None or raw == "":
        raise WorkerSubmissionError("WORKER_SUBMISSION_TIMESTAMP_INVALID", "submitted_at required")

    if isinstance(raw, datetime):
        dt = raw
    else:
        s = str(raw).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            raise WorkerSubmissionError("WORKER_SUBMISSION_TIMESTAMP_INVALID", str(raw))

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _submitted_at_key(dt: datetime) -> str:
    """정체성/해시에 쓰는 안정적 문자열 표현(마이크로초 포함 UTC ISO)."""
    return dt.astimezone(timezone.utc).isoformat()


def compute_submission_id(schedule_ref: str, phone: str, submitted_at: datetime) -> uuid.UUID:
    """정체성(schedule_ref + 정규화 phone + submitted_at) 기반 결정적 UUID5.

    payload hash 가 아니라 '정체성' 기반이다: 같은 제출자·같은 일정·같은 시각이면
    항목 내용이 달라져도 같은 submission_id 가 나온다(그 경우 RPC 가 hash 차이를 보고
    SUBMISSION_ID_REUSE_CONFLICT 로 막는다).
    """
    identity = "|".join([
        "schedule_ref=" + str(schedule_ref or ""),
        "phone=" + normalize_phone(phone),
        "submitted_at=" + _submitted_at_key(submitted_at),
    ])
    return uuid.uuid5(WORKER_SUBMISSION_NAMESPACE, identity)


def _canonical_items(items: list[dict]) -> list[dict]:
    """의미 페이로드용 정규 항목 목록(키 순서/누락 안정화)."""
    out = []
    for it in items or []:
        out.append({
            "inspection_set_item_id": (it.get("inspection_set_item_id") or None),
            "name": (it.get("name") or it.get("item_name") or ""),
            "result": (it.get("result") or it.get("result_code") or ""),
            "note": (it.get("note") or it.get("memo") or ""),
            "photo_urls": list(it.get("photo_urls") or []),
        })
    return out


def compute_request_hash(
    *,
    schedule_ref: str,
    phone: str,
    submitted_at: datetime,
    inspection_type: Optional[str],
    items: list[dict],
) -> str:
    """정규 의미 페이로드의 SHA-256. 의미가 같으면 같은 hash, 다르면 다른 hash."""
    payload = {
        "schedule_ref": str(schedule_ref or ""),
        "phone": normalize_phone(phone),
        "submitted_at": _submitted_at_key(submitted_at),
        "inspection_type": inspection_type or "",
        "items": _canonical_items(items),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _rpc_results_payload(items: list[dict]) -> list[dict]:
    """RPC p_results 로 넘길 항목 배열. result_code 는 canonical 을 그대로 전달
    (정규화는 라우터가 normalize_inspection_result_write 로 미리 수행)."""
    rows = []
    for it in items or []:
        rows.append({
            "inspection_set_item_id": (it.get("inspection_set_item_id") or None),
            "item_name": (it.get("name") or it.get("item_name") or ""),
            "result_code": (it.get("result_code") or it.get("result") or ""),
            "note": (it.get("note") or it.get("memo") or ""),
            "photo_urls": list(it.get("photo_urls") or []),
            "value_text": it.get("value_text"),
            "value_number": it.get("value_number"),
        })
    return rows


def submit_worker_inspection(
    supabase,
    *,
    schedule_ref: str,
    schedule_id: str,
    factory_id: str,
    inspector_id: str,
    phone: str,
    submitted_at: Any,
    inspection_type: Optional[str],
    items: list[dict],
    source: str = DEFAULT_SOURCE,
) -> dict:
    """Worker 제출을 원자적 생성 RPC 1회로 실행하고 snapshot 을 돌려준다.

    schedule_ref  : 정체성용 안정 키(라우터가 해석한 원 assignment/schedule 참조 문자열)
    schedule_id   : work_schedules.id (RPC lock 대상)
    반환          : {"data": snapshot, "replayed": bool}
    실패          : WorkerSubmissionError(code, detail)
    """
    dt = normalize_submitted_at(submitted_at)

    if not schedule_id:
        raise WorkerSubmissionError("INVALID_SUBMISSION_INPUT", "schedule_id required")
    if not factory_id:
        raise WorkerSubmissionError("INVALID_SUBMISSION_INPUT", "factory_id required")
    if not items:
        raise WorkerSubmissionError("EMPTY_RESULTS", "items required")

    submission_id = compute_submission_id(schedule_ref, phone, dt)
    request_hash = compute_request_hash(
        schedule_ref=schedule_ref, phone=phone, submitted_at=dt,
        inspection_type=inspection_type, items=items,
    )

    request_payload = {
        "schedule_ref": str(schedule_ref or ""),
        "phone": normalize_phone(phone),
        "submitted_at": _submitted_at_key(dt),
        "inspection_type": inspection_type or "",
        "source": source,
    }

    params = {
        "p_submission_id": str(submission_id),
        "p_request_hash": request_hash,
        "p_source": source,
        "p_schedule_id": str(schedule_id),
        "p_factory_id": str(factory_id),
        "p_inspector_id": (str(inspector_id) if inspector_id else None),
        "p_submitted_at": _submitted_at_key(dt),
        "p_results": _rpc_results_payload(items),
        "p_request_payload": request_payload,
    }

    # RPC 정확히 1회. 직접 테이블 쓰기/revision 조회 없음.
    resp = supabase.rpc(RPC_NAME, params).execute()
    result = getattr(resp, "data", resp)

    # supabase-py 는 스칼라 jsonb 를 그대로/또는 [row] 형태로 줄 수 있음
    if isinstance(result, list):
        result = result[0] if result else None
    if not isinstance(result, dict):
        raise WorkerSubmissionError("RPC_RESULT_MALFORMED", repr(result))

    if not result.get("ok", False):
        raise WorkerSubmissionError(result.get("error", "UNKNOWN_RPC_ERROR"),
                                    str(result.get("detail", "")))

    return {"data": result.get("data"), "replayed": bool(result.get("replayed", False))}
