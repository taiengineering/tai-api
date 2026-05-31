"""
services/obligation_refinement.py — Obligation Refinement v1.0.0

역할:
- Obligation Standard 목록 → Group + Index + Relationship + Evidence Link
- 데이터 손실 0
- 판단 없음, 제거 없음, 추론 없음

허용: Grouping, Indexing, Relationship Mapping, Evidence Linking
금지: Filtering, Decision, Risk, Priority, 데이터 삭제
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple


def refine(obligations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    3395 Obligations → Group + Index + Relationship.

    데이터 손실 0.
    입력 Obligation 전체 유지.
    판단 없음.
    """
    if not obligations:
        return {
            "obligations": [],
            "groups": [],
            "index": {},
            "relationships": [],
            "stats": {"total": 0, "groups": 0, "relationships": 0},
        }

    # ── 1. Index: obligation_id → obligation ──────────────────
    index: Dict[str, Dict[str, Any]] = {}
    for ob in obligations:
        oid = ob.get("obligation_id", "")
        if oid:
            index[oid] = ob

    # ── 2. Group: (law_name, article_no) 기준 ────────────────
    group_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for ob in obligations:
        law = (ob.get("law_name") or "").strip()
        art = (ob.get("article_no") or "").strip()
        key = (law, art)
        if key not in group_map:
            group_map[key] = {
                "group_id": f"{law}|{art}",
                "law_name": law,
                "article_no": art,
                "obligation_count": 0,
                "obligation_ids": [],
                "source_types": set(),
                "has_who": False,
                "has_when": False,
                "has_condition": False,
            }
        g = group_map[key]
        g["obligation_count"] += 1
        oid = ob.get("obligation_id", "")
        if oid:
            g["obligation_ids"].append(oid)
        st = ob.get("metadata", {}).get("source_type", "")
        if st:
            g["source_types"].add(st)
        if (ob.get("who") or "").strip():
            g["has_who"] = True
        if (ob.get("when") or "").strip():
            g["has_when"] = True
        if ob.get("condition", {}).get("exists"):
            g["has_condition"] = True

    # set → list (JSON 직렬화)
    groups = []
    for g in group_map.values():
        g["source_types"] = sorted(g["source_types"])
        groups.append(g)

    # count 역순 정렬
    groups.sort(key=lambda x: -x["obligation_count"])

    # ── 3. Relationship: 같은 그룹 내 obligation 간 연결 ────────
    relationships: List[Dict[str, Any]] = []
    for g in groups:
        ids = g["obligation_ids"]
        if len(ids) > 1:
            relationships.append({
                "relationship_type": "SAME_ARTICLE",
                "law_name": g["law_name"],
                "article_no": g["article_no"],
                "obligation_ids": ids,
                "count": len(ids),
            })

    # ── 4. Evidence Linking: evidence_chain 있는 것만 ───────────
    evidence_links: List[Dict[str, Any]] = []
    for ob in obligations:
        chain = (ob.get("evidence") or {}).get("chain") or []
        if chain:
            evidence_links.append({
                "obligation_id": ob.get("obligation_id", ""),
                "law_name": ob.get("law_name", ""),
                "article_no": ob.get("article_no", ""),
                "evidence_chain": chain,
            })

    return {
        "obligations": obligations,           # 전체 유지 (손실 0)
        "groups": groups,                     # 조문별 그룹
        "index": index,                       # obligation_id → obligation
        "relationships": relationships,       # SAME_ARTICLE 관계
        "evidence_links": evidence_links,     # evidence_chain 링크
        "stats": {
            "total": len(obligations),
            "groups": len(groups),
            "relationships": len(relationships),
            "evidence_links": len(evidence_links),
            "has_who_groups": sum(1 for g in groups if g["has_who"]),
            "has_when_groups": sum(1 for g in groups if g["has_when"]),
        },
    }
