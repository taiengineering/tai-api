"""WP-B PR-API · payment_success_email onboarding CTA 정정.

WO-SAFE-COMPANY-ACCESS-001. 결제 완료 후 사용자가 "다음 단계"를 알 수 있도록
Email CTA 를 Safe 직접링크(https://safe.taieng.co.kr) 에서
onboarding handoff surface (https://taieng.co.kr/mypage/onboarding) 로 교체한다.

이 파일은 :
  B1  CTA URL = onboarding · plaintext password/token 부재 · 안내블록 존재 · 발송 shape 유지
  B5  WP-A 무회귀 : company_users/auth/bootstrap import + 정책 무변동 grep
  B6  메일 실패 → payment_post_process 예외 흡수 (rollback 유발 0)
을 검증한다. 운영 SMTP/네트워크 불사용.
"""
from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from utils import email_sender as es


ONBOARDING_URL = "https://taieng.co.kr/mypage/onboarding"
SAFE_URL = "https://safe.taieng.co.kr"


def _render():
    """대표 payload 로 subject·html·text 3-tuple 생성."""
    return es.payment_success_email(
        user_name="홍길동",
        company_name="테스트건설",
        plan_code="INDUSTRY_STARTER",
        total_amount=163900,
        sector_kr="산업",
    )


# ── B1 · CTA URL / 안내블록 / 시크릿 부재 / 발송 shape ─────────────
def test_B1_html_cta_href_points_to_onboarding_not_safe_direct():
    """HTML CTA 앵커의 href 가 onboarding 이어야 하고 safe 직접링크는 CTA 로 노출 0."""
    subject, html, text = _render()
    # CTA 앵커 href 정확 매치
    m = re.search(r'<a\s+href="([^"]+)"[^>]*>\s*TAI Safe 시작하기\s*</a>', html)
    assert m is not None, "'TAI Safe 시작하기' CTA 앵커를 찾지 못했다"
    assert m.group(1) == ONBOARDING_URL, (
        f"CTA href 는 {ONBOARDING_URL} 이어야 한다 (현재: {m.group(1)})"
    )
    # safe 직접링크가 활성 CTA(<a href=...>) 로 다시 등장하면 실패
    assert f'href="{SAFE_URL}"' not in html, "safe 직접링크 CTA 가 재도입되었다"


def test_B1_text_body_uses_onboarding_url_not_safe():
    """text 버전 URL 도 onboarding 이어야 한다."""
    _, _, text = _render()
    assert ONBOARDING_URL in text, "text 본문에 onboarding URL 부재"
    assert SAFE_URL not in text, "text 본문에 safe 직접링크가 남아있다"


def test_B1_guidance_block_present():
    """안내블록(회사·사업장 확인 후 시작) 이 HTML/text 양쪽에 존재."""
    _, html, text = _render()
    key = "회사와 사업장 정보를 확인한 후 TAI Safe를 시작할 수 있습니다"
    assert key in html, f"HTML 에 안내블록 '{key}' 부재"
    assert key in text, f"text 에 안내블록 '{key}' 부재"


def test_B1_no_plaintext_password_or_token_leak():
    """평문 비번·access/refresh token·invite raw token 은 절대 노출 0."""
    subject, html, text = _render()
    forbidden = [
        "password", "PASSWORD", "비밀번호",
        "access_token", "refresh_token", "bearer ", "Bearer ",
        "invite_token", "raw_token",
    ]
    for token in forbidden:
        assert token not in subject, f"subject 에 금지 토큰 '{token}' 노출"
        assert token not in html, f"HTML 에 금지 토큰 '{token}' 노출"
        assert token not in text, f"text 에 금지 토큰 '{token}' 노출"


def test_B1_email_return_shape_and_subject_unchanged():
    """반환 shape (subject, html, text) 3-tuple · subject 문자열 유지."""
    result = _render()
    assert isinstance(result, tuple) and len(result) == 3
    subject, html, text = result
    assert isinstance(subject, str) and subject == "[TAI Safe] 결제가 완료되었습니다"
    assert isinstance(html, str) and "<a href=" in html
    assert isinstance(text, str) and text


def test_B1_send_email_signature_untouched():
    """send_email 시그니처·환경변수 기반 정책 무변동 (호출부 계약 유지)."""
    import inspect
    sig = inspect.signature(es.send_email)
    params = list(sig.parameters.keys())
    assert params[:4] == ["to", "subject", "body_html", "body_text"], (
        f"send_email 시그니처 변경 감지: {params}"
    )
    src = inspect.getsource(es.send_email)
    assert "GMAIL_USER" in src and "GMAIL_APP_PASS" in src, "Gmail SMTP env 정책 이탈"
    # SMTP host 는 모듈 상수 (SMTP_HOST) 로 정의되어 있어야 한다
    assert getattr(es, "SMTP_HOST", "") == "smtp.gmail.com", "SMTP host 정책 이탈"
    assert getattr(es, "SMTP_PORT", 0) == 587, "SMTP port 정책 이탈"


# ── B5 · WP-A 무회귀 grep (import · 정책 문자열 무변동) ────────────
def test_B5_wpa_company_users_router_symbols_present():
    """WP-A `/me/company/access` · user-invites 심볼이 여전히 import 가능해야 한다."""
    import inspect
    import routers.company_users as cu
    src = inspect.getsource(cu)
    assert "/me/company/access" in src, "WP-A `/me/company/access` 심볼 상실"
    assert "/me/company/users" in src, "WP-A `/me/company/users` 심볼 상실"
    assert "/me/company/user-invites" in src, "WP-A user-invites 심볼 상실"
    assert "_entitlement_snapshot" in src, "WP-A entitlement snapshot 심볼 상실"


def test_B5_wpa_bootstrap_intact():
    """WP-A buyer bootstrap 3-case 정책 심볼 유지."""
    from services import payment_post_process as pp
    assert callable(pp._bootstrap_buyer_company_admin), "bootstrap 함수 상실"
    assert callable(pp._is_saas_payment), "SaaS 판정 함수 상실"
    assert callable(pp.on_payment_success_sync), "on_payment_success_sync 상실"
    import inspect
    src = inspect.getsource(pp._bootstrap_buyer_company_admin)
    # Case A / B / C 판정 근거 문자열
    assert "010" in src or "011" in src, "capability role 심볼 부재"
    assert "002" in src, "Company Admin fallback role 부재"


def test_B5_auth_current_user_active_gate_intact():
    """WP-A account status gate (is_active) 무변동."""
    import inspect
    from routers import auth as au
    src = inspect.getsource(au)
    assert "_require_active_account" in src or "is_active" in src, (
        "auth active gate 심볼 상실"
    )


# ── B6 · 메일 실패는 payment/bootstrap rollback 유발 0 ─────────────
def test_B6_email_send_exception_swallowed_in_notification(monkeypatch):
    """send_email 이 예외를 던져도 send_payment_notification 은 예외를 밖으로 흘리지 않는다.
    (기존 정책 유지 확인 — WP-B 로 인해 변경되지 않음)."""
    import services.payment_post_process as ppp

    class _R:
        def __init__(self, data): self.data = data

    class _Q:
        def __init__(self, table, store):
            self.table = table; self.store = store
            self._filters = []
        def select(self, *a, **k): return self
        def eq(self, *a, **k): self._filters.append(a); return self
        def limit(self, *a, **k): return self
        def insert(self, row):
            self._ins = row; return self
        def execute(self):
            if getattr(self, "_ins", None) is not None:
                return _R([self._ins])
            if self.table == "users":
                return _R([{"name": "홍길동", "phone": "010-0000-0000", "email": "user@example.com"}])
            if self.table == "companies":
                return _R([{"name": "테스트건설"}])
            return _R([])

    class _SB:
        def __init__(self): self.store = {}
        def table(self, name): return _Q(name, self.store)

    monkeypatch.setattr(ppp, "get_supabase", lambda: _SB())
    # send_email 강제 예외
    from utils import email_sender as es_mod
    monkeypatch.setattr(es_mod, "send_email", lambda **kw: (_ for _ in ()).throw(RuntimeError("SMTP down")))
    # SMS · Slack · 인앱 부수효과 무력화 (본 테스트는 email 실패 격리 확인만)
    monkeypatch.setattr("services.notification_engine.runtime_compat.compat_send_sms",
                        lambda *a, **k: None, raising=False)

    pay = {"id": "P-B6", "company_id": "C-B6", "user_id": "U-B6", "total_amount": 100}
    plan_info = {"sector": "INDUSTRIAL"}
    # 예외가 밖으로 새어나오지 않아야 rollback 유발 0
    ppp.send_payment_notification(pay, "INDUSTRY_STARTER", plan_info)


def test_B6_source_policy_email_failure_logged_not_raised():
    """source grep : email 블록이 try/except 로 감싸져 있고 logger.error 로만 기록."""
    import inspect
    import services.payment_post_process as ppp
    src = inspect.getsource(ppp.send_payment_notification)
    # payment_success_email import + send_email 호출부가 try 블록 안에 있어야 함
    assert "payment_success_email" in src
    assert "send_email" in src
    assert "Email send failed" in src, "email 실패 로깅 심볼 상실"
    # raise 로 상위 흐름을 깨는 코드가 email 블록에 도입되지 않았어야 함
    email_block_idx = src.index("from utils.email_sender import send_email")
    tail = src[email_block_idx:email_block_idx + 500]
    assert "raise" not in tail, "email 블록에 raise 도입 감지 (rollback 유발 가능)"
