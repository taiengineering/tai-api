"""6하원칙 휴리스틱 추출 — Kiwi 토큰 + 원문 (LLM 없음).

명세 §5.6: 첫 매칭만, 없으면 NULL. 기존 값 덮어쓰지 않음 (runner에서 NULL만 채움).
"""

from __future__ import annotations

import re
from typing import Any

from engine.morpheme import PUNCT_TAGS

# 주격 조사 (이/가/은/는)
_JKS_SUBJ = frozenset({"이", "가", "은", "는"})
# 여격
_JKB_OBJ = frozenset({"에게", "한테", "께"})
# 처격/부사격
_JKB_LOC = frozenset({"에", "에서", "으로", "로"})


def _meaningful(tok_json: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in tok_json if (t.get("tag") or "") not in PUNCT_TAGS]


def extract_six_w(tok_json: list[dict[str, Any]], source_text: str) -> dict[str, str | None]:
    """토큰·원문에서 executor 등 추출. 값 없으면 None."""
    m = _meaningful(tok_json or [])
    text = source_text or ""
    out: dict[str, str | None] = {
        "executor": None,
        "recipient": None,
        "what": None,
        "when_value": None,
        "where_value": None,
        "how": None,
        "condition": None,
    }

    # executor: NNG/NNP + 바로 다음 JKS 주격
    for i in range(len(m) - 1):
        if (m[i].get("tag") or "") in ("NNG", "NNP") and (m[i + 1].get("tag") or "") == "JKS":
            if (m[i + 1].get("form") or "") in _JKS_SUBJ:
                out["executor"] = (m[i].get("form") or "").strip() or None
                break

    # recipient: JKB 여격 앞 명사
    for i in range(len(m) - 1):
        if (m[i + 1].get("form") or "") in _JKB_OBJ:
            if (m[i].get("tag") or "") in ("NNG", "NNP"):
                out["recipient"] = (m[i].get("form") or "").strip() or None
                break

    # what: 첫 VV 동사형태소
    for t in m:
        if (t.get("tag") or "").startswith("VV"):
            out["what"] = (t.get("form") or "").strip() or None
            break

    # when_value: 날짜/연도 류 (원문 regex)
    mo = re.search(
        r"(?:\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}\s*년\s*\d{1,2}\s*월|\d{4}\s*년)",
        text,
    )
    if mo:
        out["when_value"] = mo.group(0).strip()

    # where_value: 에/에서 앞 NNG/NNP (첫 매칭)
    for i in range(len(m) - 1):
        if (m[i + 1].get("form") or "") in ("에", "에서"):
            if (m[i].get("tag") or "") in ("NNG", "NNP"):
                out["where_value"] = (m[i].get("form") or "").strip() or None
                break

    # how: 첫 MAG 또는 '으로/로' 앞 명사
    for t in m:
        if (t.get("tag") or "") == "MAG":
            out["how"] = (t.get("form") or "").strip() or None
            break
    if out["how"] is None:
        for i in range(len(m) - 1):
            if (m[i + 1].get("form") or "") in ("으로", "로") and (m[i].get("tag") or "") in (
                "NNG",
                "NNP",
            ):
                out["how"] = (m[i].get("form") or "").strip() or None
                break

    # condition: ~경우 / ~때
    mc = re.search(r"([^.。\n]{2,40}(?:경우|때))", text)
    if mc:
        out["condition"] = mc.group(1).strip()[:200]

    return out
