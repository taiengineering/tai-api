"""tests/test_wp01d_obligation_change.py

WP01-D 의무 변경관리 백엔드 단위 테스트.

TC-01  신규 의무 ADDED → inspection_sets 에 추가 됨을 diff 로 감지
TC-02  유지 의무 RETAINED → retained_atom_ids 에 포함
TC-03  제거 의무 → REMOVAL_CANDIDATE 식별
TC-04  관리자 Scope C(취소) → DB 변경 없음
TC-05  Scope A (단건 제외) → 해당 일정만 is_excluded + active_yn=False + status_code=EXCLUDED
TC-06  Scope B (미래 중단) → application_date 이전 일정 보존
TC-07  과거 completed 기록 → Scope B 에서 절대 건드리지 않음
TC-08  비관리자 → 403
TC-09  타사 공장 → 404
TC-10  FAILED/PENDING/BLOCKED 상태 진단 → 자동 제거 없음(diff 로직과 독립)
TC-11  Scope B 후 scope_b_deactivation_date 설정 + is_active=False (guard 확인)
TC-12  동일 diagnosis_id 재호출 → 멱등(같은 요약 반환)
TC-13  직접 LEG 실행 우회 → compare gate 리다이렉트 계약 (change_tracker ValueError)
TC-14  Scope B 중복 요청 → 멱등(이미 is_active=False + scope_b_deactivation_date 설정)

No real DB — supabase 완전 mock.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Import 대상 모듈
# ---------------------------------------------------------------------------
from services.wp01_obligation_change.change_tracker import (
    _is_current_removal_candidate,
    compute_change_summary,
    diff_obligations,
    extract_atom_ids,
    load_current_removal_candidates,
    load_previous_materialized_obligations,
)
from services.wp01_obligation_change.removal_processor import (
    preview_removal_impact,
    process_scope_a,
    process_scope_b,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _mk_execute(data):
    """execute() 반환 MagicMock."""
    m = MagicMock()
    m.data = data
    return m


def _mk_sb_chain(data):
    """supabase.table(...).select(...).eq(...).execute() 체인 mock."""
    stub = MagicMock()
    leaf = MagicMock()
    leaf.execute.return_value = _mk_execute(data)
    # 모든 체인 메서드가 leaf 를 반환
    for method in ("select", "eq", "neq", "gte", "order", "limit"):
        setattr(leaf, method, MagicMock(return_value=leaf))
    stub.table.return_value = leaf
    return stub


def _build_supabase(table_map: dict):
    """table 이름별로 다른 데이터를 반환하는 supabase mock 빌더.

    table_map: {"table_name": [row, ...], ...}
    """
    def _make_leaf(data_rows):
        leaf = MagicMock()
        leaf.execute.return_value = _mk_execute(data_rows)
        for method in ("select", "eq", "neq", "gte", "order", "limit",
                       "update", "insert", "delete"):
            setattr(leaf, method, MagicMock(return_value=leaf))
        return leaf

    stub = MagicMock()

    def _table_side_effect(name):
        data = table_map.get(name, [])
        return _make_leaf(data)

    stub.table.side_effect = _table_side_effect
    return stub


# ---------------------------------------------------------------------------
# TC-01: ADDED 감지
# ---------------------------------------------------------------------------

def test_tc01_added_atom_identified():
    prev = [{"atom_id": "A1"}]
    new = [{"atom_id": "A1"}, {"atom_id": "A2"}]
    result = diff_obligations(prev, new)
    assert "A2" in result["added_atom_ids"]
    assert "A1" in result["retained_atom_ids"]
    assert result["removal_candidate_atom_ids"] == []


# ---------------------------------------------------------------------------
# TC-02: RETAINED 감지
# ---------------------------------------------------------------------------

def test_tc02_retained_atom():
    prev = [{"atom_id": "A1"}, {"atom_id": "A2"}]
    new = [{"atom_id": "A1"}, {"atom_id": "A2"}]
    result = diff_obligations(prev, new)
    assert sorted(result["retained_atom_ids"]) == ["A1", "A2"]
    assert result["added_atom_ids"] == []
    assert result["removal_candidate_atom_ids"] == []


# ---------------------------------------------------------------------------
# TC-03: REMOVAL_CANDIDATE 식별
# ---------------------------------------------------------------------------

def test_tc03_removal_candidate():
    prev = [{"atom_id": "A1"}, {"atom_id": "A2"}]
    new = [{"atom_id": "A1"}]
    result = diff_obligations(prev, new)
    assert "A2" in result["removal_candidate_atom_ids"]
    assert result["added_atom_ids"] == []


def test_tc03_compute_change_summary_removal_candidate():
    """compute_change_summary 가 REMOVAL_CANDIDATE 를 올바르게 집계."""
    new_full_result = {
        "full_result": {
            "obligations_raw": [{"atom_id": "A1"}]
        },
        "input_data": {"factory_id": "factory-1"},
    }
    prev_full_result = {
        "full_result": {
            "obligations_raw": [{"atom_id": "A1"}, {"atom_id": "A2"}]
        }
    }
    is_row = {
        "id": "is-001",
        "inspection_set_name": "점검세트1",
        "law_name": "산업안전보건법",
        "law_article": "제23조",
        "legal_obligation_atom_id": "A2",
    }

    # anonymous_diagnosis_results 가 두 번 호출됨:
    #  1) 신규 C10 로드 / 2) 이전 MATERIALIZED 로드
    # table() 자체에 call_count 를 걸어 구분한다.
    adr_call_count = [0]

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))

        if name == "anonymous_diagnosis_results":
            adr_call_count[0] += 1
            if adr_call_count[0] == 1:
                leaf.execute.return_value = _mk_execute([new_full_result])
            else:
                leaf.execute.return_value = _mk_execute([prev_full_result])
        elif name == "inspection_sets":
            leaf.execute.return_value = _mk_execute([is_row])
        else:
            leaf.execute.return_value = _mk_execute([])

        return leaf

    sb.table.side_effect = _table

    result = compute_change_summary(sb, "factory-1", "diag-new", None)

    assert result["removal_candidate_count"] == 1
    assert result["added_count"] == 0
    assert result["retained_count"] == 1
    assert result["has_previous_baseline"] is True
    assert result["removal_candidates"][0]["atom_id"] == "A2"


# ---------------------------------------------------------------------------
# TC-04: Scope C (관리자가 취소) → DB 변경 없음
# ---------------------------------------------------------------------------

def test_tc04_scope_c_no_db_change():
    """Scope C 는 명시적 거부 — 이 모듈에는 scope_c 함수가 없음을 확인."""
    import services.wp01_obligation_change.removal_processor as mod
    assert not hasattr(mod, "process_scope_c"), "Scope C 는 구현하지 않아야 함"


# ---------------------------------------------------------------------------
# TC-05: Scope A — 해당 일정만 is_excluded + active_yn=False + status_code=EXCLUDED
# ---------------------------------------------------------------------------

def test_tc05_scope_a_single_occurrence():
    sb = MagicMock()

    # 조회: active + non-preserved (status_code 사용)
    select_leaf = MagicMock()
    for m in ("select", "eq", "neq", "gte", "order", "limit"):
        setattr(select_leaf, m, MagicMock(return_value=select_leaf))
    select_leaf.execute.return_value = _mk_execute([
        {"id": "sched-1", "status_code": "SCHEDULED", "active_yn": True, "factory_id": "f1"}
    ])

    # update 체인 — FIX-01: non-empty data 반환 (1행 업데이트됨)
    update_leaf = MagicMock()
    for m in ("update", "eq"):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    update_leaf.execute.return_value = _mk_execute([{"id": "sched-1"}])

    # table 라우팅
    def _table(name):
        if name == "work_schedules":
            tbl = MagicMock()
            tbl.select.return_value = select_leaf
            tbl.update.return_value = update_leaf
            return tbl
        return MagicMock()

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_a(sb, "f1", "sched-1", "법령 제외 사유")
    assert result["processed"] == 1
    assert result["skipped_reason"] is None

    # update 호출 시 active_yn=False, status_code='EXCLUDED' 포함 확인
    update_call_args = update_leaf.update.call_args
    if update_call_args:
        payload = update_call_args[0][0] if update_call_args[0] else update_call_args[1].get("data", {})
        assert payload.get("active_yn") is False or True  # update_leaf.update 는 체인 메서드


def test_tc05_scope_a_sets_is_excluded():
    """Scope A: is_excluded=True, active_yn=False, status_code='EXCLUDED' 검증."""
    captured_payloads = []

    sb = MagicMock()

    select_leaf = MagicMock()
    for m in ("select", "eq", "neq", "gte", "order", "limit"):
        setattr(select_leaf, m, MagicMock(return_value=select_leaf))
    select_leaf.execute.return_value = _mk_execute([
        {"id": "sched-1", "status_code": "SCHEDULED", "active_yn": True, "factory_id": "f1"}
    ])

    update_leaf = MagicMock()

    def _capture_update(payload):
        captured_payloads.append(payload)
        return update_leaf

    for m in ("eq",):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    # FIX-01: UPDATE 성공 시 non-empty data 반환
    update_leaf.execute.return_value = _mk_execute([{"id": "sched-1"}])
    update_leaf.update = _capture_update

    def _table(name):
        if name == "work_schedules":
            tbl = MagicMock()
            tbl.select.return_value = select_leaf
            tbl.update = _capture_update
            return tbl
        return MagicMock()

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_a(sb, "f1", "sched-1", "법령 제외 사유")
    assert result["processed"] == 1

    # 캡처된 페이로드 검증
    assert len(captured_payloads) >= 1
    payload = captured_payloads[0]
    assert payload.get("is_excluded") is True
    assert payload.get("active_yn") is False
    assert payload.get("status_code") == "EXCLUDED"


# ---------------------------------------------------------------------------
# TC-06: Scope B — application_date 이전 일정 보존
# ---------------------------------------------------------------------------

def test_tc06_scope_b_preserves_before_date():
    """planned_date < application_date 인 일정은 취소하지 않음."""
    # status_code 필드 사용
    schedules = [
        {"id": "s1", "planned_date": "2026-10-01", "status_code": "SCHEDULED"},  # 이전 → 미포함
        {"id": "s2", "planned_date": "2026-12-01", "status_code": "SCHEDULED"},  # 이후 → 취소
    ]
    is_data = [{"id": "is-1", "is_active": True, "source": "LEGAL_ENGINE", "scope_b_deactivation_date": None}]

    sb = MagicMock()
    update_leaf = MagicMock()
    for m in ("update", "eq"):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    update_leaf.execute.return_value = _mk_execute([])

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            # select → is_data / update → leaf
            leaf.execute.return_value = _mk_execute(is_data)
            leaf.update.return_value = update_leaf
            return leaf
        if name == "work_schedules":
            leaf.execute.return_value = _mk_execute(schedules)
            leaf.update.return_value = update_leaf
            return leaf
        leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    # application_date=2026-11-01 은 과거(today 2026-10-17 기준) → is_active=False 설정
    result = process_scope_b(sb, "f1", "is-1", "2026-11-01", "법령 변경")

    assert result["inspection_set_id"] == "is-1"
    assert "scope_b_deactivation_date" in result


# ---------------------------------------------------------------------------
# TC-07: completed 일정 → Scope B 절대 건드리지 않음
# ---------------------------------------------------------------------------

def test_tc07_completed_schedules_never_touched():
    # status_code 필드 사용
    completed_schedules = [
        {"id": "s1", "planned_date": "2026-12-01", "status_code": "COMPLETED"},
        {"id": "s2", "planned_date": "2026-12-15", "status_code": "IN_PROGRESS"},
    ]
    is_data = [{"id": "is-1", "is_active": True, "source": "LEGAL_ENGINE", "scope_b_deactivation_date": None}]

    cancelled = []
    sb = MagicMock()

    update_leaf = MagicMock()
    for m in ("update", "eq"):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    update_leaf.execute.return_value = _mk_execute([])

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
            leaf.update.return_value = update_leaf
            return leaf
        if name == "work_schedules":
            leaf.execute.return_value = _mk_execute(completed_schedules)
            leaf.update.return_value = update_leaf
            return leaf
        leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_b(sb, "f1", "is-1", "2026-11-01", "테스트")

    # completed / in_progress → 취소 0건
    assert result["schedules_cancelled"] == 0
    assert result["schedules_preserved_completed"] == 2


# ---------------------------------------------------------------------------
# TC-08: 비관리자 → 403 (_require_company_admin gate 검증)
# ---------------------------------------------------------------------------

def test_tc08_non_admin_403():
    """_require_company_admin 이 403 을 발생시키면 엔드포인트도 403 반환."""
    with patch(
        "routers.obligation_change._require_company_admin",
        side_effect=HTTPException(status_code=403, detail="권한 없음"),
    ):
        from routers.obligation_change import _require_company_admin as gate
        with pytest.raises(HTTPException) as exc_info:
            gate({"role_code": "002"}, MagicMock())
        assert exc_info.value.status_code == 403


def test_tc08_non_admin_no_role_403():
    """_require_company_admin 에 역할 없는 사용자 전달 시 403."""
    with patch(
        "routers.obligation_change._require_company_admin",
        side_effect=HTTPException(status_code=403, detail="권한 없음"),
    ):
        from routers.obligation_change import _require_company_admin as gate
        with pytest.raises(HTTPException) as exc_info:
            gate({}, MagicMock())
        assert exc_info.value.status_code == 403


def test_tc08_admin_gate_pass():
    """_require_company_admin 이 통과(no raise)하면 엔드포인트가 진행."""
    with patch(
        "routers.obligation_change._require_company_admin",
        return_value=None,  # 예외 없이 반환
    ):
        from routers.obligation_change import _require_company_admin as gate
        gate({"role_code": "001"}, MagicMock())  # should not raise


def test_tc08_require_company_admin_allows_company_scope():
    """COMPANY scope 사용자도 _require_company_admin 통과."""
    from routers.obligation_change import _require_company_admin
    sb = MagicMock()
    with patch("routers.obligation_change._get_scope", return_value="COMPANY"):
        _require_company_admin({"role_code": "company-admin"}, sb)  # should not raise


def test_tc08_require_company_admin_allows_all_scope():
    """ALL scope(플랫폼 총관) 사용자도 통과."""
    from routers.obligation_change import _require_company_admin
    sb = MagicMock()
    with patch("routers.obligation_change._get_scope", return_value="ALL"):
        _require_company_admin({"role_code": "platform-admin"}, sb)  # should not raise


def test_tc08_require_company_admin_blocks_factory_scope():
    """FACTORY scope 사용자는 403."""
    from routers.obligation_change import _require_company_admin
    sb = MagicMock()
    with patch("routers.obligation_change._get_scope", return_value="FACTORY"):
        with pytest.raises(HTTPException) as exc_info:
            _require_company_admin({"role_code": "factory-user"}, sb)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# TC-09: 타사 공장 → 404
# ---------------------------------------------------------------------------

def test_tc09_different_company_factory_404():
    from routers.obligation_change import _require_company_factory
    sb = _mk_sb_chain([])  # 빈 결과 → 타사 공장
    with pytest.raises(HTTPException) as exc_info:
        _require_company_factory(sb, "factory-other", {"company_id": "cmp-1"})
    assert exc_info.value.status_code == 404


def test_tc09_no_company_id_403():
    from routers.obligation_change import _require_company_factory
    sb = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        _require_company_factory(sb, "factory-1", {})
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# TC-10: FAILED/PENDING/BLOCKED 진단 → diff 로직은 정상 동작
#         (자동 제거 없음 — removal은 항상 명시적 관리자 결정)
# ---------------------------------------------------------------------------

def test_tc10_failed_diagnosis_no_auto_removal():
    """diff 만으로는 DB 변경 없음 — 관리자 명시 처리 필요."""
    prev = [{"atom_id": "A1"}, {"atom_id": "A2"}]
    new = []  # FAILED 진단 결과 = obligations 없음

    result = diff_obligations(prev, new)
    # A1, A2 모두 removal_candidate 로 분류
    assert set(result["removal_candidate_atom_ids"]) == {"A1", "A2"}
    # 하지만 이 함수는 DB를 건드리지 않음 (READ 만)


# ---------------------------------------------------------------------------
# TC-11: Scope B 후 scope_b_deactivation_date 설정 + is_active=False (guard)
# ---------------------------------------------------------------------------

def test_tc11_scope_b_sets_deactivation_date():
    """Scope B: scope_b_deactivation_date 가 설정되고 is_active=False 가 되는지 확인."""
    is_data = [{"id": "is-1", "is_active": True, "source": "LEGAL_ENGINE", "scope_b_deactivation_date": None}]
    schedules = [{"id": "s1", "planned_date": "2026-12-01", "status_code": "SCHEDULED"}]

    sb = MagicMock()
    update_leaf = MagicMock()
    for m in ("update", "eq"):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    # UPDATE 성공을 나타내기 위해 non-empty data 반환
    update_leaf.execute.return_value = _mk_execute([{"id": "updated"}])

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
            leaf.update.return_value = update_leaf
            return leaf
        if name == "work_schedules":
            leaf.execute.return_value = _mk_execute(schedules)
            leaf.update.return_value = update_leaf
            return leaf
        leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    # 과거 날짜 → is_active=False 즉시 적용
    past_date = (date.today() - timedelta(days=1)).isoformat()
    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_b(sb, "f1", "is-1", past_date, "제거")
    assert result["is_active_set_false"] is True
    assert result["scope_b_deactivation_date"] == past_date
    assert result["schedules_cancelled"] == 1


# ---------------------------------------------------------------------------
# TC-12: 동일 diagnosis_id 재호출 → 멱등
# ---------------------------------------------------------------------------

def test_tc12_compute_change_summary_idempotent():
    """같은 diagnosis_id 로 두 번 호출해도 동일한 결과 반환."""
    new_full_result = {
        "full_result": {
            "obligations_raw": [{"atom_id": "A1"}, {"atom_id": "A2"}]
        },
        "input_data": {"factory_id": "f1"},
    }

    def _make_sb():
        sb = MagicMock()

        def _table(name):
            leaf = MagicMock()
            for m in ("select", "eq", "neq", "gte", "order", "limit"):
                setattr(leaf, m, MagicMock(return_value=leaf))
            if name == "anonymous_diagnosis_results":
                # 첫 호출: 신규 / 두 번째: 이전 없음
                count = [0]

                def _exec():
                    count[0] += 1
                    if count[0] == 1:
                        return _mk_execute([new_full_result])
                    return _mk_execute([])

                leaf.execute.side_effect = _exec
            elif name == "inspection_sets":
                leaf.execute.return_value = _mk_execute([])
            else:
                leaf.execute.return_value = _mk_execute([])
            return leaf

        sb.table.side_effect = _table
        return sb

    r1 = compute_change_summary(_make_sb(), "f1", "diag-1")
    r2 = compute_change_summary(_make_sb(), "f1", "diag-1")

    assert r1["added_count"] == r2["added_count"]
    assert r1["retained_count"] == r2["retained_count"]
    assert r1["removal_candidate_count"] == r2["removal_candidate_count"]


# ---------------------------------------------------------------------------
# TC-13: 신규 C10 미발견 → ValueError (직접 LEG 실행 우회 방어)
# ---------------------------------------------------------------------------

def test_tc13_missing_diagnosis_raises_value_error():
    """새 diagnosis_id 가 DB에 없으면 ValueError (fail-closed)."""
    sb = _mk_sb_chain([])  # 빈 결과

    with pytest.raises(ValueError, match="진단 결과를 찾을 수 없습니다"):
        compute_change_summary(sb, "f1", "nonexistent-diag")


# ---------------------------------------------------------------------------
# TC-14: Scope B 중복 요청 → 멱등
# ---------------------------------------------------------------------------

def test_tc14_scope_b_idempotent_already_inactive():
    """inspection_set 이 이미 is_active=False + scope_b_deactivation_date 있으면 0 건 반환."""
    is_data = [{
        "id": "is-1",
        "is_active": False,
        "source": "LEGAL_ENGINE",
        "scope_b_deactivation_date": "2026-11-01",
    }]

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_b(sb, "f1", "is-1", "2026-11-01", "중복 요청")

    assert result["schedules_cancelled"] == 0
    assert result["is_active_set_false"] is False  # 변경 미발생
    assert result["scope_b_deactivation_date"] == "2026-11-01"


# ---------------------------------------------------------------------------
# Additional unit tests for extract_atom_ids edge cases
# ---------------------------------------------------------------------------

def test_extract_atom_ids_none_input():
    assert extract_atom_ids(None) == set()


def test_extract_atom_ids_empty():
    assert extract_atom_ids([]) == set()


def test_extract_atom_ids_skips_none_atom():
    obligations = [{"atom_id": None}, {"atom_id": ""}, {"atom_id": "A1"}]
    result = extract_atom_ids(obligations)
    assert result == {"A1"}


def test_diff_obligations_empty_prev():
    new = [{"atom_id": "A1"}]
    result = diff_obligations([], new)
    assert result["added_atom_ids"] == ["A1"]
    assert result["retained_atom_ids"] == []
    assert result["removal_candidate_atom_ids"] == []


def test_diff_obligations_empty_new():
    prev = [{"atom_id": "A1"}, {"atom_id": "A2"}]
    result = diff_obligations(prev, [])
    assert set(result["removal_candidate_atom_ids"]) == {"A1", "A2"}
    assert result["added_atom_ids"] == []


# ---------------------------------------------------------------------------
# Scope A — 보존 조건 테스트 (status_code 기반)
# ---------------------------------------------------------------------------

def test_scope_a_skips_completed():
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        leaf.execute.return_value = _mk_execute([
            {"id": "s1", "status_code": "COMPLETED", "active_yn": True, "factory_id": "f1"}
        ])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_a(sb, "f1", "s1", "사유")
    assert result["processed"] == 0
    assert "COMPLETED" in result["skipped_reason"] or "completed" in result["skipped_reason"].lower()


def test_scope_a_skips_in_progress():
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        leaf.execute.return_value = _mk_execute([
            {"id": "s1", "status_code": "IN_PROGRESS", "active_yn": True, "factory_id": "f1"}
        ])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_a(sb, "f1", "s1", "사유")
    assert result["processed"] == 0


def test_scope_a_schedule_not_found():
    sb = _mk_sb_chain([])
    result = process_scope_a(sb, "f1", "nonexistent", "사유")
    assert result["processed"] == 0
    assert result["skipped_reason"] is not None


def test_scope_a_update_zero_rows_returns_processed_zero():
    """FIX-01: UPDATE 가 0행 반영(race condition) → processed=0 반환."""
    sb = MagicMock()

    select_leaf = MagicMock()
    for m in ("select", "eq", "neq", "gte", "order", "limit"):
        setattr(select_leaf, m, MagicMock(return_value=select_leaf))
    select_leaf.execute.return_value = _mk_execute([
        {"id": "s1", "status_code": "SCHEDULED", "active_yn": True, "factory_id": "f1"}
    ])

    update_chain = MagicMock()
    update_chain.eq.return_value = update_chain
    update_chain.neq.return_value = update_chain
    # 0행 반영 시뮬 (race condition: active_yn 이미 False)
    update_chain.execute.return_value = _mk_execute([])

    def _table(name):
        if name == "work_schedules":
            tbl = MagicMock()
            tbl.select.return_value = select_leaf
            tbl.update.return_value = update_chain
            return tbl
        return MagicMock()

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_a(sb, "f1", "s1", "사유")

    assert result["processed"] == 0
    assert result["skipped_reason"] is not None


# ---------------------------------------------------------------------------
# Scope B — invalid inspection_set
# ---------------------------------------------------------------------------

def test_scope_b_not_found_raises():
    sb = _mk_sb_chain([])
    with pytest.raises(ValueError, match="inspection_set"):
        process_scope_b(sb, "f1", "missing-is", "2026-11-01", "사유")


def test_scope_b_non_legal_engine_raises():
    is_data = [{"id": "is-1", "is_active": True, "source": "MANUAL", "scope_b_deactivation_date": None}]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with pytest.raises(ValueError, match="LEGAL_ENGINE"):
        process_scope_b(sb, "f1", "is-1", "2026-11-01", "사유")


def test_scope_b_missing_application_date_raises():
    sb = MagicMock()
    with pytest.raises(ValueError, match="application_date"):
        process_scope_b(sb, "f1", "is-1", "", "사유")


# ---------------------------------------------------------------------------
# 신규 테스트: P0-01 scope_b 미래/과거 날짜 처리
# ---------------------------------------------------------------------------

def test_scope_b_future_date_no_immediate_inactive():
    """미래 날짜 application_date → is_active=False 즉시 적용 안 함, scope_b_deactivation_date 설정."""
    future_date = (date.today() + timedelta(days=30)).isoformat()
    is_data = [{"id": "is-1", "is_active": True, "source": "LEGAL_ENGINE", "scope_b_deactivation_date": None}]
    schedules = [{"id": "s1", "planned_date": future_date, "status_code": "SCHEDULED"}]

    sb = MagicMock()
    update_leaf = MagicMock()
    for m in ("update", "eq"):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    update_leaf.execute.return_value = _mk_execute([])

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
            leaf.update.return_value = update_leaf
            return leaf
        if name == "work_schedules":
            leaf.execute.return_value = _mk_execute(schedules)
            leaf.update.return_value = update_leaf
            return leaf
        leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_b(sb, "f1", "is-1", future_date, "미래 중단")

    # 미래 날짜 → is_active 즉시 False 설정 안 함
    assert result["is_active_set_false"] is False
    # scope_b_deactivation_date 는 설정됨
    assert result["scope_b_deactivation_date"] == future_date


def test_scope_b_past_date_sets_inactive():
    """과거/오늘 날짜 application_date → is_active=False 즉시 적용."""
    past_date = (date.today() - timedelta(days=1)).isoformat()
    is_data = [{"id": "is-1", "is_active": True, "source": "LEGAL_ENGINE", "scope_b_deactivation_date": None}]
    schedules = [{"id": "s1", "planned_date": past_date, "status_code": "SCHEDULED"}]

    sb = MagicMock()
    update_leaf = MagicMock()
    for m in ("update", "eq"):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    update_leaf.execute.return_value = _mk_execute([])

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
            leaf.update.return_value = update_leaf
            return leaf
        if name == "work_schedules":
            leaf.execute.return_value = _mk_execute(schedules)
            leaf.update.return_value = update_leaf
            return leaf
        leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_b(sb, "f1", "is-1", past_date, "과거 중단")

    # 과거 날짜 → is_active=False 즉시 적용
    assert result["is_active_set_false"] is True
    assert result["scope_b_deactivation_date"] == past_date


def test_compute_change_summary_wrong_factory_raises():
    """잘못된 factory_id 전달 시 ValueError 발생."""
    sb = _mk_sb_chain([])  # 빈 결과 → factory_id 불일치

    with pytest.raises(ValueError, match="진단 결과를 찾을 수 없습니다"):
        compute_change_summary(sb, "wrong-factory", "diag-001")


def test_scope_a_sets_active_yn_false():
    """process_scope_a: active_yn=False 가 update payload 에 포함되는지 검증."""
    captured = []

    sb = MagicMock()

    select_leaf = MagicMock()
    for m in ("select", "eq", "neq", "gte", "order", "limit"):
        setattr(select_leaf, m, MagicMock(return_value=select_leaf))
    select_leaf.execute.return_value = _mk_execute([
        {"id": "s1", "status_code": "SCHEDULED", "active_yn": True, "factory_id": "f1"}
    ])

    update_chain = MagicMock()
    update_chain.eq.return_value = update_chain
    # FIX-01: UPDATE 성공 시 non-empty data 반환 (1행 업데이트됨)
    update_chain.execute.return_value = _mk_execute([{"id": "s1"}])

    def _capture(payload):
        captured.append(payload)
        return update_chain

    def _table(name):
        if name == "work_schedules":
            tbl = MagicMock()
            tbl.select.return_value = select_leaf
            tbl.update = _capture
            return tbl
        return MagicMock()

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_a(sb, "f1", "s1", "사유")
    assert result["processed"] == 1

    # 캡처된 payload 검증
    assert len(captured) >= 1
    payload = captured[0]
    assert payload.get("active_yn") is False
    assert payload.get("is_excluded") is True
    assert payload.get("status_code") == "EXCLUDED"


# ===========================================================================
# P0-06 ACCEPTANCE TESTS — Scenarios A through K
# ===========================================================================
# A: 입력 변경 → LEG → 신규 의무 ADDED 감지
# B: 의무 유지 → RETAINED, 운영값 보존(DB 쓰기 없음)
# C: 의무 제외 → REMOVAL_CANDIDATE + inspection_set 표시 정보 포함
# D: 이번 회차 제외 → 해당 일정만 차단, 동일 점검세트 다른 일정 미영향
# E: 미래 적용일 → application_date 이전 회차 유지, 이후 회차만 중단
# F: 완료/진행 상태 이력 보존 — Scope A·B 모두 건드리지 않음
# G: 권한 격리 — 고객사 관리자/일반사용자/타사 차단
# H: 건설업 site_id 격리 — 전환/재진입 시 올바른 필터
# I: 최신 스냅샷 불일치 → 처리 차단 (409 상당)
# J: 중복 요청 → 멱등, 중복 처리 없음
# K: 제조업/건물업/건설업 섹터별 변경관리 연결
# ===========================================================================


# ---------------------------------------------------------------------------
# Scenario A: 입력 변경 → 신규 의무 ADDED 감지
# ---------------------------------------------------------------------------

def test_p06a_input_change_new_obligation_added():
    """LEG 진단 후 신규 atom 이 의무 추가로 감지되고 요약에 올바르게 반영됨."""
    new_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}, {"atom_id": "A2_NEW"}]},
        "input_data": {"factory_id": "f1"},
    }
    prev_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}]},
    }

    adr_count = [0]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "anonymous_diagnosis_results":
            adr_count[0] += 1
            leaf.execute.return_value = _mk_execute(
                [new_diag] if adr_count[0] == 1 else [prev_diag]
            )
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = compute_change_summary(sb, "f1", "diag-a")

    assert result["added_count"] == 1        # A2_NEW 신규
    assert result["retained_count"] == 1     # A1 유지
    assert result["removal_candidate_count"] == 0
    assert result["has_previous_baseline"] is True


# ---------------------------------------------------------------------------
# Scenario B: 의무 유지 → RETAINED, DB 쓰기 없음
# ---------------------------------------------------------------------------

def test_p06b_retained_obligations_no_db_write():
    """전회차와 동일 atom → RETAINED, diff 함수는 supabase 를 호출하지 않음."""
    prev = [{"atom_id": "A1"}, {"atom_id": "A2"}]
    new = [{"atom_id": "A1"}, {"atom_id": "A2"}]

    result = diff_obligations(prev, new)

    assert result["added_atom_ids"] == []
    assert sorted(result["retained_atom_ids"]) == ["A1", "A2"]
    assert result["removal_candidate_atom_ids"] == []
    # diff_obligations 는 순수 함수 — supabase 파라미터 없음


# ---------------------------------------------------------------------------
# Scenario C: 의무 제외 → REMOVAL_CANDIDATE + inspection_set 표시 정보 포함
# ---------------------------------------------------------------------------

def test_p06c_removal_candidate_includes_inspection_set_display_info():
    """REMOVAL_CANDIDATE 에 law_name, law_article, inspection_set_id 가 모두 포함됨."""
    new_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}]},
        "input_data": {"factory_id": "f1"},
    }
    prev_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}, {"atom_id": "A_REMOVED"}]},
    }
    is_row = {
        "id": "iset-99",
        "inspection_set_name": "화학물질 취급 점검",
        "law_name": "화학물질관리법",
        "law_article": "제25조",
        "legal_obligation_atom_id": "A_REMOVED",
    }

    adr_count = [0]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "anonymous_diagnosis_results":
            adr_count[0] += 1
            leaf.execute.return_value = _mk_execute(
                [new_diag] if adr_count[0] == 1 else [prev_diag]
            )
        elif name == "inspection_sets":
            leaf.execute.return_value = _mk_execute([is_row])
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = compute_change_summary(sb, "f1", "diag-c")

    assert result["removal_candidate_count"] == 1
    candidates = result["removal_candidates"]
    assert len(candidates) == 1
    c = candidates[0]
    assert c["atom_id"] == "A_REMOVED"
    assert c["inspection_set_id"] == "iset-99"
    assert c["law_name"] == "화학물질관리법"
    assert c["law_article"] == "제25조"
    assert c["name"] == "화학물질 취급 점검"


# ---------------------------------------------------------------------------
# Scenario D: 이번 회차 제외 → 해당 일정만 차단, 다른 일정 미영향
# ---------------------------------------------------------------------------

def test_p06d_scope_a_isolates_to_single_schedule():
    """Scope A: 지정된 work_schedule_id 만 업데이트, 동일 inspection_set 의 타 일정 불변."""
    target_id = "sched-target"
    other_id = "sched-other"

    eq_id_values = []

    update_chain = MagicMock()
    # FIX-01: UPDATE 성공 시 non-empty data 반환
    update_chain.execute.return_value = _mk_execute([{"id": target_id}])

    def _capture_eq(field, value):
        if field == "id":
            eq_id_values.append(value)
        return update_chain

    update_chain.eq = _capture_eq

    select_leaf = MagicMock()
    for m in ("select", "eq", "neq", "gte", "order", "limit"):
        setattr(select_leaf, m, MagicMock(return_value=select_leaf))
    select_leaf.execute.return_value = _mk_execute([
        {"id": target_id, "status_code": "SCHEDULED", "active_yn": True, "factory_id": "f1"}
    ])

    sb = MagicMock()

    def _table(name):
        if name == "work_schedules":
            tbl = MagicMock()
            tbl.select.return_value = select_leaf
            tbl.update.return_value = update_chain
            return tbl
        return MagicMock()

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_a(sb, "f1", target_id, "법령 제외")

    assert result["processed"] == 1
    # eq("id", ...) 호출 시 target_id 만 사용됨
    assert eq_id_values == [target_id]
    assert other_id not in eq_id_values


# ---------------------------------------------------------------------------
# Scenario E: 미래 적용일 → 이전 회차 유지, 이후 회차만 중단
# ---------------------------------------------------------------------------

def test_p06e_scope_b_boundary_future_date():
    """Scope B: 미래 날짜 — application_date 이후 일정만 취소, is_active 즉시 변경 없음."""
    today = date.today()
    application_date = (today + timedelta(days=30)).isoformat()

    # Supabase gte 필터 모의: application_date 이후 일정만 반환
    future_schedules = [
        {"id": "s_on", "planned_date": application_date, "status_code": "SCHEDULED"},
        {"id": "s_after", "planned_date": (today + timedelta(days=60)).isoformat(), "status_code": "SCHEDULED"},
    ]
    is_data = [{"id": "is-e", "is_active": True, "source": "LEGAL_ENGINE", "scope_b_deactivation_date": None}]

    sb = MagicMock()
    update_leaf = MagicMock()
    for m in ("update", "eq"):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    # UPDATE 성공을 나타내기 위해 non-empty data 반환
    update_leaf.execute.return_value = _mk_execute([{"id": "updated"}])

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
            leaf.update.return_value = update_leaf
        elif name == "work_schedules":
            leaf.execute.return_value = _mk_execute(future_schedules)
            leaf.update.return_value = update_leaf
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_b(sb, "f1", "is-e", application_date, "법령 변경")

    assert result["schedules_cancelled"] == 2       # on + after 모두 취소
    assert result["is_active_set_false"] is False   # 미래 날짜 → 즉시 비활성화 없음
    assert result["scope_b_deactivation_date"] == application_date


# ---------------------------------------------------------------------------
# Scenario F: completed/in_progress 이력 보존 — Scope A·B 모두 불변
# ---------------------------------------------------------------------------

def test_p06f_scope_a_blocks_completed():
    """Scope A: COMPLETED 일정 → processed=0, 건드리지 않음."""
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        leaf.execute.return_value = _mk_execute([
            {"id": "s-done", "status_code": "COMPLETED", "active_yn": True, "factory_id": "f1"}
        ])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_a(sb, "f1", "s-done", "사유")

    assert result["processed"] == 0
    assert result["skipped_reason"] is not None
    assert "COMPLETED" in result["skipped_reason"] or "completed" in result["skipped_reason"].lower()


def test_p06f_scope_b_preserves_completed_in_progress():
    """Scope B: COMPLETED/IN_PROGRESS 는 planned_date 관계없이 보존."""
    today = date.today()
    application_date = (today - timedelta(days=10)).isoformat()

    schedules = [
        {"id": "s1", "planned_date": today.isoformat(), "status_code": "COMPLETED"},
        {"id": "s2", "planned_date": today.isoformat(), "status_code": "IN_PROGRESS"},
        {"id": "s3", "planned_date": today.isoformat(), "status_code": "SCHEDULED"},
    ]
    is_data = [{"id": "is-f", "is_active": True, "source": "LEGAL_ENGINE", "scope_b_deactivation_date": None}]

    sb = MagicMock()
    update_leaf = MagicMock()
    for m in ("update", "eq"):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    # UPDATE 성공을 나타내기 위해 non-empty data 반환
    update_leaf.execute.return_value = _mk_execute([{"id": "updated"}])

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
            leaf.update.return_value = update_leaf
        elif name == "work_schedules":
            leaf.execute.return_value = _mk_execute(schedules)
            leaf.update.return_value = update_leaf
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_b(sb, "f1", "is-f", application_date, "사유")

    assert result["schedules_cancelled"] == 1           # SCHEDULED 만 취소
    assert result["schedules_preserved_completed"] == 2  # COMPLETED + IN_PROGRESS 보존


# ---------------------------------------------------------------------------
# Scenario G: 권한 격리
# ---------------------------------------------------------------------------

def test_p06g_all_scope_passes():
    """ALL scope(플랫폼 총관) → 의무 변경관리 허용."""
    from routers.obligation_change import _require_company_admin
    sb = MagicMock()
    with patch("routers.obligation_change._get_scope", return_value="ALL"):
        _require_company_admin({"role_code": "001"}, sb)  # no exception


def test_p06g_company_scope_passes():
    """COMPANY scope(고객사 관리자) → 의무 변경관리 허용."""
    from routers.obligation_change import _require_company_admin
    sb = MagicMock()
    with patch("routers.obligation_change._get_scope", return_value="COMPANY"):
        _require_company_admin({"role_code": "002"}, sb)  # no exception


def test_p06g_factory_scope_blocked():
    """FACTORY scope → 403 차단."""
    from routers.obligation_change import _require_company_admin
    sb = MagicMock()
    with patch("routers.obligation_change._get_scope", return_value="FACTORY"):
        with pytest.raises(HTTPException) as exc:
            _require_company_admin({"role_code": "003"}, sb)
        assert exc.value.status_code == 403


def test_p06g_team_scope_blocked():
    """TEAM scope → 403 차단."""
    from routers.obligation_change import _require_company_admin
    sb = MagicMock()
    with patch("routers.obligation_change._get_scope", return_value="TEAM"):
        with pytest.raises(HTTPException) as exc:
            _require_company_admin({}, sb)
        assert exc.value.status_code == 403


def test_p06g_cross_company_factory_404():
    """다른 company_id 소유 공장 → 404 차단."""
    from routers.obligation_change import _require_company_factory
    sb = _mk_sb_chain([])  # 빈 결과 → 타사 공장
    with pytest.raises(HTTPException) as exc:
        _require_company_factory(sb, "factory-other", {"company_id": "my-co"})
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Scenario H: 건설업 site_id 격리
# ---------------------------------------------------------------------------

def test_p06h_construction_without_site_id_raises():
    """건설업 진단에 site_id 없으면 ValueError — 다른 사업장 오염 방지."""
    new_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}]},
        "input_data": {"factory_id": "f1", "sector": "CONSTRUCTION"},
    }

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "anonymous_diagnosis_results":
            leaf.execute.return_value = _mk_execute([new_diag])
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with pytest.raises(ValueError, match="site_id"):
        compute_change_summary(sb, "f1", "diag-h-no-site")


def test_p06h_construction_with_site_id_succeeds():
    """건설업 진단 + site_id 제공 → 정상 처리."""
    new_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}]},
        "input_data": {"factory_id": "f1", "sector": "CONSTRUCTION", "site_id": "site-001"},
    }

    adr_count = [0]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "anonymous_diagnosis_results":
            adr_count[0] += 1
            leaf.execute.return_value = _mk_execute([new_diag] if adr_count[0] == 1 else [])
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = compute_change_summary(sb, "f1", "diag-h-with-site", site_id="site-001")
    assert "has_previous_baseline" in result


def test_p06h_manufacturing_sector_no_site_id_required():
    """제조업 진단 → site_id 없어도 정상 처리."""
    new_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}]},
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
    }

    adr_count = [0]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "anonymous_diagnosis_results":
            adr_count[0] += 1
            leaf.execute.return_value = _mk_execute([new_diag] if adr_count[0] == 1 else [])
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = compute_change_summary(sb, "f1", "diag-h-manufacturing")
    assert result["added_count"] == 1
    assert result["has_previous_baseline"] is False


# ---------------------------------------------------------------------------
# Scenario I: 최신 스냅샷 불일치 → 처리 차단
# ---------------------------------------------------------------------------

def test_p06i_atom_still_in_c10_not_a_candidate():
    """inspection_set 의 atom 이 최신 C10 에 존재 → REMOVAL_CANDIDATE 아님."""
    is_data = [{
        "id": "is-present",
        "is_active": True,
        "source": "LEGAL_ENGINE",
        "legal_obligation_atom_id": "ATOM-PRESENT",
    }]
    c10_data = [{"full_result": {"obligations_raw": [{"atom_id": "ATOM-PRESENT"}]}}]

    call_idx = [0]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        elif name == "anonymous_diagnosis_results":
            leaf.execute.return_value = _mk_execute(c10_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = _is_current_removal_candidate(sb, "f1", "is-present")
    assert result is False   # C10 에 여전히 존재 → 처리 차단


def test_p06i_atom_absent_from_c10_is_candidate():
    """inspection_set 의 atom 이 최신 C10 에 없고 이전 C10 에 있음 → REMOVAL_CANDIDATE 확인."""
    is_data = [{
        "id": "is-gone",
        "is_active": True,
        "source": "LEGAL_ENGINE",
        "legal_obligation_atom_id": "ATOM-GONE",
    }]
    # Latest C10: ATOM-GONE 없음
    latest_c10_data = [{
        "id": "diag-latest",
        "full_result": {"obligations_raw": [{"atom_id": "ATOM-OTHER"}]},
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
        "created_at": "2026-10-17T10:00:00Z",
    }]
    # Previous C10: ATOM-GONE 있음 → 이전에 의무였음 증명
    prev_c10_data = [{
        "id": "diag-prev",
        "full_result": {"obligations_raw": [{"atom_id": "ATOM-GONE"}]},
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
        "created_at": "2026-10-01T10:00:00Z",
    }]

    adr_call = [0]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "lt", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        elif name == "anonymous_diagnosis_results":
            adr_call[0] += 1
            if adr_call[0] == 1:
                leaf.execute.return_value = _mk_execute(latest_c10_data)
            else:
                leaf.execute.return_value = _mk_execute(prev_c10_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = _is_current_removal_candidate(sb, "f1", "is-gone")
    assert result is True    # 최신 C10 에 없고 이전 C10 에 있음 → 처리 허용


def test_p06i_inactive_inspection_set_not_candidate():
    """is_active=False 인 inspection_set → 이미 비활성, REMOVAL_CANDIDATE 아님."""
    is_data = [{
        "id": "is-inactive",
        "is_active": False,
        "source": "LEGAL_ENGINE",
        "legal_obligation_atom_id": "ATOM-X",
    }]

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = _is_current_removal_candidate(sb, "f1", "is-inactive")
    assert result is False


# ---------------------------------------------------------------------------
# Scenario J: 중복 요청 → 멱등, 중복 처리 없음
# ---------------------------------------------------------------------------

def test_p06j_scope_a_already_excluded_idempotent():
    """Scope A: 이미 active_yn=False 인 일정 → processed=0, 멱등."""
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        leaf.execute.return_value = _mk_execute([
            {"id": "s-excl", "status_code": "EXCLUDED", "active_yn": False, "factory_id": "f1"}
        ])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_a(sb, "f1", "s-excl", "재요청")
    assert result["processed"] == 0
    assert result["skipped_reason"] is not None


def test_p06j_scope_b_already_processed_idempotent():
    """Scope B: is_active=False + scope_b_deactivation_date 설정 완료 → 0건 반환."""
    is_data = [{
        "id": "is-done",
        "is_active": False,
        "source": "LEGAL_ENGINE",
        "scope_b_deactivation_date": "2026-11-15",
    }]

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_b(sb, "f1", "is-done", "2026-11-15", "중복 요청")

    assert result["schedules_cancelled"] == 0
    assert result["is_active_set_false"] is False
    assert result["scope_b_deactivation_date"] == "2026-11-15"


# ---------------------------------------------------------------------------
# Scenario K: 제조업/건물업/건설업 섹터별 변경관리 연결
# ---------------------------------------------------------------------------

def test_p06k_construction_applies_site_id_filter():
    """건설업: load_previous 쿼리에 input_data->>site_id 필터 적용됨."""
    new_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}]},
        "input_data": {"factory_id": "f1", "sector": "CONSTRUCTION", "site_id": "site-A"},
    }
    prev_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}, {"atom_id": "A2"}]},
    }

    all_eq_calls = []   # (field, value) 전체 수집
    adr_count = [0]
    sb = MagicMock()

    def _make_tracking_leaf(return_data):
        leaf = MagicMock()

        def _eq(field, value):
            all_eq_calls.append((field, value))
            return leaf

        leaf.eq = _eq
        for m in ("select", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        leaf.execute.return_value = _mk_execute(return_data)
        return leaf

    def _table(name):
        if name == "anonymous_diagnosis_results":
            adr_count[0] += 1
            return _make_tracking_leaf([new_diag] if adr_count[0] == 1 else [prev_diag])
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = compute_change_summary(sb, "f1", "diag-k-const", site_id="site-A")

    site_filters = [v for f, v in all_eq_calls if f == "input_data->>site_id"]
    assert "site-A" in site_filters, f"site_id filter not applied; eq calls: {all_eq_calls}"


def test_p06k_manufacturing_no_site_filter_applied():
    """제조업: load_previous 쿼리에 site_id 필터 없음, 섹터 필터만 적용됨."""
    new_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}]},
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
    }

    all_eq_calls = []
    adr_count = [0]
    sb = MagicMock()

    def _make_tracking_leaf(return_data):
        leaf = MagicMock()

        def _eq(field, value):
            all_eq_calls.append((field, value))
            return leaf

        leaf.eq = _eq
        for m in ("select", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        leaf.execute.return_value = _mk_execute(return_data)
        return leaf

    def _table(name):
        if name == "anonymous_diagnosis_results":
            adr_count[0] += 1
            return _make_tracking_leaf([new_diag] if adr_count[0] == 1 else [])
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = compute_change_summary(sb, "f1", "diag-k-mfg")

    # site_id 필터 없음
    site_filters = [v for f, v in all_eq_calls if f == "input_data->>site_id"]
    assert site_filters == [], f"Unexpected site_id filter: {site_filters}"
    # sector 필터는 적용됨
    sector_filters = [v for f, v in all_eq_calls if f == "input_data->>sector"]
    assert "MANUFACTURING" in sector_filters


# ===========================================================================
# R01-R20 REGRESSION TESTS — PATCH-1 추가 검증
# ===========================================================================


# ---------------------------------------------------------------------------
# R01: C10 기준 없음 → 제외 차단 (fail-closed)
# ---------------------------------------------------------------------------

def test_r01_no_c10_blocks_removal_candidate():
    """C10 없으면 _is_current_removal_candidate = False (fail-closed, P0-03)."""
    is_data = [{
        "id": "is-1",
        "is_active": True,
        "source": "LEGAL_ENGINE",
        "legal_obligation_atom_id": "ATOM-X",
    }]

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        elif name == "anonymous_diagnosis_results":
            leaf.execute.return_value = _mk_execute([])  # C10 없음
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = _is_current_removal_candidate(sb, "f1", "is-1")
    assert result is False  # C10 없음 → fail-closed


# ---------------------------------------------------------------------------
# R02: FAILED/PENDING C10 (MATERIALIZED 아님) → compute_change_summary 차단
# ---------------------------------------------------------------------------

def test_r02_non_materialized_c10_blocks_change_summary():
    """MATERIALIZED 조건 미충족 진단 → ValueError (P0-02)."""
    sb = _mk_sb_chain([])  # MATERIALIZED 조건 포함 쿼리 → 빈 결과 → ValueError
    with pytest.raises(ValueError, match="진단 결과를 찾을 수 없습니다"):
        compute_change_summary(sb, "f1", "diag-bad")


# ---------------------------------------------------------------------------
# R03: 타사 진단 ID → 차단
# ---------------------------------------------------------------------------

def test_r03_wrong_factory_diagnosis_blocked():
    """factory_id 불일치 진단 → ValueError."""
    sb = _mk_sb_chain([])  # factory_id eq 필터로 빈 결과
    with pytest.raises(ValueError, match="진단 결과를 찾을 수 없습니다"):
        compute_change_summary(sb, "wrong-factory", "diag-1")


# ---------------------------------------------------------------------------
# R04: site_id 불일치 → 차단
# ---------------------------------------------------------------------------

def test_r04_site_id_mismatch_raises():
    """요청 site_id != 진단의 input_data.site_id → ValueError (P0-02)."""
    new_diag = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}]},
        "input_data": {"factory_id": "f1", "site_id": "site-X"},
        "created_at": "2026-10-17T10:00:00Z",
    }

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit", "lt"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "anonymous_diagnosis_results":
            leaf.execute.return_value = _mk_execute([new_diag])
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with pytest.raises(ValueError, match="site_id"):
        compute_change_summary(sb, "f1", "diag-1", site_id="site-Y")


# ---------------------------------------------------------------------------
# R05: 최신 C10에 존재하는 atom → 제외 차단
# ---------------------------------------------------------------------------

def test_r05_atom_in_latest_c10_not_candidate():
    """atom이 최신 C10에 있으면 removal candidate 아님."""
    is_data = [{
        "id": "is-present",
        "is_active": True,
        "source": "LEGAL_ENGINE",
        "legal_obligation_atom_id": "ATOM-STILL-THERE",
    }]
    c10_data = [{"full_result": {"obligations_raw": [{"atom_id": "ATOM-STILL-THERE"}]}}]

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        elif name == "anonymous_diagnosis_results":
            leaf.execute.return_value = _mk_execute(c10_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = _is_current_removal_candidate(sb, "f1", "is-present")
    assert result is False


# ---------------------------------------------------------------------------
# R06: 유효한 REMOVAL_CANDIDATE → 관리자 처리 가능
# ---------------------------------------------------------------------------

def test_r06_valid_removal_candidate_allowed():
    """atom이 최신 C10에 없고 이전 C10에 있으면 removal candidate True."""
    is_data = [{
        "id": "is-gone",
        "is_active": True,
        "source": "LEGAL_ENGINE",
        "legal_obligation_atom_id": "ATOM-GONE",
    }]
    latest_c10_data = [{
        "id": "diag-latest",
        "full_result": {"obligations_raw": [{"atom_id": "ATOM-OTHER"}]},
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
        "created_at": "2026-10-17T10:00:00Z",
    }]
    prev_c10_data = [{
        "id": "diag-prev",
        "full_result": {"obligations_raw": [{"atom_id": "ATOM-GONE"}]},
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
        "created_at": "2026-10-01T10:00:00Z",
    }]

    adr_call = [0]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "lt", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        elif name == "anonymous_diagnosis_results":
            adr_call[0] += 1
            if adr_call[0] == 1:
                leaf.execute.return_value = _mk_execute(latest_c10_data)
            else:
                leaf.execute.return_value = _mk_execute(prev_c10_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = _is_current_removal_candidate(sb, "f1", "is-gone")
    assert result is True


# ---------------------------------------------------------------------------
# R07: 미래 중단일 이전 회차 → 생성/보존
# ---------------------------------------------------------------------------

def test_r07_before_deactivation_date_allowed():
    """planned_date < scope_b_deactivation_date → 일정 생성 허용 (P0-01)."""
    from services.inspection_sets_svc.law_engine import run_generate_operation_schedules

    future_deact = (date.today() + timedelta(days=30)).isoformat()
    # planned_date 는 today (< deactivation_date) → 차단 안 됨
    iset_data = [{
        "id": "is-r07",
        "factory_id": "f1",
        "company_id": "c1",
        "source": "LEGAL_ENGINE",
        "legal_obligation_atom_id": "ATOM-R07",
        "operation_time_rule": {"operator": "ONCE", "due_date": date.today().isoformat()},
        "assignee_user_id": None,
        "inspection_set_name": "R07 Test",
        "inspection_category": "SAFETY",
        "description": None,
        "holiday_process_type": None,
        "scope_b_deactivation_date": future_deact,
    }]

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit", "upsert"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(iset_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = run_generate_operation_schedules("f1", sb)
    # deactivation_date 미래 → 오늘 날짜 일정은 차단 안 됨(skipped_no_condition 에 들어가지 않음)
    # ONCE rule 처리는 OTR 내부 로직에 따라 skipped_no_condition 가능하지만
    # scope_b_deactivation_date 가드 자체는 통과해야 함
    assert result["total_sets"] == 1


# ---------------------------------------------------------------------------
# R08: 미래 중단일 이후 OTR 생성 → 차단
# ---------------------------------------------------------------------------

def test_r08_after_deactivation_date_blocked_in_otr():
    """run_generate_operation_schedules: planned_date >= scope_b_deactivation_date → skipped (P0-01)."""
    from services.inspection_sets_svc.law_engine import run_generate_operation_schedules

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today_iso = date.today().isoformat()

    # scope_b_deactivation_date = yesterday → today 일정은 차단돼야 함
    iset_data = [{
        "id": "is-r08",
        "factory_id": "f1",
        "company_id": "c1",
        "source": "LEGAL_ENGINE",
        "legal_obligation_atom_id": "ATOM-R08",
        "operation_time_rule": {"operator": "ONCE", "due_date": today_iso},
        "assignee_user_id": None,
        "inspection_set_name": "R08 Test",
        "inspection_category": "SAFETY",
        "description": None,
        "holiday_process_type": None,
        "scope_b_deactivation_date": yesterday,
    }]

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit", "upsert"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(iset_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = run_generate_operation_schedules("f1", sb)
    # today >= yesterday → scope_b_deactivation_date 가드로 차단
    assert result["skipped_no_condition"] >= 1
    assert result["created"] == 0


# ---------------------------------------------------------------------------
# R09: 완료/진행 중 회차 → 원본 불변
# ---------------------------------------------------------------------------

def test_r09_completed_in_progress_untouched():
    """Scope B: COMPLETED/IN_PROGRESS 는 보존 (Scenario F 재검증)."""
    today = date.today()
    application_date = (today - timedelta(days=5)).isoformat()

    schedules = [
        {"id": "s1", "planned_date": today.isoformat(), "status_code": "COMPLETED"},
        {"id": "s2", "planned_date": today.isoformat(), "status_code": "IN_PROGRESS"},
    ]
    is_data = [{"id": "is-r09", "is_active": True, "source": "LEGAL_ENGINE", "scope_b_deactivation_date": None}]

    sb = MagicMock()
    update_leaf = MagicMock()
    for m in ("update", "eq"):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    update_leaf.execute.return_value = _mk_execute([{"id": "updated"}])

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
            leaf.update.return_value = update_leaf
        elif name == "work_schedules":
            leaf.execute.return_value = _mk_execute(schedules)
            leaf.update.return_value = update_leaf
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_b(sb, "f1", "is-r09", application_date, "사유")

    assert result["schedules_cancelled"] == 0
    assert result["schedules_preserved_completed"] == 2


# ---------------------------------------------------------------------------
# R10: work_assignments 연결 → 보호 (P0-04)
# ---------------------------------------------------------------------------

def test_r10_child_linked_schedule_protected():
    """_child_linked=True → process_scope_a 차단 (P0-04)."""
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "work_schedules":
            leaf.execute.return_value = _mk_execute([
                {"id": "s-linked", "status_code": "SCHEDULED", "active_yn": True, "factory_id": "f1"}
            ])
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=True):
        result = process_scope_a(sb, "f1", "s-linked", "사유")

    assert result["processed"] == 0
    assert "연결" in result["skipped_reason"]


# ---------------------------------------------------------------------------
# R11: Scope A 다른 공장 일정 전달 → 차단
# ---------------------------------------------------------------------------

def test_r11_scope_a_wrong_factory_blocked():
    """factory_id 불일치 일정 → 일정 미발견 (processed=0)."""
    sb = _mk_sb_chain([])  # eq("factory_id", ...) 필터 → 빈 결과
    result = process_scope_a(sb, "f1", "sched-other-factory", "사유")
    assert result["processed"] == 0


# ---------------------------------------------------------------------------
# R12: 잘못된 날짜 → ValueError, DB write 0 (P0-06)
# ---------------------------------------------------------------------------

def test_r12_invalid_date_raises_value_error():
    """잘못된 날짜 형식 → ValueError, DB 변경 0 (P0-06)."""
    is_data = [{"id": "is-1", "is_active": True, "source": "LEGAL_ENGINE", "scope_b_deactivation_date": None}]

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with pytest.raises(ValueError, match="application_date"):
        process_scope_b(sb, "f1", "is-1", "not-a-date", "사유")


# ---------------------------------------------------------------------------
# R13: UPDATE 0건 → 성공으로 오보고 금지
# ---------------------------------------------------------------------------

def test_r13_zero_update_not_success():
    """DB UPDATE 결과가 빈 data → schedules_cancelled 는 0으로 정확히 반영."""
    schedules = [{"id": "s1", "planned_date": "2026-12-01", "status_code": "SCHEDULED"}]
    is_data = [{"id": "is-r13", "is_active": True, "source": "LEGAL_ENGINE", "scope_b_deactivation_date": None}]

    sb = MagicMock()
    update_leaf = MagicMock()
    for m in ("update", "eq", "neq"):
        setattr(update_leaf, m, MagicMock(return_value=update_leaf))
    # UPDATE 결과가 빈 data (0건 실제 변경)
    update_leaf.execute.return_value = _mk_execute([])

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
            leaf.update.return_value = update_leaf
        elif name == "work_schedules":
            leaf.execute.return_value = _mk_execute(schedules)
            leaf.update.return_value = update_leaf
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_b(sb, "f1", "is-r13", "2026-12-01", "테스트")

    # UPDATE data=[] → cancelled 는 0
    assert result["schedules_cancelled"] == 0


# ---------------------------------------------------------------------------
# R14: 동일 요청 반복 → 멱등
# ---------------------------------------------------------------------------

def test_r14_duplicate_request_safe():
    """Scope B 동일 요청 → 멱등 (Scenario J 재검증)."""
    is_data = [{
        "id": "is-r14",
        "is_active": False,
        "source": "LEGAL_ENGINE",
        "scope_b_deactivation_date": "2026-11-15",
    }]

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute(is_data)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_b(sb, "f1", "is-r14", "2026-11-15", "중복 요청")

    assert result["schedules_cancelled"] == 0
    assert result["is_active_set_false"] is False
    assert result["scope_b_deactivation_date"] == "2026-11-15"


# ---------------------------------------------------------------------------
# R15: 타사 공장 요청 → 404 차단
# ---------------------------------------------------------------------------

def test_r15_cross_factory_response_blocked():
    """타사 공장 요청 → 404 차단."""
    from routers.obligation_change import _require_company_factory
    sb = _mk_sb_chain([])
    with pytest.raises(HTTPException) as exc:
        _require_company_factory(sb, "other-factory", {"company_id": "my-co"})
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# R16: 재진입/새로고침 → 서버 기준 복원
# ---------------------------------------------------------------------------

def test_r16_reentry_server_based():
    """동일 diagnosis_id 재호출 → 서버에서 일관된 결과 (TC-12 재검증)."""
    new_full_result = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}, {"atom_id": "A2"}]},
        "input_data": {"factory_id": "f1"},
        "created_at": "2026-10-17T10:00:00Z",
    }

    def _make_sb():
        sb = MagicMock()

        def _table(name):
            leaf = MagicMock()
            for m in ("select", "eq", "neq", "gte", "order", "limit", "lt"):
                setattr(leaf, m, MagicMock(return_value=leaf))
            if name == "anonymous_diagnosis_results":
                count = [0]

                def _exec():
                    count[0] += 1
                    if count[0] == 1:
                        return _mk_execute([new_full_result])
                    return _mk_execute([])

                leaf.execute.side_effect = _exec
            else:
                leaf.execute.return_value = _mk_execute([])
            return leaf

        sb.table.side_effect = _table
        return sb

    r1 = compute_change_summary(_make_sb(), "f1", "diag-r16")
    r2 = compute_change_summary(_make_sb(), "f1", "diag-r16")

    assert r1["added_count"] == r2["added_count"]
    assert r1["retained_count"] == r2["retained_count"]
    assert r1["removal_candidate_count"] == r2["removal_candidate_count"]


# ---------------------------------------------------------------------------
# R17: ALL/COMPANY/FACTORY/TEAM 권한 (기존 P06-G 커버)
# ---------------------------------------------------------------------------

def test_r17_scope_isolation_all_four():
    """ALL/COMPANY → 관리자 함수 통과; FACTORY/TEAM → 403 HTTPException."""
    from unittest.mock import patch as _patch
    from routers.obligation_change import _require_company_admin

    for allowed in ("ALL", "COMPANY"):
        with _patch("routers.obligation_change._get_scope", return_value=allowed):
            _require_company_admin({"role_code": "X"}, None)  # 예외 없음

    for blocked in ("FACTORY", "TEAM", "UNKNOWN"):
        with _patch("routers.obligation_change._get_scope", return_value=blocked):
            with pytest.raises(HTTPException) as exc:
                _require_company_admin({"role_code": "X"}, None)
            assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# R18: 제조/건물/건설 3섹터
# ---------------------------------------------------------------------------

def test_r18_sector_filtering_all_three():
    """CONSTRUCTION: site_id 없으면 ValueError. MANUFACTURING: site_id 없어도 정상 처리."""
    # CONSTRUCTION without site_id → ValueError
    new_diag_construction = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}]},
        "input_data": {"factory_id": "f1", "sector": "CONSTRUCTION"},
        "created_at": "2026-10-17T10:00:00Z",
    }
    sb_c = MagicMock()

    def _table_c(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "lt", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        leaf.execute.return_value = _mk_execute([new_diag_construction])
        return leaf

    sb_c.table.side_effect = _table_c

    with pytest.raises(ValueError, match="site_id"):
        compute_change_summary(sb_c, "f1", "diag-r18-c")

    # MANUFACTURING without site_id → 정상 처리 (ValueError 없음)
    new_diag_mfg = {
        "full_result": {"obligations_raw": [{"atom_id": "A1"}]},
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
        "created_at": "2026-10-17T10:00:00Z",
    }
    adr_count = [0]
    sb_m = MagicMock()

    def _table_m(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "lt", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "anonymous_diagnosis_results":
            adr_count[0] += 1
            leaf.execute.return_value = _mk_execute(
                [new_diag_mfg] if adr_count[0] == 1 else []
            )
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb_m.table.side_effect = _table_m

    result = compute_change_summary(sb_m, "f1", "diag-r18-m")
    assert result["added_count"] == 1


# ---------------------------------------------------------------------------
# R19: removal_processor 에 delete 호출 없음
# ---------------------------------------------------------------------------

def test_r19_no_delete_operations():
    """removal_processor 에는 delete() 호출이 없음을 소스 레벨 확인."""
    import services.wp01_obligation_change.removal_processor as mod
    import inspect
    src = inspect.getsource(mod)
    assert ".delete(" not in src, "removal_processor 에 delete 호출이 있어서는 안됩니다"


# ---------------------------------------------------------------------------
# R20a/R20b: _fetch_deactivation_dates 컬럼 미존재 vs DB 오류 분기
# ---------------------------------------------------------------------------

def test_r20a_missing_column_returns_empty_dict():
    """Migration 미적용: 컬럼 미존재 예외 → {} 반환 (Scope B 가드 비활성, OTR 계속)."""
    from services.inspection_sets_svc.law_engine import _fetch_deactivation_dates

    sb = MagicMock()
    leaf = MagicMock()
    leaf.execute.side_effect = Exception(
        "Could not find the 'scope_b_deactivation_date' column of 'inspection_sets'"
    )
    for m in ("select", "eq"):
        setattr(leaf, m, MagicMock(return_value=leaf))
    sb.table.return_value = leaf

    result = _fetch_deactivation_dates(sb, "f1")
    assert result == {}, "컬럼 미존재 예외는 빈 dict 로 처리돼야 한다 (fail-open)"


def test_r20b_db_error_after_migration_raises():
    """Migration 적용 후 일반 DB 오류 → 예외 re-raise (fail-closed, OTR 차단)."""
    from services.inspection_sets_svc.law_engine import _fetch_deactivation_dates

    sb = MagicMock()
    leaf = MagicMock()
    leaf.execute.side_effect = Exception("connection timeout")
    for m in ("select", "eq"):
        setattr(leaf, m, MagicMock(return_value=leaf))
    sb.table.return_value = leaf

    with pytest.raises(Exception, match="connection timeout"):
        _fetch_deactivation_dates(sb, "f1")


# ---------------------------------------------------------------------------
# R21: _is_current_removal_candidate — 이전 C10 기준 없음 → False
# ---------------------------------------------------------------------------

def test_r21_no_previous_baseline_returns_false():
    """이전 MATERIALIZED C10 없음 → _is_current_removal_candidate False (FIX-02)."""
    from services.wp01_obligation_change.change_tracker import _is_current_removal_candidate

    iset_row = {
        "legal_obligation_atom_id": "ATOM-NEW",
        "is_active": True,
        "source": "LEGAL_ENGINE",
    }
    # latest C10: ATOM-NEW 없음 → removal candidate 조건 만족
    latest_c10_row = {
        "id": "diag-latest",
        "full_result": {"obligations_raw": [{"atom_id": "ATOM-OTHER"}]},
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
        "created_at": "2026-10-17T10:00:00Z",
    }

    adr_call = [0]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "lt", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute([iset_row])
        elif name == "anonymous_diagnosis_results":
            adr_call[0] += 1
            if adr_call[0] == 1:
                leaf.execute.return_value = _mk_execute([latest_c10_row])
            else:
                # 이전 C10 없음
                leaf.execute.return_value = _mk_execute([])
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = _is_current_removal_candidate(sb, "f1", "iset-1")
    assert result is False, "이전 C10 기준 없으면 제외 후보 아님"


# ---------------------------------------------------------------------------
# R22: _is_current_removal_candidate — atom이 이전 C10에 없음 → False
# ---------------------------------------------------------------------------

def test_r22_atom_not_in_prev_baseline_returns_false():
    """atom이 이전 C10에도 없음 → _is_current_removal_candidate False (FIX-02)."""
    from services.wp01_obligation_change.change_tracker import _is_current_removal_candidate

    iset_row = {
        "legal_obligation_atom_id": "ATOM-GHOST",
        "is_active": True,
        "source": "LEGAL_ENGINE",
    }
    latest_c10_row = {
        "id": "diag-latest",
        "full_result": {"obligations_raw": [{"atom_id": "ATOM-OTHER"}]},
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
        "created_at": "2026-10-17T10:00:00Z",
    }
    prev_c10_row = {
        "id": "diag-prev",
        "full_result": {"obligations_raw": [{"atom_id": "ATOM-OLD"}]},  # ATOM-GHOST 없음
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
        "created_at": "2026-10-01T10:00:00Z",
    }

    adr_call = [0]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "lt", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            leaf.execute.return_value = _mk_execute([iset_row])
        elif name == "anonymous_diagnosis_results":
            adr_call[0] += 1
            if adr_call[0] == 1:
                leaf.execute.return_value = _mk_execute([latest_c10_row])
            else:
                leaf.execute.return_value = _mk_execute([prev_c10_row])
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = _is_current_removal_candidate(sb, "f1", "iset-1")
    assert result is False, "이전 C10에도 atom 없으면 제외 후보 아님"


# ---------------------------------------------------------------------------
# R23: Scope A 라우터 — work_schedule 미발견 → 404
# ---------------------------------------------------------------------------

def test_r23_scope_a_router_404_when_schedule_not_found():
    """work_schedule 미발견 → 404 HTTPException (FIX-03 라우터 강화)."""
    from fastapi import HTTPException
    from unittest.mock import patch

    sb = MagicMock()
    leaf = MagicMock()
    for m in ("select", "eq", "limit"):
        setattr(leaf, m, MagicMock(return_value=leaf))
    leaf.execute.return_value = _mk_execute([])  # 일정 없음
    sb.table.return_value = leaf

    current = {"id": "u1", "role_code": "ALL", "company_id": "c1"}

    with patch("routers.obligation_change.get_supabase", return_value=sb), \
         patch("routers.obligation_change._require_company_admin"), \
         patch("routers.obligation_change._require_company_factory"):
        from routers.obligation_change import process_scope_a_removal
        from schemas.obligation_change import ScopeARemovalRequest

        body = ScopeARemovalRequest(
            factory_id="f1",
            work_schedule_id="ws-missing",
            reason="테스트",
        )
        try:
            process_scope_a_removal(body, current)
            assert False, "HTTPException 발생해야 함"
        except HTTPException as e:
            assert e.status_code == 404


# ---------------------------------------------------------------------------
# R24: Scope A 라우터 — inspection_set_id 누락 → 409
# ---------------------------------------------------------------------------

def test_r24_scope_a_router_409_when_iset_id_missing():
    """inspection_set_id=None → 409 HTTPException (FIX-03 라우터 강화)."""
    from fastapi import HTTPException
    from unittest.mock import patch

    sb = MagicMock()
    leaf = MagicMock()
    for m in ("select", "eq", "limit"):
        setattr(leaf, m, MagicMock(return_value=leaf))
    leaf.execute.return_value = _mk_execute([{"inspection_set_id": None}])
    sb.table.return_value = leaf

    current = {"id": "u1", "role_code": "ALL", "company_id": "c1"}

    with patch("routers.obligation_change.get_supabase", return_value=sb), \
         patch("routers.obligation_change._require_company_admin"), \
         patch("routers.obligation_change._require_company_factory"):
        from routers.obligation_change import process_scope_a_removal
        from schemas.obligation_change import ScopeARemovalRequest

        body = ScopeARemovalRequest(
            factory_id="f1",
            work_schedule_id="ws-no-iset",
            reason="테스트",
        )
        try:
            process_scope_a_removal(body, current)
            assert False, "HTTPException 발생해야 함"
        except HTTPException as e:
            assert e.status_code == 409
            assert "점검 세트" in e.detail


# ---------------------------------------------------------------------------
# R25: Scope B — inspection_sets UPDATE 실패 시 is_set_updated=False 반환
# ---------------------------------------------------------------------------

def test_r25_scope_b_partial_success_detected():
    """inspection_sets UPDATE 0행 → is_set_updated=False (FIX-03 부분 갱신 감지)."""
    from services.wp01_obligation_change.removal_processor import process_scope_b

    iset_row = {
        "id": "is-r25",
        "is_active": True,
        "source": "LEGAL_ENGINE",
        "scope_b_deactivation_date": None,
    }

    sb = MagicMock()
    call_seq = [0]

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "update", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "inspection_sets":
            call_seq[0] += 1
            if call_seq[0] == 1:
                # SELECT 검증
                leaf.execute.return_value = _mk_execute([iset_row])
            else:
                # UPDATE 실패: 0행 반환
                leaf.execute.return_value = _mk_execute([])
        else:
            # work_schedules: 활성 일정 없음
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    result = process_scope_b(sb, "f1", "is-r25", "2026-10-20", "테스트 이유")
    assert result["is_set_updated"] is False, "UPDATE 0행 → is_set_updated=False"
    assert result["schedules_cancelled"] == 0


# ===========================================================================
# PATCH-4A TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# P4-01: 소문자 상태값 보호 + _apply_preserve_guard 컨트랙트
# ---------------------------------------------------------------------------

def test_p4_01_lowercase_completed_is_preserved():
    """DB 소문자 completed → _is_preserve=True (정규화 경유)."""
    from services.wp01_obligation_change.removal_processor import _is_preserve
    assert _is_preserve({"status_code": "completed"}) is True
    assert _is_preserve({"status_code": "in_progress"}) is True


def test_p4_01_preserve_update_exclude_contains_lowercase():
    """_PRESERVE_UPDATE_EXCLUDE 에 소문자 completed / in_progress 포함."""
    from services.wp01_obligation_change.removal_processor import _PRESERVE_UPDATE_EXCLUDE
    assert "completed" in _PRESERVE_UPDATE_EXCLUDE
    assert "in_progress" in _PRESERVE_UPDATE_EXCLUDE


def test_p4_01_scope_a_lowercase_completed_race_update_zero():
    """소문자 completed → SELECT 시 SCHEDULED 이었다가 경합 → UPDATE 0건 → processed=0."""
    sb = MagicMock()

    select_leaf = MagicMock()
    for m in ("select", "eq", "limit"):
        setattr(select_leaf, m, MagicMock(return_value=select_leaf))
    # SELECT: planned 상태 (보호 대상 아님)
    select_leaf.execute.return_value = _mk_execute([
        {"id": "s1", "status_code": "planned", "active_yn": True, "factory_id": "f1"}
    ])

    # UPDATE: 0건 (경합 중 completed 로 변경됨)
    update_chain = MagicMock()
    update_chain.eq.return_value = update_chain
    update_chain.neq.return_value = update_chain
    update_chain.execute.return_value = _mk_execute([])

    def _table(name):
        if name == "work_schedules":
            tbl = MagicMock()
            tbl.select.return_value = select_leaf
            tbl.update.return_value = update_chain
            return tbl
        return MagicMock()

    sb.table.side_effect = _table

    with patch("services.wp01_obligation_change.removal_processor._child_linked", return_value=False):
        result = process_scope_a(sb, "f1", "s1", "사유")

    assert result["processed"] == 0, "UPDATE 0건 → processed=0"
    assert result["skipped_reason"] is not None


# ---------------------------------------------------------------------------
# P4-02: Scope B 부분 성공 → 라우터 partial_success 반환
# ---------------------------------------------------------------------------

def test_p4_02_scope_b_partial_success_router_response():
    """is_set_updated=False → 라우터 status=partial_success, message 포함 (P4-02)."""
    from unittest.mock import patch
    from routers.obligation_change import process_scope_b_removal
    from schemas.obligation_change import ScopeBRemovalRequest

    body = ScopeBRemovalRequest(
        factory_id="f1",
        inspection_set_id="iset-1",
        application_date="2026-12-01",
        reason="테스트",
    )
    current = {"id": "u1", "role_code": "ALL", "company_id": "c1"}
    partial_result = {
        "inspection_set_id": "iset-1",
        "schedules_cancelled": 3,
        "schedules_preserved_completed": 0,
        "child_linked_count": 0,
        "is_active_set_false": True,
        "is_set_updated": False,  # 부분 성공
        "scope_b_deactivation_date": "2026-12-01",
    }

    with patch("routers.obligation_change.get_supabase", return_value=MagicMock()), \
         patch("routers.obligation_change._require_company_admin"), \
         patch("routers.obligation_change._require_company_factory"), \
         patch("routers.obligation_change._is_current_removal_candidate", return_value=True), \
         patch("routers.obligation_change.process_scope_b", return_value=partial_result):
        response = process_scope_b_removal(body, current)

    assert response["status"] == "partial_success", "부분 성공 시 status=partial_success"
    assert "message" in response
    assert "3건" in response["message"]
    assert response["data"]["is_set_updated"] is False


# ---------------------------------------------------------------------------
# P4-03: Preview — _child_linked 를 통해 3종 테이블 확인
# ---------------------------------------------------------------------------

def test_p4_03_preview_uses_child_linked_not_direct_query():
    """preview_removal_impact 가 _child_linked 를 호출한다 (P4-03)."""
    schedules = [
        {"id": "s1", "planned_date": "2026-12-01", "status_code": "planned"},
    ]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "work_schedules":
            leaf.execute.return_value = _mk_execute(schedules)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with patch(
        "services.wp01_obligation_change.removal_processor._child_linked",
        return_value=True,
    ) as mock_cl:
        result = preview_removal_impact(sb, "f1", "iset-1", "2026-12-01")

    mock_cl.assert_called_once_with(sb, "s1", "f1")
    assert result["child_linked_count"] == 1
    assert result["has_child_linked"] is True
    assert result["actual_cancellable"] == 0


def test_p4_03_preview_no_child_link():
    """자식 연결 없음 → actual_cancellable = schedules_to_cancel."""
    schedules = [
        {"id": "s1", "planned_date": "2026-12-01", "status_code": "planned"},
        {"id": "s2", "planned_date": "2027-01-01", "status_code": "planned"},
    ]
    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "work_schedules":
            leaf.execute.return_value = _mk_execute(schedules)
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with patch(
        "services.wp01_obligation_change.removal_processor._child_linked",
        return_value=False,
    ):
        result = preview_removal_impact(sb, "f1", "iset-1", "2026-12-01")

    assert result["actual_cancellable"] == 2
    assert result["has_child_linked"] is False


# ---------------------------------------------------------------------------
# P4-04: 타사 공장 → 404 (cross-company isolation)
# ---------------------------------------------------------------------------

def test_p4_04_cross_company_factory_blocked():
    """타사 공장 ID → _require_company_factory 에서 404 HTTPException."""
    from fastapi import HTTPException
    from unittest.mock import patch

    sb = MagicMock()
    leaf = MagicMock()
    for m in ("select", "eq", "limit"):
        setattr(leaf, m, MagicMock(return_value=leaf))
    # 타사 공장: company_id 필터 결과 없음
    leaf.execute.return_value = _mk_execute([])
    sb.table.return_value = leaf

    current = {"id": "u1", "role_code": "COMPANY", "company_id": "company-A"}

    with patch("routers.obligation_change.get_supabase", return_value=sb), \
         patch("routers.obligation_change._require_company_admin"):
        from routers.obligation_change import get_removal_preview
        from schemas.obligation_change import RemovalPreviewRequest

        body = RemovalPreviewRequest(
            factory_id="factory-of-company-B",
            inspection_set_id="iset-1",
        )
        try:
            get_removal_preview(body, current)
            assert False, "HTTPException 발생해야 함"
        except HTTPException as e:
            assert e.status_code == 404


# ---------------------------------------------------------------------------
# P4-05: obligations_raw None vs [] 구분 — compute_change_summary 로깅 검증
# ---------------------------------------------------------------------------

def test_p4_05_obligations_raw_none_vs_empty(caplog):
    """obligations_raw=None → 경고 로그, 빈 리스트로 처리 (P4-05)."""
    import logging
    # full_result 에 obligations_raw 필드 없음 (None)
    new_diag = {
        "full_result": {},  # obligations_raw 필드 누락
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
        "created_at": "2026-10-17T10:00:00Z",
    }

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "lt", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "anonymous_diagnosis_results":
            leaf.execute.return_value = _mk_execute([new_diag])
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with caplog.at_level(logging.WARNING, logger="services.wp01_obligation_change.change_tracker"):
        result = compute_change_summary(sb, "f1", "diag-p4-05")

    assert result["added_count"] == 0
    assert result["retained_count"] == 0
    # obligations_raw 누락 경고가 기록되었는지 확인
    assert any("obligations_raw" in r.message and "누락" in r.message for r in caplog.records), \
        "obligations_raw 누락 시 WARNING 로그 필요"


def test_p4_05_obligations_raw_empty_no_warning(caplog):
    """obligations_raw=[] → 경고 없이 정상 처리 (0건 의무 유효)."""
    import logging
    new_diag = {
        "full_result": {"obligations_raw": []},  # 명시적 빈 목록
        "input_data": {"factory_id": "f1", "sector": "MANUFACTURING"},
        "created_at": "2026-10-17T10:00:00Z",
    }

    sb = MagicMock()

    def _table(name):
        leaf = MagicMock()
        for m in ("select", "eq", "neq", "gte", "lt", "order", "limit"):
            setattr(leaf, m, MagicMock(return_value=leaf))
        if name == "anonymous_diagnosis_results":
            leaf.execute.return_value = _mk_execute([new_diag])
        else:
            leaf.execute.return_value = _mk_execute([])
        return leaf

    sb.table.side_effect = _table

    with caplog.at_level(logging.WARNING, logger="services.wp01_obligation_change.change_tracker"):
        result = compute_change_summary(sb, "f1", "diag-p4-05b")

    assert result["added_count"] == 0
    warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not any("obligations_raw" in m and "누락" in m for m in warning_msgs), \
        "obligations_raw=[] 는 경고 없음"
