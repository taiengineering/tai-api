"""OBJ-GRAPH controlled mapping. Precision over coverage. No fuzzy/LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

RULE_SET_VERSION = "GRAPH_RULES_V1"

ALLOWED_METHODS = frozenset(
    {
        "EXACT_MAPPING",
        "TAXONOMY",
        "CONTROLLED_KEYWORD",
        "SOURCE_NATIVE",
        "DETERMINISTIC_RULE",
    }
)

FORBIDDEN_METHODS = frozenset({"SEMANTIC_CANDIDATE", "LLM_CANDIDATE"})

CONTENT_TYPES = frozenset(
    {
        "KOSHA_GUIDE",
        "SAFETY_MATERIAL",
        "ACCIDENT",
        "LAW_UPDATE",
        "PRECEDENT",
        "KNOWLEDGE_CENTER",
    }
)

CONTEXT_RELATION_TYPES = frozenset(
    {
        "topic",
        "sector",
        "industry",
        "process",
        "equipment",
        "task",
        "chemical",
        "legal_obligation",
        "legal_article",
    }
)

DIRECT_RELATION_TYPES = frozenset(
    {"RELATED_TO", "EXPLAINS", "ACCIDENT_CASE_FOR", "GUIDE_FOR"}
)

WAVE3_GENERATED_RELATIONS = frozenset({"equipment", "process", "task", "topic", "sector"})

DISABLED_RELATIONS = frozenset({"chemical", "legal_obligation"})


@dataclass(frozen=True)
class ControlledRule:
    rule_id: str
    rule_version: str
    relation_type: str
    relation_key: str
    relation_label: str
    aliases: tuple[str, ...]
    allowed_fields: tuple[str, ...]
    match_mode: str
    method: str = "CONTROLLED_KEYWORD"
    allowed_content_types: tuple[str, ...] = ()


CONTROLLED_RULES: tuple[ControlledRule, ...] = (
    ControlledRule(
        rule_id="EQUIPMENT_FORKLIFT_V1",
        rule_version="1",
        relation_type="equipment",
        relation_key="forklift",
        relation_label="지게차",
        aliases=("지게차", "포크리프트", "forklift"),
        allowed_fields=("title", "summary", "category", "guide_title", "description", "accident_summary"),
        match_mode="CONTROLLED_PHRASE",
    ),
    ControlledRule(
        rule_id="TASK_WELDING_V1",
        rule_version="1",
        relation_type="task",
        relation_key="welding",
        relation_label="용접",
        aliases=("용접작업", "용접", "welding"),
        allowed_fields=("title", "summary", "category", "guide_title", "description", "accident_summary", "work_type"),
        match_mode="CONTROLLED_PHRASE",
    ),
    ControlledRule(
        rule_id="PROCESS_EXCAVATION_V1",
        rule_version="1",
        relation_type="process",
        relation_key="excavation",
        relation_label="굴착",
        aliases=("굴착작업", "굴착", "excavation"),
        allowed_fields=("title", "summary", "category", "guide_title", "description", "accident_summary", "work_type"),
        match_mode="CONTROLLED_PHRASE",
    ),
    ControlledRule(
        rule_id="TOPIC_FALL_V1",
        rule_version="1",
        relation_type="topic",
        relation_key="fall",
        relation_label="추락",
        aliases=("떨어짐", "추락", "fall"),
        allowed_fields=("title", "summary", "category", "guide_title", "description", "accident_summary", "accident_type", "hazard_type"),
        match_mode="CONTROLLED_PHRASE",
    ),
    ControlledRule(
        rule_id="SECTOR_CONSTRUCTION_V1",
        rule_version="1",
        relation_type="sector",
        relation_key="construction",
        relation_label="건설",
        aliases=("건설업", "건설", "construction"),
        allowed_fields=("sector", "work_type", "category"),
        match_mode="SOURCE_NATIVE",
        method="SOURCE_NATIVE",
    ),
)


def _contains_phrase(text: str, alias: str) -> bool:
    if not text or not alias:
        return False
    if alias.isascii() and alias.isalpha():
        import re
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None
    return alias in text


def match_field(value: str | None, rule: ControlledRule) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if rule.match_mode == "EXACT_VALUE":
        for alias in rule.aliases:
            if text == alias or text.lower() == alias.lower():
                return alias
        return None
    if rule.match_mode in {"CONTROLLED_PHRASE", "SOURCE_NATIVE"}:
        # Longer aliases first so "용접작업" wins over "용접" when both match.
        for alias in sorted(rule.aliases, key=len, reverse=True):
            if _contains_phrase(text, alias):
                return alias
        return None
    return None


def accept_candidate(method: str) -> str:
    if method in FORBIDDEN_METHODS:
        return "REJECTED"
    if method in ALLOWED_METHODS:
        return "ACCEPTED"
    return "REJECTED"


def rules_for_fields(field_names: Iterable[str]) -> list[ControlledRule]:
    fields = set(field_names)
    return [rule for rule in CONTROLLED_RULES if fields.intersection(rule.allowed_fields)]
