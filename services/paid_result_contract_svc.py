"""services/paid_result_contract_svc.py — PAID RESULT PRODUCT CONTRACT v1 (STEP3B-A / STEP3B-A.1).

DESIGN BASELINE
    tai-www docs 2026-08-30_PAID_DIAGNOSIS_RESULT_DERIVATION_DESIGN_V1.md
    tai-www DESIGN_paid-product-surface-v1_2026-08-30.md
    STEP3A Materializer @ 131c96022de2e564b4ff3b545361015907b819bb
    STEP3B-A.1 PRODUCT CONTRACT v1.1 — DIAGNOSIS PROFILE 작업지시
    STEP4C-2 PKG-0 PRODUCT CONTRACT PROFILE +2 작업지시
    tai-www docs 2026-08-31_PAID_DIAGNOSIS_PREMIUM_WEB_VALUE_SPEC_V2.md §6.7

WHAT THIS IS
    저장된 진단 결과 row 를 상품 계약(Product Contract v1)으로 조립하는 얇은 계층.

        anonymous_diagnosis_results row
            ├── row.full_result   -> Materializer -> paid_result_materials_v1
            ├── row 컬럼           -> diagnosis metadata
            └── row.input_data
                row.full_result.facility_used  -> diagnosis_profile   (v1.1 신규)
                                   => Product Contract v1

    이 모듈은 조립만 한다. R01~R16 을 다시 계산하지 않는다.

SOURCE OF TRUTH
    AUTHORITATIVE TABLE      public.anonymous_diagnosis_results
    LEGAL RESULT SOURCE      row.full_result
    DIAGNOSIS METADATA       row 의 실제 컬럼만 (id / public_token / tier_code /
                             status / created_at / expires_at)
    CUSTOMER PROFILE SOURCE  row.input_data · row.full_result.facility_used 의
                             명시적 저장값만 (STEP3B-A.1)
    full_result 밖의 metadata 로 법적 의무를 만들거나 보충하지 않는다.

DIAGNOSIS PROFILE 의 의미 (STEP3B-A.1 §9 — 경계 고정)
    diagnosis_profile 는 법적 적용 판정이 아니다.
    고객이 진단에 제공했고 저장 결과에 남은 사업장 사실의 표현용 snapshot 이다.

        diagnosis_profile   -> presentation / PDF header / Excel profile
        LEGAL MATERIAL      -> 무변경

    profile 은 Materializer 입력으로 다시 들어가지 않는다.
    profile 값으로 법 적용 여부·의무·판정을 만들거나 보정하지 않는다.

    허용 = 저장된 값의 그대로 운반(trim / null 정규화만)
    금지 = 추정 · 역산 · 합성 · 등급화 라벨 생성
           (86 -> "중규모", 12400 -> "대형", 53 -> "고액 공사" 전부 금지)
           raw input_data 통째 pass-through 도 금지 — 허용목록 밖 key 는 통과 0.

PRESENCE FACT 의 보존 규칙 (STEP4C-2 PKG-0)
    has_excavation · has_hazardous_material 는 facility_used 의 저장값을 그대로 옮긴다.

        SOURCE true     -> True
        SOURCE false    -> False
        SOURCE 키 없음    -> None

    missing -> False 변환 = 금지.
    bool(value) / value or False / default=False / "true" 문자열 생성 = 금지.
    None 과 False 는 다른 사실이다. 전자는 기록되지 않은 것이고 후자는 아니라고
    기록된 것이다. 계약은 이 구분을 소비자에게 그대로 넘긴다.

    고객 화면 표현(해당 / 행 생략 등)은 이 계약의 책임이 아니다.
    tai-www 가 정한다. 이 모듈은 한국어 label 을 만들지 않는다.

NOT INCLUDED, BY DESIGN
    factory_id / company_id / public_token / auth_log_id / payment_ref /
    ci_hash / claimed_user_id
        식별 · trace · 내부 값. 고객 profile 에 넣지 않는다.
    scale / region
        저장돼 있어도 이번 v1.1 에서는 제외한다. 고객 표현 의미와 canonical
        label 이 아직 확정되지 않았고, 임의 해석을 하지 않는다. (STEP3B-A.1 §4)
    business_no / ceo_name
        현행 writer 가 보존하지 않는다. 빈 문자열·추정값으로도 만들지 않는다.

PUBLIC EXPOSURE = 0 (STEP3B-A / STEP3B-A.1)
    이 계약은 아직 어떤 공개 endpoint 에도 실리지 않는다.
    routers/diagnosis_result_web.py 및 GET /diagnosis/paid-result/{public_token} 무변경.
    공개 노출은 ACCESS GATE 가 닫힌 뒤 별도 STEP 에서 다룬다.

PURITY CONTRACT
    DB / HTTP / filesystem / datetime / random / uuid / env / LLM = 0
    입력 row mutation = 0
    같은 row 이면 항상 같은 출력

MEANING BOUNDARIES (STEP3A 조사에서 확정 — 변경 금지)
    LEGAL APPLICABILITY SCOPE = full_result 의 원본 의무 배열 전건
    engine_applicability  = INTERNAL TRACE                    (법 적용 여부 아님)
    check_result          = CHECK / EVIDENCE VALIDATION STATUS (법 적용 여부 아님)
    consumer_status       = EVALUATION USABILITY LABEL         (법 적용 여부 아님)
    usable_for_evaluation = RESULT / EVIDENCE USABILITY        (법 적용 여부 아님)
    -> NOT_APPLICABLE 을 "귀사에 적용되지 않음"으로 번역하지 않는다.
       이 모듈은 어떤 한국어 상태 label 도 만들지 않는다(R06 번역은 별도 Rule Contract).

PUBLIC ENTRYPOINT
    build_paid_result_contract_v1(row: dict) -> dict
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from services.paid_result_materializer import build_paid_result_materials_v1

CONTRACT_VERSION = 1
PROFILE_VERSION = 1

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

# profile 값을 읽어도 되는 두 source. 이 두 곳 밖에서는 읽지 않는다.
PROFILE_SOURCE_INPUT = "input_data"
PROFILE_SOURCE_FACILITY = "facility_used"

# 고객 사업장 사실 whitelist + source 우선순위 (STEP3B-A.1 §2).
#   앞의 source 에 값이 있으면 거기서 멈춘다. deterministic.
#   이 표에 없는 필드는 어떤 경로로도 profile 에 들어가지 않는다.
PROFILE_SOURCE_PRIORITY: Tuple[Tuple[str, Tuple[Tuple[str, str], ...]], ...] = (
    ("company_name", (
        (PROFILE_SOURCE_INPUT, "company_name"),
    )),
    # sector 는 input 값만 쓴다. full_result 쪽 sector 는 어휘가 다르다
    # (input INDUSTRIAL -> full_result MANUFACTURING 로 저장된 row 가 실재).
    # profile 은 "고객이 제공한 사실" 이므로 엔진이 변환한 값으로 대체하지 않는다.
    ("sector", (
        (PROFILE_SOURCE_INPUT, "sector"),
    )),
    ("workers", (
        (PROFILE_SOURCE_INPUT, "workers"),
        (PROFILE_SOURCE_INPUT, "worker_count"),
        (PROFILE_SOURCE_FACILITY, "worker_count"),
    )),
    ("floor_area", (
        (PROFILE_SOURCE_INPUT, "floor_area"),
        (PROFILE_SOURCE_FACILITY, "total_floor_area"),
    )),
    ("contract_amount_eok", (
        (PROFILE_SOURCE_INPUT, "contract_amount_eok"),
    )),
    ("site_kind", (
        (PROFILE_SOURCE_INPUT, "site_kind"),
    )),
    ("construction_type", (
        (PROFILE_SOURCE_FACILITY, "construction_type"),
    )),
    ("building_use_type", (
        (PROFILE_SOURCE_FACILITY, "building_use_type"),
    )),
    # address 는 input 에 실제로 저장된 값이 있을 때만. region 등 다른 값으로
    # 주소를 합성하지 않는다 (STEP3B-A.1 §8).
    ("address", (
        (PROFILE_SOURCE_INPUT, "address"),
    )),
    # --- STEP4C-2 PKG-0 (v1.1 additive transport extension) -------------------
    # presence fact 2개. source 는 facility_used 하나뿐이다.
    #   input_data fallback = 0 · 다른 필드로부터의 추론 = 0
    # 저장값을 그대로 운반한다: true -> True, false -> False, 키 없음 -> None.
    # 현재 저장 데이터에 false 행이 0건이라는 사실은 계약이 false 를 버릴 근거가
    # 아니다. 없는 사실을 만들지 않는 것과 있는 사실을 지우지 않는 것은 같은 규칙이다.
    ("has_excavation", (
        (PROFILE_SOURCE_FACILITY, "has_excavation"),
    )),
    ("has_hazardous_material", (
        (PROFILE_SOURCE_FACILITY, "has_hazardous_material"),
    )),
)

PROFILE_FIELDS: Tuple[str, ...] = tuple(field for field, _ in PROFILE_SOURCE_PRIORITY)

# profile 에 절대 싣지 않는 필드. whitelist 구조상 이미 불가능하지만,
# "무엇을 의도적으로 뺐는가" 를 코드에 고정해 둔다.
PROFILE_EXCLUDED_FIELDS: Tuple[str, ...] = (
    "factory_id",
    "company_id",
    "public_token",
    "auth_log_id",
    "payment_ref",
    "ci_hash",
    "claimed_user_id",
    "scale",
    "region",
)

# 계약에 절대 만들어 넣지 않는 필드(근거 없음 — 현행 writer 미보존).
# company_name / address 는 v1.1 부터 "저장돼 있을 때만" 운반한다. 생성은 여전히 0.
NEVER_INVENTED_FIELDS: Tuple[str, ...] = (
    "business_no",
    "ceo_name",
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


def _stored_value(value: Any) -> Optional[Any]:
    """저장값 정규화. 허용된 것만: trim · 빈 문자열 -> None · scalar 유지.

    · bool 은 그대로 보존한다. True 도 False 도 실제 저장값이다.
      (STEP4C-2 PKG-0) Python 에서 bool 은 int 의 subclass 라 아래 숫자 분기로도
      결과적으로 통과하지만, presence fact 의 false 보존은 계약 규칙이지
      언어 타입 특성에 기대는 우연이 아니다. 그래서 분기를 앞에 명시한다.
      숫자 분기를 먼저 두면 False 가 0 으로 읽힐 여지도 생긴다.
    · 문자열은 trim 하고, 비면 값이 없는 것으로 본다.
    · 숫자는 타입 그대로 보존한다. 0 은 실제 저장값이므로 살린다.
    · dict / list 는 통과시키지 않는다. 허용된 key 라도 구조를 통째로
      내보내지 않기 위한 하드 가드다.
    · 등급·라벨로 바꾸지 않는다. 값의 의미는 손대지 않는다.
    · 키가 없을 때 False 를 만들어 넣지 않는다. 없는 것은 None 이다.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    if isinstance(value, (int, float)):
        return value
    return None


def _profile_sources(row: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """profile 이 읽어도 되는 두 개의 저장 위치만 꺼낸다."""
    stored_input = row.get(PROFILE_SOURCE_INPUT)
    legal_result = row.get("full_result")
    facility = legal_result.get(PROFILE_SOURCE_FACILITY) if isinstance(legal_result, dict) else None
    return {
        PROFILE_SOURCE_INPUT: stored_input if isinstance(stored_input, dict) else {},
        PROFILE_SOURCE_FACILITY: facility if isinstance(facility, dict) else {},
    }


def _diagnosis_profile(row: Dict[str, Any]) -> Dict[str, Any]:
    """저장된 사업장 사실 -> diagnosis_profile (STEP3B-A.1).

    whitelist 밖 key 는 어떤 경로로도 통과하지 않는다. 값이 없으면 None 이며
    대체 문구·추정값을 만들지 않는다. 필드 key 는 값이 없어도 항상 출력한다
    (diagnosis metadata 와 같은 style — shape 고정).
    """
    sources = _profile_sources(row)

    profile: Dict[str, Any] = {"profile_version": PROFILE_VERSION}
    available_facts: List[str] = []

    for field, priority in PROFILE_SOURCE_PRIORITY:
        value = None
        for source_name, stored_key in priority:
            candidate = _stored_value(sources[source_name].get(stored_key))
            if candidate is not None:
                value = candidate
                break
        profile[field] = value
        # 판정 기준은 "값이 있었는가" 이지 "참인가" 가 아니다.
        # False 와 0 은 저장된 값이므로 available_facts 에 들어간다.
        # truthiness 로 바꾸면 저장된 사실이 사라진다.
        if value is not None:
            available_facts.append(field)

    # 선언 순서 그대로 — 같은 row 이면 항상 같은 목록.
    profile["available_facts"] = available_facts
    return profile


def build_paid_result_contract_v1(row: Any) -> Dict[str, Any]:
    """저장된 anonymous_diagnosis_results row -> Product Contract v1.

    PURE FUNCTION. 입력 row 를 변경하지 않으며, 같은 row 이면 항상 같은 출력을 낸다.

    조립만 한다:
      · paid_result_materials_v1 = build_paid_result_materials_v1(row["full_result"])
      · diagnosis                = row 컬럼 6개
      · diagnosis_profile        = 저장된 사업장 사실 whitelist 11개
                                   (STEP3B-A.1 9개 + STEP4C-2 PKG-0 presence 2개)
    파생 계산(COUNT / GROUP / DISTINCT / timing / portfolio / coverage 등)은
    전부 STEP3A Materializer 의 책임이며 이 모듈에서 다시 구현하지 않는다.
    diagnosis_profile 은 Materializer 입력으로 들어가지 않으며 법적 재료를 바꾸지 않는다.
    """
    src = copy.deepcopy(row) if isinstance(row, dict) else {}

    return {
        "contract_version": CONTRACT_VERSION,
        "diagnosis": _diagnosis_metadata(src),
        "diagnosis_profile": _diagnosis_profile(src),
        # material_version 을 포함한 Materializer 출력을 그대로 싣는다. 덮어쓰지 않는다.
        "paid_result_materials_v1": build_paid_result_materials_v1(src.get("full_result")),
    }


__all__ = ["build_paid_result_contract_v1"]
