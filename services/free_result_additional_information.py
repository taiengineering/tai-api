"""무료 결과 '추가 확인 정보' count projection.

WO-FREE-RESULT-ADDITIONAL-INFORMATION-001 (READ-ONLY / additive).

무료진단 당시 저장된 full_result 만으로 count 를 뽑는다.
새 법령판정/유료진단 재실행/raw 재판정 = 0.

원천(GATE-0 실측 확정):
  input_gaps      = full_result.contract.{missing_fields, unknown_fields, invalid_fields} 길이
  obligation_gaps = full_result.obligations_raw[*].enrichment.missing_fields 가 non-empty 인 의무 수
  coverage        = full_result.obligations_raw[*].enrichment.usable_for_evaluation (strict bool)
                    true→evaluable / false→not_evaluable / 부재·null·비bool→unknown

원칙:
  - 배열 내용/field_code 는 노출하지 않는다 — 숫자만(WO 6).
  - review_required_count/unconfirmed_count 를 재사용하지 않는다(의미 혼입 방지, WO 7).
  - usable_for_evaluation 은 'true'/'false' 문자열을 bool 로 추론하지 않는다(WO 8).
  - fail-closed: 원천 부재·malformed → 해당 count 0. 절대 raise 하지 않는다(WO 9).
"""
from __future__ import annotations

from typing import Any, Dict


def _arr_len(v: Any) -> int:
    return len(v) if isinstance(v, list) else 0


def _is_nonempty_list(v: Any) -> bool:
    return isinstance(v, list) and len(v) > 0


def _empty() -> Dict[str, Any]:
    return {
        "input_gaps": {"missing_count": 0, "unknown_count": 0, "invalid_count": 0},
        "obligation_gaps": {"affected_count": 0},
        "coverage": {"evaluable_count": 0, "not_evaluable_count": 0, "unknown_count": 0},
    }


def project_additional_information(full_result: Any) -> Dict[str, Any]:
    """full_result -> additional_information dict (counts only).

    항상 dict 반환. 어떤 실패에서도 raise 하지 않고 0 으로 채운다(fail-closed).
    """
    try:
        fr = full_result if isinstance(full_result, dict) else {}

        # ── input gaps (contract 기준) ──
        contract = fr.get("contract")
        contract = contract if isinstance(contract, dict) else {}
        input_gaps = {
            "missing_count": _arr_len(contract.get("missing_fields")),
            "unknown_count": _arr_len(contract.get("unknown_fields")),
            "invalid_count": _arr_len(contract.get("invalid_fields")),
        }

        # ── obligation gaps + coverage (obligations_raw[*].enrichment 기준) ──
        obligations = fr.get("obligations_raw")
        obligations = obligations if isinstance(obligations, list) else []

        affected = 0
        evaluable = 0
        not_evaluable = 0
        cov_unknown = 0
        for ob in obligations:
            enr = ob.get("enrichment") if isinstance(ob, dict) else None
            enr = enr if isinstance(enr, dict) else {}
            if _is_nonempty_list(enr.get("missing_fields")):
                affected += 1
            usable = enr.get("usable_for_evaluation")
            if usable is True:
                evaluable += 1
            elif usable is False:
                not_evaluable += 1
            else:
                # 키 없음/null/비bool(문자열 등) → 추론 변환 금지, unknown 처리(WO 8).
                cov_unknown += 1

        return {
            "input_gaps": input_gaps,
            "obligation_gaps": {"affected_count": affected},
            "coverage": {
                "evaluable_count": evaluable,
                "not_evaluable_count": not_evaluable,
                "unknown_count": cov_unknown,
            },
        }
    except Exception:
        return _empty()
