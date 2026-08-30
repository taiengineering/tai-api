"""services/paid_result_contract_svc.py — PAID RESULT PRODUCT CONTRACT v1 (STEP3B-A).

DESIGN BASELINE
    tai-www docs 2026-08-30_PAID_DIAGNOSIS_RESULT_DERIVATION_DESIGN_V1.md
    tai-www DESIGN_paid-product-surface-v1_2026-08-30.md
    STEP3A Materializer @ 131c96022de2e564b4ff3b545361015907b819bb

WHAT THIS IS
    저장된 진단 결과 row 를 상품 계약(Product Contract v1)으로 조립하는 얇은 계층.

        anonymous_diagnosis_results row
            ├── row.full_result   -> Materializer -> paid_result_materials_v1
            └── row 컬럼           -> diagnosis metadata
                                   => Product Contract v1

    이 모듈은 조립만 한다. R01~R16 을 다시 계산하지 않는다.

SOURCE OF TRUTH
    AUTHORITATIVE TABLE      public.anonymous_diagnosis_results
    LEGAL RESULT SOURCE      row.full_result
    DIAGNOSIS METADATA       row 의 실제 컬럼만 (id / public_token / tier_code /
                             status / created_at / expires_at)
    full_result 밖의 metadata 로 법적 의무를 만들거나 보충하지 않는다.

PUBLIC EXPOSURE = 0 (STEP3B-A)
    이 계약은 아직 어떤 공개 endpoint 에도 실리지 않는다.
    routers/diagnosis_result_web.py 및 GET /diagnosis/paid-result/{public_token} 무변경.
    공개 노출은 ACCESS GATE 가 닫힌 뒤 STEP3B-B 에서 다룬다.

PURITY CONTRACT
    DB / HTTP / filesystem / datetime / random / uuid / env / LLM = 0
    입력 row mutation = 0
    같은 row 이면 항상 같은 출력

MEANING BOUNDARIES (STEP3A 조사에서 확정 — 변경 금지)
    LEGAL APPLICABILITY SCOPE = full_result.obligations_raw[] 전건
    engine_applicability  = INTERNAL TRACE                    (법 적용 여부 아님)
    check_result          = CHECK / EVIDENCE VALIDATION STATUS (법 적용 여부 아님)
    consumer_status       = EVALUATION USABILITY LABEL         (법 적용 여부 아님)
    usable_for_evaluation = RESULT / EVIDENCE USABILITY        (법 적용 여부 아님)
    -> NOT_APPLICABLE 을 "귀사에 적용되지 않음"으로 번역하지 않는다.
       이 모듈은 어떤 한국어 상태 label 도 만들지 않는다(R06 번역은 별도 Rule Contract).

NOT INCLUDED, BY DESIGN
    company_name / business_no / ceo_name / address
        현행 paid writer 가 보존하지 않는다. 빈 문자열·추정값으로도 만들지 않는다.
        근거가 없으면 계약에도 넣지 않는다. (writer 개선은 별도 작업선)
    row.input_data
        pass-through 하지 않는다. input_data 계약은 다른 작업선에서 재설계 중이다.

PUBLIC ENTRYPOINT
    build_paid_result_contract_v1(row: dict) -> dict
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

from services.paid_result_materializer import build_paid_result_materials_v1

CONTRACT_VERSION = 1

# 진단 metadata 로 운반하는 row 컬럼. 이 목록 밖의 컬럼은 계약에 싣지 않는다.
#   row 컬럼명 -> 계약 필드명
DIAGNOSIS_METADATA_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("id", "result_id"),
    ("public_token", "public_token"),
    ("tier_code", "tier_code"),
    ("status", "status"),
    ("created_at", "diagnosed_at"),
    ("expires_at", "expires_at"),
)

# 계약에 절대 만들어 넣지 않는 필드(근거 없음 — 현행 writer 미보존).
# 상수로 남겨 두는 이유는 "생성하지 않는다"는 경계를 코드에 고정하기 위해서다.
NEVER_INVENTED_FIELDS: Tuple[str, ...] = (
    "company_name",
    "business_no",
    "ceo_name",
    "address",
)


def _diagnosis_metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    """row 컬럼 -> diagnosis metadata. 값 변환·보정·기본값 생성 없음.

    컬럼이 없으면 None. 특히 created_at 이 없으면 diagnosed_at 은 None 이며,
    현재 시각으로 대체하지 않는다(Product Surface Design: 진단일은 저장된 실제 진단일).
    """
    return {
        contract_field: row.get(column)
        for column, contract_field in DIAGNOSIS_METADATA_FIELDS
    }


def build_paid_result_contract_v1(row: Any) -> Dict[str, Any]:
    """저장된 anonymous_diagnosis_results row -> Product Contract v1.

    PURE FUNCTION. 입력 row 를 변경하지 않으며, 같은 row 이면 항상 같은 출력을 낸다.

    조립만 한다:
      · paid_result_materials_v1 = build_paid_result_materials_v1(row["full_result"])
      · diagnosis                = row 컬럼 6개
    파생 계산(COUNT / GROUP / DISTINCT / timing / duplicate / portfolio / coverage 등)은
    전부 STEP3A Materializer 의 책임이며 이 모듈에서 다시 구현하지 않는다.
    """
    src = copy.deepcopy(row) if isinstance(row, dict) else {}

    return {
        "contract_version": CONTRACT_VERSION,
        "diagnosis": _diagnosis_metadata(src),
        # material_version 을 포함한 Materializer 출력을 그대로 싣는다. 덮어쓰지 않는다.
        "paid_result_materials_v1": build_paid_result_materials_v1(src.get("full_result")),
    }


__all__ = ["build_paid_result_contract_v1"]
