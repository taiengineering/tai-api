"""WP-DOCUMENT-ARCH-04 (Q4) — deterministic hash contract tests.

repository root 기준 실행(pytest). 순수 함수 테스트이며 DB/네트워크 접근 없음.
public API 는 compute_confirmed_snapshot_hash / SnapshotCanonicalizationError 뿐이며,
내부 결정성 검증을 위해서만 underscore 함수를 직접 import 한다.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from services import document_snapshot_integrity as dsi
from services.document_snapshot_integrity import (
    SnapshotCanonicalizationError,
    compute_confirmed_snapshot_hash,
)
from services.document_snapshot_integrity import (  # internal — 테스트 전용
    _build_canonical_snapshot_payload,
    _canonicalize_confirmed_snapshot,
    _compute_snapshot_hash,
)

DOC_ID = UUID("11111111-1111-1111-1111-111111111111")
BY = UUID("22222222-2222-2222-2222-222222222222")
AT = datetime(2026, 8, 23, 1, 30, 0, 123456, tzinfo=timezone.utc)

TRACE = [
    {
        "source_type": "inspection",
        "source_id": None,
        "entity": "safety_inspections",
        "provenance": "UNKNOWN",
        "reason": "WP-SIR-PROVENANCE-01 pending",
    }
]


def base(**over):
    fields = dict(
        runtime_document_id=DOC_ID,
        document_version=1,
        snapshot_schema_version=1,
        runtime_values_snapshot={
            "company_name": "태왕엔지니어링",
            "items": [{"id": "a", "result": "정상"}, {"id": "b", "result": "지적"}],
            "normal_count": 1,
        },
        source_trace_snapshot=TRACE,
        template_identity="tmpl:sha256:cafebabe",
        confirmed_at=AT,
        confirmed_by=BY,
        evidence_manifest=[{"object_id": "o1", "hash": "h1"}],
        rendered_body="<html><body>점검결과</body></html>",
    )
    fields.update(over)
    return fields


# ── 재확인 1: repository 실제 경로 import ─────────────────────────────────
def test_A1_repository_path_import():
    assert dsi.__name__ == "services.document_snapshot_integrity"
    assert callable(compute_confirmed_snapshot_hash)
    assert issubclass(SnapshotCanonicalizationError, Exception)


# ── 재확인 2: 공식 진입점 단일화 (API contract 수준) ───────────────────────
def test_A2_public_api_is_single_entry_point():
    assert set(dsi.__all__) == {
        "compute_confirmed_snapshot_hash",
        "SnapshotCanonicalizationError",
    }
    # 검증을 건너뛰는 저수준 함수가 public 이름으로 노출되면 안 된다.
    for leaked in (
        "compute_snapshot_hash",
        "canonicalize_confirmed_snapshot",
        "build_canonical_snapshot_payload",
        "normalize_for_canonical_json",
        "HASH_INPUT_FIELDS",
    ):
        assert not hasattr(dsi, leaked), "public bypass 노출: %s" % leaked
    public = {
        n for n in dir(dsi) if not n.startswith("_") and n not in ("annotations",)
    }
    # import 된 표준 모듈/타입을 제외한 자체 public 심볼은 __all__ 과 일치해야 한다.
    own = public - {"hashlib", "json", "datetime", "timezone", "Decimal", "UUID",
                    "Any", "Dict", "List"}
    assert own == set(dsi.__all__)


# ── 재확인 3: confirmed_at wrong type 거부 ────────────────────────────────
def test_A3_confirmed_at_type_contract():
    for bad in ("2026-08-23T01:30:00Z", 1755912600, None, datetime(2026, 8, 23)):
        with pytest.raises(SnapshotCanonicalizationError):
            compute_confirmed_snapshot_hash(**base(confirmed_at=bad))


# ── 재확인 4: identifier invalid 거부 / canonical 정규화 ──────────────────
def test_A4_identifier_contract():
    for field in ("runtime_document_id", "confirmed_by"):
        for bad in (123, "not-a-uuid", "", []):
            with pytest.raises(SnapshotCanonicalizationError):
                compute_confirmed_snapshot_hash(**base(**{field: bad}))
    # UUID object == canonical str == uppercase str == hex 표기
    h = compute_confirmed_snapshot_hash(**base())
    assert h == compute_confirmed_snapshot_hash(**base(confirmed_by=str(BY)))
    assert h == compute_confirmed_snapshot_hash(**base(confirmed_by=str(BY).upper()))
    assert h == compute_confirmed_snapshot_hash(**base(confirmed_by=BY.hex))
    assert h == compute_confirmed_snapshot_hash(**base(runtime_document_id=str(DOC_ID)))


# ── deterministic 계약 16종 ───────────────────────────────────────────────
# 1. dict key 순서가 달라도 hash 동일
def test_01_top_level_key_order_invariant():
    p1 = _build_canonical_snapshot_payload(**base())
    p2 = {k: p1[k] for k in reversed(list(p1.keys()))}
    assert list(p1.keys()) != list(p2.keys())
    assert _compute_snapshot_hash(p1) == _compute_snapshot_hash(p2)


# 2. nested dict key 순서가 달라도 hash 동일
def test_02_nested_key_order_invariant():
    a = compute_confirmed_snapshot_hash(
        **base(runtime_values_snapshot={"x": {"p": 1, "q": 2}, "y": 3})
    )
    b = compute_confirmed_snapshot_hash(
        **base(runtime_values_snapshot={"y": 3, "x": {"q": 2, "p": 1}})
    )
    assert a == b


# 3. list 순서가 바뀌면 hash 다름
def test_03_list_order_significant():
    a = compute_confirmed_snapshot_hash(
        **base(runtime_values_snapshot={"items": [1, 2, 3]})
    )
    b = compute_confirmed_snapshot_hash(
        **base(runtime_values_snapshot={"items": [3, 2, 1]})
    )
    assert a != b


# 4. 구조적 whitespace 는 canonical 직렬화에서 제거된다
def test_04_whitespace_irrelevant():
    payload = _build_canonical_snapshot_payload(**base())
    canonical = _canonicalize_confirmed_snapshot(payload).decode("utf-8")
    assert " " not in canonical.split('"rendered_body"')[0]
    assert canonical == _canonicalize_confirmed_snapshot(payload).decode("utf-8")
    # 값 내부 whitespace 는 내용이므로 hash 를 바꾼다
    assert compute_confirmed_snapshot_hash(
        **base(rendered_body="<html> </html>")
    ) != compute_confirmed_snapshot_hash(**base(rendered_body="<html></html>"))


# 5. 한글/Unicode deterministic (ensure_ascii=False, UTF-8 고정)
def test_05_unicode_deterministic():
    h = [compute_confirmed_snapshot_hash(**base()) for _ in range(5)]
    assert len(set(h)) == 1
    canonical = _canonicalize_confirmed_snapshot(
        _build_canonical_snapshot_payload(**base())
    )
    assert "태왕엔지니어링".encode("utf-8") in canonical  # escape 되지 않음


# 6. confirmed_at 변경 → hash 변경
def test_06_confirmed_at_significant():
    assert compute_confirmed_snapshot_hash(**base()) != compute_confirmed_snapshot_hash(
        **base(confirmed_at=AT + timedelta(microseconds=1))
    )


# 6b. 동일 시각의 다른 timezone 표현은 UTC 정규화되어 hash 동일
def test_06b_timezone_normalized_to_utc():
    kst = AT.astimezone(timezone(timedelta(hours=9)))
    assert kst.utcoffset() != timedelta(0)
    assert compute_confirmed_snapshot_hash(**base()) == compute_confirmed_snapshot_hash(
        **base(confirmed_at=kst)
    )


# 7. confirmed_by 변경 → hash 변경
def test_07_confirmed_by_significant():
    other = UUID("33333333-3333-3333-3333-333333333333")
    assert compute_confirmed_snapshot_hash(**base()) != compute_confirmed_snapshot_hash(
        **base(confirmed_by=other)
    )


# 8. rendered_body 변경 → hash 변경
def test_08_rendered_body_significant():
    assert compute_confirmed_snapshot_hash(**base()) != compute_confirmed_snapshot_hash(
        **base(rendered_body="<html><body>변조</body></html>")
    )


# 9. source_trace 변경 → hash 변경
def test_09_source_trace_significant():
    changed = [dict(TRACE[0], provenance="KNOWN")]
    assert compute_confirmed_snapshot_hash(**base()) != compute_confirmed_snapshot_hash(
        **base(source_trace_snapshot=changed)
    )


# 10. evidence_manifest 변경 → hash 변경
def test_10_evidence_manifest_significant():
    assert compute_confirmed_snapshot_hash(**base()) != compute_confirmed_snapshot_hash(
        **base(evidence_manifest=[{"object_id": "o1", "hash": "TAMPERED"}])
    )


# 11. excluded metadata 는 hash 에 유입 불가
def test_11_excluded_metadata_cannot_enter():
    expected = compute_confirmed_snapshot_hash(**base())
    for extra in (
        "id",
        "created_at",
        "updated_at",
        "archived_at",
        "snapshot_hash",
        "storage_path",
        "pdf_hash",
        "download_url",
        "evidence_links_snapshot",
    ):
        with pytest.raises(TypeError):  # keyword-only ALLOWLIST — 인자로 받지 않음
            compute_confirmed_snapshot_hash(**base(**{extra: "X"}))
    # 내부 payload 경로로 밀어넣어도 거부
    payload = _build_canonical_snapshot_payload(**base())
    payload["created_at"] = "2026-08-23T00:00:00Z"
    with pytest.raises(SnapshotCanonicalizationError):
        _compute_snapshot_hash(payload)
    assert compute_confirmed_snapshot_hash(**base()) == expected


# 12. unsupported type → 예외 (FAIL-CLOSED, 조용한 문자열 변환 없음)
def test_12_unsupported_type_raises():
    class Weird:
        pass

    for bad in (Weird(), b"bytes", {1, 2}, float("nan")):
        with pytest.raises(SnapshotCanonicalizationError):
            compute_confirmed_snapshot_hash(**base(runtime_values_snapshot={"v": bad}))
    with pytest.raises(SnapshotCanonicalizationError):
        compute_confirmed_snapshot_hash(**base(rendered_body=None))
    with pytest.raises(SnapshotCanonicalizationError):
        compute_confirmed_snapshot_hash(**base(source_trace_snapshot=[]))
    with pytest.raises(SnapshotCanonicalizationError):
        compute_confirmed_snapshot_hash(**base(source_trace_snapshot="not-an-array"))


# 13. 동일 payload 100회 반복 → 동일 bytes / 동일 hash
def test_13_repeat_100_stable():
    payload = _build_canonical_snapshot_payload(**base())
    byte_set = {_canonicalize_confirmed_snapshot(payload) for _ in range(100)}
    hash_set = {compute_confirmed_snapshot_hash(**base()) for _ in range(100)}
    assert len(byte_set) == 1
    assert len(hash_set) == 1


# 14. hash 길이 = 64 hex 소문자, prefix 없음
def test_14_hash_shape():
    h = compute_confirmed_snapshot_hash(**base())
    assert len(h) == 64
    assert h == h.lower()
    assert all(c in "0123456789abcdef" for c in h)
    assert not h.startswith("sha256:")


# 15. Decimal scale 보존 / bool 이 int 로 뭉개지지 않음
def test_15_decimal_and_scalar_normalization():
    a = compute_confirmed_snapshot_hash(
        **base(runtime_values_snapshot={"v": Decimal("1.10")})
    )
    b = compute_confirmed_snapshot_hash(
        **base(runtime_values_snapshot={"v": Decimal("1.1")})
    )
    assert a != b  # 문서 snapshot 전용 규칙: scale 유의
    t = compute_confirmed_snapshot_hash(**base(runtime_values_snapshot={"v": True}))
    one = compute_confirmed_snapshot_hash(**base(runtime_values_snapshot={"v": 1}))
    assert t != one
