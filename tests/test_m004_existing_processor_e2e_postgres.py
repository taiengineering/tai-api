"""WO-TAI-DOC-M004-EXISTING-PROCESSOR-E2E-001 + CORR-001 + CORR-002 + CORR-003
기존 문서 프로세서 E2E — 격리 PostgreSQL (로컬) 통합 테스트.

대상: PR #625
DB:   tai_test_m004_e2e (localhost:5432) — 운영 DB 연결 금지

실행 조건:
  - PostgreSQL@16 실행 중 (localhost:5432)
  - psql -c "CREATE DATABASE tai_test_m004_e2e"  (최초 1회)
  - 또는 TEST_M004_DSN 환경변수 지정

## 테스트 분류

### DSN 격리 가드 단위 테스트 (TestDsnGuard) — DB 불필요, 항상 실행
  DSN-G1  잘못된 dbname → RuntimeError (연결 전 차단)
  DSN-G2  원격 host (keyword DSN) → RuntimeError (연결 전 차단)
  DSN-G3  원격 host (URI DSN) → RuntimeError (연결 전 차단)
  DSN-G4  service 파라미터 → RuntimeError (간접 접속 차단)
  DSN-G5  safe params 항상 hostaddr=127.0.0.1 명시 (PGHOSTADDR 무력화)
  DSN-G6  PGHOSTADDR 환경변수 설정 시에도 safe params = 127.0.0.1

### Direct SQL DB 계약 테스트 (TestPgE2E) — 격리 PostgreSQL 필요
  PG-01  DB 연결 + 격리 DB 안전성 가드(연결 후 SQL 재확인) + 테이블 존재
  PG-02  runtime_state_transition_rule 시드 데이터 (8건)
  PG-03  Document CREATE — DRAFT INSERT + 컬럼 계약
  PG-04  Document LIST — factory_id 필터 격리
  PG-05  Document OPEN — id SELECT + absent = None
  PG-06  Status DRAFT → IN_PROGRESS (직접 UPDATE, 서비스 레이어 경유 없음)
  PG-07  Status IN_PROGRESS → SUBMITTED_FOR_REVIEW (submitted_by 바인딩, 직접 SQL)
  PG-08  Status SUBMITTED_FOR_REVIEW → REVIEW_PENDING (직접 SQL)
  PG-09  confirm_document_atomic() 정상 경로 (REVIEW_PENDING → APPROVED_BY_HUMAN)
  PG-10  Archive 행 생성 및 컬럼 계약 검증
  PG-11  Approval 행 생성 및 컬럼 계약 검증
  CF-01-A  trg_rdd_seal_guard: REVIEW_PENDING UPDATE 통과 (P0001 미발화)
  CF-01-B  trg_rdd_seal_guard: APPROVED_BY_HUMAN UPDATE 차단 (P0001 RaiseException)
  PG-R1  Archive INSERT UniqueViolation → 전체 롤백 (approval=0, doc=REVIEW_PENDING)
  PG-R2  Approval INSERT 실패(테스트 트리거) → 전체 롤백 (archive=0, doc=REVIEW_PENDING)
  PG-R3  Seal UPDATE 실패(테스트 트리거) → 전체 롤백 (archive=0, approval=0, doc=REVIEW_PENDING)
  PG-ENV  PGHOSTADDR=1.2.3.4 환경변수 설정 시에도 safe params로 로컬 DB에 연결됨

### Mock/Stub 처리 항목 (비-DB 의존)
  validate_required_signatures      — Stub (no-op)
  resolve_signature_images_for_render — Stub (Storage 연결 없음)
  build_render_artifacts            — Stub (렌더링 엔진 미호출)
  compute_confirmed_snapshot_hash   — Stub (실제 해시 미검증)

### 미검증 항목
  실제 렌더링 품질 (HTML/PDF 출력 포맷)
  Supabase Storage 업로드/다운로드 경로
  PostgREST RLS 정책 (격리 DB에 미적용)
  서비스 레이어(supabase-py) 상태 전이 경로 (PG-06~08은 직접 SQL)

## CORR-003 적용 내역 (GPT DSN-FINAL-001)
  - _build_safe_connection_params(): 검증 + 안전 파라미터 구성 통합
    hostaddr=127.0.0.1 명시 → PGHOSTADDR 환경변수 무력화
    service 파라미터 거부 → 간접 접속 차단
    URI/keyword DSN 양 형식 지원
  - 모든 psycopg2 연결: 파라미터 딕셔너리 사용 (문자열 연결 제거)
  - _stub_confirm_non_db_deps: _DATABASE_URL 대신 _connect 직접 교체
  - DSN 단위 테스트 (TestDsnGuard): DB 불필요, 항상 실행
  - TestPgE2E: class-level skipif (모듈 레벨 pytestmark 제거)
  - clean fixture: TestPgE2E 내부 autouse로 이동

## CORR-002 적용 내역
  - _validate_dsn_isolation(): 연결 전 DSN 파싱 검증
  - 격리 조건 불일치 → RuntimeError (SKIP 아닌 명시적 오류)

## CORR-001 적용 내역
  - 트리거 ERRCODE: check_violation → raise_exception (운영 정본 일치)
  - 원자 롤백 검증 3건 추가 (PG-R1, PG-R2, PG-R3)
"""
from __future__ import annotations

import os
import uuid

import psycopg2
import psycopg2.errors
import psycopg2.extensions
import psycopg2.extras
import pytest

# ── DSN ──────────────────────────────────────────────────────────────────────

_DSN = os.getenv("TEST_M004_DSN", "host=localhost dbname=tai_test_m004_e2e user=taiwangsim")

_EXPECTED_DBNAME = "tai_test_m004_e2e"
_ALLOWED_HOSTS   = frozenset({"", "localhost", "127.0.0.1", "::1"})


def _validate_dsn_isolation(dsn: str) -> None:
    """DSN 파싱 + 격리 조건 검증 — 연결 시도 전 실행.

    허용: dbname=tai_test_m004_e2e, host∈{localhost,127.0.0.1,::1,''}
    차단: 원격 host, hostaddr 원격 주소, service 파라미터
    불일치 시 RuntimeError (SKIP 아닌 명시적 오류).
    """
    try:
        parsed = psycopg2.extensions.parse_dsn(dsn)
    except Exception as e:
        raise RuntimeError(f"DSN 파싱 실패: {e}") from e

    if "service" in parsed:
        raise RuntimeError(
            f"격리 DB DSN 안전성 위반: service={parsed['service']!r}. "
            "간접 접속 파라미터 사용 금지."
        )
    dbname   = parsed.get("dbname", "")
    host     = parsed.get("host", "localhost")
    hostaddr = parsed.get("hostaddr", "")
    if dbname != _EXPECTED_DBNAME:
        raise RuntimeError(
            f"격리 DB DSN 안전성 위반: dbname={dbname!r}, 예상={_EXPECTED_DBNAME!r}. "
            "연결 전 차단."
        )
    if host not in _ALLOWED_HOSTS:
        raise RuntimeError(
            f"격리 DB DSN 안전성 위반: host={host!r}. 원격 연결 금지."
        )
    if hostaddr and hostaddr not in {"127.0.0.1", "::1"}:
        raise RuntimeError(
            f"격리 DB DSN 안전성 위반: hostaddr={hostaddr!r}. 원격 연결 금지."
        )


def _build_safe_connection_params(dsn: str) -> dict:
    """DSN 파싱 → 격리 검증 → 안전한 로컬 전용 연결 파라미터 딕셔너리 구성.

    hostaddr=127.0.0.1 명시:
      psycopg2(libpq)는 explicit 파라미터가 환경변수보다 우선.
      PGHOSTADDR 환경변수가 원격 주소를 지정해도 127.0.0.1로 고정.

    URI/keyword DSN 양 형식 지원.
    서비스 파일(PGSERVICE) 우회 차단.
    """
    _validate_dsn_isolation(dsn)  # 불일치 시 RuntimeError
    parsed = psycopg2.extensions.parse_dsn(dsn)
    safe: dict = {
        "dbname":          _EXPECTED_DBNAME,
        "host":            "localhost",
        "hostaddr":        "127.0.0.1",  # PGHOSTADDR 무력화
        "connect_timeout": "5",
    }
    for key in ("user", "password", "port"):
        if key in parsed:
            safe[key] = parsed[key]
    return safe


# 모듈 로드 시 1회 실행 — DSN 불량이면 RuntimeError로 즉시 중단
_SAFE_CONN_PARAMS: dict = _build_safe_connection_params(_DSN)

_DB_AVAILABLE: bool = False
try:
    _probe = psycopg2.connect(**{**_SAFE_CONN_PARAMS, "connect_timeout": "2"})
    _probe.close()
    _DB_AVAILABLE = True
except Exception:
    pass


def _assert_isolated_db(conn) -> None:
    """연결 후 SQL로 격리 DB 재확인 — 2단계 방어."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT current_database() AS db, inet_server_addr() AS host")
    row = cur.fetchone()
    actual_db   = row["db"]
    actual_host = str(row["host"] or "127.0.0.1")
    assert actual_db == _EXPECTED_DBNAME, (
        f"격리 DB 안전성 위반(연결 후): db={actual_db}. 즉시 중단."
    )
    assert actual_host in ("127.0.0.1", "::1", "localhost", "None"), (
        f"격리 DB 안전성 위반(연결 후): host={actual_host}. 즉시 중단."
    )


# ── 상수 ─────────────────────────────────────────────────────────────────────

USER_ID    = "11111111-1111-1111-1111-111111111111"
FACTORY_ID = "ffffffff-f001-f001-f001-000000000001"
COMPANY_ID = "cccccccc-c001-c001-c001-000000000001"
SCHEMA_ID  = "a0000000-0000-0000-0000-000000000001"

_TRANSITION_RULES = [
    {"from_status": "DRAFT",                "to_status": "IN_PROGRESS",          "requires_reviewer": False, "requires_comment": False},
    {"from_status": "IN_PROGRESS",          "to_status": "SUBMITTED_FOR_REVIEW", "requires_reviewer": False, "requires_comment": False},
    {"from_status": "SUBMITTED_FOR_REVIEW", "to_status": "REVIEW_PENDING",       "requires_reviewer": False, "requires_comment": False},
    {"from_status": "REVIEW_PENDING",       "to_status": "APPROVED_BY_HUMAN",    "requires_reviewer": True,  "requires_comment": True},
    {"from_status": "REVIEW_PENDING",       "to_status": "REJECTED_BY_HUMAN",    "requires_reviewer": True,  "requires_comment": True},
    {"from_status": "REVIEW_PENDING",       "to_status": "RETURNED_FOR_EDIT",    "requires_reviewer": True,  "requires_comment": False},
    {"from_status": "APPROVED_BY_HUMAN",    "to_status": "ARCHIVED",             "requires_reviewer": False, "requires_comment": False},
    {"from_status": "REJECTED_BY_HUMAN",    "to_status": "DRAFT",                "requires_reviewer": False, "requires_comment": False},
]

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS public.factories (
    id         uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid
);

CREATE TABLE IF NOT EXISTS public.runtime_form_schema (
    id                  uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    status              text,
    form_name           text,
    version             int,
    catalog_document_id uuid,
    field_count         int DEFAULT 0,
    checklist_count     int DEFAULT 0,
    evidence_count      int DEFAULT 0,
    source_trace        jsonb,
    form_type           text,
    document_family     text,
    schema_candidate_id uuid
);

CREATE TABLE IF NOT EXISTS public.runtime_field (
    id               uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    form_schema_id   uuid,
    field_label      text,
    field_key        text,
    input_type       text,
    field_order      int,
    required_status  text,
    source_trace     jsonb,
    status           text
);

CREATE TABLE IF NOT EXISTS public.runtime_checklist_item (
    id             uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    form_schema_id uuid
);

CREATE TABLE IF NOT EXISTS public.runtime_document_data (
    id                    uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    form_schema_id        uuid,
    factory_id            uuid,
    company_id            uuid,
    status                text NOT NULL DEFAULT 'DRAFT',
    version               int NOT NULL DEFAULT 1,
    runtime_data_json     jsonb NOT NULL DEFAULT '{}',
    evidence_links        jsonb NOT NULL DEFAULT '[]',
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    created_by            uuid,
    submitted_by          uuid,
    reviewed_by           uuid,
    reviewed_at           timestamptz,
    review_comment        text,
    source_inspection_id  uuid
);

-- 봉인 트리거 — 운영 정본과 동일한 ERRCODE = raise_exception (P0001)
CREATE OR REPLACE FUNCTION public.fn_rdd_seal_guard()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'APPROVED_BY_HUMAN' THEN
        RAISE EXCEPTION
            'trg_rdd_seal_guard: document id=% is sealed (status=APPROVED_BY_HUMAN). UPDATE denied.',
            OLD.id
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_rdd_seal_guard ON public.runtime_document_data;
CREATE TRIGGER trg_rdd_seal_guard
    BEFORE UPDATE ON public.runtime_document_data
    FOR EACH ROW EXECUTE FUNCTION public.fn_rdd_seal_guard();

CREATE TABLE IF NOT EXISTS public.runtime_document_archive (
    id                      uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    runtime_document_id     uuid NOT NULL,
    runtime_values_snapshot jsonb,
    evidence_links_snapshot jsonb,
    confirmed_at            timestamptz,
    confirmed_by            uuid,
    document_version        int,
    snapshot_schema_version int,
    source_trace_snapshot   jsonb,
    rendered_body           text,
    evidence_manifest       jsonb,
    snapshot_hash           text,
    template_identity       text,
    UNIQUE (runtime_document_id, document_version)
);

CREATE TABLE IF NOT EXISTS public.runtime_document_approval (
    id                    uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    runtime_document_id   uuid NOT NULL,
    reviewer_id           uuid,
    reviewed_at           timestamptz,
    review_action         text,
    review_comment        text,
    snapshot_id           uuid,
    runtime_snapshot      jsonb,
    evidence_snapshot     jsonb,
    source_trace_snapshot jsonb,
    rollback_available    boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS public.runtime_state_transition_rule (
    from_status       text NOT NULL,
    to_status         text NOT NULL,
    requires_reviewer boolean NOT NULL DEFAULT false,
    requires_comment  boolean NOT NULL DEFAULT false,
    PRIMARY KEY (from_status, to_status)
);
"""

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg():
    conn = psycopg2.connect(**_SAFE_CONN_PARAMS)
    conn.autocommit = True
    _assert_isolated_db(conn)
    cur = conn.cursor()
    cur.execute(_BOOTSTRAP_SQL)
    _seed_transition_rules(cur)
    yield conn
    conn.close()


def _seed_transition_rules(cur) -> None:
    cur.execute("DELETE FROM public.runtime_state_transition_rule")
    for r in _TRANSITION_RULES:
        cur.execute(
            "INSERT INTO public.runtime_state_transition_rule "
            "(from_status, to_status, requires_reviewer, requires_comment) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (r["from_status"], r["to_status"], r["requires_reviewer"], r["requires_comment"]),
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _insert_schema(pg, schema_id: str = SCHEMA_ID) -> None:
    cur = pg.cursor()
    cur.execute(
        "INSERT INTO public.runtime_form_schema (id, status, form_name, version) "
        "VALUES (%s, 'APPROVED_FOR_RUNTIME_USE', '격리E2E서식', 1)",
        (schema_id,),
    )


def _insert_factory(pg, factory_id: str = FACTORY_ID, company_id: str = COMPANY_ID) -> None:
    cur = pg.cursor()
    cur.execute(
        "INSERT INTO public.factories (id, company_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (factory_id, company_id),
    )


def _insert_doc(
    pg,
    doc_id: str,
    status: str = "DRAFT",
    factory_id: str = FACTORY_ID,
    company_id: str = COMPANY_ID,
    schema_id: str = SCHEMA_ID,
    submitted_by: str | None = None,
    version: int = 1,
) -> None:
    cur = pg.cursor()
    cur.execute(
        "INSERT INTO public.runtime_document_data "
        "(id, form_schema_id, factory_id, company_id, status, submitted_by, version) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (doc_id, schema_id, factory_id, company_id, status, submitted_by, version),
    )


def _current_status(pg, doc_id: str) -> str | None:
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT status FROM public.runtime_document_data WHERE id = %s", (doc_id,))
    row = cur.fetchone()
    return row["status"] if row else None


def _count_archive(pg, doc_id: str) -> int:
    cur = pg.cursor()
    cur.execute(
        "SELECT count(*) FROM public.runtime_document_archive "
        "WHERE runtime_document_id = %s", (doc_id,),
    )
    return cur.fetchone()[0]


def _count_approval(pg, doc_id: str) -> int:
    cur = pg.cursor()
    cur.execute(
        "SELECT count(*) FROM public.runtime_document_approval "
        "WHERE runtime_document_id = %s", (doc_id,),
    )
    return cur.fetchone()[0]


# ── Confirm 의존 stub ─────────────────────────────────────────────────────────

def _stub_confirm_non_db_deps(monkeypatch) -> None:
    """Storage·렌더·서명·해시 함수를 stub으로 교체.

    _connect 직접 교체: _DATABASE_URL 문자열 대신 _SAFE_CONN_PARAMS 딕셔너리 사용.
    monkeypatch가 테스트 완료(성공·실패) 후 원래 값을 자동 복원한다.
    """
    import services.document_confirm_svc as svc

    monkeypatch.setattr(svc, "validate_required_signatures",        lambda rv, flds: None)
    monkeypatch.setattr(svc, "resolve_signature_images_for_render", lambda **kw: {"images": {}, "manifest": {}})
    monkeypatch.setattr(
        svc, "build_render_artifacts",
        lambda **kw: {
            "source_trace_snapshot": {},
            "template_identity":     "ISOLATED_TEST_TEMPLATE",
            "evidence_manifest":     {},
            "rendered_body":         "<html>isolated-e2e</html>",
        },
    )
    monkeypatch.setattr(
        svc, "compute_confirmed_snapshot_hash",
        lambda **kw: "test_hash_" + str(uuid.uuid4()),
    )

    import db.direct_sql as ds
    monkeypatch.setattr(ds, "_connect", lambda: psycopg2.connect(**_SAFE_CONN_PARAMS))


def _user(uid: str = USER_ID) -> dict:
    return {
        "id":         uid,
        "role_code":  "011",
        "company_id": COMPANY_ID,
        "factory_id": FACTORY_ID,
    }


# ════════════════════════════════════════════════════════════════════════
# DSN 격리 가드 단위 테스트 (TestDsnGuard)
# PostgreSQL 서버 없이 실행 가능 — _build_safe_connection_params 순수 단위 테스트
# ════════════════════════════════════════════════════════════════════════

class TestDsnGuard:
    """DSN 격리 가드 단위 테스트 — DB 연결 불필요, 항상 실행."""

    def test_dsn_g1_wrong_dbname_blocked(self):
        """DSN-G1 — 잘못된 dbname은 RuntimeError로 연결 전 차단."""
        with pytest.raises(RuntimeError, match="dbname"):
            _build_safe_connection_params(
                "host=localhost dbname=postgres user=taiwangsim"
            )

    def test_dsn_g2_remote_host_keyword_blocked(self):
        """DSN-G2 — 원격 host (keyword DSN) 연결 전 차단."""
        with pytest.raises(RuntimeError, match="host"):
            _build_safe_connection_params(
                "host=prod-db.example.com dbname=tai_test_m004_e2e user=taiwangsim"
            )

    def test_dsn_g3_remote_host_uri_blocked(self):
        """DSN-G3 — 원격 host (URI DSN) 연결 전 차단."""
        with pytest.raises(RuntimeError, match="host"):
            _build_safe_connection_params(
                "postgresql://user@prod-db.example.com/tai_test_m004_e2e"
            )

    def test_dsn_g4_service_param_blocked(self):
        """DSN-G4 — service 파라미터는 간접 접속 우회 가능성 → 차단."""
        with pytest.raises(RuntimeError, match="service"):
            _build_safe_connection_params("service=myremoteservice")

    def test_dsn_g5_safe_params_always_hostaddr_127(self):
        """DSN-G5 — safe params는 항상 hostaddr=127.0.0.1 명시.

        PGHOSTADDR 환경변수 유무와 무관하게 함수 반환값에 hostaddr=127.0.0.1이 포함.
        psycopg2(libpq)는 explicit 파라미터가 환경변수보다 우선하므로
        PGHOSTADDR가 원격 주소를 가리켜도 실제 접속은 127.0.0.1로 고정됨.
        """
        params = _build_safe_connection_params(
            "host=localhost dbname=tai_test_m004_e2e user=taiwangsim"
        )
        assert params["hostaddr"] == "127.0.0.1", (
            "safe params must always set hostaddr=127.0.0.1"
        )

    def test_dsn_g6_pghostaddr_env_does_not_affect_safe_params(self, monkeypatch):
        """DSN-G6 — PGHOSTADDR=원격IP 환경변수 설정 시에도 safe params = 127.0.0.1.

        PGHOSTADDR는 libpq 환경변수이지만, explicit hostaddr 파라미터가 우선함.
        _build_safe_connection_params()는 환경변수와 무관하게 127.0.0.1을 출력.
        """
        monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
        params = _build_safe_connection_params(
            "host=localhost dbname=tai_test_m004_e2e user=taiwangsim"
        )
        assert params["hostaddr"] == "127.0.0.1"


# ════════════════════════════════════════════════════════════════════════
# PostgreSQL 격리 E2E 테스트 (TestPgE2E)
# 격리 DB 필요 — tai_test_m004_e2e (localhost:5432)
# ════════════════════════════════════════════════════════════════════════

class TestPgE2E:
    """격리 PostgreSQL DB 필요 테스트 — _DB_AVAILABLE=False이면 전체 SKIP."""

    pytestmark = pytest.mark.skipif(
        not _DB_AVAILABLE,
        reason="tai_test_m004_e2e DB 없음 — BLOCKED (격리 PostgreSQL 미준비)",
    )

    @pytest.fixture(autouse=True)
    def clean(self, pg):
        cur = pg.cursor()
        cur.execute(
            "TRUNCATE public.runtime_document_approval, "
            "public.runtime_document_archive, "
            "public.runtime_document_data, "
            "public.runtime_field, "
            "public.runtime_form_schema, "
            "public.factories CASCADE;"
        )
        yield

    # ── Direct SQL DB 계약 테스트 ──────────────────────────────────────

    def test_pg01_db_connection_and_tables_exist(self, pg):
        """PG-01 — DB 연결 + 격리 DB 안전성 재확인 + 테이블 존재"""
        _assert_isolated_db(pg)
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY(%s)",
            ([
                "runtime_document_data", "runtime_document_archive",
                "runtime_document_approval", "runtime_state_transition_rule",
                "runtime_form_schema", "runtime_field",
            ],),
        )
        found = {r["table_name"] for r in cur.fetchall()}
        expected = {
            "runtime_document_data", "runtime_document_archive",
            "runtime_document_approval", "runtime_state_transition_rule",
            "runtime_form_schema", "runtime_field",
        }
        assert found == expected, f"누락 테이블: {expected - found}"

    def test_pg02_transition_rules_seeded(self, pg):
        """PG-02 — runtime_state_transition_rule 시드 8건"""
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT from_status, to_status FROM public.runtime_state_transition_rule")
        pairs = {(r["from_status"], r["to_status"]) for r in cur.fetchall()}
        for rule in _TRANSITION_RULES:
            assert (rule["from_status"], rule["to_status"]) in pairs
        assert len(pairs) == 8

    def test_pg03_document_create_draft(self, pg):
        """PG-03 — Document CREATE (DRAFT INSERT + 컬럼 계약, 직접 SQL)"""
        _insert_schema(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id)
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM public.runtime_document_data WHERE id = %s", (doc_id,))
        row = cur.fetchone()
        assert row is not None
        assert row["status"] == "DRAFT"
        assert str(row["form_schema_id"]) == SCHEMA_ID
        assert row["version"] == 1

    def test_pg04_document_list_by_factory(self, pg):
        """PG-04 — Document LIST (factory_id 필터 격리)"""
        _insert_schema(pg)
        other_factory = _new_id()
        target_ids = [_new_id() for _ in range(3)]
        for doc_id in target_ids:
            _insert_doc(pg, doc_id)
        _insert_doc(pg, _new_id(), factory_id=other_factory)

        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id FROM public.runtime_document_data WHERE factory_id = %s",
            (FACTORY_ID,),
        )
        found_ids = {str(r["id"]) for r in cur.fetchall()}
        for doc_id in target_ids:
            assert doc_id in found_ids
        assert len(found_ids) == 3, f"다른 factory 문서가 섞임: {len(found_ids)}건"

    def test_pg05_document_open_by_id(self, pg):
        """PG-05 — Document OPEN (id SELECT + absent = None)"""
        _insert_schema(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id)
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM public.runtime_document_data WHERE id = %s", (doc_id,))
        assert cur.fetchone() is not None
        cur.execute("SELECT * FROM public.runtime_document_data WHERE id = %s", (_new_id(),))
        assert cur.fetchone() is None

    def test_pg06_status_draft_to_in_progress(self, pg):
        """PG-06 — Status DRAFT → IN_PROGRESS (직접 UPDATE, 서비스 레이어 경유 없음)"""
        _insert_schema(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="DRAFT")
        cur = pg.cursor()
        cur.execute(
            "UPDATE public.runtime_document_data SET status = 'IN_PROGRESS', updated_at = now() "
            "WHERE id = %s AND status = 'DRAFT'", (doc_id,),
        )
        assert cur.rowcount == 1
        assert _current_status(pg, doc_id) == "IN_PROGRESS"

    def test_pg07_status_to_submitted_for_review(self, pg):
        """PG-07 — Status IN_PROGRESS → SUBMITTED_FOR_REVIEW (submitted_by 바인딩, 직접 SQL)"""
        _insert_schema(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="IN_PROGRESS")
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "UPDATE public.runtime_document_data "
            "SET status = 'SUBMITTED_FOR_REVIEW', submitted_by = %s, updated_at = now() "
            "WHERE id = %s AND status = 'IN_PROGRESS' RETURNING *",
            (USER_ID, doc_id),
        )
        row = cur.fetchone()
        assert row is not None
        assert row["status"] == "SUBMITTED_FOR_REVIEW"
        assert str(row["submitted_by"]) == USER_ID

    def test_pg08_status_to_review_pending(self, pg):
        """PG-08 — Status SUBMITTED_FOR_REVIEW → REVIEW_PENDING (직접 SQL)"""
        _insert_schema(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="SUBMITTED_FOR_REVIEW", submitted_by=USER_ID)
        cur = pg.cursor()
        cur.execute(
            "UPDATE public.runtime_document_data SET status = 'REVIEW_PENDING', updated_at = now() "
            "WHERE id = %s AND status = 'SUBMITTED_FOR_REVIEW'", (doc_id,),
        )
        assert cur.rowcount == 1
        assert _current_status(pg, doc_id) == "REVIEW_PENDING"

    # ── psycopg2 Confirm 실제 트랜잭션 테스트 ─────────────────────────

    def test_pg09_confirm_happy_path(self, pg, monkeypatch):
        """PG-09 — confirm_document_atomic() 정상 경로

        psycopg2 트랜잭션 실제 실행. 비-DB 함수는 Stub 처리.
        """
        _stub_confirm_non_db_deps(monkeypatch)
        _insert_schema(pg)
        _insert_factory(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="REVIEW_PENDING", submitted_by=USER_ID)

        from services.document_confirm_svc import confirm_document_atomic
        sealed = confirm_document_atomic(
            doc_id=doc_id,
            current_user=_user(),
            actor_id=USER_ID,
            comment="격리 DB E2E confirm 테스트",
        )
        assert sealed["status"] == "APPROVED_BY_HUMAN"
        assert str(sealed["reviewed_by"]) == USER_ID
        assert _current_status(pg, doc_id) == "APPROVED_BY_HUMAN"

    def test_pg10_archive_row_created(self, pg, monkeypatch):
        """PG-10 — Archive 행 생성 및 컬럼 계약 검증

        Stub 렌더 결과로 확인. 실제 렌더링 품질은 미검증.
        """
        _stub_confirm_non_db_deps(monkeypatch)
        _insert_schema(pg)
        _insert_factory(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="REVIEW_PENDING", submitted_by=USER_ID)

        from services.document_confirm_svc import confirm_document_atomic
        confirm_document_atomic(
            doc_id=doc_id,
            current_user=_user(),
            actor_id=USER_ID,
            comment="archive 검증",
        )
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM public.runtime_document_archive WHERE runtime_document_id = %s",
            (doc_id,),
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        archive = rows[0]
        assert archive["document_version"]        == 1
        assert archive["snapshot_schema_version"] == 1
        assert archive["snapshot_hash"]           is not None
        assert archive["template_identity"]       == "ISOLATED_TEST_TEMPLATE"

    def test_pg11_approval_row_created(self, pg, monkeypatch):
        """PG-11 — Approval 행 생성 및 컬럼 계약 검증"""
        _stub_confirm_non_db_deps(monkeypatch)
        _insert_schema(pg)
        _insert_factory(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="REVIEW_PENDING", submitted_by=USER_ID)

        from services.document_confirm_svc import confirm_document_atomic
        confirm_document_atomic(
            doc_id=doc_id,
            current_user=_user(),
            actor_id=USER_ID,
            comment="approval 검증",
        )
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM public.runtime_document_approval WHERE runtime_document_id = %s",
            (doc_id,),
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        approval = rows[0]
        assert approval["review_action"]      == "APPROVE"
        assert str(approval["reviewer_id"])   == USER_ID
        assert approval["rollback_available"] is True
        assert approval["snapshot_id"]        is not None

    # ── CF-01 트리거 계약 테스트 ──────────────────────────────────────

    def test_cf01_a_trigger_allows_review_pending_update(self, pg):
        """CF-01-A — trg_rdd_seal_guard: REVIEW_PENDING UPDATE 통과

        OLD.status='REVIEW_PENDING' ≠ 'APPROVED_BY_HUMAN' → 트리거 조건 불일치 → 통과.
        Confirm(REVIEW_PENDING→APPROVED_BY_HUMAN)은 CF-01 충돌 없음.
        """
        _insert_schema(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="REVIEW_PENDING", submitted_by=USER_ID)
        cur = pg.cursor()
        cur.execute(
            "UPDATE public.runtime_document_data SET status = 'APPROVED_BY_HUMAN' "
            "WHERE id = %s", (doc_id,),
        )
        assert cur.rowcount == 1
        assert _current_status(pg, doc_id) == "APPROVED_BY_HUMAN"

    def test_cf01_b_trigger_blocks_approved_by_human_update(self, pg):
        """CF-01-B — trg_rdd_seal_guard: APPROVED_BY_HUMAN UPDATE 차단

        CONFIRMED CONFLICT: P0001 RaiseException — 운영 정본과 동일한 ERRCODE.
        봉인 트리거 해제·우회 금지. Owner 설계 결정 필요.
        """
        _insert_schema(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="APPROVED_BY_HUMAN", submitted_by=USER_ID)
        cur = pg.cursor()
        with pytest.raises(psycopg2.errors.RaiseException):
            cur.execute(
                "UPDATE public.runtime_document_data SET status = 'ARCHIVED' "
                "WHERE id = %s", (doc_id,),
            )
        pg.rollback()
        assert _current_status(pg, doc_id) == "APPROVED_BY_HUMAN"

    # ── 원자 롤백 검증 ────────────────────────────────────────────────

    def test_pg_r1_archive_insert_fail_rollback(self, pg, monkeypatch):
        """PG-R1 — Archive INSERT UniqueViolation → 전체 롤백

        방법: (runtime_document_id, document_version)=(doc_id, 1) 사전 삽입
        검증: 409, approval=0, doc.status=REVIEW_PENDING
        """
        _stub_confirm_non_db_deps(monkeypatch)
        _insert_schema(pg)
        _insert_factory(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="REVIEW_PENDING", submitted_by=USER_ID)

        cur = pg.cursor()
        cur.execute(
            "INSERT INTO public.runtime_document_archive "
            "(runtime_document_id, document_version, snapshot_hash) VALUES (%s, 1, 'pre_existing')",
            (doc_id,),
        )

        from services.document_confirm_svc import confirm_document_atomic, ConfirmError
        with pytest.raises(ConfirmError) as exc_info:
            confirm_document_atomic(
                doc_id=doc_id, current_user=_user(), actor_id=USER_ID, comment="충돌 테스트",
            )
        assert exc_info.value.http_status == 409
        assert _count_approval(pg, doc_id) == 0, "approval 행 잔류 — 부분 커밋"
        assert _current_status(pg, doc_id) == "REVIEW_PENDING", "doc 상태 변경 — 부분 커밋"
        assert _count_archive(pg, doc_id) == 1

    def test_pg_r2_approval_insert_fail_rollback(self, pg, monkeypatch):
        """PG-R2 — Approval INSERT 실패(테스트 트리거) → 전체 롤백

        검증: 500, archive=0 (롤백), doc.status=REVIEW_PENDING
        """
        _stub_confirm_non_db_deps(monkeypatch)
        _insert_schema(pg)
        _insert_factory(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="REVIEW_PENDING", submitted_by=USER_ID)

        cur = pg.cursor()
        cur.execute("""
            CREATE OR REPLACE FUNCTION public.fn_test_block_approval_insert()
            RETURNS TRIGGER LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'test_pg_r2: approval INSERT blocked'
                    USING ERRCODE = 'raise_exception';
            END;
            $$;
            DROP TRIGGER IF EXISTS test_trg_block_approval ON public.runtime_document_approval;
            CREATE TRIGGER test_trg_block_approval
                BEFORE INSERT ON public.runtime_document_approval
                FOR EACH ROW EXECUTE FUNCTION public.fn_test_block_approval_insert();
        """)

        try:
            from services.document_confirm_svc import confirm_document_atomic, ConfirmError
            with pytest.raises(ConfirmError) as exc_info:
                confirm_document_atomic(
                    doc_id=doc_id, current_user=_user(), actor_id=USER_ID, comment="approval 실패 테스트",
                )
            assert exc_info.value.http_status == 500
            assert _count_archive(pg, doc_id) == 0, "archive 행 잔류 — 부분 커밋"
            assert _count_approval(pg, doc_id) == 0, "approval 행 잔류 — 부분 커밋"
            assert _current_status(pg, doc_id) == "REVIEW_PENDING"
        finally:
            cur.execute(
                "DROP TRIGGER IF EXISTS test_trg_block_approval ON public.runtime_document_approval; "
                "DROP FUNCTION IF EXISTS public.fn_test_block_approval_insert();"
            )

    def test_pg_r3_seal_update_fail_rollback(self, pg, monkeypatch):
        """PG-R3 — Seal UPDATE 실패(테스트 트리거) → 전체 롤백

        검증: 500, archive=0, approval=0, doc.status=REVIEW_PENDING
        """
        _stub_confirm_non_db_deps(monkeypatch)
        _insert_schema(pg)
        _insert_factory(pg)
        doc_id = _new_id()
        _insert_doc(pg, doc_id, status="REVIEW_PENDING", submitted_by=USER_ID)

        cur = pg.cursor()
        cur.execute("""
            CREATE OR REPLACE FUNCTION public.fn_test_block_seal_update()
            RETURNS TRIGGER LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.status = 'APPROVED_BY_HUMAN' THEN
                    RAISE EXCEPTION 'test_pg_r3: seal UPDATE blocked'
                        USING ERRCODE = 'raise_exception';
                END IF;
                RETURN NEW;
            END;
            $$;
            DROP TRIGGER IF EXISTS test_trg_block_seal ON public.runtime_document_data;
            CREATE TRIGGER test_trg_block_seal
                BEFORE UPDATE ON public.runtime_document_data
                FOR EACH ROW EXECUTE FUNCTION public.fn_test_block_seal_update();
        """)

        try:
            from services.document_confirm_svc import confirm_document_atomic, ConfirmError
            with pytest.raises(ConfirmError) as exc_info:
                confirm_document_atomic(
                    doc_id=doc_id, current_user=_user(), actor_id=USER_ID, comment="seal 실패 테스트",
                )
            assert exc_info.value.http_status == 500
            assert _count_archive(pg, doc_id) == 0, "archive 행 잔류 — 부분 커밋"
            assert _count_approval(pg, doc_id) == 0, "approval 행 잔류 — 부분 커밋"
            assert _current_status(pg, doc_id) == "REVIEW_PENDING"
        finally:
            cur.execute(
                "DROP TRIGGER IF EXISTS test_trg_block_seal ON public.runtime_document_data; "
                "DROP FUNCTION IF EXISTS public.fn_test_block_seal_update();"
            )

    # ── PGHOSTADDR 환경변수 통합 테스트 ──────────────────────────────

    def test_pg_env_pghostaddr_does_not_reroute(self, pg, monkeypatch):
        """PG-ENV — PGHOSTADDR=원격IP 환경변수 설정 시에도 safe params로 로컬 DB에 연결됨.

        libpq explicit 파라미터(hostaddr=127.0.0.1)가 PGHOSTADDR 환경변수보다 우선.
        실제 연결이 격리 DB로 이루어졌는지 SQL로 재확인.
        """
        monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
        conn = psycopg2.connect(**_SAFE_CONN_PARAMS)
        try:
            _assert_isolated_db(conn)
        finally:
            conn.close()
