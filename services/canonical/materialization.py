"""Canonical lossless materialization — Phase 1.

WO-GATE8-CANONICAL-LOSSLESS-MATERIALIZATION-IMPLEMENT-01.

소비자 입력에 **이미 존재하는** RTM-vocabulary applicability 값을 손실 없이 공통
Canonical 계약(``DiagnoseStep1Body.input``)까지 운반하기 위한 단일 책임 helper.

패턴 (FREEZE):
    AVAILABLE INPUT
      -> canonical_applicability()  (vocab-allowlist, 값 존재 시만 보존)
      -> DiagnoseStep1Body.input
      -> build_facility(CURRENT _LEG_INPUT_FIELDS projection) EXISTING PROJECTION
      -> LEG RTM

엄격 규칙:
- allowlist = LEG ``_LEG_INPUT_FIELDS`` (RTM mapped_field vocabulary, exact-name).
  vocabulary와 **정확히 같은 이름**인 입력값만 이 Phase 에서 보존한다.
- 값이 실제 존재할 때만 preserve. 없는 값 생성/기본값/파생/추정 = 0.
- alias 없음(정확 이름만). derivation 없음(process/equipment -> has_* 계산 금지).
- build_facility 는 변경하지 않는다. 기존 input[code] 사영을 그대로 이용한다.

이 helper 는 nexas adapter(보존)와 run_diagnosis(병합) 두 지점이 공유한다.
동일 필터 로직을 두 곳에 중복 작성하지 않기 위한 단일 출처다.
"""

from __future__ import annotations

from typing import Any, Dict

# allowlist SoT — LEG Runtime 이 판정에 참조하는 입력 vocabulary(정확 이름).
from clients.leg_runtime_client import _LEG_INPUT_FIELDS


def canonical_applicability(source: Dict[str, Any]) -> Dict[str, Any]:
    """``source`` 에서 RTM-vocab(_LEG_INPUT_FIELDS) 과 정확히 같은 이름인 키만,
    값이 실제 존재할 때 그대로(verbatim) 보존한 dict 를 돌려준다.

    - alias/derivation/값 생성 없음.
    - None / 공백 문자열은 미보존(값 없음으로 취급).
    - 그 외 값(bool/int/float/list/dict 등)은 변형 없이 그대로 복사.
    """
    if not isinstance(source, dict):
        return {}
    out: Dict[str, Any] = {}
    for code in _LEG_INPUT_FIELDS:
        if code not in source:
            continue
        val = source[code]
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        out[code] = val
    return out
