"""LEG Collector Live Activation (WO-CHECK-013).

Frozen contract (CHECK-012):
  (law_name, law_article) -> matching law_article rows -> distinct law_id
  distinct law_id == 1 => LAW_RESOLVED (law_id fixed); ==0 NOT_FOUND; >1 AMBIGUOUS
  semantic_clause.id NOT required; single law_article.id NOT required.

Adds ONLY full_result["check"]["collectors"]["penalty"|"agency"] (add-only, no overwrite).
Fail-closed: any resolver/collector failure returns a contracted safe node and NEVER
raises into the Runtime result (Collector failure != Runtime failure).

Policy frozen:
  Penalty: relation_scope=SAME_LAW_ONLY, obligation_specific=false, meaning="same-law penalty exists"
  Agency:  ministry only; submit_org=NOT_FOUND unless evidence; no URL/phone/homepage.
"""
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional

LAW_RESOLVED, LAW_NOT_FOUND, LAW_AMBIGUOUS = "LAW_RESOLVED", "LAW_NOT_FOUND", "LAW_AMBIGUOUS"
COLLECTED, NOT_FOUND, ERROR = "COLLECTED", "NOT_FOUND", "ERROR"
NOT_FOUND_PENALTY_REASON = ("No penalty/administrative-fine article found in the same law_id. "
                            "Cross-law relation was not evaluated.")


def _dsn() -> str:
    dsn = (os.environ.get("SUPABASE_DB_URL") or os.environ.get("RTM_DATABASE_URL")
           or os.environ.get("LEG_LAW_DB_URL") or os.environ.get("DATABASE_URL"))
    if not dsn:
        raise RuntimeError("DB 환경변수 미설정(SUPABASE_DB_URL/RTM_DATABASE_URL)")
    return dsn


def _rows(sql: str, params) -> List[Dict[str, Any]]:
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(_dsn())
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# DB callables (leg-db). Identity resolution is law_id-level (CHECK-012 contract).
def resolve_law_ids(law_name: str, law_article: str) -> List[str]:
    try:
        art = int(str(law_article).strip())
    except Exception:
        return []
    rows = _rows(
        "SELECT DISTINCT lm.id::text AS law_id FROM public.law_master lm "
        "JOIN public.law_article la ON la.law_id = lm.id "
        "WHERE lm.law_name = %s AND la.article_no = %s;",
        (law_name, art),
    )
    return [r["law_id"] for r in rows]


def find_penalty_articles(law_id: str) -> List[Dict[str, Any]]:
    return _rows(
        "SELECT p.id::text AS article_id, p.article_no, p.article_title AS title, "
        "left(regexp_replace(coalesce(p.article_text,''),'\\s+',' ','g'),300) AS evidence "
        "FROM public.law_article p WHERE p.law_id = %s::uuid AND p.article_title ~ '벌칙|과태료' "
        "ORDER BY p.article_no;",
        (law_id,),
    )


def find_ministry(law_id: str) -> Optional[str]:
    rows = _rows("SELECT ministry_name FROM public.law_master WHERE id = %s::uuid;", (law_id,))
    return rows[0]["ministry_name"] if rows else None


def _resolve(law_name: str, law_article: str) -> Dict[str, Any]:
    try:
        ids = sorted(set(x for x in resolve_law_ids(law_name, law_article) if x))
    except Exception:
        return {"status": LAW_NOT_FOUND, "law_id": None}
    if len(ids) == 1:
        return {"status": LAW_RESOLVED, "law_id": ids[0]}
    return {"status": LAW_NOT_FOUND if not ids else LAW_AMBIGUOUS, "law_id": None}


def _penalty(law_id, status) -> Dict[str, Any]:
    base = {"collector": "PenaltyCollector", "relation_scope": "SAME_LAW_ONLY", "obligation_specific": False}
    if status != LAW_RESOLVED or not law_id:
        return {**base, "status": NOT_FOUND, "value": {"scope": "same_law", "exists": False, "articles": []},
                "reason": NOT_FOUND_PENALTY_REASON}
    try:
        arts = find_penalty_articles(law_id) or []
    except Exception:
        return {**base, "status": ERROR, "value": {"scope": "same_law", "exists": False, "articles": []},
                "source_table": "law_article", "source_key": "law_id=%s" % law_id}
    if not arts:
        return {**base, "status": NOT_FOUND, "value": {"scope": "same_law", "exists": False, "articles": []},
                "source_table": "law_article", "source_key": "law_id=%s" % law_id, "reason": NOT_FOUND_PENALTY_REASON}
    return {**base, "status": COLLECTED, "value": {"scope": "same_law", "exists": True, "articles": arts},
            "source_table": "law_article", "source_key": "law_id=%s" % law_id, "confidence": 0.9}


def _agency(law_id, status) -> Dict[str, Any]:
    submit = {"value": None, "status": NOT_FOUND}
    if status != LAW_RESOLVED or not law_id:
        return {"ministry": {"value": None, "status": NOT_FOUND, "collector": "AgencyCollector"}, "submit_org": submit}
    try:
        m = find_ministry(law_id)
    except Exception:
        return {"ministry": {"value": None, "status": ERROR, "collector": "AgencyCollector"}, "submit_org": submit}
    if not m:
        return {"ministry": {"value": None, "status": NOT_FOUND, "collector": "AgencyCollector",
                             "source_table": "law_master", "source_key": "law_id=%s" % law_id}, "submit_org": submit}
    return {"ministry": {"value": m, "status": COLLECTED, "collector": "AgencyCollector",
                         "source_table": "law_master", "source_key": "law_id=%s" % law_id}, "submit_org": submit}


def activate(full_result: Dict[str, Any]) -> Dict[str, Any]:
    """Add-only merge of check.collectors.{penalty,agency}. Never raises into runtime."""
    try:
        obls = full_result.get("obligations_raw") or []
        if not obls:
            return full_result
        first = obls[0]
        ln = (first.get("law_name") or "").strip()
        la = str(first.get("law_article") or "").strip()
        res = _resolve(ln, la)
        pen = _penalty(res["law_id"], res["status"])
        agc = _agency(res["law_id"], res["status"])
        check = full_result.setdefault("check", {})
        collectors = check.setdefault("collectors", {})
        collectors.setdefault("penalty", pen)
        collectors.setdefault("agency", agc)
    except Exception:
        return full_result
    return full_result
