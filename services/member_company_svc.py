"""회원 회사정보 orchestration (BACKEND-1) — /me/company.

SoT = public.companies (신규 invoice-company master 생성 금지).
- ownership 은 100%% 토큰(current_user)에서 결정. client company_id/user_id 신뢰 금지.
- company-less 회원: company INSERT -> users.company_id conditional bind (+ race/compensation).
- 기존 같은 사업자번호 자동 소유권 연결 금지(회사 탈취 방지) -> 409.
- payments / tax_invoice_requests 등 세무 객체는 절대 건드리지 않는다(이 서비스에서 미참조).

supabase client 는 호출측이 주입한다(테스트 가능성 + 단위테스트 격리).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from services.time import now_kst, serialize_external_utc

# 수정 허용 법적/청구 필드(companies 재사용). 그 외(운영/권한/코드) 필드는 금지.
EDITABLE_FIELDS = (
    "name",
    "business_number",
    "representative_name",
    "contact_email",
    "contact_phone",
    "zipcode",
    "address_road",
    "address_detail",
    "business_type",
    "business_category",
)
# GET/응답에 싣는 법적 필드(+ id)
VIEW_FIELDS = ("id",) + EDITABLE_FIELDS


class MemberCompanyError(Exception):
    """회사정보 orchestration 비즈니스 오류(라우터에서 HTTPException 변환)."""

    def __init__(self, status_code: int, code: str, detail: str):
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _now_iso() -> str:
    return serialize_external_utc(now_kst())


def normalize_business_number(raw: Optional[str]) -> Optional[str]:
    """하이픈/공백 허용 -> 숫자만 추출. 값이 있으면 10자리 아니면 400. 없으면 None."""
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if digits == "":
        return None
    if len(digits) != 10:
        raise MemberCompanyError(400, "INVALID_BUSINESS_NUMBER", "사업자등록번호는 숫자 10자리여야 합니다.")
    return digits


def _bn_variants(digits: str) -> List[str]:
    """중복 검사용 표현: 숫자-only + 표준 하이픈(3-2-5). 운영 혼재 포맷 대응."""
    hy = "{}-{}-{}".format(digits[0:3], digits[3:5], digits[5:10])
    return [digits, hy]


def _is_business_number_unique_violation(e: Exception) -> bool:
    """companies.business_number UNIQUE 위반만 True. bare 23505 는 False.

    companies 에는 UNIQUE 가 2개(companies_business_number_unique, companies_company_code_unique)
    이므로 code==23505 만으로는 사업자번호 중복을 확정할 수 없다.
    constraint name 또는 business_number 식별이 있어야 한다('duplicate' 문자열 단독 금지).
    """
    parts = [
        str(getattr(e, "code", "") or ""),
        str(getattr(e, "message", "") or ""),
        str(getattr(e, "details", "") or ""),
        str(getattr(e, "hint", "") or ""),
        str(e),
    ]
    text = " ".join(parts)
    if "companies_business_number_unique" in text:
        return True
    if str(getattr(e, "code", "") or "") == "23505" and "business_number" in text:
        return True
    return False


def _clean(payload: Dict[str, Any]) -> Dict[str, Any]:
    """허용 필드(business_number 제외)만 추려 저장용으로 정리(strip)."""
    row: Dict[str, Any] = {}
    for f in EDITABLE_FIELDS:
        if f == "business_number":
            continue
        if f in payload and payload[f] is not None:
            v = payload[f]
            row[f] = v.strip() if isinstance(v, str) else v
    return row


def _select_view(sb, company_id: str) -> Optional[Dict[str, Any]]:
    res = sb.table("companies").select(", ".join(VIEW_FIELDS)).eq("id", company_id).limit(1).execute()
    data = res.data or []
    return data[0] if data else None


def _bn_conflict(sb, bn_digits: str, *, exclude_company_id: Optional[str]) -> bool:
    """동일 사업자번호(숫자/하이픈 변형)가 다른 회사에 존재하면 True."""
    res = sb.table("companies").select("id").in_("business_number", _bn_variants(bn_digits)).execute()
    for r in (res.data or []):
        if exclude_company_id and str(r.get("id")) == str(exclude_company_id):
            continue
        return True
    return False


def get_member_company(sb, current_user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """토큰의 company_id 로 자기 회사 조회. 없으면 None(정상)."""
    company_id = current_user.get("company_id")
    if not company_id:
        return None
    return _select_view(sb, company_id)


def _update_existing(sb, company_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = _clean(payload)
    if "business_number" in payload:
        bn = normalize_business_number(payload.get("business_number"))
        if bn and _bn_conflict(sb, bn, exclude_company_id=company_id):
            raise MemberCompanyError(409, "BUSINESS_NUMBER_ALREADY_EXISTS", "이미 등록된 사업자등록번호입니다.")
        row["business_number"] = bn  # None -> 값 지움(명시된 경우만)
    if not row:
        cur = _select_view(sb, company_id)
        if not cur:
            raise MemberCompanyError(404, "COMPANY_NOT_FOUND", "회사를 찾을 수 없습니다.")
        return cur
    row["updated_at"] = _now_iso()
    sb.table("companies").update(row).eq("id", company_id).execute()
    cur = _select_view(sb, company_id)
    if not cur:
        raise MemberCompanyError(404, "COMPANY_NOT_FOUND", "회사를 찾을 수 없습니다.")
    return cur


def _compensate_delete(sb, company_id: str, *, reason: str) -> None:
    try:
        sb.table("companies").delete().eq("id", company_id).execute()
    except Exception as e:  # noqa: BLE001
        raise MemberCompanyError(
            500, "COMPANY_BIND_COMPENSATION_FAILED",
            "회사 생성 보상처리에 실패했습니다({}): {}".format(reason, e),
        ) from e


def _user_company_id(sb, user_id: str) -> Optional[str]:
    ures = sb.table("users").select("id, company_id").eq("id", user_id).limit(1).execute()
    data = ures.data or []
    if not data:
        return None
    return data[0].get("company_id")


def _create_and_bind(sb, current_user: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    user_id = current_user.get("id")
    if not user_id:
        raise MemberCompanyError(401, "UNAUTHENTICATED", "사용자 식별에 실패했습니다.")

    name = (payload.get("name") or "").strip()
    if not name:
        raise MemberCompanyError(400, "COMPANY_NAME_REQUIRED", "회사명은 필수입니다.")

    bn = normalize_business_number(payload.get("business_number")) if "business_number" in payload else None
    if bn and _bn_conflict(sb, bn, exclude_company_id=None):
        raise MemberCompanyError(
            409, "BUSINESS_NUMBER_ALREADY_EXISTS",
            "이미 등록된 사업자등록번호입니다. 기존 회사 관리자 연결이 필요합니다.",
        )

    # 1) race 재확인: 이미 bind 됐으면 CREATE 안 하고 기존 경로.
    existing_cid = _user_company_id(sb, user_id)
    if existing_cid:
        return _update_existing(sb, existing_cid, payload)

    # 2) company INSERT
    row = _clean(payload)
    row["name"] = name
    if "business_number" in payload:
        row["business_number"] = bn
    row["created_by"] = user_id
    row["created_at"] = _now_iso()
    row["updated_at"] = _now_iso()
    try:
        ins = sb.table("companies").insert(row).execute()
    except Exception as e:
        # 예외를 먼저 분류하지 않고 user 재조회 — concurrent 가 이미 bind 했으면 winner 반환.
        cid2 = _user_company_id(sb, user_id)
        if cid2:
            # loser payload 로 winner 를 수정하지 않는다(조회만).
            return _select_view(sb, cid2)
        # 실제 business_number UNIQUE(companies_business_number_unique / 23505+business_number) 만 409.
        if _is_business_number_unique_violation(e):
            raise MemberCompanyError(
                409, "BUSINESS_NUMBER_ALREADY_EXISTS",
                "이미 등록된 사업자등록번호입니다. 기존 회사 관리자 연결이 필요합니다.",
            ) from e
        # 그 외 모든 INSERT 오류는 500(409 위장 금지). bare 23505(company_code 등) 포함.
        raise MemberCompanyError(500, "COMPANY_CREATE_FAILED", "회사 생성에 실패했습니다.") from e
    if not ins.data:
        raise MemberCompanyError(500, "COMPANY_CREATE_FAILED", "회사 생성에 실패했습니다.")
    new_company_id = ins.data[0]["id"]

    # 3) conditional bind: company_id IS NULL 인 경우에만 연결
    try:
        bind = (
            sb.table("users")
            .update({"company_id": new_company_id, "updated_at": _now_iso()})
            .eq("id", user_id)
            .is_("company_id", "null")
            .execute()
        )
    except Exception as e:  # bind 자체 오류 -> 방금 만든 회사 보상삭제 후 원오류
        _compensate_delete(sb, new_company_id, reason="bind_error")
        raise MemberCompanyError(500, "COMPANY_BIND_FAILED", "회사 연결에 실패했습니다.") from e

    if not bind.data:
        # race loser: 다른 요청이 먼저 bind -> 방금 만든 회사 보상삭제 + winner 반환
        _compensate_delete(sb, new_company_id, reason="bind_race_loser")
        winner = _user_company_id(sb, user_id)
        if winner:
            return _select_view(sb, winner)
        raise MemberCompanyError(409, "COMPANY_BIND_CONFLICT", "회사 연결 처리 중 충돌이 발생했습니다. 다시 시도해주세요.")

    return _select_view(sb, new_company_id)


def upsert_member_company(sb, current_user: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """자기 회사 있으면 update, 없으면 create+bind. company_id 는 토큰에서만."""
    company_id = current_user.get("company_id")
    if company_id:
        return _update_existing(sb, company_id, payload)
    return _create_and_bind(sb, current_user, payload)
