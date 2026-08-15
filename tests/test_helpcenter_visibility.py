# -*- coding: utf-8 -*-
"""헬프센터 노출 판정·등급 리졸버 단위 테스트.

DB 를 붙이지 않는다. services.helpcenter_visibility 는 순수 함수이고,
services.help_plan_level 은 get_supabase 를 patch 해서 계약 행만 흉내 낸다.

이 테스트가 지키는 것
  P13 게이팅 근거는 서버가 도출한 값뿐이다 — viewer 에 없는 값으로는 아무것도 열리지 않는다.
  P14 등급 미상(level=None)이면 min_level 문서를 열지 않는다.
  P9  비로그인도 PUBLIC 문서는 본다.
"""
from unittest.mock import MagicMock, patch

import pytest

from services import help_plan_level as lv
from services import helpcenter_visibility as vis


# ─────────────────────────────────────────────────────────────────────────
# 도우미
# ─────────────────────────────────────────────────────────────────────────

def node(**kw):
    base = {
        "id": "n1", "parent_id": None, "root_key": "app", "node_type": "DOC",
        "title": "T", "slug": "t", "sort_order": 1, "status": "PUBLISHED",
        "visibility": "PUBLIC", "roles": None, "sectors": None, "min_level": None,
        "addons": None, "doc_id": "GUIDE-app-tbm", "link_url": None, "icon": None,
        "description": None,
    }
    base.update(kw)
    return base


def viewer(**kw):
    base = dict(vis.ANONYMOUS)
    base.update(kw)
    return base


LOGGED_IN = {"authed": True, "role": "003", "sector": "INDUSTRIAL", "level": 3, "level_reason": None}


# ─────────────────────────────────────────────────────────────────────────
# is_visible — 판정 5단계
# ─────────────────────────────────────────────────────────────────────────

def test_anonymous_sees_public_published():
    assert vis.is_visible(node(), vis.ANONYMOUS) is True


def test_draft_is_hidden_from_everyone():
    assert vis.is_visible(node(status="DRAFT"), LOGGED_IN) is False
    assert vis.is_visible(node(status="DRAFT"), vis.ANONYMOUS) is False


def test_auth_only_node_hidden_from_anonymous():
    n = node(visibility="AUTH")
    assert vis.is_visible(n, vis.ANONYMOUS) is False
    assert vis.is_visible(n, LOGGED_IN) is True


def test_role_restriction():
    n = node(roles=["004", "005"])
    assert vis.is_visible(n, LOGGED_IN) is False              # role 003
    assert vis.is_visible(n, viewer(authed=True, role="004")) is True


def test_sector_restriction():
    n = node(sectors=["CONSTRUCTION"])
    assert vis.is_visible(n, LOGGED_IN) is False              # sector INDUSTRIAL
    assert vis.is_visible(n, viewer(authed=True, sector="CONSTRUCTION")) is True


def test_empty_restriction_list_means_no_restriction():
    assert vis.is_visible(node(roles=[], sectors=[]), vis.ANONYMOUS) is True


def test_min_level_gate():
    n = node(min_level=3)
    assert vis.is_visible(n, viewer(authed=True, level=3)) is True
    assert vis.is_visible(n, viewer(authed=True, level=2)) is False


def test_unknown_level_is_hidden_not_allowed():
    """P14 — 등급을 모르면 여는 게 아니라 감춘다."""
    n = node(min_level=1)
    assert vis.is_visible(n, viewer(authed=True, level=None, level_reason="unmapped_plan")) is False


def test_gating_ignores_fields_not_in_viewer():
    """P13 — viewer 에 없는 키를 아무리 넣어도 판정이 바뀌지 않는다."""
    n = node(min_level=4, roles=["009"])
    forged = viewer(authed=True, level=None, role=None)
    forged["client_level"] = 9        # 클라이언트가 보냈다고 가정한 값
    forged["client_role"] = "009"
    assert vis.is_visible(n, forged) is False


# ─────────────────────────────────────────────────────────────────────────
# prune_tree — 고아 금지
# ─────────────────────────────────────────────────────────────────────────

def test_prune_tree_drops_children_of_hidden_parent():
    parent = node(id="p", node_type="SECTION", doc_id=None, visibility="AUTH")
    child = node(id="c", parent_id="p")
    kept = vis.prune_tree([parent, child], vis.ANONYMOUS)
    assert kept == []


def test_prune_tree_keeps_visible_child_of_visible_parent():
    parent = node(id="p", node_type="SECTION", doc_id=None)
    child = node(id="c", parent_id="p")
    kept_ids = {n["id"] for n in vis.prune_tree([parent, child], vis.ANONYMOUS)}
    assert kept_ids == {"p", "c"}


def test_prune_tree_hides_only_restricted_child():
    parent = node(id="p", node_type="SECTION", doc_id=None)
    open_child = node(id="c1", parent_id="p")
    gated_child = node(id="c2", parent_id="p", min_level=2)
    kept_ids = {n["id"] for n in vis.prune_tree([parent, open_child, gated_child], vis.ANONYMOUS)}
    assert kept_ids == {"p", "c1"}


def test_prune_tree_drops_node_whose_parent_is_absent():
    orphan = node(id="c", parent_id="missing")
    assert vis.prune_tree([orphan], vis.ANONYMOUS) == []


# ─────────────────────────────────────────────────────────────────────────
# public_node — 게이팅 근거 비노출
# ─────────────────────────────────────────────────────────────────────────

def test_public_node_strips_gating_fields():
    out = vis.public_node(node(roles=["004"], sectors=["INDUSTRIAL"], min_level=2, addons=["X"]))
    for leaked in ("roles", "sectors", "min_level", "addons", "visibility", "status"):
        assert leaked not in out
    assert out["slug"] == "t"


# ─────────────────────────────────────────────────────────────────────────
# build_viewer
# ─────────────────────────────────────────────────────────────────────────

def test_build_viewer_anonymous_when_no_user():
    v = vis.build_viewer(None, None)
    assert v["authed"] is False and v["level"] is None


def test_build_viewer_takes_role_and_sector_from_user_row():
    v = vis.build_viewer(
        {"role_code": "004", "sector": "CONSTRUCTION", "company_id": "c1"},
        {"level": 2, "sector": "INDUSTRIAL", "reason": None},
    )
    assert v["role"] == "004"
    assert v["sector"] == "CONSTRUCTION"    # users.sector 가 정본, 계약 업종은 참고값
    assert v["level"] == 2


def test_build_viewer_level_none_when_contract_missing():
    v = vis.build_viewer({"role_code": "004", "sector": "INDUSTRIAL"}, {"level": None, "reason": "no_contract"})
    assert v["level"] is None
    assert v["level_reason"] == "no_contract"


# ─────────────────────────────────────────────────────────────────────────
# help_plan_level — 추측 금지
# ─────────────────────────────────────────────────────────────────────────

def test_normalize_plan_code_strips_version_suffix_only():
    assert lv.normalize_plan_code("INDUSTRY_STARTER_V2") == "INDUSTRY_STARTER"
    assert lv.normalize_plan_code("CONSTRUCTION_STANDARD") == "CONSTRUCTION_STANDARD"
    assert lv.normalize_plan_code(" industry_pro ") == "INDUSTRY_PRO"
    assert lv.normalize_plan_code(None) == ""


def test_level_of_plan_known():
    got = lv.level_of_plan("INDUSTRY_STARTER_V2")
    assert got["sector"] == "INDUSTRIAL" and got["level"] == 1


def test_level_of_plan_unknown_returns_none_without_fallback():
    """payment_post_process 는 폴백하지만 게이팅은 폴백하지 않는다."""
    assert lv.level_of_plan("STANDARD") is None
    assert lv.level_of_plan("") is None


def _sb_with_contracts(rows):
    sb = MagicMock()
    chain = sb.table.return_value
    for attr in ("select", "eq", "in_", "order", "limit"):
        getattr(chain, attr).return_value = chain
    chain.execute.return_value = MagicMock(data=rows)
    return sb


def test_resolve_for_company_no_company():
    got = lv.resolve_for_company(None)
    assert got["level"] is None and got["reason"] == "no_company"


@patch("services.help_plan_level.get_supabase")
def test_resolve_for_company_no_contract(mock_sb):
    mock_sb.return_value = _sb_with_contracts([])
    got = lv.resolve_for_company("comp-1")
    assert got["level"] is None and got["reason"] == "no_contract"


@patch("services.help_plan_level.get_supabase")
def test_resolve_for_company_maps_known_plan(mock_sb):
    mock_sb.return_value = _sb_with_contracts([
        {"plan_code": "INDUSTRY_PRO", "status_code": "ACTIVE", "is_active": True,
         "end_date": None, "created_at": "2026-01-01"},
    ])
    got = lv.resolve_for_company("comp-1")
    assert got == {"level": 3, "sector": "INDUSTRIAL", "plan_code": "INDUSTRY_PRO", "reason": None}


@patch("services.help_plan_level.get_supabase")
def test_resolve_for_company_unmapped_plan_stays_none(mock_sb):
    """실측: 활성 계약 6건 중 STANDARD 는 매핑에 없다. 업종조차 유추하지 않는다."""
    mock_sb.return_value = _sb_with_contracts([
        {"plan_code": "STANDARD", "status_code": "ACTIVE", "is_active": True,
         "end_date": None, "created_at": "2026-01-01"},
    ])
    got = lv.resolve_for_company("comp-1")
    assert got["level"] is None
    assert got["sector"] is None
    assert got["reason"] == "unmapped_plan"
    assert got["plan_code"] == "STANDARD"


@patch("services.help_plan_level.get_supabase")
def test_resolve_for_company_takes_highest_mapped_level(mock_sb):
    mock_sb.return_value = _sb_with_contracts([
        {"plan_code": "INDUSTRY_STARTER", "status_code": "ACTIVE", "is_active": True,
         "end_date": None, "created_at": "2026-02-01"},
        {"plan_code": "INDUSTRY_PRO", "status_code": "ACTIVE", "is_active": True,
         "end_date": None, "created_at": "2026-01-01"},
    ])
    assert lv.resolve_for_company("comp-1")["level"] == 3


@patch("services.help_plan_level.get_supabase")
def test_resolve_for_company_db_error_is_not_an_open_door(mock_sb):
    sb = MagicMock()
    sb.table.side_effect = RuntimeError("db down")
    mock_sb.return_value = sb
    got = lv.resolve_for_company("comp-1")
    assert got["level"] is None


# ─────────────────────────────────────────────────────────────────────────
# 게이팅 종단 — 등급 미상 사용자는 min_level 문서를 못 본다
# ─────────────────────────────────────────────────────────────────────────

@patch("services.help_plan_level.get_supabase")
def test_unmapped_plan_user_cannot_see_min_level_doc(mock_sb):
    mock_sb.return_value = _sb_with_contracts([
        {"plan_code": "STANDARD", "status_code": "ACTIVE", "is_active": True,
         "end_date": None, "created_at": "2026-01-01"},
    ])
    contract = lv.resolve_for_company("comp-1")
    v = vis.build_viewer({"role_code": "004", "sector": "CONSTRUCTION", "company_id": "comp-1"}, contract)
    assert vis.is_visible(node(min_level=1), v) is False
    assert vis.is_visible(node(), v) is True          # 등급 조건 없는 문서는 그대로 보인다


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
