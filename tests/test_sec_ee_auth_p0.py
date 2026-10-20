"""SEC-03 ENGINE-EQUIPMENT AUTH P0
WO-TAI-SEC03-ENGINE-EQUIPMENT-AUTH-P0-IMPLEMENT-001 소스 계약 테스트.

BASE_SHA = 18fa7d9a0177373d029c37e390e16ddb52fc82c9

검증 방식:
  EE-SRC-*  : 정적 소스 분석 (파일 기반)
  EE-UNIT-* : mock 기반 단위 테스트 (실제 DB 연결 없음)

DB 실측(DB_INT)은 TEST_DB_ENVIRONMENT_REQUIRED.

SOURCE GATE 기준:
  - EE-01~EE-11 전 함수에 Depends(get_current_user) 명시
  - EE-12 /categories 인증 없음 유지
  - EE-01/05/07/08/11 서비스 함수에 _require_admin 호출
  - EE-02 run_list_assets에 스코프 필터 적용
  - EE-03 run_patch_asset에 EQUIPMENT_UPDATE 검사 + 소유권 검증 선행
  - TOCTOU 방어: UPDATE 조건에 checked_factory_id 포함
  - permission_guard._PUBLIC에 /engine-equipment/categories 등록
  - DB Migration 없음

테스트 목록:
  EE-SRC-01  EE-01 get_equipment_stats Depends(get_current_user) 확인
  EE-SRC-02  EE-02 list_assets Depends(get_current_user) 확인
  EE-SRC-03  EE-03 patch_asset Depends(get_current_user) 확인
  EE-SRC-04  EE-04 list_equipment_master Depends(get_current_user) 확인
  EE-SRC-05  EE-05 refresh_engine_equipment Depends(get_current_user) 확인
  EE-SRC-06  EE-06 get_equipment_detail Depends(get_current_user) 확인
  EE-SRC-07  EE-07 update_equipment_master Depends(get_current_user) 확인
  EE-SRC-08  EE-08 bulk_approve_review Depends(get_current_user) 확인
  EE-SRC-09  EE-09 list_equipment_models Depends(get_current_user) 확인
  EE-SRC-10  EE-10 get_model_detail Depends(get_current_user) 확인
  EE-SRC-11  EE-11 update_model Depends(get_current_user) 확인
  EE-SRC-12  EE-12 get_categories 인증 없음 (Depends 미사용)
  EE-SRC-13  EE-05 run_refresh_engine_equipment에 _require_admin 호출
  EE-SRC-14  EE-07 run_update_equipment_master에 _require_admin 호출
  EE-SRC-15  EE-08 run_bulk_approve_review에 _require_admin 호출
  EE-SRC-16  EE-11 run_update_model에 _require_admin 호출
  EE-SRC-17  EE-01 run_get_equipment_stats에 _require_admin 호출
  EE-SRC-18  EE-02 run_list_assets에 _resolve_asset_scope 호출
  EE-SRC-19  EE-03 run_patch_asset에 EQUIPMENT_UPDATE 권한 검사 선행
  EE-SRC-20  EE-03 run_patch_asset에 소유권 검증 후 UPDATE 실행
  EE-SRC-21  EE-03 TOCTOU 방어 — checked_factory_id UPDATE 조건 포함
  EE-SRC-22  permission_guard._PUBLIC에 /engine-equipment/categories 등록
  EE-SRC-23  DB Migration 파일 없음 (20261020000010 이상 없음)
  EE-UNIT-01 run_patch_asset: EQUIPMENT_UPDATE 미보유 → 403
  EE-UNIT-02 run_patch_asset: 타사 자산 → 404
  EE-UNIT-03 run_patch_asset: 타 factory 자산 (FACTORY tier) → 404
  EE-UNIT-04 run_patch_asset: factory_id NULL 비-ALL → 404
  EE-UNIT-05 run_list_assets: PLATFORM tier → 빈 결과
  EE-UNIT-06 run_list_assets: 무회사 사용자 → 빈 결과
  EE-UNIT-07 run_refresh: 비-ALL → 403
  EE-UNIT-08 run_update_equipment_master: 비-ALL → 403
  EE-UNIT-09 run_bulk_approve_review: 비-ALL → 403
  EE-UNIT-10 run_update_model: 비-ALL → 403
  EE-UNIT-11 run_get_equipment_stats: 비-ALL → 403
  EE-UNIT-12 run_patch_asset: 권한 실패 시 DB Update 미호출
  EE-UNIT-13 run_list_assets: ALL tier → scope 필터 없음
  EE-UNIT-14 _resolve_asset_scope: FACTORY tier factory 교차검증 실패 → DENY
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import re
from unittest.mock import MagicMock, patch, call

import pytest
from fastapi import HTTPException

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_ROUTER_PY = _ROOT / "routers" / "engine_equipment.py"
_ENGINE_SVC = _ROOT / "services" / "equipment_engine_svc.py"
_CATALOG_SVC = _ROOT / "services" / "equipment_catalog_svc.py"
_GUARD_PY = _ROOT / "services" / "permission_guard.py"

BASE_SHA = "18fa7d9a0177373d029c37e390e16ddb52fc82c9"
_EMPTY_PAGE = {"items": [], "total": 0, "page": 1, "page_size": 50, "total_pages": 0}


def _router_src() -> str:
    return _ROUTER_PY.read_text(encoding="utf-8")


def _engine_src() -> str:
    return _ENGINE_SVC.read_text(encoding="utf-8")


def _catalog_src() -> str:
    return _CATALOG_SVC.read_text(encoding="utf-8")


def _guard_src() -> str:
    return _GUARD_PY.read_text(encoding="utf-8")


# ── EE-SRC: 정적 소스 분석 ──────────────────────────────────────────────────


def _has_depends_get_current_user(func_name: str) -> bool:
    """라우터 소스에서 func_name 함수가 Depends(get_current_user)를 갖는지 확인."""
    src = _router_src()
    # 함수 정의 블록을 찾아서 current.*Depends.*get_current_user 존재 여부 검사
    pattern = re.compile(
        rf"async def {re.escape(func_name)}\s*\(.*?(?=\n@router|\nasync def |\Z)",
        re.DOTALL,
    )
    m = pattern.search(src)
    if not m:
        return False
    block = m.group(0)
    return bool(re.search(r"Depends\s*\(\s*get_current_user\s*\)", block))


def test_ee_src_01_stats_depends():
    """EE-SRC-01: get_equipment_stats Depends(get_current_user)"""
    assert _has_depends_get_current_user("get_equipment_stats"), \
        "get_equipment_stats에 Depends(get_current_user) 없음"


def test_ee_src_02_assets_list_depends():
    """EE-SRC-02: list_assets Depends(get_current_user)"""
    assert _has_depends_get_current_user("list_assets"), \
        "list_assets에 Depends(get_current_user) 없음"


def test_ee_src_03_patch_asset_depends():
    """EE-SRC-03: patch_asset Depends(get_current_user)"""
    assert _has_depends_get_current_user("patch_asset"), \
        "patch_asset에 Depends(get_current_user) 없음"


def test_ee_src_04_list_master_depends():
    """EE-SRC-04: list_equipment_master Depends(get_current_user)"""
    assert _has_depends_get_current_user("list_equipment_master"), \
        "list_equipment_master에 Depends(get_current_user) 없음"


def test_ee_src_05_refresh_depends():
    """EE-SRC-05: refresh_engine_equipment Depends(get_current_user)"""
    assert _has_depends_get_current_user("refresh_engine_equipment"), \
        "refresh_engine_equipment에 Depends(get_current_user) 없음"


def test_ee_src_06_detail_depends():
    """EE-SRC-06: get_equipment_detail Depends(get_current_user)"""
    assert _has_depends_get_current_user("get_equipment_detail"), \
        "get_equipment_detail에 Depends(get_current_user) 없음"


def test_ee_src_07_update_master_depends():
    """EE-SRC-07: update_equipment_master Depends(get_current_user)"""
    assert _has_depends_get_current_user("update_equipment_master"), \
        "update_equipment_master에 Depends(get_current_user) 없음"


def test_ee_src_08_approve_depends():
    """EE-SRC-08: bulk_approve_review Depends(get_current_user)"""
    assert _has_depends_get_current_user("bulk_approve_review"), \
        "bulk_approve_review에 Depends(get_current_user) 없음"


def test_ee_src_09_models_depends():
    """EE-SRC-09: list_equipment_models Depends(get_current_user)"""
    assert _has_depends_get_current_user("list_equipment_models"), \
        "list_equipment_models에 Depends(get_current_user) 없음"


def test_ee_src_10_model_detail_depends():
    """EE-SRC-10: get_model_detail Depends(get_current_user)"""
    assert _has_depends_get_current_user("get_model_detail"), \
        "get_model_detail에 Depends(get_current_user) 없음"


def test_ee_src_11_update_model_depends():
    """EE-SRC-11: update_model Depends(get_current_user)"""
    assert _has_depends_get_current_user("update_model"), \
        "update_model에 Depends(get_current_user) 없음"


def test_ee_src_12_categories_no_depends():
    """EE-SRC-12: get_categories 인증 없음 (Depends 미사용 — 공개)"""
    src = _router_src()
    pattern = re.compile(
        r"async def get_categories\s*\(.*?(?=\n@router|\nasync def |\Z)",
        re.DOTALL,
    )
    m = pattern.search(src)
    assert m, "get_categories 함수를 찾을 수 없습니다"
    block = m.group(0)
    assert not re.search(r"Depends\s*\(\s*get_current_user\s*\)", block), \
        "get_categories에 Depends(get_current_user)가 있습니다 — 공개 유지 위반"


def test_ee_src_13_refresh_requires_admin():
    """EE-SRC-13: run_refresh_engine_equipment에 _require_admin 호출"""
    src = _catalog_src()
    func_pat = re.compile(
        r"def run_refresh_engine_equipment\s*\(.*?(?=\ndef |\Z)", re.DOTALL
    )
    m = func_pat.search(src)
    assert m, "run_refresh_engine_equipment를 찾을 수 없습니다"
    assert "_require_admin" in m.group(0), \
        "run_refresh_engine_equipment에 _require_admin 호출 없음"


def test_ee_src_14_update_master_requires_admin():
    """EE-SRC-14: run_update_equipment_master에 _require_admin 호출"""
    src = _catalog_src()
    func_pat = re.compile(
        r"def run_update_equipment_master\s*\(.*?(?=\ndef |\Z)", re.DOTALL
    )
    m = func_pat.search(src)
    assert m, "run_update_equipment_master를 찾을 수 없습니다"
    assert "_require_admin" in m.group(0), \
        "run_update_equipment_master에 _require_admin 호출 없음"


def test_ee_src_15_approve_requires_admin():
    """EE-SRC-15: run_bulk_approve_review에 _require_admin 호출"""
    src = _catalog_src()
    func_pat = re.compile(
        r"def run_bulk_approve_review\s*\(.*?(?=\ndef |\Z)", re.DOTALL
    )
    m = func_pat.search(src)
    assert m, "run_bulk_approve_review를 찾을 수 없습니다"
    assert "_require_admin" in m.group(0), \
        "run_bulk_approve_review에 _require_admin 호출 없음"


def test_ee_src_16_update_model_requires_admin():
    """EE-SRC-16: run_update_model에 _require_admin 호출"""
    src = _catalog_src()
    func_pat = re.compile(
        r"def run_update_model\s*\(.*?(?=\ndef |\Z)", re.DOTALL
    )
    m = func_pat.search(src)
    assert m, "run_update_model를 찾을 수 없습니다"
    assert "_require_admin" in m.group(0), \
        "run_update_model에 _require_admin 호출 없음"


def test_ee_src_17_stats_requires_admin():
    """EE-SRC-17: run_get_equipment_stats에 _require_admin 호출"""
    src = _engine_src()
    func_pat = re.compile(
        r"def run_get_equipment_stats\s*\(.*?(?=\ndef |\Z)", re.DOTALL
    )
    m = func_pat.search(src)
    assert m, "run_get_equipment_stats를 찾을 수 없습니다"
    assert "_require_admin" in m.group(0), \
        "run_get_equipment_stats에 _require_admin 호출 없음"


def test_ee_src_18_list_assets_scope():
    """EE-SRC-18: run_list_assets에 _resolve_asset_scope 호출"""
    src = _engine_src()
    func_pat = re.compile(
        r"def run_list_assets\s*\(.*?(?=\ndef |\Z)", re.DOTALL
    )
    m = func_pat.search(src)
    assert m, "run_list_assets를 찾을 수 없습니다"
    assert "_resolve_asset_scope" in m.group(0), \
        "run_list_assets에 _resolve_asset_scope 호출 없음"


def test_ee_src_19_patch_asset_permission_first():
    """EE-SRC-19: run_patch_asset에 EQUIPMENT_UPDATE 검사가 DB 조회보다 먼저"""
    src = _engine_src()
    func_pat = re.compile(
        r"def run_patch_asset\s*\(.*?(?=\ndef |\Z)", re.DOTALL
    )
    m = func_pat.search(src)
    assert m, "run_patch_asset를 찾을 수 없습니다"
    block = m.group(0)
    perm_pos = block.find("EQUIPMENT_UPDATE")
    db_pos = block.find('.table("equipment_assets")')
    assert perm_pos != -1, "EQUIPMENT_UPDATE 검사 없음"
    assert db_pos != -1, "equipment_assets 조회 없음"
    assert perm_pos < db_pos, \
        "EQUIPMENT_UPDATE 검사가 DB 조회보다 뒤에 있음 — 권한 검사 순서 위반"


def test_ee_src_20_patch_asset_ownership_before_update():
    """EE-SRC-20: run_patch_asset에 소유권 검증 후 UPDATE 실행"""
    src = _engine_src()
    func_pat = re.compile(
        r"def run_patch_asset\s*\(.*?(?=\ndef |\Z)", re.DOTALL
    )
    m = func_pat.search(src)
    assert m, "run_patch_asset를 찾을 수 없습니다"
    block = m.group(0)
    # 소유권 검증: factories 조회
    ownership_pos = block.find('table("factories")')
    # 실제 업데이트 실행
    update_pos = block.find(".update(update_data)")
    assert ownership_pos != -1, "factories 소유권 검증 없음"
    assert update_pos != -1, "update_data UPDATE 없음"
    assert ownership_pos < update_pos, \
        "소유권 검증이 UPDATE보다 뒤에 있음"


def test_ee_src_21_toctou_factory_in_update():
    """EE-SRC-21: TOCTOU 방어 — checked_factory_id UPDATE 조건 포함"""
    src = _engine_src()
    func_pat = re.compile(
        r"def run_patch_asset\s*\(.*?(?=\ndef |\Z)", re.DOTALL
    )
    m = func_pat.search(src)
    assert m, "run_patch_asset를 찾을 수 없습니다"
    block = m.group(0)
    assert "checked_factory_id" in block, "checked_factory_id 없음"
    assert re.search(r"\.eq\(\s*['\"]factory_id['\"].*checked_factory_id", block), \
        "UPDATE 조건에 checked_factory_id가 포함되지 않음 — TOCTOU 방어 누락"


def test_ee_src_22_categories_in_public():
    """EE-SRC-22: permission_guard._PUBLIC에 /engine-equipment/categories 등록"""
    src = _guard_src()
    assert '"/engine-equipment/categories"' in src, \
        "_PUBLIC 목록에 /engine-equipment/categories 없음"
    # 전체 prefix 공개가 아닌지 확인 — /engine-equipment/ (trailing slash) 없어야 함
    assert '"/engine-equipment/"' not in src, \
        "_PUBLIC에 /engine-equipment/ prefix 전체가 등록됨 — exact 경로만 허용"


def test_ee_src_23_no_new_migration():
    """EE-SRC-23: 20261020000010 이상 신규 Migration 없음"""
    migrations = list((_ROOT / "supabase" / "migrations").glob("20261020000010*.sql"))
    migrations += list((_ROOT / "supabase" / "migrations").glob("2026102000001*.sql"))
    assert not migrations, f"예상치 못한 신규 Migration: {migrations}"


# ── EE-UNIT: mock 기반 단위 테스트 ─────────────────────────────────────────


def _make_supabase_mock():
    """공통 supabase mock."""
    sb = MagicMock()
    # table().select().eq().limit().execute() 체인 기본 반환
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.count = 0
    return sb


def _current(role_code="001", company_id="cid-A", factory_id="fid-A", scope="ALL"):
    return {
        "role_code": role_code,
        "company_id": company_id,
        "factory_id": factory_id,
        "status_code": "ACTIVE",
        "is_active": True,
    }


# ── EE-UNIT-01: EQUIPMENT_UPDATE 미보유 → 403

def test_ee_unit_01_patch_no_equipment_update_perm():
    """EE-UNIT-01: run_patch_asset EQUIPMENT_UPDATE 없음 → 403"""
    from services.equipment_engine_svc import run_patch_asset
    sb = _make_supabase_mock()
    body = MagicMock()
    body.last_inspection_date = None
    body.next_inspection_date = None
    body.is_legal_target = None
    body.is_operating = None
    body.model_id = None
    body.equipment_model_id = None

    with patch("services.permission_guard.has_permission", return_value=False):
        with pytest.raises(HTTPException) as exc:
            run_patch_asset(sb, "some-asset-id", body, _current())
    assert exc.value.status_code == 403
    # DB update 미호출 확인
    sb.table.return_value.update.assert_not_called()


# ── EE-UNIT-02: 타사 자산 → 404

def test_ee_unit_02_patch_cross_tenant_asset():
    """EE-UNIT-02: 타사 자산 수정 시도 → 404"""
    from services.equipment_engine_svc import run_patch_asset

    sb = _make_supabase_mock()
    body = MagicMock()
    body.last_inspection_date = None
    body.next_inspection_date = None
    body.is_legal_target = True
    body.is_operating = None
    body.model_id = None
    body.equipment_model_id = None

    # 자산 조회: factory_id = fid-B (타사 공장)
    asset_chain = MagicMock()
    asset_chain.data = [{"id": "asset-x", "factory_id": "fid-B"}]
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = asset_chain

    # factories 조회: company_id = cid-B (타사)
    factory_chain = MagicMock()
    factory_chain.data = [{"company_id": "cid-B"}]

    def _table_side_effect(name):
        t = MagicMock()
        if name == "equipment_assets":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = asset_chain
        elif name == "factories":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = factory_chain
        return t

    sb.table.side_effect = _table_side_effect

    with patch("services.permission_guard.has_permission", return_value=True):
        with patch("services.company_scope._scope", return_value="COMPANY"):
            with pytest.raises(HTTPException) as exc:
                run_patch_asset(sb, "asset-x", body, _current(role_code="002", company_id="cid-A"))
    assert exc.value.status_code == 404


# ── EE-UNIT-03: FACTORY tier 타 factory 자산 → 404

def test_ee_unit_03_patch_factory_tier_wrong_factory():
    """EE-UNIT-03: FACTORY tier 타 factory 자산 → 404"""
    from services.equipment_engine_svc import run_patch_asset

    sb = MagicMock()
    body = MagicMock()
    body.last_inspection_date = None
    body.next_inspection_date = None
    body.is_legal_target = True
    body.is_operating = None
    body.model_id = None
    body.equipment_model_id = None

    # 자산: factory_id = fid-other (자기 factory가 아님)
    asset_chain = MagicMock()
    asset_chain.data = [{"id": "asset-y", "factory_id": "fid-other"}]

    # factory.company_id = 자기 회사 (회사는 일치, factory만 불일치)
    factory_chain = MagicMock()
    factory_chain.data = [{"company_id": "cid-A"}]

    def _table_se(name):
        t = MagicMock()
        if name == "equipment_assets":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = asset_chain
        elif name == "factories":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = factory_chain
        return t

    sb.table.side_effect = _table_se

    with patch("services.permission_guard.has_permission", return_value=True):
        with patch("services.company_scope._scope", return_value="FACTORY"):
            with pytest.raises(HTTPException) as exc:
                run_patch_asset(
                    sb, "asset-y", body,
                    _current(role_code="012", company_id="cid-A", factory_id="fid-mine"),
                )
    assert exc.value.status_code == 404


# ── EE-UNIT-04: factory_id NULL 비-ALL → 404

def test_ee_unit_04_patch_null_factory_non_admin():
    """EE-UNIT-04: factory_id NULL 자산, 비-ALL → 404"""
    from services.equipment_engine_svc import run_patch_asset

    sb = MagicMock()
    body = MagicMock()
    body.last_inspection_date = None
    body.next_inspection_date = None
    body.is_legal_target = True
    body.is_operating = None
    body.model_id = None
    body.equipment_model_id = None

    asset_chain = MagicMock()
    asset_chain.data = [{"id": "asset-null", "factory_id": None}]

    def _table_se(name):
        t = MagicMock()
        if name == "equipment_assets":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = asset_chain
        return t

    sb.table.side_effect = _table_se

    with patch("services.permission_guard.has_permission", return_value=True):
        with patch("services.company_scope._scope", return_value="COMPANY"):
            with pytest.raises(HTTPException) as exc:
                run_patch_asset(
                    sb, "asset-null", body,
                    _current(role_code="002", company_id="cid-A"),
                )
    assert exc.value.status_code == 404


# ── EE-UNIT-05: PLATFORM tier → 빈 결과

def test_ee_unit_05_list_assets_platform_denied():
    """EE-UNIT-05: PLATFORM tier run_list_assets → 빈 결과"""
    from services.equipment_engine_svc import run_list_assets

    sb = MagicMock()
    with patch("services.company_scope._scope", return_value="PLATFORM"):
        result = run_list_assets(
            sb, 1, 50, None, None, None, None, None,
            _current(role_code="031"),
        )
    assert result["data"]["total"] == 0
    assert result["data"]["items"] == []
    sb.table.assert_not_called()


# ── EE-UNIT-06: 무회사 사용자 → 빈 결과

def test_ee_unit_06_list_assets_no_company():
    """EE-UNIT-06: company_id 없는 사용자 → 빈 결과"""
    from services.equipment_engine_svc import run_list_assets

    sb = MagicMock()
    user = _current()
    user["company_id"] = None

    with patch("services.company_scope._scope", return_value="COMPANY"):
        result = run_list_assets(sb, 1, 50, None, None, None, None, None, user)
    assert result["data"]["total"] == 0
    sb.table.assert_not_called()


# ── EE-UNIT-07: run_refresh 비-ALL → 403

def test_ee_unit_07_refresh_non_admin():
    """EE-UNIT-07: run_refresh_engine_equipment COMPANY role → 403"""
    from services.equipment_catalog_svc import run_refresh_engine_equipment

    sb = MagicMock()

    with patch("services.company_scope._scope", return_value="COMPANY"):
        with pytest.raises(HTTPException) as exc:
            run_refresh_engine_equipment(sb, _current(role_code="002"))
    assert exc.value.status_code == 403
    sb.rpc.assert_not_called()


# ── EE-UNIT-08: run_update_equipment_master 비-ALL → 403

def test_ee_unit_08_update_master_non_admin():
    """EE-UNIT-08: run_update_equipment_master FACTORY role → 403"""
    from services.equipment_catalog_svc import run_update_equipment_master

    sb = MagicMock()
    with patch("services.company_scope._scope", return_value="FACTORY"):
        with pytest.raises(HTTPException) as exc:
            run_update_equipment_master(
                sb, "some-facility", {"needs_review": False},
                _current(role_code="012"),
            )
    assert exc.value.status_code == 403
    sb.table.return_value.update.assert_not_called()


# ── EE-UNIT-09: run_bulk_approve_review 비-ALL → 403

def test_ee_unit_09_approve_non_admin():
    """EE-UNIT-09: run_bulk_approve_review TEAM role → 403"""
    from services.equipment_catalog_svc import run_bulk_approve_review

    sb = MagicMock()
    with patch("services.company_scope._scope", return_value="TEAM"):
        with pytest.raises(HTTPException) as exc:
            run_bulk_approve_review(
                sb, {"facility_names": ["펌프A"]},
                _current(role_code="004"),
            )
    assert exc.value.status_code == 403
    sb.table.return_value.update.assert_not_called()


# ── EE-UNIT-10: run_update_model 비-ALL → 403

def test_ee_unit_10_update_model_non_admin():
    """EE-UNIT-10: run_update_model ASSIGNED role → 403"""
    from services.equipment_catalog_svc import run_update_model

    sb = MagicMock()
    with patch("services.company_scope._scope", return_value="ASSIGNED"):
        with pytest.raises(HTTPException) as exc:
            run_update_model(
                sb, "model-id-x", {"risk_score": 5},
                _current(role_code="005"),
            )
    assert exc.value.status_code == 403
    sb.table.return_value.update.assert_not_called()


# ── EE-UNIT-11: run_get_equipment_stats 비-ALL → 403

def test_ee_unit_11_stats_non_admin():
    """EE-UNIT-11: run_get_equipment_stats COMPANY role → 403"""
    from services.equipment_engine_svc import run_get_equipment_stats

    sb = MagicMock()
    with patch("services.company_scope._scope", return_value="COMPANY"):
        with pytest.raises(HTTPException) as exc:
            run_get_equipment_stats(sb, "4.5.0", _current(role_code="002"))
    assert exc.value.status_code == 403
    sb.table.assert_not_called()


# ── EE-UNIT-12: 권한 실패 시 DB Update 미호출

def test_ee_unit_12_patch_no_perm_no_db_write():
    """EE-UNIT-12: EQUIPMENT_UPDATE 없으면 DB Update 호출 없음"""
    from services.equipment_engine_svc import run_patch_asset

    sb = MagicMock()
    body = MagicMock()
    body.last_inspection_date = None
    body.next_inspection_date = None
    body.is_legal_target = True
    body.is_operating = None
    body.model_id = None
    body.equipment_model_id = None

    with patch("services.permission_guard.has_permission", return_value=False):
        with pytest.raises(HTTPException):
            run_patch_asset(sb, "any-id", body, _current())

    sb.table.assert_not_called()


# ── EE-UNIT-13: ALL tier → scope 필터 없음 (전체 조회)

def test_ee_unit_13_list_assets_all_no_filter():
    """EE-UNIT-13: ALL tier → _resolve_asset_scope = None (필터 없음)"""
    from services.equipment_engine_svc import _resolve_asset_scope

    sb = MagicMock()
    with patch("services.company_scope._scope", return_value="ALL"):
        result = _resolve_asset_scope(sb, _current(role_code="001"))
    assert result is None, f"ALL tier인데 필터가 적용됨: {result}"


# ── EE-UNIT-14: FACTORY tier factory 교차검증 실패 → DENY

def test_ee_unit_14_resolve_scope_factory_cross_validation_fail():
    """EE-UNIT-14: FACTORY tier에서 factory.company_id != current.company_id → DENY"""
    from services.equipment_engine_svc import _resolve_asset_scope

    sb = MagicMock()
    # factories 조회: company_id = 타사
    factory_chain = MagicMock()
    factory_chain.data = [{"company_id": "cid-other"}]

    def _table_se(name):
        t = MagicMock()
        if name == "factories":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = factory_chain
        return t

    sb.table.side_effect = _table_se

    with patch("services.company_scope._scope", return_value="FACTORY"):
        result = _resolve_asset_scope(
            sb,
            _current(role_code="012", company_id="cid-A", factory_id="fid-mine"),
        )
    assert result == "DENY", f"교차검증 실패 시 DENY여야 함, 실제: {result}"
