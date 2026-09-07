"""WP-C PRECONDITION PATCH-1 — role_menu_permissions 스키마 정합 회귀.

WO-SAFE-COMPANY-ACCESS-001. 운영 role_menu_permissions 실 컬럼 :
    can_list · can_create · can_update · can_delete · can_export
(read 액션용 컬럼은 부재).

배포된 `services/company_user_svc._require_company_user_admin` 의 select 가
없는 컬럼 (can_list, can_create, ..., can_update, can_delete) 를 요청하면
PostgREST 42703 → except → 503 MENU_PERM_LOOKUP_FAILED (fail-closed) 로
회사 사용자관리 API 가 운영에서 전부 막힌다.

_ACTION_TO_CRUD 매핑 (LIST → can_list · INVITE → can_create ·
APPROVE/ROLE/STATUS → can_update · CANCEL → can_delete) 은 read 액션용 컬럼을
사용하지 않으므로, 그 컬럼만 select 에서 제거하면 데이터 변경 없이 정상 통과한다.

이 파일은 :
    T1  source invariant : select 문자열에서 read 액션용 컬럼 부재 · 파일 전체 grep = 0
    T2  LIST   : can_list=true → PASS
    T3  INVITE : can_create=true → PASS
    T4  UPDATE : can_update=true → APPROVE / ROLE / STATUS 3 action PASS
    T5  CANCEL : can_delete=true → PASS
    T6  deny   : crud=false → 403 MENU_PERMISSION_DENIED
    T7  regression : WP-A FINAL POLICY (expired READ 200 · WRITE 403) 유지
을 검증한다. FakeSupabase fixture 는 실 스키마와 동일하게 read 액션용 컬럼을
제공하지 않는다 (재발 시 T2~T5 가 실패).
"""
from __future__ import annotations

import os
import re
import inspect

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services import company_user_svc as svc


# ── T1 · source invariant ────────────────────────────────────────────
def test_T1_source_select_omits_read_column_and_lists_only_crud():
    """_require_company_user_admin select 는 4 CRUD 컬럼만 요청해야 한다."""
    src = inspect.getsource(svc._require_company_user_admin)
    # role_menu_permissions select 문자열 추출
    m = re.search(
        r'\.table\("role_menu_permissions"\)\s*\.\s*select\("([^"]+)"\)',
        src,
    )
    assert m is not None, "role_menu_permissions select 문자열을 찾지 못했다"
    cols = [c.strip() for c in m.group(1).split(",")]
    assert set(cols) == {"can_list", "can_create", "can_update", "can_delete"}, (
        f"WP-C PRECONDITION 위반 : select 컬럼 = {cols}. "
        "정합 스키마는 can_list/create/update/delete 만 허용 (운영 스키마 정합)."
    )


def test_T1_source_file_wide_no_read_column_reference():
    """파일 전체에서 read 액션용 컬럼 참조 = 0 (재발 방지)."""
    src = inspect.getsource(svc)
    # 컬럼 참조가 아닌 임의 read 단어와 구분하기 위해 `can_` 접두 + read 접미어만 매치
    forbidden = re.findall(r"can_read", src)
    assert not forbidden, (
        f"파일에 read 액션용 컬럼 참조가 재도입되었다 (occurrences={len(forbidden)})"
    )


def test_T1_action_to_crud_mapping_uses_only_crud_columns():
    """_ACTION_TO_CRUD 매핑도 4 CRUD 컬럼만 사용."""
    mapping = svc._ACTION_TO_CRUD
    allowed = {"can_list", "can_create", "can_update", "can_delete"}
    used = set(mapping.values())
    assert used <= allowed, (
        f"_ACTION_TO_CRUD 가 허용 컬럼 초과 : {used - allowed}"
    )
    # 최소 매핑 covers LIST/INVITE/APPROVE/ROLE/STATUS/CANCEL
    assert set(mapping.keys()) >= {"LIST", "INVITE", "APPROVE", "ROLE", "STATUS", "CANCEL"}


def test_T1_worker_list_menu_code_unchanged():
    assert svc.WORKER_LIST_MENU_CODE == "worker-list"


# ── T2 ~ T5 · CRUD 통과 · FakeSupabase 는 실 스키마와 동일하게 read 컬럼 부재 ─
class _Result:
    def __init__(self, data): self.data = data


class _Query:
    def __init__(self, store, table):
        self.store = store; self.table = table
        self._cols = "*"; self._filters = []; self._limit = None
    def select(self, cols="*", *a, **k):
        self._cols = cols; return self
    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def limit(self, n): self._limit = n; return self
    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c)) != str(v):
                return False
        return True
    def _project(self, row):
        if not self._cols or self._cols == "*":
            return dict(row)
        keys = [c.strip() for c in self._cols.split(",") if c.strip()]
        # 실 postgrest 동치 : 없는 컬럼 select 는 raise
        for k in keys:
            if k not in row:
                raise KeyError(f"column {k} does not exist on {self.table}")
        return {k: row.get(k) for k in keys}
    def execute(self):
        rows = self.store.setdefault(self.table, [])
        matched = [r for r in rows if self._match(r)]
        if self._limit is not None:
            matched = matched[:self._limit]
        return _Result([self._project(r) for r in matched])


class _FakeSB:
    def __init__(self, store): self.store = store
    def table(self, name): return _Query(self.store, name)


def _active_admin(role_code="002", cid="C-A"):
    return {"id": "U-ADMIN", "email": "admin@a.co.kr", "name": "A",
            "role_code": role_code, "company_id": cid,
            "status_code": "ACTIVE", "is_active": True}


def _store_prod_schema(role_code="002", **crud_flags):
    """운영 스키마 정합 : role_menu_permissions row 에 read 액션용 컬럼 부재."""
    # 기본값 : 전부 true (실 데이터와 동치 · 002/010/011/012 x worker-list)
    row = {
        "role_code": role_code,
        "menu_code": svc.WORKER_LIST_MENU_CODE,
        "can_list": True, "can_create": True,
        "can_update": True, "can_delete": True,
        # can_export 는 실 스키마엔 있지만 svc 는 select 하지 않음. 있어도 무해.
        "can_export": True,
    }
    row.update(crud_flags)
    return {
        "role_data_scope": [
            {"role_code": role_code, "scope_type": "COMPANY"},
        ],
        "role_menu_permissions": [row],
    }


def test_T2_LIST_action_passes_with_can_list_true():
    sb = _FakeSB(_store_prod_schema())
    # 예외 없이 통과해야 한다
    svc._require_company_user_admin(_active_admin(), sb, "LIST")


def test_T3_INVITE_action_passes_with_can_create_true():
    sb = _FakeSB(_store_prod_schema())
    svc._require_company_user_admin(_active_admin(), sb, "INVITE")


def test_T4_APPROVE_ROLE_STATUS_pass_with_can_update_true():
    sb = _FakeSB(_store_prod_schema())
    for action in ("APPROVE", "ROLE", "STATUS"):
        svc._require_company_user_admin(_active_admin(), sb, action)


def test_T5_CANCEL_passes_with_can_delete_true():
    sb = _FakeSB(_store_prod_schema())
    svc._require_company_user_admin(_active_admin(), sb, "CANCEL")


# ── T6 · deny (crud=false → 403 MENU_PERMISSION_DENIED) ──────────────
def test_T6_deny_when_can_list_false():
    from fastapi import HTTPException
    sb = _FakeSB(_store_prod_schema(can_list=False))
    with pytest.raises(HTTPException) as ei:
        svc._require_company_user_admin(_active_admin(), sb, "LIST")
    assert ei.value.status_code == 403
    assert ei.value.detail["code"] == "MENU_PERMISSION_DENIED"


def test_T6_deny_when_can_delete_false():
    from fastapi import HTTPException
    sb = _FakeSB(_store_prod_schema(can_delete=False))
    with pytest.raises(HTTPException) as ei:
        svc._require_company_user_admin(_active_admin(), sb, "CANCEL")
    assert ei.value.status_code == 403
    assert ei.value.detail["code"] == "MENU_PERMISSION_DENIED"


# ── T6b · 없는 컬럼 select 재도입 시 T2~T5 가 KeyError → 503 로 폭파되는지 회귀 ─
def test_T6b_regression_marker_read_column_reintroduction_would_break():
    """FakeSupabase 가 실 postgrest 처럼 없는 컬럼 select 시 KeyError 를 던지도록
    구현되어 있으므로, select 문자열에 없는 컬럼이 재도입되면 T2~T5 가 자동 실패한다.
    이 테스트는 그 안전망의 존재 자체를 명시적으로 문서화한다."""
    # store 에 없는 컬럼을 요청하도록 강제 → KeyError 로 폭파 확인
    store = {"role_data_scope": [{"role_code": "002", "scope_type": "COMPANY"}],
             "role_menu_permissions": [{
                 "role_code": "002", "menu_code": svc.WORKER_LIST_MENU_CODE,
                 "can_list": True, "can_create": True,
                 "can_update": True, "can_delete": True,
             }]}
    sb = _FakeSB(store)
    q = sb.table("role_menu_permissions").select("can_list, does_not_exist")
    q.eq("role_code", "002").eq("menu_code", "worker-list").limit(1)
    with pytest.raises(KeyError):
        q.execute()


# ── T7 · WP-A FINAL POLICY 무회귀 ────────────────────────────────────
def test_T7_wpa_final_policy_symbols_intact():
    """WRITE gate (require_active_company_saas) · READ 무게이트 정책 소스 유지."""
    import routers.company_users as cu
    src = inspect.getsource(cu)

    def _endpoint_block(marker):
        idx = src.index(marker)
        rest = src[idx:]
        next_at = rest.find("@router.", 1)
        return rest[:next_at] if next_at > 0 else rest

    # GET 3 : gate 부재 유지
    for m in ('@router.get("/me/company/users")',
              '@router.get("/me/company/user-roles")',
              '@router.get("/me/company/user-invites")'):
        assert "require_active_company_saas" not in _endpoint_block(m), (
            f"WP-A FINAL 회귀 : {m} 에 gate 재도입"
        )

    # WRITE 5 : gate 유지 (DELETE 포함)
    for m in ('@router.post("/me/company/user-invites")',
              '@router.delete("/me/company/user-invites/{invite_id}")',
              '@router.post("/me/company/users/{user_id}/approve")',
              '@router.patch("/me/company/users/{user_id}/role")',
              '@router.patch("/me/company/users/{user_id}/status")'):
        assert "require_active_company_saas" in _endpoint_block(m), (
            f"WP-A FINAL 회귀 : {m} 에서 gate 제거됨"
        )


def test_T7_entitlement_snapshot_hotfix_symbols_intact():
    import routers.company_users as cu
    src = inspect.getsource(cu._entitlement_snapshot)
    sub_start = src.index('sb.table("subscriptions")')
    sub_end = src.index("for row in sub", sub_start)
    sub_block = src[sub_start:sub_end]
    assert "started_at" in sub_block
    assert "start_date" not in sub_block


def test_T7_has_company_admin_capability_unchanged():
    """_has_company_admin_capability 는 이번 PATCH 대상 아님 (이미 read 액션 컬럼 미참조)."""
    src = inspect.getsource(svc._has_company_admin_capability)
    m = re.search(
        r'\.table\("role_menu_permissions"\)\s*\.\s*select\("([^"]+)"\)',
        src,
    )
    assert m is not None
    cols = [c.strip() for c in m.group(1).split(",")]
    assert set(cols) == {"can_list", "can_create", "can_update", "can_delete"}
