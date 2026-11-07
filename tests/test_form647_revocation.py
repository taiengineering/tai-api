"""FORM647 검색 철회·재인덱스 경로 테스트 (G3 / SOURCE_IV R5)
WO-TAI-FORM647-R4-SOURCE-IV-FINAL-FIX-001

incremental.sync_object() + OpenSearch 삭제 경로:

O01  철회된 서식 → delete_document 호출, outcome = DELETE
O02  재구축 Fence 활성 → SKIP_FENCE, delete 호출 없음
O03  OpenSearch alias 조회 실패 → ProjectionWriteError
O04  이미 삭제된 서식 → DELETE_NOOP (NotFoundError → 정상 완료 구분)
O05  OpenSearch 삭제 오류 (비 404) → 예외 전파 (성공으로 처리 금지)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call

from services.shared_search.adapters.form647 import Form647SearchAdapter


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

_RUN_ID = "form647-remediation-002-714df47a637e3e73"
_EK = "15267319"
_CANONICAL_ID = f"f647-{_EK}"

_SNAP_OPEN = {
    "run_id": _RUN_ID,
    "ek": _EK,
    "source_gate": "PASS",
    "frozen_name": "도급인의 안전·보건에 관한 정보 제공",
    "api_target": "licbyl",
    "created_at": "2026-10-14T04:45:19+00:00",
    "is_approved": True,
}


def _make_adapter(*, canonical_id: str = _CANONICAL_ID, payload_override=None):
    """fetch_by_id 를 고정값으로 반환하는 FORM647 어댑터."""
    payloads = {canonical_id: payload_override}  # None → 철회, 행 없음

    def _fetch_by_id(cid: str):
        return payloads.get(cid)  # cid 없으면 None

    return Form647SearchAdapter(
        fetch_current=lambda: iter([]),
        fetch_by_id=_fetch_by_id,
    )


def _make_supabase(*, rebuild_active: bool = False):
    """fence 테이블만 모의하는 Supabase 클라이언트."""
    sb = MagicMock()
    tbl = MagicMock()
    tbl.select.return_value = tbl
    tbl.eq.return_value = tbl
    tbl.limit.return_value = tbl
    tbl.execute.return_value = MagicMock(data=[{"rebuild_active": rebuild_active}])
    sb.table.return_value = tbl
    return sb


def _make_os_client(*, alias_index: str = "tai-search-v1", raise_on_delete=None):
    """OpenSearch 클라이언트 모의.

    alias_index: get_alias() 가 반환할 단일 인덱스 이름.
    raise_on_delete: delete() 호출 시 raise 할 예외 (None이면 성공).
    """
    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {alias_index: {}}
    if raise_on_delete is not None:
        os_client.delete.side_effect = raise_on_delete
    # side_effect 없으면 delete() 는 MagicMock 반환 (성공 처리)
    return os_client


# ---------------------------------------------------------------------------
# O01-O05 테스트
# ---------------------------------------------------------------------------

def test_o01_revoked_form_delete_called():
    """G3: 철회 서식(payload=None) → delete_document 호출, outcome=DELETE."""
    from services.shared_search.incremental import sync_object

    adapter = _make_adapter(payload_override=None)  # 철회 → fetch_by_id returns None
    sb = _make_supabase(rebuild_active=False)
    os = _make_os_client()

    result = sync_object(
        domain_name="FORM647",
        object_type="REFERENCE_FORM",
        canonical_id=_CANONICAL_ID,
        supabase_client=sb,
        os_client=os,
        adapter_map={"FORM647": adapter},
    )

    assert result["outcome"] == "DELETE"
    os.delete.assert_called_once()
    # delete() 는 refresh=False 로 호출돼야 함 (G3 계약)
    _call_kwargs = os.delete.call_args[1] if os.delete.call_args else {}
    assert _call_kwargs.get("refresh") is False


def test_o02_fence_active_skip_fence():
    """재구축 Fence 활성 → SKIP_FENCE, OpenSearch delete 호출 없음."""
    from services.shared_search.incremental import sync_object

    adapter = _make_adapter(payload_override=None)
    sb = _make_supabase(rebuild_active=True)
    os = _make_os_client()

    result = sync_object(
        domain_name="FORM647",
        object_type="REFERENCE_FORM",
        canonical_id=_CANONICAL_ID,
        supabase_client=sb,
        os_client=os,
        adapter_map={"FORM647": adapter},
    )

    assert result["outcome"] == "SKIP_FENCE"
    os.delete.assert_not_called()


def test_o03_opensearch_alias_error_raises_projection_write_error():
    """OpenSearch alias 조회 실패 → ProjectionWriteError 발생."""
    from services.shared_search.incremental import sync_object, ProjectionWriteError

    adapter = _make_adapter(payload_override=None)
    sb = _make_supabase(rebuild_active=False)
    os = MagicMock()
    os.indices.get_alias.side_effect = Exception("ConnectionError: OpenSearch unreachable")

    with pytest.raises(ProjectionWriteError, match="alias lookup failed"):
        sync_object(
            domain_name="FORM647",
            object_type="REFERENCE_FORM",
            canonical_id=_CANONICAL_ID,
            supabase_client=sb,
            os_client=os,
            adapter_map={"FORM647": adapter},
        )


def test_o04_already_deleted_returns_delete_noop():
    """이미 삭제된 서식 → DELETE_NOOP (NotFoundError → 오류 아님, 정상 완료로 구분)."""
    from services.shared_search.incremental import sync_object
    from opensearchpy import NotFoundError

    adapter = _make_adapter(payload_override=None)
    sb = _make_supabase(rebuild_active=False)
    os = _make_os_client(raise_on_delete=NotFoundError(404, "not found", {}))

    result = sync_object(
        domain_name="FORM647",
        object_type="REFERENCE_FORM",
        canonical_id=_CANONICAL_ID,
        supabase_client=sb,
        os_client=os,
        adapter_map={"FORM647": adapter},
    )

    assert result["outcome"] == "DELETE_NOOP"


def test_o05_opensearch_delete_error_propagates():
    """OpenSearch 삭제 오류(비 404) → 예외 전파 — 성공으로 처리하지 않음."""
    from services.shared_search.incremental import sync_object

    adapter = _make_adapter(payload_override=None)
    sb = _make_supabase(rebuild_active=False)
    os = _make_os_client(raise_on_delete=ConnectionError("OpenSearch write refused"))

    with pytest.raises(ConnectionError, match="OpenSearch write refused"):
        sync_object(
            domain_name="FORM647",
            object_type="REFERENCE_FORM",
            canonical_id=_CANONICAL_ID,
            supabase_client=sb,
            os_client=os,
            adapter_map={"FORM647": adapter},
        )
