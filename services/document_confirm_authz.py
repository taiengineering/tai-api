"""
WP-DOCUMENT-ARCH-05B-B0A / -B1-CORR-01 — Document confirm authorization policy (순수 정책).

목적: confirm(APPROVED_BY_HUMAN) 요청이 인가되는지 판정하는 **순수 함수**.
      DB·네트워크·라우터를 건드리지 않는다. 조회 결과(current_user, document,
      factory→company 매핑)는 호출자(B1 라우터/서비스)가 주입한다.

배경 (B0 조사 확정):
  현재 confirm 진입점은 body.actor_id 를 그대로 신뢰한다(schemas StatusChangeIn.actor_id).
  인증 컨텍스트가 없어 누구든 임의 actor_id 로 승인·봉인할 수 있었다.
  이 모듈은 그 구멍을 닫는 정책을 코드로 고정한다.

정책 정본 (B1-CORR-01, 운영자 확정 — 기존 role allowlist 폐기):
  Confirm 권한 = role 이 아니라 **제출자 identity**.
    authenticated current_user.id == runtime_document_data.submitted_by → Confirm 가능.
  role_code(001/011/012/013/014 …)는 Confirm 판정 기준이 아니다.
  body.actor_id 는 SoT 아님. 오면 current_user.id 와 일치해야 한다(불일치 → 403 사칭).
  ownership consistency 는 유지: 제출자 identity 만 맞아도 corrupted ownership 문서는
    봉인하지 않는다(소유 판정 불능/충돌 → 404 존재 은닉).
  실제 authenticated user 의 company/factory scope 값으로 소유 일치를 직접 확인한다
    (role tier ALL/COMPANY/FACTORY 로 승인자를 선정하지 않는다).
  판정 불능(정보 부족)은 전부 DENY(FAIL-CLOSED).

이 모듈은 '누가 승인 가능한가'만 판정한다. 상태 전이 규칙(REVIEW_PENDING→...),
lock, hash, archive INSERT 는 05B-B1 트랜잭션의 몫이며 여기서 다루지 않는다.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = [
    "ConfirmAuthResult",
    "authorize_confirm",
]


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
    actor_id: Any = None,
    factory_company_id: Any = None,
) -> "ConfirmAuthResult":
    """confirm 인가 판정 (순수). Confirm 권한 = 제출자 본인.

    인자:
      current_user       get_current_user 결과 dict (없으면 미인증). id/company_id/
                         factory_id 를 읽는다. role_code 는 판정에 쓰지 않는다.
      document           대상 runtime_document_data dict. id/submitted_by/
                         company_id/factory_id.
      actor_id           클라이언트가 보낸 body.actor_id (신뢰하지 않음, 대조만).
      factory_company_id document.factory_id 로 조회한 factories.company_id (선택).

    반환: ConfirmAuthResult. 허용 시 confirmed_by = current_user.id.

    실패 매핑:
      401 인증 없음/불완전
      403 actor_id 사칭 · 제출자 아님 · user scope 부족(같은 회사 내)
      404 문서 없음 · cross-company(존재 은닉) · 소유 회사 판정 불능 · factory mismatch
      409 submitted_by NULL (REVIEW_PENDING lifecycle 무결성 위반)
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

    # ── 4. 제출자 무결성 + 제출자 == 인증 사용자 ──────────────────────────
    # REVIEW_PENDING 인데 submitted_by 가 없으면 정상 lifecycle 문서가 아니다 → 409.
    submitted_by = _norm_id(document.get("submitted_by"))
    if submitted_by is None:
        return _deny(409, "REVIEW_PENDING state integrity conflict: submitted_by is null")
    # Confirm 권한의 유일한 기준: 제출한 본인만 확정한다.
    if submitted_by != user_id:
        return _deny(403, "confirm is permitted only to the submitter")

    # ── 5. ownership consistency (제출자 맞아도 corrupted ownership 봉인 금지) ─
    user_company = _norm_id(current_user.get("company_id"))
    user_factory = _norm_id(current_user.get("factory_id"))
    doc_company = _norm_id(document.get("company_id"))
    doc_factory = _norm_id(document.get("factory_id"))
    factory_company = _norm_id(factory_company_id)

    # doc 이 factory 를 가리키면 그 factory 의 소유 회사가 반드시 도출되어야 하고,
    # doc.company_id 와도 어긋나면 안 된다. 어긋난 metadata → FAIL-CLOSED(존재 은닉 404).
    if doc_factory is not None:
        if factory_company is None:
            return _deny(404, "document ownership cannot be resolved")
        if doc_company is not None and doc_company != factory_company:
            return _deny(404, "document ownership cannot be resolved")

    resolved_doc_company = doc_company or factory_company

    # 소유주 자체를 특정할 수 없는 문서는 봉인하지 않는다(FAIL-CLOSED). 존재 은닉 404.
    if resolved_doc_company is None:
        return _deny(404, "document ownership cannot be resolved")

    # ── 6. authenticated user 의 실제 company/factory scope 로 소유 일치 확인 ──
    # role tier 가 아니라 사용자의 실제 소속 값을 직접 사용한다.
    # Company: 사용자 회사가 없으면 fail-closed 403, 다른 회사면 존재 은닉 404.
    if not user_company:
        return _deny(403, "user has no company scope")
    if resolved_doc_company != user_company:
        return _deny(404, "document not found")

    # Factory: 문서가 factory-level 이면 사용자 factory 가 일치해야 한다.
    # 문서가 company-level(factory_id=None)이면 회사 일치만으로 진행.
    if doc_factory is not None:
        if not user_factory:
            return _deny(403, "user has no factory scope")
        if user_factory != doc_factory:
            return _deny(404, "document not found")

    # ── 7. ALLOW — 제출자 본인 + ownership 일치 ───────────────────────────
    return ConfirmAuthResult(True, confirmed_by=user_id)
