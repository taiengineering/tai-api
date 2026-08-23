"""
WP-DOCUMENT-ARCH-04 (Q4) — Confirmed Snapshot Canonicalization & Hash Contract.

이 모듈은 confirmed document snapshot 의 정본 hash 를 생성하는 **단일 지점**이다.

PUBLIC API:
    compute_confirmed_snapshot_hash(...)
    SnapshotCanonicalizationError

    SUPPORTED PUBLIC API        = single entry point
    NORMAL CALLER BYPASS        = blocked by API contract/convention (__all__ + underscore)
    LANGUAGE-LEVEL ACCESS CTRL  = 없음 (underscore 함수도 명시 import 하면 호출 가능)

그 외 함수는 전부 underscore internal 이다. 계약 검증(_build_canonical_snapshot_payload)
을 건너뛴 저수준 hash 경로를 정상 API 처럼 쓸 수 없게 하기 위함이다.
Q5 confirm transaction 은 compute_confirmed_snapshot_hash() 하나만 호출한다.

계약 (WP-DOCUMENT-ARCH-02 REV-1 / ARCH-04 조사 판정):
  ALGORITHM      = SHA-256, full 64 hex digest (prefix 없음)
  CANONICAL JSON = UTF-8 / sorted keys / ensure_ascii=False / separators=(",", ":")
  INPUT          = EXPLICIT ALLOWLIST (10 field). DB row 전체를 받아 제외하는 방식 금지.
  FAILURE MODE   = FAIL-CLOSED. 실패 시 예외 → CONFIRM 실패.
                   snapshot_hash=NULL 로 진행하는 경로는 존재하지 않는다.

재사용 금지 근거:
  services/persistence_svc.py, watch_engine/emitter.py 에 SHA-256+sorted JSON 패턴이 있으나
  16 hex truncation / default=str / separators 미고정 / fail-open(None) 이라 의미가 다르다.
  기존 helper 를 공유하면 해당 엔진들의 hash 의미가 바뀌므로 전용 유틸로 분리한다.

Decimal scale 보존(1.10 != 1.1)은 **문서 snapshot 전용** 규칙이다.
확정 당시 표현된 값까지 증거로 보존하기 위함이며, 다른 엔진의 numeric canonicalization
규칙으로 확장하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from uuid import UUID

# production code 가 import 할 수 있는 것은 이 둘 뿐이다.
__all__ = [
    "compute_confirmed_snapshot_hash",
    "SnapshotCanonicalizationError",
]

_SNAPSHOT_HASH_ALGORITHM = "sha256"

# ALLOWLIST — 이 10개 외의 어떤 값도 hash 입력이 될 수 없다.
# archive 테이블에 컬럼이 추가되어도 여기에 명시하지 않는 한 hash 에 영향이 없다.
_HASH_INPUT_FIELDS = (
    "runtime_document_id",       # document identity
    "document_version",
    "snapshot_schema_version",
    "runtime_values_snapshot",   # canonical render payload (fetcher output verbatim)
    "source_trace_snapshot",     # JSON ARRAY
    "template_identity",
    "confirmed_at",              # seal identity (언제 확정했는가)
    "confirmed_by",              # seal identity (누가 확정했는가)
    "evidence_manifest",
    "rendered_body",
)

# EXCLUDED (참고용 · keyword-only 인자로 받지 않으므로 구조적으로 유입 불가):
#   runtime_document_archive.id / created_at / updated_at 등 저장 메타
#   snapshot_hash 자기 자신
#   archived_at (confirmation 이후 lifecycle metadata)
#   generated_document 상태 일체(storage_path / pdf_hash / download_url / status)
#   evidence_links_snapshot (draft references — sealed manifest 가 아님)


class SnapshotCanonicalizationError(Exception):
    """canonicalization 또는 hash 입력 계약 위반. FAIL-CLOSED — CONFIRM 을 중단시킨다."""


def _fail(message: str) -> "SnapshotCanonicalizationError":
    return SnapshotCanonicalizationError(message)


def _normalize_identifier(value: Any, field: str) -> str:
    """UUID object OR valid UUID string → canonical lowercase hyphenated UUID.

    uppercase / hex(하이픈 없음) / urn / 중괄호 표기도 UUID() 가 해석 가능하면 받아서
    canonical form 으로 수렴시킨다. 표기 차이가 hash 를 흔들지 않게 하기 위함이다.
    """
    if isinstance(value, UUID):
        return str(value).lower()
    if isinstance(value, str):
        try:
            parsed = UUID(value)
        except (ValueError, AttributeError, TypeError):
            raise _fail("%s is not a valid UUID string" % field)
        # "{...}" / urn / 하이픈 없는 표기를 모두 canonical 형태로 수렴시킨다.
        return str(parsed).lower()
    raise _fail(
        "%s must be a UUID object or a valid UUID string, got %s"
        % (field, type(value).__name__)
    )


def _normalize_for_canonical_json(value: Any, _path: str = "$") -> Any:
    """지원 타입만 JSON 표현으로 명시 변환. 미지원 타입은 예외(FAIL-CLOSED).

    default=str 을 쓰지 않는 이유: datetime/Decimal/UUID 가 실행 환경 의존 문자열로
    조용히 변환되어 hash 가 달라질 수 있다. 변환 규칙을 여기에 고정한다.
    """
    # bool 은 int 의 subclass 이므로 반드시 먼저 검사한다.
    if value is None or isinstance(value, (bool, str)):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        # NaN/Infinity 는 JSON 표현이 없다 → 거부.
        if value != value or value in (float("inf"), float("-inf")):
            raise _fail("non-finite float at %s" % _path)
        return value

    if isinstance(value, datetime):
        # naive datetime 은 시간대가 모호하여 hash 재현성을 깨뜨린다 → 거부.
        if value.tzinfo is None or value.utcoffset() is None:
            raise _fail("naive datetime (tz 없음) at %s" % _path)
        utc = value.astimezone(timezone.utc)
        # 고정 형식: UTC · microsecond 6자리 항상 표기 · 'Z' suffix
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

    if isinstance(value, UUID):
        return str(value).lower()

    if isinstance(value, Decimal):
        if not value.is_finite():
            raise _fail("non-finite Decimal at %s" % _path)
        # 지수 표기 금지 · 주어진 scale 보존. 1.10 과 1.1 은 다른 값으로 취급한다.
        return format(value, "f")

    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _fail("non-string dict key %s at %s" % (type(key).__name__, _path))
            out[key] = _normalize_for_canonical_json(item, "%s.%s" % (_path, key))
        return out

    if isinstance(value, (list, tuple)):
        # list 순서는 의미가 있으므로 정렬하지 않는다.
        return [
            _normalize_for_canonical_json(item, "%s[%d]" % (_path, idx))
            for idx, item in enumerate(value)
        ]

    raise _fail("unsupported type %s at %s" % (type(value).__name__, _path))


def _build_canonical_snapshot_payload(
    *,
    runtime_document_id: Any,
    document_version: Any,
    snapshot_schema_version: Any,
    runtime_values_snapshot: Any,
    source_trace_snapshot: Any,
    template_identity: Any,
    confirmed_at: Any,
    confirmed_by: Any,
    evidence_manifest: Any,
    rendered_body: Any,
) -> Dict[str, Any]:
    """ALLOWLIST 10 field 만으로 정규 payload 를 새로 구성한다(keyword-only).

    DB row 를 받아 제외 필드를 지우는 방식이 아니라, 허용 필드만 명시적으로 옮긴다.
    """
    raw = {
        "runtime_document_id": runtime_document_id,
        "document_version": document_version,
        "snapshot_schema_version": snapshot_schema_version,
        "runtime_values_snapshot": runtime_values_snapshot,
        "source_trace_snapshot": source_trace_snapshot,
        "template_identity": template_identity,
        "confirmed_at": confirmed_at,
        "confirmed_by": confirmed_by,
        "evidence_manifest": evidence_manifest,
        "rendered_body": rendered_body,
    }

    # sealed row 는 DB 에서 전부 NOT NULL 이다. hash 단계에서 먼저 거른다(FAIL-CLOSED).
    missing: List[str] = [name for name in _HASH_INPUT_FIELDS if raw[name] is None]
    if missing:
        raise _fail("required hash field is None: %s" % ", ".join(sorted(missing)))

    # identity 계약 — UUID object 또는 valid UUID string → canonical lowercase.
    raw["runtime_document_id"] = _normalize_identifier(
        runtime_document_id, "runtime_document_id"
    )
    raw["confirmed_by"] = _normalize_identifier(confirmed_by, "confirmed_by")

    # seal time 계약 — timezone-aware datetime only. 문자열/naive 거부.
    if not isinstance(confirmed_at, datetime):
        raise _fail(
            "confirmed_at must be a timezone-aware datetime, got %s"
            % type(confirmed_at).__name__
        )
    if confirmed_at.tzinfo is None or confirmed_at.utcoffset() is None:
        raise _fail("confirmed_at must be timezone-aware (naive datetime 금지)")

    if not isinstance(document_version, int) or isinstance(document_version, bool):
        raise _fail("document_version must be int")
    if not isinstance(snapshot_schema_version, int) or isinstance(
        snapshot_schema_version, bool
    ):
        raise _fail("snapshot_schema_version must be int")
    if document_version < 1 or snapshot_schema_version < 1:
        raise _fail("version fields must be >= 1")

    if not isinstance(template_identity, str):
        raise _fail("template_identity must be str")
    if not isinstance(rendered_body, str):
        raise _fail("rendered_body must be str")

    # DB CHECK(chk_rdarch_source_trace_array) 와 동일 계약: 비어있지 않은 ARRAY.
    if not isinstance(source_trace_snapshot, (list, tuple)):
        raise _fail("source_trace_snapshot must be a JSON array")
    if len(source_trace_snapshot) == 0:
        raise _fail("source_trace_snapshot must not be empty")

    return _normalize_for_canonical_json(raw)


def _canonicalize_confirmed_snapshot(payload: Dict[str, Any]) -> bytes:
    """정규 payload → 결정적 byte sequence.

    동일 의미의 payload 는 key 삽입 순서/whitespace 와 무관하게 항상 동일한 bytes 가 된다.
    """
    if not isinstance(payload, dict):
        raise _fail("payload must be a dict")

    unknown = set(payload.keys()) - set(_HASH_INPUT_FIELDS)
    if unknown:
        raise _fail("payload has non-allowlisted keys: %s" % ", ".join(sorted(unknown)))
    absent = set(_HASH_INPUT_FIELDS) - set(payload.keys())
    if absent:
        raise _fail("payload missing keys: %s" % ", ".join(sorted(absent)))

    try:
        text = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # pragma: no cover - normalize 가 선제 차단
        raise _fail("json serialization failed: %s" % exc)

    return text.encode("utf-8")


def _compute_snapshot_hash(payload: Dict[str, Any]) -> str:
    """정규 payload → SHA-256 full 64 hex (소문자, prefix 없음)."""
    return hashlib.sha256(_canonicalize_confirmed_snapshot(payload)).hexdigest()


def compute_confirmed_snapshot_hash(**fields: Any) -> str:
    """confirmed snapshot hash 의 **유일한** 공식 진입점.

    build(계약 검증) → canonicalize → SHA-256 을 하나로 묶는다. 우회 경로는 없다.
    실패는 전부 SnapshotCanonicalizationError 이며, 호출자는 예외를 삼키지 말고
    confirm 트랜잭션을 중단해야 한다(FAIL-CLOSED).

    필수 keyword 인자 (ALLOWLIST 10):
        runtime_document_id      UUID object | valid UUID string (→ canonical lowercase)
        document_version         int >= 1
        snapshot_schema_version  int >= 1
        runtime_values_snapshot  JSON 값
        source_trace_snapshot    비어있지 않은 list
        template_identity        str
        confirmed_at             timezone-aware datetime
        confirmed_by             UUID object | valid UUID string (→ canonical lowercase)
        evidence_manifest        JSON 값
        rendered_body            str
    """
    return _compute_snapshot_hash(_build_canonical_snapshot_payload(**fields))
