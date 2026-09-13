"""OBJ-GRAPH producers. Candidates only. No DB writes. No LLM."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from services.knowledge_graph_rules import (
    CONTROLLED_RULES,
    DISABLED_RELATIONS,
    WAVE3_GENERATED_RELATIONS,
    accept_candidate,
    match_field,
)

GUIDE_MATERIAL_RULE_ID = "GUIDE_MATERIAL_RELATED_V1"
GUIDE_STOPWORDS = frozenset({"안전", "보건", "작업", "관리", "지침", "기술지침", "기준", "방법", "대한", "관한", "관련"})


@dataclass(frozen=True)
class GraphCandidate:
    source_content_type: str
    source_content_id: str
    edge_kind: str
    relation_type: str
    relation_key: str | None
    relation_label: str | None
    target_content_type: str | None
    target_content_id: str | None
    method: str
    evidence_type: str
    evidence_value: str | None
    source_field: str | None
    rule_id: str | None
    rule_version: str | None
    source_version: str | None
    source_content_hash: str
    status: str


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_source_content(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def is_current_guide(item: dict[str, Any], current_ids: set[str] | None) -> bool:
    if current_ids is None:
        return True
    return str(item.get("content_id") or item.get("guide_no") or "") in current_ids


def is_current_material(item: dict[str, Any], current_ids: set[str] | None) -> bool:
    if item.get("in_current_snapshot") is False:
        return False
    if current_ids is None:
        return True
    return str(item.get("content_id") or item.get("id") or "") in current_ids


def is_current_accident(item: dict[str, Any]) -> bool:
    # Source table has no current=true column. Public list contract = row exists with identity.
    return bool(item.get("content_id") or item.get("id"))


def is_current_law(item: dict[str, Any]) -> bool:
    return bool(item.get("is_public") is True and str(item.get("status") or "").upper() == "PUBLISHED")


def is_current_precedent(item: dict[str, Any]) -> bool:
    return bool(item.get("content_id") or item.get("id") or item.get("case_name"))


def is_current_knowledge_center(item: dict[str, Any]) -> bool:
    return bool(item.get("content_id") or item.get("slug")) and item.get("is_public", True) is not False


def _field_map_for(content_type: str, item: dict[str, Any]) -> dict[str, str]:
    if content_type == "KOSHA_GUIDE":
        return {
            "guide_title": str(item.get("guide_title") or item.get("title") or ""),
            "category": str(item.get("category") or item.get("category_name") or ""),
            "title": str(item.get("guide_title") or item.get("title") or ""),
        }
    if content_type == "SAFETY_MATERIAL":
        return {
            "title": str(item.get("title") or ""),
            "description": str(item.get("description") or ""),
            "category": str(item.get("category") or ""),
        }
    if content_type == "ACCIDENT":
        return {
            "title": str(item.get("title") or ""),
            "accident_summary": str(item.get("accident_summary") or item.get("summary") or ""),
            "work_type": str(item.get("work_type") or ""),
            "accident_type": str(item.get("accident_type") or ""),
            "summary": str(item.get("accident_summary") or item.get("summary") or ""),
        }
    if content_type == "LAW_UPDATE":
        return {
            "law_name": str(item.get("law_name") or ""),
            "summary": str(item.get("summary") or ""),
            "title": str(item.get("law_name") or item.get("title") or ""),
        }
    if content_type == "PRECEDENT":
        return {
            "case_name": str(item.get("case_name") or ""),
            "summary": str(item.get("summary") or ""),
            "hazard_type": str(item.get("hazard_type") or ""),
            "sector": str(item.get("sector") or ""),
            "title": str(item.get("case_name") or ""),
        }
    if content_type == "KNOWLEDGE_CENTER":
        return {
            "title": str(item.get("title") or ""),
            "summary": str(item.get("summary") or ""),
            "category": str(item.get("category") or ""),
        }
    return {}


def _source_hash(content_type: str, content_id: str, fields: dict[str, str]) -> str:
    payload = {
        "content_type": content_type,
        "content_id": content_id,
        **{k: v for k, v in sorted(fields.items()) if v},
    }
    return hash_source_content(payload)


def produce_controlled_candidates(
    content_type: str,
    item: dict[str, Any],
    *,
    current: bool,
) -> list[GraphCandidate]:
    if not current:
        return []
    content_id = str(item.get("content_id") or item.get("id") or item.get("guide_no") or item.get("slug") or "")
    if not content_id:
        return []
    fields = _field_map_for(content_type, item)
    source_hash = _source_hash(content_type, content_id, fields)
    source_version = str(item.get("content_hash") or item.get("source_version") or source_hash)
    out: list[GraphCandidate] = []
    seen: set[tuple[str, str]] = set()
    for rule in CONTROLLED_RULES:
        if rule.relation_type in DISABLED_RELATIONS:
            continue
        if rule.relation_type not in WAVE3_GENERATED_RELATIONS:
            continue
        if rule.allowed_content_types and content_type not in rule.allowed_content_types:
            continue
        for field_name, value in fields.items():
            if field_name not in rule.allowed_fields:
                continue
            hit = match_field(value, rule)
            if not hit:
                continue
            identity = (rule.relation_type, rule.relation_key)
            if identity in seen:
                continue
            seen.add(identity)
            method = rule.method
            out.append(
                GraphCandidate(
                    source_content_type=content_type,
                    source_content_id=content_id,
                    edge_kind="CONTEXT",
                    relation_type=rule.relation_type,
                    relation_key=rule.relation_key,
                    relation_label=rule.relation_label,
                    target_content_type=None,
                    target_content_id=None,
                    method=method,
                    evidence_type="FIELD_PHRASE",
                    evidence_value=hit,
                    source_field=field_name,
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    source_version=source_version,
                    source_content_hash=source_hash,
                    status=accept_candidate(method),
                )
            )
            break
    return out


def produce_guide_relations(items: Iterable[dict[str, Any]], *, current_ids: set[str] | None) -> list[GraphCandidate]:
    out: list[GraphCandidate] = []
    for item in items:
        out.extend(produce_controlled_candidates("KOSHA_GUIDE", item, current=is_current_guide(item, current_ids)))
    return out


def produce_safety_material_relations(items: Iterable[dict[str, Any]], *, current_ids: set[str] | None) -> list[GraphCandidate]:
    out: list[GraphCandidate] = []
    for item in items:
        out.extend(produce_controlled_candidates("SAFETY_MATERIAL", item, current=is_current_material(item, current_ids)))
    return out


def produce_accident_relations(items: Iterable[dict[str, Any]]) -> list[GraphCandidate]:
    out: list[GraphCandidate] = []
    for item in items:
        out.extend(produce_controlled_candidates("ACCIDENT", item, current=is_current_accident(item)))
    return out


def produce_law_relations(items: Iterable[dict[str, Any]]) -> list[GraphCandidate]:
    out: list[GraphCandidate] = []
    for item in items:
        out.extend(produce_controlled_candidates("LAW_UPDATE", item, current=is_current_law(item)))
    return out


def produce_precedent_relations(items: Iterable[dict[str, Any]]) -> list[GraphCandidate]:
    out: list[GraphCandidate] = []
    for item in items:
        out.extend(produce_controlled_candidates("PRECEDENT", item, current=is_current_precedent(item)))
    return out


def produce_knowledge_center_relations(items: Iterable[dict[str, Any]] | None) -> list[GraphCandidate]:
    if items is None:
        return []
    out: list[GraphCandidate] = []
    for item in items:
        out.extend(produce_controlled_candidates("KNOWLEDGE_CENTER", item, current=is_current_knowledge_center(item)))
    return out


def _normalize_title(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"[^\w가-힣]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(value: str) -> list[str]:
    return [part for part in _normalize_title(value).split(" ") if part]


def _high_signal(tokens: Iterable[str]) -> list[str]:
    return [token for token in tokens if token not in GUIDE_STOPWORDS and len(token) >= 2]


def is_guide_material_related(guide_title: str, material_title: str) -> bool:
    """Shadow of tai-www koshaGuides.js matcher. Not the production GUIDE owner."""
    guide_tokens = _high_signal(_tokenize(guide_title))
    material_tokens = set(_high_signal(_tokenize(material_title)))
    unique_overlap = len({token for token in guide_tokens if token in material_tokens})
    specific_hit = any(len(token) >= 4 and token in material_tokens for token in guide_tokens)
    return unique_overlap >= 2 or specific_hit


def produce_guide_material_shadow(
    guides: Iterable[dict[str, Any]],
    materials: Iterable[dict[str, Any]],
    *,
    current_guide_ids: set[str] | None,
    current_material_ids: set[str] | None,
) -> list[GraphCandidate]:
    """DIRECT RELATED_TO evidence only. Does not own GUIDE robots/sitemap."""
    out: list[GraphCandidate] = []
    material_list = list(materials)
    for guide in guides:
        if not is_current_guide(guide, current_guide_ids):
            continue
        guide_id = str(guide.get("content_id") or guide.get("guide_no") or "")
        guide_title = str(guide.get("guide_title") or guide.get("title") or "")
        fields = _field_map_for("KOSHA_GUIDE", guide)
        source_hash = _source_hash("KOSHA_GUIDE", guide_id, fields)
        source_version = str(guide.get("content_hash") or source_hash)
        for material in material_list:
            if not is_current_material(material, current_material_ids):
                continue
            material_id = str(material.get("content_id") or material.get("id") or "")
            material_title = str(material.get("title") or "")
            if not is_guide_material_related(guide_title, material_title):
                continue
            out.append(
                GraphCandidate(
                    source_content_type="KOSHA_GUIDE",
                    source_content_id=guide_id,
                    edge_kind="DIRECT",
                    relation_type="RELATED_TO",
                    relation_key=None,
                    relation_label=None,
                    target_content_type="SAFETY_MATERIAL",
                    target_content_id=material_id,
                    method="DETERMINISTIC_RULE",
                    evidence_type="TITLE_TOKEN_OVERLAP",
                    evidence_value=material_title,
                    source_field="guide_title",
                    rule_id=GUIDE_MATERIAL_RULE_ID,
                    rule_version="1",
                    source_version=source_version,
                    source_content_hash=source_hash,
                    status=accept_candidate("DETERMINISTIC_RULE"),
                )
            )
    return out
