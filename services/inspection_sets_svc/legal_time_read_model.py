"""services/inspection_sets_svc/legal_time_read_model.py

WO-SAAS-LEGAL-TIME-CONSUME-001 / STEP 4B-4B.

inspection_sets 조회 응답 row 에 additive read-model `legal_time_normalized` 를 부착한다.

- DERIVED HELPER (LEG SoT 아님 · operation schedule 아님).
- source = legal_operation_presentation.timing / .cycle (#304 가 보존한 official raw snapshot).
- shared legal_time_normalizer(normalize_legal_time_text) 만 사용. cycle_unit/value 역해석·law/article 추정·DB·LEG 0.
- 단순 계약: legal_operation_presentation 이 dict 면 normalize 시도, 없음/NULL/malformed 면 key 미생성.
  (canonical/legacy 판별 조건 — source/atom_id — 을 새로 만들지 않는다.)
- input dict mutation 0: 반드시 shallow copy 후 additive. 원본/legal_operation_presentation/cycle_* 무변경.
"""
from __future__ import annotations

from typing import Any

from services.legal_time_normalizer import VERSION, normalize_legal_time_text


def attach_legal_time_normalized(item: Any) -> Any:
    """응답 row → legal_time_normalized additive 부착된 **새 dict**. 입력 mutation 0.

    legal_operation_presentation.{timing,cycle} 을 normalize. 둘 다 None 이면 key 미생성.
    """
    if not isinstance(item, dict):
        return item

    out = dict(item)  # shallow copy — 원본 row mutation 0

    presentation = item.get("legal_operation_presentation")
    if not isinstance(presentation, dict):
        return out  # 없음/NULL/malformed → key 미생성 (fail-close)

    timing = normalize_legal_time_text(presentation.get("timing"))
    cycle = normalize_legal_time_text(presentation.get("cycle"))
    if timing is None and cycle is None:
        return out

    normalized: dict = {"version": VERSION}  # shared normalizer VERSION 재사용
    if timing is not None:
        normalized["timing"] = timing
    if cycle is not None:
        normalized["cycle"] = cycle

    out["legal_time_normalized"] = normalized
    return out


__all__ = ["attach_legal_time_normalized"]
