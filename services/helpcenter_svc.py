# -*- coding: utf-8 -*-
"""헬프센터(help.taieng.co.kr) 조회 서비스. DB: tai-db — help_node / help_doc / help_feedback / help_search_log.

구자산 safe_help_content 와는 별개다. 그 테이블은 읽지도 쓰지도 않는다.

설계
  트리(help_node)는 배치를, 문서(help_doc)는 내용을 소유한다. 같은 doc_id 를 여러 노드에
  배치할 수 있으므로, 사실은 DB 에 1벌만 두고 섹션마다 참조한다.
  노출 판정은 전부 services.helpcenter_visibility 를 경유한다 — 이 모듈은 직접 판정하지 않는다.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services import helpcenter_visibility as vis
from services.time import now_kst

log = logging.getLogger(__name__)

_NODE = "help_node"
_DOC = "help_doc"
_FEEDBACK = "help_feedback"
_SEARCH_LOG = "help_search_log"

_NODE_COLS = (
    "id, parent_id, root_key, node_type, title, slug, description, sort_order, "
    "visibility, roles, sectors, min_level, addons, doc_id, link_url, icon, status"
)
_DOC_LIST_COLS = (
    "doc_id, type, slug, lang, title, answer_short, page_slug, status, updated_at, "
    "aliases, symptom_texts, pair_doc"
)

_TYPE_RANK = {"TROUBLE": 0, "FAQ": 1, "TASK": 2, "CONCEPT": 3, "GUIDE": 4, "POLICY": 5}


# ─────────────────────────────────────────────────────────────────────────
# 내부 — 노드 적재
# ─────────────────────────────────────────────────────────────────────────

def _load_nodes(root_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """노드 전량(또는 한 축) 적재. 트리 규모가 수백 수준이라 한 번에 읽어 메모리에서 다룬다."""
    sb = get_supabase()
    q = sb.table(_NODE).select(_NODE_COLS)
    if root_key:
        q = q.eq("root_key", root_key)
    res = q.order("sort_order", desc=False).order("title", desc=False).execute()
    return res.data or []


def _node_path(node_id: str, by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """루트까지의 경로(루트가 앞). 브레드크럼의 원천이다 — 내부 슬러그를 쓰지 않는다."""
    chain: List[Dict[str, Any]] = []
    cur = by_id.get(node_id)
    depth = 0
    while cur is not None and depth <= 32:
        chain.append(cur)
        parent_id = cur.get("parent_id")
        cur = by_id.get(parent_id) if parent_id else None
        depth += 1
    chain.reverse()
    return chain


# ─────────────────────────────────────────────────────────────────────────
# O8 TreeService
# ─────────────────────────────────────────────────────────────────────────

def get_tree(root_key: Optional[str], viewer: Dict[str, Any]) -> List[Dict[str, Any]]:
    """축 하나(또는 전체)의 트리. 노출 판정 후 고아 없이 중첩 구조로 돌려준다.

    노드에는 문서 slug 가 없다(배치와 내용을 분리했으므로). 그런데 화면은 /doc/{slug} 로 링크해야
    하므로, 여기서 doc_id → 문서 slug 를 한 번에 붙여 준다. 프론트가 doc_id 로 다시 조회하는
    왕복을 만들지 않기 위해서다.
    """
    nodes = _load_nodes(root_key)
    allowed = vis.prune_tree(nodes, viewer)

    slug_of = {
        d["doc_id"]: d.get("slug")
        for d in _fetch_docs_by_ids([n.get("doc_id") for n in allowed if n.get("doc_id")])
    }

    out: Dict[str, Dict[str, Any]] = {}
    for n in allowed:
        item = vis.public_node({**n, "doc_slug": slug_of.get(n.get("doc_id"))})
        item["children"] = []
        out[n["id"]] = item

    roots: List[Dict[str, Any]] = []
    for n in allowed:
        item = out[n["id"]]
        parent_id = n.get("parent_id")
        if parent_id and parent_id in out:
            out[parent_id]["children"].append(item)
        else:
            roots.append(item)
    return roots


def count_by_root(viewer: Dict[str, Any]) -> Dict[str, int]:
    """축별 문서 수 — 첫 화면 역할 카드의 'N개 문서' 표기에 쓴다."""
    nodes = vis.prune_tree(_load_nodes(None), viewer)
    counts: Dict[str, int] = {}
    for n in nodes:
        if n.get("node_type") == "DOC":
            counts[n["root_key"]] = counts.get(n["root_key"], 0) + 1
    return counts


# ─────────────────────────────────────────────────────────────────────────
# O9 DocService
# ─────────────────────────────────────────────────────────────────────────

def _fetch_doc(slug: str, lang: str) -> Optional[Dict[str, Any]]:
    sb = get_supabase()
    res = sb.table(_DOC).select("*").eq("slug", slug).eq("lang", lang).limit(1).execute()
    return (res.data or [None])[0]


def _fetch_docs_by_ids(doc_ids: List[str]) -> List[Dict[str, Any]]:
    ids = [d for d in dict.fromkeys(doc_ids) if d]
    if not ids:
        return []
    sb = get_supabase()
    res = sb.table(_DOC).select(_DOC_LIST_COLS).in_("doc_id", ids).execute()
    return res.data or []


def _include_refs(blocks: List[Dict[str, Any]]) -> List[str]:
    """include 블록이 가리키는 doc_id 목록. DB 의 help_doc_include_refs() 와 같은 규칙이다."""
    return [
        b.get("doc_id") for b in (blocks or [])
        if isinstance(b, dict) and b.get("type") == "include" and b.get("doc_id")
    ]


def _resolve_includes(
    blocks: List[Dict[str, Any]],
    viewer: Dict[str, Any],
    depth: int = 0,
) -> List[Dict[str, Any]]:
    """include 블록을 대상 문서의 블록으로 펼친다.

    같은 사실은 DB 에 1벌만 두고 필요한 문서가 참조한다(P10). 읽는 사람에게는 펼쳐서 보여야
    문서가 끊기지 않으므로, 응답 시점에 서버가 펼친다.

    · 대상이 이 viewer 에게 안 보이면 그 블록은 통째로 뺀다 — 게이팅을 우회하는 통로가 되지 않게 한다.
    · 펼친 블록에는 from_doc 을 달아 어디서 온 사실인지 남긴다.
    · 깊이 상한 3. DB 트리거가 순환을 막지만 여기서도 무한 확장을 두지 않는다.
    """
    refs = _include_refs(blocks)
    if not refs:
        return list(blocks or [])
    if depth >= 3:
        # 상한을 넘으면 더 펼치지 않고 include 블록을 뺀다 — 미해결 참조를 내보내지 않는다.
        log.warning("[helpcenter] include 깊이 상한 도달 — 남은 참조 제외: %s", refs)
        return [b for b in blocks if not (isinstance(b, dict) and b.get("type") == "include")]

    sources = {d["doc_id"]: d for d in _fetch_full_docs(refs)}
    allowed = vis.prune_tree(_load_nodes(None), viewer)
    visible_doc_ids = {n.get("doc_id") for n in allowed if n.get("doc_id")}

    out: List[Dict[str, Any]] = []
    for b in blocks or []:
        if not (isinstance(b, dict) and b.get("type") == "include"):
            out.append(b)
            continue
        src = sources.get(b.get("doc_id"))
        if not src or src.get("doc_id") not in visible_doc_ids or src.get("status") != vis.PUBLISHED:
            log.info("[helpcenter] include 대상 미노출 — 블록 제외: %s", b.get("doc_id"))
            continue
        for inner in _resolve_includes(src.get("blocks") or [], viewer, depth + 1):
            item = dict(inner)
            item["block_id"] = f"{b.get('block_id')}::{inner.get('block_id')}"
            item["from_doc"] = src.get("doc_id")
            out.append(item)
    return out


def _fetch_full_docs(doc_ids: List[str]) -> List[Dict[str, Any]]:
    ids = [d for d in dict.fromkeys(doc_ids) if d]
    if not ids:
        return []
    sb = get_supabase()
    return sb.table(_DOC).select("doc_id, blocks, status").in_("doc_id", ids).execute().data or []


def get_doc(slug: str, viewer: Dict[str, Any], lang: str = "ko") -> Optional[Dict[str, Any]]:
    """문서 단건 + 브레드크럼 + 관련 문서 + 짝 문서.

    문서 자체의 노출은 그 문서를 담은 노드로 판정한다. 노드가 하나도 안 보이면 문서도 안 보인다.
    """
    doc = _fetch_doc(slug, lang)
    if not doc:
        return None

    nodes = _load_nodes(None)
    allowed = vis.prune_tree(nodes, viewer)
    by_id = {n["id"]: n for n in allowed}
    holders = [n for n in allowed if n.get("doc_id") == doc["doc_id"]]
    if not holders:
        return None

    holder = sorted(holders, key=lambda n: (n.get("root_key") or "", n.get("sort_order") or 0))[0]
    path = _node_path(holder["id"], by_id)
    breadcrumb = [{"title": n.get("title"), "slug": n.get("slug")} for n in path]

    blocks = _resolve_includes(doc.get("blocks") or [], viewer)

    # 관련 문서는 include 로 끌어다 쓴 문서 + 짝 문서다. 별도 컬럼을 두지 않는다 —
    # 같은 사실을 두 곳에 적지 않기 위해 참조가 곧 관계다(P10).
    related_ids = _include_refs(doc.get("blocks") or [])
    if doc.get("pair_doc"):
        related_ids.append(doc["pair_doc"])
    visible_doc_ids = {n.get("doc_id") for n in allowed if n.get("doc_id")}
    related = [
        d for d in _fetch_docs_by_ids(related_ids)
        if d.get("doc_id") in visible_doc_ids and d.get("status") == vis.PUBLISHED
    ]

    pair = next((d for d in related if d.get("doc_id") == doc.get("pair_doc")), None)
    related = [d for d in related if d.get("doc_id") != doc.get("pair_doc")]

    return {
        "doc_id": doc.get("doc_id"),
        "type": doc.get("type"),
        "slug": doc.get("slug"),
        "lang": doc.get("lang"),
        "doc_group": doc.get("doc_group"),
        "title": doc.get("title"),
        "answer_short": doc.get("answer_short"),
        "blocks": blocks,
        "page_slug": doc.get("page_slug"),
        "related_laws": doc.get("related_laws") or [],
        "updated_at": doc.get("updated_at"),
        "change_note": doc.get("change_note"),
        "breadcrumb": breadcrumb,
        "related": [_doc_brief(d) for d in related],
        "pair": _doc_brief(pair) if pair else None,
    }


def get_doc_by_id_for_viewer(doc_id: str, viewer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """doc_id 가 이 viewer 에게 보이는 문서인지 확인한다. 피드백 수집 전 관문이다.

    안 보이는 문서에 피드백을 남길 수 있으면 존재 여부가 새어 나간다.
    """
    if not doc_id:
        return None
    allowed = vis.prune_tree(_load_nodes(None), viewer)
    if doc_id not in {n.get("doc_id") for n in allowed if n.get("doc_id")}:
        return None
    rows = _fetch_docs_by_ids([doc_id])
    row = rows[0] if rows else None
    if not row or row.get("status") != vis.PUBLISHED:
        return None
    return row


def _doc_brief(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "doc_id": d.get("doc_id"),
        "type": d.get("type"),
        "slug": d.get("slug"),
        "title": d.get("title"),
        "answer_short": d.get("answer_short"),
        "updated_at": d.get("updated_at"),
    }


# ─────────────────────────────────────────────────────────────────────────
# O11 ContextService — 앱·어드민 '?' 진입
# ─────────────────────────────────────────────────────────────────────────

def get_context(page_slug: str, viewer: Dict[str, Any], lang: str = "ko") -> Dict[str, Any]:
    """한 화면의 GUIDE + TROUBLE + FAQ 묶음. 없는 화면은 빈 묶음 + 안내를 돌려준다."""
    sb = get_supabase()
    res = (
        sb.table(_DOC).select(_DOC_LIST_COLS)
        .eq("page_slug", page_slug).eq("lang", lang).execute()
    )
    docs = res.data or []

    allowed_nodes = vis.prune_tree(_load_nodes(None), viewer)
    visible_doc_ids = {n.get("doc_id") for n in allowed_nodes if n.get("doc_id")}
    docs = [d for d in docs if d.get("doc_id") in visible_doc_ids and d.get("status") == vis.PUBLISHED]

    # 한 화면에 GUIDE 가 둘 이상일 때, 예전에는 next() 가 첫 건만 집고 나머지가 조용히 사라졌다.
    # other 의 조건이 GUIDE 를 배제하므로 그쪽으로도 가지 않았고, 쿼리에 ORDER BY 가 없어
    # 어느 것이 남는지 DB 행 순서에 달려 있었다 — 재현되지 않는 사라짐이었다(실측으로 겪음).
    # 이제는 화면 이름과 slug 가 같은 문서를 대표로 세우고, 나머지는 other 로 흘려 보낸다.
    guides = [d for d in docs if d.get("type") == "GUIDE"]
    guides.sort(key=lambda d: (d.get("slug") != page_slug, d.get("doc_id") or ""))
    guide = guides[0] if guides else None
    if len(guides) > 1:
        log.warning(
            "[helpcenter] page_slug=%s 에 GUIDE 가 %d건이다. 대표=%s, 나머지는 other 로 보낸다: %s",
            page_slug, len(guides), guide.get("doc_id"),
            [d.get("doc_id") for d in guides[1:]],
        )
    trouble = [d for d in docs if d.get("type") == "TROUBLE"]
    faq = [d for d in docs if d.get("type") == "FAQ"]
    other = guides[1:] + [d for d in docs if d.get("type") not in ("GUIDE", "TROUBLE", "FAQ")]

    return {
        "page_slug": page_slug,
        "found": bool(docs),
        "guide": _doc_brief(guide) if guide else None,
        "trouble": [_doc_brief(d) for d in trouble],
        "faq": [_doc_brief(d) for d in faq],
        "other": [_doc_brief(d) for d in other],
        "message": None if docs else "이 화면의 도움말은 아직 준비 중입니다.",
    }


# ─────────────────────────────────────────────────────────────────────────
# O10 SearchService
# ─────────────────────────────────────────────────────────────────────────

_TERM_UNSAFE = ',()"{}\\%'


def _sanitize_term(term: str) -> str:
    """postgrest or_ 표현식과 ilike 패턴을 깨뜨리는 문자를 공백으로 바꾼다.

    or_ 는 쉼표로 조건을 나누고 괄호로 묶으며, cs 는 중괄호로 배열을 표기한다.
    이 문자들이 검색어에 섞여 들어오면 필터 문법 자체가 어긋난다. 막는 게 아니라 지운다 —
    사용자가 오류 문구를 그대로 붙여넣는 경로가 주된 입력이기 때문이다.
    """
    out = "".join(" " if ch in _TERM_UNSAFE else ch for ch in (term or ""))
    return " ".join(out.split())


def _score(doc: Dict[str, Any], q: str, ctx: Optional[str], viewer: Dict[str, Any]) -> tuple:
    """정렬 키 — ① ctx 일치 최상단 ② 유형 가중치 ③ 관련도 ④ 제목.

    파이썬 튜플 비교라 값이 작을수록 앞이다. viewer 는 정렬에 쓰지 않는다 —
    역할별 가중치는 노출 판정과 섞이기 쉬워 두지 않았다. 노출은 VisibilityFilter 가 이미 끝냈다.
    """
    ctx_hit = 0 if (ctx and doc.get("page_slug") == ctx) else 1
    type_rank = _TYPE_RANK.get(doc.get("type") or "", 9)

    ql = q.lower()
    title = (doc.get("title") or "").lower()
    short = (doc.get("answer_short") or "").lower()
    symptoms = " ".join(doc.get("symptom_texts") or []).lower()
    aliases = " ".join(doc.get("aliases") or []).lower()

    if ql and ql in symptoms:
        relevance = 0          # 앱이 띄우는 오류 문구와 일치 — 가장 강한 신호
    elif ql and title.startswith(ql):
        relevance = 1
    elif ql and ql in title:
        relevance = 2
    elif ql and ql in aliases:
        relevance = 3
    elif ql and ql in short:
        relevance = 4
    else:
        relevance = 5

    return (ctx_hit, type_rank, relevance, doc.get("title") or "")


def search(
    q: str,
    viewer: Dict[str, Any],
    ctx: Optional[str] = None,
    types: Optional[List[str]] = None,
    lang: str = "ko",
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """제목·요약 부분일치 + 동의어(aliases)·오류문구(symptom_texts) 배열 매칭.

    후보 수집 범위의 한계 — 알고 쓴다
      title·answer_short 는 ilike 부분일치다. aliases·symptom_texts 는 `cs`(배열 포함)이므로
      **원소 전체가 일치**해야 걸린다. 앱이 띄운 오류 문구를 통째로 붙여넣는 경로는 이걸로 잡히고,
      배열 원소의 일부만 입력한 경우는 못 잡는다. 형태소 색인(kiwi)으로 그 구멍을 메우는 것은
      WP-7 IndexBuilder 과제다. 지금 없는 기능을 있는 척하지 않는다.
    """
    term = (q or "").strip()
    if not term:
        return {"items": [], "total": 0, "suggestions": []}

    sb = get_supabase()
    query = sb.table(_DOC).select(_DOC_LIST_COLS).eq("lang", lang)
    if types:
        query = query.in_("type", types)
    safe = _sanitize_term(term)
    if not safe:
        return {"items": [], "total": 0, "suggestions": _suggestions(viewer)}
    query = query.or_(
        f"title.ilike.%{safe}%,answer_short.ilike.%{safe}%,"
        f"aliases.cs.{{{safe}}},symptom_texts.cs.{{{safe}}}"
    )
    rows = query.limit(500).execute().data or []

    allowed_nodes = vis.prune_tree(_load_nodes(None), viewer)
    visible_doc_ids = {n.get("doc_id") for n in allowed_nodes if n.get("doc_id")}
    rows = [r for r in rows if r.get("doc_id") in visible_doc_ids and r.get("status") == vis.PUBLISHED]

    rows.sort(key=lambda d: _score(d, term, ctx, viewer))
    total = len(rows)
    page = rows[offset: offset + limit]

    return {
        "items": [_doc_brief(d) for d in page],
        "total": total,
        "suggestions": _suggestions(viewer) if total == 0 else [],
    }


def _suggestions(viewer: Dict[str, Any], n: int = 3) -> List[Dict[str, Any]]:
    """결과 0건일 때 보여줄 대체 질문 — 증상 문서를 우선 뽑는다."""
    sb = get_supabase()
    res = (
        sb.table(_DOC).select(_DOC_LIST_COLS)
        .eq("type", "TROUBLE").eq("status", vis.PUBLISHED)
        .order("updated_at", desc=True).limit(30).execute()
    )
    rows = res.data or []
    allowed_nodes = vis.prune_tree(_load_nodes(None), viewer)
    visible_doc_ids = {x.get("doc_id") for x in allowed_nodes if x.get("doc_id")}
    rows = [r for r in rows if r.get("doc_id") in visible_doc_ids]
    return [_doc_brief(d) for d in rows[:n]]


# ─────────────────────────────────────────────────────────────────────────
# O5 / O12 수집
# ─────────────────────────────────────────────────────────────────────────

def record_search(q: str, result_count: int, ctx: Optional[str], viewer: Dict[str, Any]) -> None:
    """검색어 적재. 결과 0건인 검색어가 문서 결손 후보다. 실패해도 조회를 막지 않는다."""
    try:
        get_supabase().table(_SEARCH_LOG).insert({
            "q": (q or "")[:300],
            "ctx": ctx,
            "role": viewer.get("role"),
            "sector": viewer.get("sector"),
            "result_count": int(result_count or 0),
        }).execute()
    except Exception as e:  # noqa: BLE001
        log.warning("[helpcenter] 검색로그 적재 실패: %s", e)


def record_feedback(payload: Dict[str, Any]) -> Dict[str, Any]:
    """문서 피드백 1건. 개인 식별자를 저장하지 않는다 — session_hash 만 받는다."""
    doc_id = (payload or {}).get("doc_id")
    verdict = (payload or {}).get("verdict")
    session_hash = (payload or {}).get("session_hash")
    if not doc_id or verdict not in ("UP", "DOWN") or not session_hash:
        raise ValueError("doc_id, verdict(UP|DOWN), session_hash 는 필수입니다.")

    row = {
        "doc_id": doc_id,
        "block_id": payload.get("block_id"),
        "verdict": verdict,
        "reason_code": payload.get("reason_code"),
        "reason_text": (payload.get("reason_text") or None),
        "ctx": payload.get("ctx"),
        "referrer": payload.get("referrer"),
        "session_hash": str(session_hash)[:128],
    }
    sb = get_supabase()
    try:
        res = sb.table(_FEEDBACK).insert(row).execute()
        return (res.data or [{}])[0]
    except Exception as e:  # noqa: BLE001
        # 같은 세션이 같은 문서에 이미 남긴 경우 — 유니크 제약이 막는다. 오류로 다루지 않는다.
        log.info("[helpcenter] 피드백 중복 또는 적재 실패 doc_id=%s: %s", doc_id, e)
        return {"doc_id": doc_id, "recorded": False}


def feedback_summary(period_days: int = 30) -> List[Dict[str, Any]]:
    """최근 period_days 일의 문서별 부정 비율 — 결손 되먹임(GapLoop)의 입력."""
    sb = get_supabase()
    since = (now_kst() - timedelta(days=max(1, period_days))).isoformat()
    res = (
        sb.table(_FEEDBACK).select("doc_id, verdict")
        .gte("created_at", since).limit(5000).execute()
    )
    agg: Dict[str, Dict[str, int]] = {}
    for r in res.data or []:
        d = agg.setdefault(r["doc_id"], {"up": 0, "down": 0})
        if r.get("verdict") == "DOWN":
            d["down"] += 1
        else:
            d["up"] += 1
    out = []
    for doc_id, c in agg.items():
        total = c["up"] + c["down"]
        out.append({
            "doc_id": doc_id, "up": c["up"], "down": c["down"], "total": total,
            "down_rate": round(100.0 * c["down"] / total) if total else 0,
        })
    out.sort(key=lambda x: (-x["down_rate"], -x["total"]))
    return out


def zero_result_terms(limit: int = 50, period_days: int = 30) -> List[Dict[str, Any]]:
    """최근 period_days 일의 결과 0건 검색어 — 문서 결손 목록."""
    sb = get_supabase()
    since = (now_kst() - timedelta(days=max(1, period_days))).isoformat()
    res = (
        sb.table(_SEARCH_LOG).select("q, ctx, created_at")
        .eq("result_count", 0).gte("created_at", since)
        .order("created_at", desc=True).limit(1000).execute()
    )
    counts: Dict[str, int] = {}
    for r in res.data or []:
        key = (r.get("q") or "").strip().lower()
        if key:
            counts[key] = counts.get(key, 0) + 1
    items = [{"q": k, "count": v} for k, v in counts.items()]
    items.sort(key=lambda x: -x["count"])
    return items[:limit]
