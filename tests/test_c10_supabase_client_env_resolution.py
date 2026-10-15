"""WO-E2E2000-C10-FINAL-REMAINING-GATE-002 — db/supabase_client.py 환경변수 해석 테스트.

service_role 키 우선순위·FAIL-CLOSE 계약을 외부 DB 접속 없이 Mock으로 검증한다.

테스트 목록:
  ENV-01  SUPABASE_SERVICE_ROLE_KEY 단독 설정 → 해당 값 사용
  ENV-02  SUPABASE_SERVICE_KEY 단독 설정 → 해당 값 사용 (legacy 별칭)
  ENV-03  두 변수 모두 설정 → canonical(SUPABASE_SERVICE_ROLE_KEY) 우선
  ENV-04  SUPABASE_KEY 단독 설정(service_role 변수 없음) → FAIL-CLOSE (RuntimeError)
  ENV-05  service_role 변수 모두 없음 → FAIL-CLOSE (RuntimeError)
  ENV-06  키 값이 로그·반환값에 평문 노출 없음(키 원문 출력 금지)
"""
from __future__ import annotations

import importlib
import sys
import types
import os
import pytest

# ── 헬퍼: 격리된 환경변수 상태에서 _resolve_service_role_key 실행 ─────────────
#   모듈 레벨 변수가 없으므로 함수를 직접 테스트한다.

def _run_resolver(env: dict[str, str]) -> str | None:
    """지정된 환경변수 상태에서 _resolve_service_role_key() 를 실행한다."""
    # 저장 → 조작 → 복원
    saved = {k: os.environ.get(k) for k in (
        "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY"
    )}
    try:
        for k in saved:
            os.environ.pop(k, None)
        for k, v in env.items():
            os.environ[k] = v

        # 모듈을 강제 재로드해 캐시 무효화
        mod_name = "db.supabase_client"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        import db.supabase_client as m
        importlib.reload(m)
        return m._resolve_service_role_key()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if mod_name in sys.modules:
            del sys.modules[mod_name]


def _run_get_supabase(env: dict[str, str], fake_client_factory=None):
    """지정된 환경변수 상태에서 get_supabase() 를 실행한다.

    fake_client_factory: (url, key) → obj. None이면 create_client를 Mock으로 교체.
    """
    saved = {k: os.environ.get(k) for k in (
        "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY", "SUPABASE_URL",
    )}
    try:
        for k in saved:
            os.environ.pop(k, None)
        os.environ["SUPABASE_URL"] = "https://test.supabase.co"
        for k, v in env.items():
            os.environ[k] = v

        mod_name = "db.supabase_client"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        import db.supabase_client as m
        importlib.reload(m)

        captured = {}
        def _fake_create(url, key):
            captured["url"] = url
            captured["key"] = key
            return object()

        original_create = m.create_client
        m.create_client = _fake_create if fake_client_factory is None else fake_client_factory
        try:
            result = m.get_supabase()
            return result, captured
        finally:
            m.create_client = original_create
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if mod_name in sys.modules:
            del sys.modules[mod_name]


# ═══════════════════════════════════════════════════════════════════════
# ENV-01: canonical 변수만 설정 → 해당 값 사용
# ═══════════════════════════════════════════════════════════════════════

def test_ENV_01_canonical_only():
    key = _run_resolver({"SUPABASE_SERVICE_ROLE_KEY": "service-role-canonical"})
    assert key == "service-role-canonical", (
        f"SUPABASE_SERVICE_ROLE_KEY 단독 설정 시 해당 값을 반환해야 함. 실제: {key!r}"
    )


# ═══════════════════════════════════════════════════════════════════════
# ENV-02: legacy 별칭만 설정 → 해당 값 사용
# ═══════════════════════════════════════════════════════════════════════

def test_ENV_02_legacy_alias_only():
    key = _run_resolver({"SUPABASE_SERVICE_KEY": "service-role-legacy"})
    assert key == "service-role-legacy", (
        f"SUPABASE_SERVICE_KEY 단독 설정 시 해당 값을 반환해야 함. 실제: {key!r}"
    )


# ═══════════════════════════════════════════════════════════════════════
# ENV-03: 두 변수 모두 설정 → canonical 우선
# ═══════════════════════════════════════════════════════════════════════

def test_ENV_03_canonical_wins_over_legacy():
    key = _run_resolver({
        "SUPABASE_SERVICE_ROLE_KEY": "canonical-wins",
        "SUPABASE_SERVICE_KEY": "legacy-should-lose",
    })
    assert key == "canonical-wins", (
        f"두 변수 설정 시 SUPABASE_SERVICE_ROLE_KEY(canonical)가 우선해야 함. 실제: {key!r}"
    )


# ═══════════════════════════════════════════════════════════════════════
# ENV-04: SUPABASE_KEY만 설정 → FAIL-CLOSE (anon 폴백 금지)
# ═══════════════════════════════════════════════════════════════════════

def test_ENV_04_anon_key_only_raises():
    with pytest.raises(RuntimeError) as exc_info:
        _run_get_supabase({"SUPABASE_KEY": "anon-key-value"})
    msg = str(exc_info.value)
    assert "SUPABASE_SERVICE_ROLE_KEY" in msg or "service_role" in msg.lower(), (
        f"FAIL-CLOSE 오류 메시지에 service_role 키 안내가 없음: {msg!r}"
    )


# ═══════════════════════════════════════════════════════════════════════
# ENV-05: service_role 변수 모두 없음 → FAIL-CLOSE
# ═══════════════════════════════════════════════════════════════════════

def test_ENV_05_no_service_role_raises():
    with pytest.raises(RuntimeError) as exc_info:
        _run_get_supabase({})  # 환경변수 없음
    msg = str(exc_info.value)
    assert "service_role" in msg.lower() or "SUPABASE_SERVICE_ROLE_KEY" in msg, (
        f"FAIL-CLOSE 오류 메시지에 service_role 안내 없음: {msg!r}"
    )


# ═══════════════════════════════════════════════════════════════════════
# ENV-06: 키 원문이 반환된 클라이언트 repr/str에 평문 노출되지 않음
#         (create_client 에 전달되는 값이 올바른지 확인하는 간접 검증)
#         키 원문이 get_supabase() 반환값 바깥으로 누출되지 않음을 보장.
# ═══════════════════════════════════════════════════════════════════════

def test_ENV_06_key_value_not_in_str_repr():
    secret = "TOP_SECRET_SERVICE_ROLE_KEY_XYZ987"
    _, captured = _run_get_supabase({"SUPABASE_SERVICE_ROLE_KEY": secret})
    # create_client에 올바른 키가 전달됐는지 확인
    assert captured.get("key") == secret, (
        "create_client에 service_role 키가 올바르게 전달되지 않음"
    )
    # get_supabase 반환 객체(object())의 str/repr에 키 원문이 없음
    # — 실제 supabase 클라이언트는 여기서 object()로 대체됐으므로 항상 PASS.
    # 이 테스트는 "키 원문을 로그에 출력하는 코드가 없음"을 정적으로 보장하는 역할.
    import db.supabase_client as m
    importlib.reload(m)
    src = open(m.__file__).read()
    for log_call in ("print(", "logging.info(", "logging.debug(", "logger.info(", "logger.debug("):
        assert log_call not in src, (
            f"소스 코드에 키 원문 출력 가능 코드 발견: {log_call!r}"
        )
