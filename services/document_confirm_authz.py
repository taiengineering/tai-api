"""
WP-DOCUMENT-ARCH-05B-B0A — Document confirm authorization policy (순수 정책).

목적: confirm(APPROVED_BY_HUMAN) 요청이 인가되는지 판정하는 **순수 함수**.
      DB·네트워크·라우터를 건드리지 않는다. 조회 결과(current_user, document,
      role_scope, factory→company 매핑)는 호출자(B1 라우터/서비스)가 주입한다.

배경 (B0 조사 확정):
  현재 confirm 진입점은 body.actor_id 를 그대로 신뢰한다(schemas StatusChangeIn.actor_id).
  인증 컨텍스트가 없어 누구든 임의 actor_id 로 승인·봉인할 수 있었다.
  이 모듈은 그 구멍을 닫는 정책을 코드로 고정한다.

계약 (운영자 확정):
  APPROVE 주체 SoT = 인증된 current_user (body.actor_id 아님)
  body.actor_id 가 오면 current_user.id 와 일치해야 한다. 불일치 → DENY(사칭)
  DB 에 승인 전용 permission(DOCUMENT_APPROVE)이 없으므로,
    권한은 role 기반으로 API 에서 fail-closed 판정한다(신규 DB permission 추가 안 함).
  data scope 는 기존 role_data_scope 규칙을 재사용한다(신규 authz framework 금지).
    미정의/미지정 scope = 가장 좁게(deny). PLATFORM 을 ALL 로 자동 확장하지 않는다.
  cross-company 는 존재를 숨기기 위해 404 로 처리한다(기존 leader_scope 관례).
  판정 불능(정보 부족)은 전부 DENY(FAIL-CLOSED).

이 모듈은 '누가 승인 가능한가'만 판정한다. 상태 전이 규칙(REVIEW_PENDING→...),
lock, hash, archive INSERT 는 05B-B1 트랜잭션의 몫이며 여기서 다루지 않는다.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = [
    "APPROVE_ROLE_CODES",
    "WIDE_SCOPES",
    "ConfirmAuthResult",
    "authorize_confirm",
]

# ── 승인 가능 role (운영자 확정 시 이 집합만 바꾼다) ────────────────────────
# DB permission 을 신설하지 않고 API 에서 fail-closed 로 판정하기 위한 allowlist.
# 여기에 없는 role 은 confirm 불가. 이름이 아니라 이 코드 집합이 SoT 다.
# (역할 배정은 운영자 결정 사항 — 아래는 가장 방어적인 시작점)
APPROVE_ROLE_CODES = frozenset({
    "001",  # 최고관리자 (data_scope ALL)
    "011",  # 안전보건관리책임자 (data_scope COMPANY)
})

# 팀 경계를 넘어 볼 수 있는 등급. leader_scope.py 와 동일 정의.
WIDE_SCOPES = ("ALL", "COMPANY", "FACTORY")


class ConfirmAuthResult:
    """인가 판정 결과. allowed=False 면 http_status/reason 으로 거부 사유를 전한다."""

    __slots__ = ("allowed", "http_status", "reason", "confirmed_by")

    def __init__(
        self,
        allowed: bool,
        http_status: Optional[int] = None,
        reason: str = "",
        confirmed_by: Optional[str] = None,
    ):
        self.allowed = allowed
        self.http_status = http_status
        self.reason = reason
        # 봉인에 쓸 확정자 id. 항상 인증 사용자에서 온다(허용된 경우에만 채운다).
        self.confirmed_by = confirmed_by

    def __repr__(self) -> str:  # 디버깅용
        if self.allowed:
            return "ConfirmAuthResult(ALLOW confirmed_by=%s)" % self.confirmed_by
        return "ConfirmAuthResult(DENY %s %s)" % (self.http_status, self.reason)


def _deny(http_status: int, reason: str) -> "ConfirmAuthResult":
    return ConfirmAuthResult(False, http_status=http_status, reason=reason)


def _norm_id(value: Any) -> Optional[str]:
    """식별자를 문자열로 정규화. None/빈문자 → None."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def authorize_confirm(
    *,
    current_user: Optional[Dict[str, Any]],
    document: Optional[Dict[str, Any]],
    role_scope: Optional[str],
    actor_id: Any = None,
    factory_company_id: Any = None,
) -> "ConfirmAuthResult":
    """confirm 인가 판정 (순수).

    인자:
      current_user       get_current_user 결과 dict (없으면 미인증). id/role_code/
                         company_id/factory_id 를 읽는다.
      document           대상 runtime_document_data dict. id/company_id/factory_id.
      role_scope         current_user.role_code 의 role_data_scope.scope_type.
                         호출자가 조회해 주입한다(미정의면 None → 가장 좁게 취급).
      actor_id           클라이언트가 보낸 body.actor_id (신뢰하지 않음, 대조만).
      factory_company_id document.factory_id 로 조회한 factories.company_id (선택).
                         document.company_id 가 없을 때 소유 회사 판정에 쓴다.

    반환: ConfirmAuthResult. 허용 시 confirmed_by = current_user.id.

    실패 매핑:
      401 인증 없음/불완전
      403 actor_id 사칭 · 권한(role) 없음 · scope 부족(같은 회사 내)
      404 문서 없음 · cross-company(존재 은닉) · 소유 회사 판정 불능
    """
    # ── 1. 인증 ────────────────────────────────────────────────────────────
    if not isinstance(current_user, dict):
        return _deny(401, "authentication required")
    user_id = _norm_id(current_user.get("id"))
    if not user_id:
        return _deny(401, "authenticated user has no id")

    # ── 2. actor_id 사칭 차단 (SoT = 인증 사용자) ─────────────────────────
    supplied_actor = _norm_id(actor_id)
    if supplied_actor is not None and supplied_actor != user_id:
        # 존재 은닉이 아니라 명시적 사칭이므로 403.
        return _deny(403, "actor_id does not match authenticated user")

    # ── 3. 문서 존재 ──────────────────────────────────────────────────────
    if not isinstance(document, dict):
        return _deny(404, "document not found")
    if not _norm_id(document.get("id")):
        return _deny(404, "document not found")

    # ── 4. 권한(role) — DB permission 부재 → role allowlist fail-closed ────
    role_code = _norm_id(current_user.get("role_code"))
    if role_code not in APPROVE_ROLE_CODES:
        return _deny(403, "role is not permitted to approve documents")

    # ── 5. data scope — 기존 role_data_scope 규칙 재사용 ──────────────────
    # 미정의/미지정 scope 는 가장 좁게(deny). PLATFORM 을 ALL 로 확장하지 않는다.
    scope = _norm_id(role_scope)
    user_company = _norm_id(current_user.get("company_id"))
    user_factory = _norm_id(current_user.get("factory_id"))
    doc_company = _norm_id(document.get("company_id"))
    doc_factory = _norm_id(document.get("factory_id"))
    factory_company = _norm_id(factory_company_id)

    # ── 5a. ownership consistency (scope 판정보다 먼저, ALL 에도 적용) ─────
    # doc 이 factory 를 가리키면 그 factory 의 소유 회사가 반드시 도출되어야 하고,
    # doc.company_id 와도 어긋나면 안 된다. 어긋난 metadata 를 001(ALL)이라도
    # 봉인해서는 안 되므로 여기서 FAIL-CLOSED(존재 은닉 404).
    if doc_factory is not None:
        if factory_company is None:
            return _deny(404, "document ownership cannot be resolved")
        if doc_company is not None and doc_company != factory_company:
            return _deny(404, "document ownership cannot be resolved")

    resolved_doc_company = doc_company or factory_company

    # 소유주 자체를 특정할 수 없는 문서는 어떤 scope 로도 봉인하지 않는다.
    # ALL 은 '다른 회사 문서까지' 승인 가능하다는 뜻이지, '소유주 없는 문서'
    # 승인 가능이 아니다(B0 확정: 소유 판정 불능 → FAIL-CLOSED). 존재 은닉 404.
    if resolved_doc_company is None:
        return _deny(404, "document ownership cannot be resolved")

    if scope == "ALL":
        # 플랫폼 최고관리자 등. 회사 경계를 넘는다. (consistency + ownership 도출 통과 후)
        return ConfirmAuthResult(True, confirmed_by=user_id)

    if scope == "COMPANY":
        if not user_company:
            return _deny(403, "user has no company scope")
        if resolved_doc_company != user_company:
            # cross-company: 존재 자체를 숨긴다.
            return _deny(404, "document not found")
        return ConfirmAuthResult(True, confirmed_by=user_id)

    if scope == "FACTORY":
        # 완전 fail-closed 순서: 회사 확인 → 시설 확인. 어느 정보든 없으면 거부.
        if not user_company:
            return _deny(403, "user has no company scope")
        if resolved_doc_company != user_company:
            # cross-company: 존재 은닉.
            return _deny(404, "document not found")
        if not user_factory:
            return _deny(403, "user has no factory scope")
        if doc_factory is None:
            return _deny(404, "document ownership cannot be resolved")
        if doc_factory != user_factory:
            # 같은 회사의 다른 시설 — company_scope 관례에 맞춰 존재 은닉 404.
            return _deny(404, "document not found")
        return ConfirmAuthResult(True, confirmed_by=user_id)

    # TEAM/ASSIGNED/PLATFORM/None/기타 = confirm 권한 대상 아님 → FAIL-CLOSED.
    return _deny(403, "role scope is not permitted to approve documents")
