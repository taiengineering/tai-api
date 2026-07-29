"""위험성 결정 판정 서비스.

Goal: G-ms5zwv4v-b88c4a
설계: docs/ops/tai-risk-assessment/PLAN_risk-assessment-design_v2.md
검증: docs/ops/tai-risk-assessment/RESEARCH_legal-verification_v1.md

■ 판정의 성격
  산업안전보건법 제36조제1항은 "위험성의 크기가 허용 가능한 범위인지를 평가"하도록 규정한다.
  즉 최종 산출은 점수가 아니라 '허용 가능 / 허용 불가'의 이진 판정이다.
  2023년 개정으로 고시 제8조에서 '위험성 추정' 단계가 삭제되었고, 빈도·강도 계산은
  독립 단계가 아니라 '위험성 결정' 내부의 선택 가능한 계산 방식 중 하나가 되었다.

■ 척도는 코드가 아니라 데이터
  고시 원문에는 척도 수치(3x3, 5x4, 상/중/하)가 없다. 제9조제2항이 위험성 수준과
  판단기준, 허용 가능한 위험성 수준을 사업주가 사전에 확정하도록 위임한다.
  따라서 이 서비스는 ra_scale 레코드를 받아 판정하며, 어떤 수준 체계도 가정하지 않는다.

■ 4기법 단일 인터페이스 (고시 제7조제5항)
  빈도·강도법 / 체크리스트법 / 3단계 판단법 / 핵심요인기술법(OPS)
  입력 형태만 다르고 산출은 모두 (level, acceptable) 이다.

■ 승급 사유는 '판정 시점'의 상태로 본다 (2026-07-29 정정)
  승급 사유의 요건은 인원수 그 자체가 아니라 "많은 근로자가 '위험에 노출될 것'이
  예상되는" 상태다. 감소대책을 실행해 노출이 차단되면 그 요건은 더 이상 성립하지 않는다.
  따라서 승급 판단은 이번 판정의 입력(raw_input_json)을 우선 보고, 값이 없을 때만
  요인에 등록된 값을 쓴다. 이렇게 하지 않으면 대책을 아무리 세워도 등급이 내려가지 않아
  고시 제12조제3항의 반복 루프가 영원히 끝나지 않는다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# 대책 우선순위 (고시 제12조제1항 각 호 + 안내서가 명시한 0순위)
HIERARCHY_LABELS = {
    0: "법령에 규정된 조치",
    1: "제거·대체·설계단계 저감",
    2: "공학적 대책",
    3: "관리적 대책",
    4: "개인용 보호구",
}

# 다수 근로자 노출로 볼 기본 임계값. 사업장이 조정할 수 있도록 인자로 받는다.
DEFAULT_MANY_EXPOSED = 10

ESCALATION_LABELS = {
    "LEGAL_NONCOMPLIANCE": "법령에서 규정하는 사항을 만족하지 않음",
    "SEVERE_EXPECTED": "중대재해 또는 건강장해가 명확히 예상됨",
    "MANY_EXPOSED": "많은 근로자가 위험에 노출될 것으로 예상됨",
    "INDUSTRY_PRECEDENT": "동종업계 중대재해와 연관 있음",
}


class DecisionError(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


# ── 척도 유틸 ────────────────────────────────────────────────────────
def _levels(scale: Dict[str, Any]) -> List[Dict[str, Any]]:
    lv = scale.get("levels_json") or []
    return [l for l in lv if isinstance(l, dict) and l.get("code")]


def _order_map(scale: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i, l in enumerate(_levels(scale), start=1):
        try:
            out[str(l["code"])] = int(l.get("order", i))
        except (TypeError, ValueError):
            out[str(l["code"])] = i
    return out


def _max_level_code(scale: Dict[str, Any]) -> Optional[str]:
    om = _order_map(scale)
    return max(om, key=lambda k: om[k]) if om else None


def is_acceptable(level_code: Optional[str], scale: Dict[str, Any]) -> Optional[bool]:
    """허용 가능 여부. 고시 제11조제2항 — 허용 가능한 위험성 수준인지 결정한다."""
    if not level_code:
        return None
    om = _order_map(scale)
    acc = scale.get("acceptable_max")
    if not acc or acc not in om or level_code not in om:
        return None
    return om[level_code] <= om[acc]


# ── 기법별 수준 산출 ─────────────────────────────────────────────────
def _level_three_step(raw: Dict[str, Any], scale: Dict[str, Any]) -> Optional[str]:
    """3단계 판단법 — 근로자 경험을 반영해 수준을 직접 선택한다(계산 없음)."""
    return raw.get("level") or raw.get("level_code")


def _level_checklist(raw: Dict[str, Any], scale: Dict[str, Any]) -> Optional[str]:
    """체크리스트법 — 항목별 O/X 를 적정/보완으로 분류한다."""
    mark = str(raw.get("mark", "")).strip().upper()
    if mark in ("X", "N", "NG", "FALSE", "보완"):
        return _max_level_code(scale)
    if mark in ("O", "Y", "OK", "TRUE", "적정"):
        om = _order_map(scale)
        return min(om, key=lambda k: om[k]) if om else None
    return raw.get("level")


def _level_ops(raw: Dict[str, Any], scale: Dict[str, Any]) -> Optional[str]:
    """핵심요인 기술법 — 기존 조치로 충분한지 여부로 판정한다(점수 없음)."""
    v = raw.get("is_sufficient")
    if v is None:
        return raw.get("level")
    om = _order_map(scale)
    if not om:
        return None
    return (min(om, key=lambda k: om[k]) if v else max(om, key=lambda k: om[k]))


def _level_freq_sev(raw: Dict[str, Any], scale: Dict[str, Any]) -> Optional[str]:
    """빈도·강도법 — 조합 연산과 구간표는 전적으로 사업장 설정(matrix_json)을 따른다.

    matrix_json 예:
      {"op":"MULTIPLY",
       "bands":[{"min":1,"max":3,"level_code":"LOW"},
                {"min":4,"max":9,"level_code":"HIGH"}]}
    op 은 MULTIPLY | ADD | MATRIX(cells) 를 지원한다.
    """
    m = scale.get("matrix_json") or {}
    try:
        f = int(raw.get("freq"))
        s = int(raw.get("sev"))
    except (TypeError, ValueError):
        return raw.get("level")

    op = str(m.get("op", "MULTIPLY")).upper()
    if op == "ADD":
        score = f + s
    elif op == "MATRIX":
        cells = m.get("cells") or {}
        try:
            return str(cells[str(f)][str(s)])
        except Exception:  # noqa: BLE001
            return None
    else:
        score = f * s

    for b in (m.get("bands") or []):
        try:
            if int(b["min"]) <= score <= int(b["max"]):
                return str(b["level_code"])
        except (KeyError, TypeError, ValueError):
            continue
    return None


_METHOD_FN = {
    "THREE_STEP": _level_three_step,
    "CHECKLIST": _level_checklist,
    "OPS": _level_ops,
    "FREQ_SEV": _level_freq_sev,
}


# ── 자동 승급 ────────────────────────────────────────────────────────
def _int_or_none(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def escalate(level_code: Optional[str], item: Dict[str, Any], scale: Dict[str, Any],
             many_exposed_threshold: int = DEFAULT_MANY_EXPOSED
             ) -> Tuple[Optional[str], List[Dict[str, str]]]:
    """위험성 수준을 높게 분류해야 하는 경우를 반영한다.

    고시 해설·안내서가 드는 사유:
      1. 법령에서 규정하는 사항을 만족하지 않는 경우      → 최고 수준으로
      2. 중대재해·건강장해가 명확히 예상되는 경우          → 최고 수준으로
      3. 많은 근로자가 위험에 노출될 것이 예상되는 경우    → 한 단계 상향
      4. 동종업계 중대재해와 연관이 있는 경우              → 한 단계 상향

    3번은 '노출될 것이 예상되는' 상태를 요건으로 하므로, 이번 판정의 입력에
    exposed_count 가 실려 있으면 그 값(잔여 노출 인원)을 먼저 본다.
    """
    raw = item.get("raw_input_json") or {}
    reasons: List[Dict[str, str]] = []
    om = _order_map(scale)
    if not om:
        return level_code, reasons

    inv = {v: k for k, v in om.items()}
    cur = om.get(level_code or "", 0)
    top = max(om.values())

    def to_top(code_reason: str) -> None:
        nonlocal cur
        cur = top
        reasons.append({"rule": code_reason, "label": ESCALATION_LABELS.get(code_reason, ""),
                        "effect": "TO_TOP"})

    def step_up(code_reason: str) -> None:
        nonlocal cur
        if cur < top:
            cur = min(cur + 1, top)
        reasons.append({"rule": code_reason, "label": ESCALATION_LABELS.get(code_reason, ""),
                        "effect": "STEP_UP"})

    if raw.get("legal_noncompliance") or item.get("legal_noncompliance"):
        to_top("LEGAL_NONCOMPLIANCE")
    if raw.get("severe_expected"):
        to_top("SEVERE_EXPECTED")

    # 잔여 노출 인원 — 이번 판정 입력이 우선, 없으면 요인 등록값
    exposed = _int_or_none(raw.get("exposed_count"))
    if exposed is None:
        exposed = _int_or_none(item.get("exposed_count")) or 0
    if exposed >= many_exposed_threshold:
        step_up("MANY_EXPOSED")

    if raw.get("industry_precedent"):
        step_up("INDUSTRY_PRECEDENT")

    if not reasons:
        return level_code, reasons
    return inv.get(cur, level_code), reasons


# ── 판정 진입점 ──────────────────────────────────────────────────────
def decide(item: Dict[str, Any], scale: Dict[str, Any],
           many_exposed_threshold: int = DEFAULT_MANY_EXPOSED) -> Dict[str, Any]:
    """유해·위험요인 1건의 위험성을 결정한다.

    반환: {"level", "acceptable", "escalation": [...], "method"}
    """
    if not scale:
        raise DecisionError("척도(ra_scale)가 지정되지 않았습니다. 고시 제9조제2항에 따라 사전에 확정해야 합니다.")
    method = str(scale.get("method") or "").upper()
    fn = _METHOD_FN.get(method)
    if not fn:
        raise DecisionError(f"지원하지 않는 평가방법입니다: {method}")

    raw = item.get("raw_input_json") or {}
    base = fn(raw, scale)
    level, reasons = escalate(base, item, scale, many_exposed_threshold)
    acc = is_acceptable(level, scale)

    return {
        "method": method,
        "level": level,
        "level_before_escalation": base,
        "acceptable": acc,
        "escalation": reasons,
    }


# ── 가드 ────────────────────────────────────────────────────────────
def check_discovery_methods(items: List[Dict[str, Any]]) -> Optional[str]:
    """고시 제10조 — 특별한 사정이 없으면 사업장 순회점검(제1호)을 포함해야 한다."""
    if not items:
        return None
    methods = {str(i.get("discovery_method") or "") for i in items}
    if "PATROL" not in methods:
        return ("유해·위험요인 파악 방법에 사업장 순회점검(PATROL)이 없습니다. "
                "고시 제10조는 특별한 사정이 없으면 순회점검을 포함하도록 정합니다.")
    return None


def check_control_hierarchy(controls: List[Dict[str, Any]]) -> Optional[str]:
    """고시 제12조제1항 — 개인용 보호구는 우선순위 마지막이며 보충적 수단이다."""
    if not controls:
        return None
    hs = {int(c.get("hierarchy")) for c in controls if c.get("hierarchy") is not None}
    if hs and hs == {4}:
        return ("감소대책이 개인용 보호구(4순위)만으로 구성되어 있습니다. "
                "고시 제12조제1항은 법령 규정 조치, 제거·대체, 공학적·관리적 대책을 "
                "우선 검토하도록 정합니다.")
    return None


def assessment_readiness(items: List[Dict[str, Any]],
                         controls_by_item: Dict[str, List[Dict[str, Any]]]
                         ) -> Dict[str, Any]:
    """완료 가능 여부 점검.

    고시 제12조제3항 — 허용 가능한 수준이 될 때까지 추가 대책을 수립·실행해야 한다.
    다만 제12조제4항의 잠정 조치가 있는 경우는 완료를 허용하되 그 사실을 남긴다.
    """
    open_items, interim_items = [], []
    for it in items:
        if it.get("acceptable") is True:
            continue
        cs = controls_by_item.get(str(it.get("id")), [])
        entry = {
            "id": it.get("id"), "hazard": it.get("hazard"), "level": it.get("level"),
            "escalation": it.get("escalation_json") or [],
        }
        (interim_items if any(c.get("is_interim") for c in cs) else open_items).append(entry)

    warnings = [w for w in (check_discovery_methods(items),) if w]
    for it in items:
        w = check_control_hierarchy(controls_by_item.get(str(it.get("id")), []))
        if w:
            warnings.append(f"[{it.get('hazard')}] {w}")

    return {
        "can_complete": not open_items,
        "open_items": open_items,
        "interim_items": interim_items,
        "warnings": warnings,
    }
