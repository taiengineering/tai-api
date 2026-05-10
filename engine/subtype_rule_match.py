"""rule_classify_subtype 매칭 — Kiwi 토큰 JSON + 원문 (LLM 없음).

명세: priority ASC 첫 매칭 / COMPOSITE·TAIL_POS·HEAD_TOKEN 전략 지원.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from engine.morpheme import PUNCT_TAGS

logger = logging.getLogger(__name__)


def _meaningful(tok_json: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in tok_json if (t.get("tag") or "") not in PUNCT_TAGS]


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def _form_match(actual: str, expected: str) -> bool:
    """Kiwi 변형(ᆫ다 vs ㄴ다 등) 허용하되 태그는 별도 검증."""
    if actual == expected:
        return True
    a, e = _nfc(actual), _nfc(expected)
    if a == e:
        return True
    # 종결 어미에서 초성/종성 분해 차이
    if a.replace("\u11ab", "ㄴ") == e.replace("\u11ab", "ㄴ"):
        return True
    if len(a) >= 2 and len(e) >= 2 and a[-2:] == e[-2:]:
        return True
    return False


def _parse_tail_pattern(pattern: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for part in pattern.split("+"):
        p = part.strip()
        if "/" not in p:
            continue
        form, tag = p.rsplit("/", 1)
        out.append((form.strip(), tag.strip()))
    return out


def _tail_pos_match(tok_json: list[dict[str, Any]], pattern: str, pattern_position: str) -> bool:
    parts = _parse_tail_pattern(pattern)
    if not parts:
        return False
    m = _meaningful(tok_json)
    if len(m) < len(parts):
        return False
    tail = m[-len(parts) :]
    for t, (ef, et) in zip(tail, parts):
        if (t.get("tag") or "") != et:
            return False
        tf = t.get("form") or ""
        if not _form_match(tf, ef):
            return False
    return True


def match_subtype_rule(rule: dict[str, Any], tok_json: list[dict[str, Any]], source_text: str) -> bool:
    """단일 룰 매칭 여부."""
    strategy = rule.get("match_strategy") or ""
    pattern = rule.get("pattern") or ""
    pos = rule.get("pattern_position") or ""

    try:
        if strategy == "COMPOSITE":
            return re.search(pattern, source_text or "") is not None

        if strategy == "HEAD_TOKEN":
            st = (source_text or "").strip()
            if not st:
                return False
            return re.match(pattern, st) is not None

        if strategy == "TAIL_POS":
            return _tail_pos_match(tok_json, pattern, pos)
    except re.error as ex:
        logger.warning("regex error rule=%s: %s", rule.get("rule_name"), ex)
        return False

    return False


def pick_first_matching_subtype_rule(
    rules: list[dict[str, Any]],
    tok_json: list[dict[str, Any]],
    source_text: str,
) -> dict[str, Any] | None:
    """priority 정렬된 룰 목록에서 첫 매칭 룰 (없으면 None)."""
    for rule in rules:
        if match_subtype_rule(rule, tok_json, source_text):
            return rule
    return None
