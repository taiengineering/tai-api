# -*- coding: utf-8 -*-
"""VisibilityFilter — 헬프센터 노출 판정을 한 곳에서 종결한다.

원칙 (routers/leader_scope.py 의 '클라이언트 값 불신' 관례를 따른다)
  판정 근거는 토큰에서 도출한 값뿐이다. 클라이언트가 쿼리 파라미터로 보낸
  role·sector·level 은 읽지 않는다. 값을 조작해도 응답이 바뀌지 않아야 한다.

  기존 /help/search 는 이 4축을 전부 쿼리로 받아 게이팅이 무력한 상태다.
  신규 경로는 그것을 승계하지 않는다.

DB 는 service_role 키로 붙어 RLS 가 우회되므로, 노출 판정은 전적으로 이 모듈이 책임진다.

addons 는 이번 범위에서 판정 축이 아니다 — 사용자가 어떤 addon 을 보유했는지 저장하는
데이터가 없기 때문이다. help_node.addons 컬럼은 남겨두되 필터에 쓰지 않는다.
"""
from typing import Any, Dict, Iterable, List, Optional

PUBLISHED = "PUBLISHED"
VIS_PUBLIC = "PUBLIC"
VIS_AUTH = "AUTH"


def build_viewer(
    user: Optional[Dict[str, Any]] = None,
    contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """토큰에서 도출한 사용자 행 + 계약 등급 → 판정용 viewer.

    user      : routers.auth.get_current_user 가 돌려준 users 행. 비로그인이면 None.
    contract  : services.help_plan_level.resolve_for_company 결과. 없으면 등급 미상.
    """
    if not user:
        return {"authed": False, "role": None, "sector": None, "level": None, "level_reason": "anonymous"}

    contract = contract or {}
    # 업종은 users.sector 를 정본으로 본다. 계약 업종은 참고값이다.
    sector = user.get("sector") or contract.get("sector")
    return {
        "authed": True,
        "role": user.get("role_code"),
        "sector": sector,
        "level": contract.get("level"),
        "level_reason": contract.get("reason"),
    }


ANONYMOUS = {"authed": False, "role": None, "sector": None, "level": None, "level_reason": "anonymous"}


def _matches_list(allowed: Optional[Iterable[str]], value: Optional[str]) -> bool:
    """목록이 비어 있으면 제한 없음. 값이 없는데 제한이 있으면 불통과."""
    items = [x for x in (allowed or []) if x]
    if not items:
        return True
    if not value:
        return False
    return value in items


def is_visible(row: Dict[str, Any], viewer: Dict[str, Any]) -> bool:
    """노드 또는 문서 1건이 이 viewer 에게 보이는가.

    판정 순서
      1) status 가 PUBLISHED 가 아니면 감춘다.
      2) visibility 가 AUTH 인데 비로그인이면 감춘다.
      3) roles 가 지정돼 있으면 viewer.role 이 그 안에 있어야 한다.
      4) sectors 가 지정돼 있으면 viewer.sector 가 그 안에 있어야 한다.
      5) min_level 이 지정돼 있으면 viewer.level 이 그 이상이어야 한다.
         **등급 미상(level=None)이면 감춘다** — 모를 때 보여주지 않는 쪽으로 판정한다.
    """
    if (row.get("status") or "") != PUBLISHED:
        return False

    visibility = row.get("visibility") or VIS_PUBLIC
    if visibility == VIS_AUTH and not viewer.get("authed"):
        return False

    if not _matches_list(row.get("roles"), viewer.get("role")):
        return False

    if not _matches_list(row.get("sectors"), viewer.get("sector")):
        return False

    min_level = row.get("min_level")
    if min_level is not None:
        level = viewer.get("level")
        if level is None or level < min_level:
            return False

    return True


def apply(rows: Iterable[Dict[str, Any]], viewer: Dict[str, Any]) -> List[Dict[str, Any]]:
    """목록에서 보이는 것만 남긴다."""
    return [r for r in (rows or []) if is_visible(r, viewer)]


def prune_tree(nodes: List[Dict[str, Any]], viewer: Dict[str, Any]) -> List[Dict[str, Any]]:
    """트리에서 보이는 노드만 남기되 고아를 만들지 않는다.

    부모가 감춰지면 그 아래 전부 감춘다. 부모가 보이는데 자식만 감추는 것은 허용한다.
    """
    visible_ids = {n["id"] for n in nodes if is_visible(n, viewer)}
    by_id = {n["id"]: n for n in nodes}

    def reachable(node: Dict[str, Any]) -> bool:
        cur = node
        depth = 0
        while cur is not None:
            if cur["id"] not in visible_ids:
                return False
            parent_id = cur.get("parent_id")
            if not parent_id:
                return True
            cur = by_id.get(parent_id)
            depth += 1
            if depth > 32:
                return False
        # 부모가 목록에 없으면(상위가 감춰졌거나 다른 축이면) 고아로 보고 제외한다.
        return False

    return [n for n in nodes if reachable(n)]


def public_node(node: Dict[str, Any]) -> Dict[str, Any]:
    """응답용 노드 — 내부 판정 필드를 밖으로 내보내지 않는다.

    roles·sectors·min_level·addons·visibility 는 게이팅 근거이므로 응답에서 제외한다.
    무엇이 왜 감춰졌는지 클라이언트가 역산할 수 있게 두지 않는다.

    doc_slug 는 판정 근거가 아니라 링크 재료다. 노드는 doc_id 만 갖고 있어서 화면이
    /doc/{slug} 를 만들 수 없고, 그러면 노드 slug 로 잘못 링크한다. 호출부(get_tree)가 채워 준다.
    """
    return {
        "id": node.get("id"),
        "parent_id": node.get("parent_id"),
        "root_key": node.get("root_key"),
        "node_type": node.get("node_type"),
        "title": node.get("title"),
        "slug": node.get("slug"),
        "description": node.get("description"),
        "sort_order": node.get("sort_order"),
        "icon": node.get("icon"),
        "doc_id": node.get("doc_id"),
        "doc_slug": node.get("doc_slug"),
        "link_url": node.get("link_url"),
    }
