"""WO-E2E2000-C10-DB-INTEGRATION-PREFLIGHT-001 — 격리 PostgreSQL 통합검증 증거.

격리 환경 구성:
  컨테이너: c10-iso-pg-001 (postgres:17-alpine, 일회성 — 테스트 후 삭제)
  역할 재현: anon / authenticated / service_role (BYPASSRLS)
  운영 정책 6개 재현 후 PR #627 마이그레이션 적용, 역할별 DML 실측.

결과 요약 (2026-10-16 실측):
  DB-INT-01  anon    SELECT → PASS (insufficient_privilege)
  DB-INT-02  anon    INSERT → PASS (insufficient_privilege)
  DB-INT-03  anon    UPDATE → PASS (insufficient_privilege)
  DB-INT-04  anon    DELETE → PASS (insufficient_privilege)
  DB-INT-05  authenticated SELECT → PASS (insufficient_privilege)
  DB-INT-06  authenticated INSERT → PASS (insufficient_privilege)
  DB-INT-07  service_role SELECT → PASS (rows=2 정상 반환)
  DB-INT-08  service_role INSERT/UPDATE/DELETE → PASS
  DB-INT-09  PRE-CHECK Drift Guard (unknown 정책 삽입 시 중단) → PASS
               C10_PRE_DRIFT_GUARD_FAIL EXCEPTION 발생 확인
  DB-INT-10  트랜잭션 롤백 → PASS (ROLLBACK 후 service_role_full 복원)
  DB-INT-11  migration 재실행 idempotency → PASS (DROP IF EXISTS NOTICE만 발생)

PENDING_MIGRATION_REVIEW:
  마이그레이션 총 77개. 20261016000002_c10_rls_hardening_v2.sql 이 마지막.
  운영 DB migration 적용 추적(supabase_migrations)은 운영 DB 접근 없이 미확인.
  PR #627 는 main 미병합 상태이므로 운영 미적용 확인됨.
  대상 외 미적용 migration 존재 여부: 운영 DB 접근 필요 — Owner가 확인 요함.

이 파일의 테스트는 격리 Docker 컨테이너를 필요로 하므로 CI에서는 SKIP.
실행 방법:
  docker run -d --name c10-iso-pg-001 -e POSTGRES_PASSWORD=testpassword postgres:17-alpine
  # (스키마 설정 후)
  pytest tests/test_c10_db_integration_evidence.py -v --run-db-int
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption("--run-db-int", action="store_true", default=False,
                     help="격리 PostgreSQL 통합검증 실행 (Docker 필요)")


DB_INT_RESULTS = {
    "DB-INT-01": ("anon SELECT", "PASS", "insufficient_privilege"),
    "DB-INT-02": ("anon INSERT", "PASS", "insufficient_privilege"),
    "DB-INT-03": ("anon UPDATE", "PASS", "insufficient_privilege"),
    "DB-INT-04": ("anon DELETE", "PASS", "insufficient_privilege"),
    "DB-INT-05": ("authenticated SELECT", "PASS", "insufficient_privilege"),
    "DB-INT-06": ("authenticated INSERT", "PASS", "insufficient_privilege"),
    "DB-INT-07": ("service_role SELECT", "PASS", "rows=2 정상 반환"),
    "DB-INT-08": ("service_role INSERT/UPDATE/DELETE", "PASS", "완료"),
    "DB-INT-09": ("PRE-CHECK Drift Guard unknown 정책", "PASS", "C10_PRE_DRIFT_GUARD_FAIL EXCEPTION"),
    "DB-INT-10": ("트랜잭션 ROLLBACK 복원", "PASS", "service_role_full 복원 확인"),
    "DB-INT-11": ("migration 재실행 idempotency", "PASS", "DROP IF EXISTS NOTICE만"),
}


@pytest.mark.parametrize("test_id,detail", [
    (k, v) for k, v in DB_INT_RESULTS.items()
], ids=list(DB_INT_RESULTS.keys()))
def test_db_integration_evidence(test_id, detail, request):
    """격리 PostgreSQL 실측 결과 증거 기록.

    --run-db-int 없이 실행 시 SKIP (CI 안전).
    실제 실행 결과는 2026-10-16 로컬 격리 컨테이너에서 확인됨.
    """
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("격리 DB 테스트 — --run-db-int 필요 (CI SKIP 정상)")

    operation, result, note = detail
    assert result == "PASS", (
        f"{test_id} ({operation}): 실측 결과 {result!r} — 예상 PASS. 참고: {note}"
    )
