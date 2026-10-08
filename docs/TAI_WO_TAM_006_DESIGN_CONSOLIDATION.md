# TAI-WO-TAM-006 — 공통 결재 모듈 설계 정합화

## 0. 문서 상태

```
DOCUMENT         = TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md
STATUS           = DESIGN CORRECTION — TAM-007 보정 적용, GPT 독립검증 전
BASIS            = TAM-006 DESIGN CONSOLIDATION (TAM-007 보정 적용)
                   TAM-006 CONDITIONAL PASS (GPT TAM-006 검증 결과)
                   Chemical WP-07I Semantic Contract v1
                   TAI API 기존 패턴 (work_permits, migrations)

WORK_TYPE        = DESIGN CONSOLIDATION (DOCS ONLY)
CODE_CHANGES     = 0
DB_WRITES        = 0
MIGRATIONS       = 0
DEPLOY           = 0
MERGE            = 0

IMPLEMENTATION   = BLOCKED — GPT 독립검증 + Owner 승인 필요
```

---

## 1. 설계 기준

```
MODULE           = TAM (TAI Common Approval Module)
HOST             = EXISTING TAI API service
DATABASE         = EXISTING TAI API PostgreSQL
IDENTITY         = TAI CORE (companies / factories / users)
LEGAL_SOT        = LEG

NEW_SERVER       = 0
NEW_DB_INSTANCE  = 0
LICENSE_FEE      = 0

STATE_ENGINE     = optional (transitions/python-statemachine MIT) — 교체 가능한 내부 구성요소
FLOWABLE         = OUT OF SCOPE
45CM_MEM         = DEFERRED
```

---

## 2. 아키텍처

```
┌──────────────────────────────────────────────────────┐
│                     TAI CORE                         │
│   companies / factories / users / roles              │
│   Bearer token → /auth/me identity verification      │
└──────────────────┬───────────────────────────────────┘
                   │ HTTP identity lookup
┌──────────────────▼───────────────────────────────────┐
│           TAM — TAI 공통 결재 모듈                     │
│   HOST: 기존 TAI API service (FastAPI)               │
│   DB:   기존 TAI API PostgreSQL                      │
│                                                      │
│  [Route Definition Layer]                            │
│    tam_approval_routes                               │
│    tam_approval_route_versions  (DRAFT→PUBLISHED)    │
│    tam_approval_route_steps                          │
│    tam_approval_step_assignees                       │
│                                                      │
│  [Execution Layer]                                   │
│    tam_approval_requests                             │
│    tam_approval_request_snapshots  (append-only)     │
│    tam_approval_decisions          (append-only)     │
│                                                      │
│  [Delegation Layer]                                  │
│    tam_approval_delegations                          │
│    tam_delegation_revocations      (append-only)     │
│                                                      │
│  [Revocation Layer]                                  │
│    tam_approval_effectiveness_revocations (append-only)
│                                                      │
│  [Audit Layer]                                       │
│    tam_approval_audit_events       (append-only)     │
└────────────────┬───────────────┬─────────────────────┘
                 │ HTTP           │ HTTP
    ┌────────────▼───┐   ┌────────▼─────────────┐
    │  TAI SAFE      │   │  TAI CHEMICAL        │
    │  (consumer)    │   │  (consumer)          │
    │  Safe DB       │   │  Chemical Supabase   │
    │                │   │  override_approvals  │
    └────────────────┘   │  override_revocations│
                         └──────────────────────┘
```

**설계 원칙:**
- TAM = 결재 상태 원장 전용; 업무 데이터·법령 판단 소유 없음
- Consumer = 업무 사실 + 선행조건 + 최종 실행 단독 주체
- State engine library = 선택적; 제거 시 DB 계약·API 그대로 유지
- Fail-closed: 결재경로 없음 / 권한 확인 불가 / TAM 불가 → 전부 BLOCK

---

## 3. 데이터 모델

### 3.1 `tam_approval_routes`

결재경로 식별 레지스트리.

```sql
CREATE TABLE tam_approval_routes (
    route_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID        NOT NULL,
    factory_id      UUID,                                   -- NULL = 회사 전체 범위
    route_scope     TEXT        NOT NULL,
        -- 'COMPANY_DEFAULT' | 'FACTORY_DEFAULT' | 'DOCUMENT_TYPE' | 'PROCESS_TYPE'
    scope_key       TEXT,                                   -- 문서/프로세스 유형 코드
                                                            -- DEFAULT scope는 NULL
    display_name    TEXT        NOT NULL,
    is_active       BOOLEAN     NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID        NOT NULL,
    current_version_id UUID,                                -- 최초 발행 전 NULL; 발행 시 원자적 갱신
                                                            -- FK는 순환참조로 versions 생성 후 추가 (아래)

    CONSTRAINT tam_routes_scope_chk CHECK (
        route_scope IN ('COMPANY_DEFAULT','FACTORY_DEFAULT','DOCUMENT_TYPE','PROCESS_TYPE')
    ),
    CONSTRAINT tam_routes_default_key_chk CHECK (
        (route_scope IN ('COMPANY_DEFAULT','FACTORY_DEFAULT') AND scope_key IS NULL)
        OR
        (route_scope IN ('DOCUMENT_TYPE','PROCESS_TYPE') AND scope_key IS NOT NULL)
    ),
    CONSTRAINT tam_routes_factory_default_requires_factory CHECK (
        route_scope != 'FACTORY_DEFAULT' OR factory_id IS NOT NULL
    )
);

-- current_version_id FK: 순환참조(routes → versions → routes)이므로 versions 테이블 생성 후 추가:
-- ALTER TABLE tam_approval_routes
--     ADD CONSTRAINT tam_routes_current_version_fk
--     FOREIGN KEY (current_version_id)
--     REFERENCES tam_approval_route_versions(version_id)
--     DEFERRABLE INITIALLY DEFERRED;

-- NULL 포함 복합 UNIQUE: PostgreSQL NULLS NOT DISTINCT (v15+)
-- 또는 하위 버전 대안: expression index 또는 partial unique index per scope
-- 구현 시 PG 버전 확인 필요 → OWNER_DECISION_REQUIRED: PG 버전 확정
CREATE UNIQUE INDEX tam_routes_uniq
    ON tam_approval_routes (
        company_id,
        COALESCE(factory_id, '00000000-0000-0000-0000-000000000000'),
        route_scope,
        COALESCE(scope_key, '')
    );

-- Indexes
CREATE INDEX ix_tam_routes_tenant ON tam_approval_routes (company_id, factory_id, is_active);
```

### 3.2 `tam_approval_route_versions`

결재경로 버전. DRAFT → PUBLISHED 라이프사이클.

```sql
CREATE TABLE tam_approval_route_versions (
    version_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id        UUID        NOT NULL
                                REFERENCES tam_approval_routes(route_id),
    version_number  INT         NOT NULL,       -- route_id당 1부터 순차 증가
    version_status  TEXT        NOT NULL DEFAULT 'DRAFT',
        -- 'DRAFT' | 'PUBLISHED'
        -- (SUPERSEDED 없음; 이전 PUBLISHED 버전은 이력으로 보존,
        --  현재 버전은 tam_approval_routes.current_version_id 포인터로 지정)
    notes           TEXT,
    published_at    TIMESTAMPTZ,               -- PUBLISHED 전이 시 기록
    published_by    UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID        NOT NULL,

    CONSTRAINT tam_route_ver_status_chk CHECK (
        version_status IN ('DRAFT','PUBLISHED')
    ),
    CONSTRAINT tam_route_ver_published_fields CHECK (
        version_status != 'PUBLISHED'
        OR (published_at IS NOT NULL AND published_by IS NOT NULL)
    ),
    UNIQUE (route_id, version_number)
);

-- route_id당 PUBLISHED 버전은 1개만
CREATE UNIQUE INDEX tam_route_ver_single_published
    ON tam_approval_route_versions (route_id)
    WHERE version_status = 'PUBLISHED';

-- 현재 버전 선택: tam_approval_routes.current_version_id → 현재 활성 버전 (원자적 포인터 교체)
-- PUBLISHED 버전은 이력으로 다수 존재 가능; current_version_id가 활성 버전 지정
-- (tam_route_ver_single_published partial index 제거됨 — 포인터 방식으로 대체)

-- Append-only policy (PUBLISHED 버전 내용 전체 불변):
-- BEFORE UPDATE trigger: old.version_status = 'PUBLISHED' → RAISE EXCEPTION (내용·상태 변경 금지)
--   DRAFT → PUBLISHED 전이만 허용: old.version_status = 'DRAFT' 이므로 trigger 미발동
-- BEFORE DELETE trigger: RAISE EXCEPTION (모든 버전 삭제 금지)

-- Index
CREATE INDEX ix_tam_route_ver_route ON tam_approval_route_versions (route_id, version_status);
```

**DRAFT/PUBLISHED 라이프사이클:**
- 생성 시: version_status = 'DRAFT'
- 단계/결재자 편집: DRAFT 상태에서만 허용
- 발행(Publish): DRAFT → PUBLISHED; 동일 트랜잭션에서 tam_approval_routes.current_version_id 교체
- 신규 버전 발행: 기존 PUBLISHED 버전은 불변 이력으로 유지; 신규 DRAFT 생성 → 발행 → current_version_id 교체
- PUBLISHED: 이후 버전 내용·steps·assignees 일체 변경 금지 (트리거 강제)

### 3.3 `tam_approval_route_steps`

버전별 결재 단계.

```sql
CREATE TABLE tam_approval_route_steps (
    step_id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id       UUID    NOT NULL
                             REFERENCES tam_approval_route_versions(version_id),
    step_order       INT     NOT NULL,          -- 1-based
    step_name        TEXT    NOT NULL,
    step_type        TEXT    NOT NULL,
        -- 'SEQUENTIAL' | 'PARALLEL_ANY' | 'PARALLEL_ALL'
    allow_supplement BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT tam_steps_type_chk CHECK (
        step_type IN ('SEQUENTIAL','PARALLEL_ANY','PARALLEL_ALL')
    ),
    UNIQUE (version_id, step_order)
);

-- steps 삽입/수정: version_status = 'DRAFT'인 경우만 허용
-- BEFORE INSERT/UPDATE trigger: SELECT version_status FROM tam_approval_route_versions
--   WHERE version_id = NEW.version_id → 'DRAFT' 아니면 RAISE EXCEPTION

-- Index
CREATE INDEX ix_tam_steps_version ON tam_approval_route_steps (version_id, step_order);
```

### 3.4 `tam_approval_step_assignees`

단계별 명시적 결재자. 이 목록에 없는 사용자는 처리 불가.

```sql
CREATE TABLE tam_approval_step_assignees (
    assignee_id  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    step_id      UUID        NOT NULL
                             REFERENCES tam_approval_route_steps(step_id),
    user_id      UUID        NOT NULL,          -- TAI Core user_id
    assigned_by  UUID        NOT NULL,
    assigned_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (step_id, user_id)
);

-- assignee 삽입/수정: version DRAFT인 경우만 허용 (step → version 경유 검증)
-- 발행 시 검증: 모든 step에 assignee >= 1명

-- Index
CREATE INDEX ix_tam_assignees_step    ON tam_approval_step_assignees (step_id);
CREATE INDEX ix_tam_assignees_user    ON tam_approval_step_assignees (user_id, step_id);
```

### 3.5 `tam_approval_requests`

결재 요청 실행상태. 진행 중 요청은 동일 business object당 1개.

```sql
CREATE TABLE tam_approval_requests (
    request_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Idempotency: 동일 (company_id, consumer_type, idempotency_key) = 동일 요청
    company_id           UUID        NOT NULL,
    consumer_type        TEXT        NOT NULL,  -- 'CHEMICAL' | 'SAFE'
    idempotency_key      TEXT        NOT NULL,

    factory_id           UUID,
    business_object_type TEXT        NOT NULL,
    business_object_id   UUID        NOT NULL,
    evidence_ref         TEXT,                  -- Consumer context ref (e.g. evaluation_id)

    -- Route resolution result
    resolved_route_id    UUID        REFERENCES tam_approval_routes(route_id),
    instance_route_id    UUID        REFERENCES tam_approval_routes(route_id),
    snapshot_id          UUID,                  -- set after snapshot created

    -- State
    status               TEXT        NOT NULL DEFAULT 'PENDING',
        -- 'PENDING' | 'IN_PROGRESS' | 'SUPPLEMENT_REQUESTED'
        -- | 'APPROVED' | 'REJECTED' | 'CANCELLED'
    current_step_order   INT,                   -- NULL until IN_PROGRESS
    current_round        INT         NOT NULL DEFAULT 1,

    -- Actor
    requested_by         UUID        NOT NULL,
    requested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at         TIMESTAMPTZ,

    -- Optimistic lock
    obj_version          INT         NOT NULL DEFAULT 1,

    CONSTRAINT tam_requests_status_chk CHECK (
        status IN ('PENDING','IN_PROGRESS','SUPPLEMENT_REQUESTED',
                   'APPROVED','REJECTED','CANCELLED')
    ),
    CONSTRAINT tam_requests_consumer_chk CHECK (
        consumer_type IN ('CHEMICAL','SAFE')
    ),

    -- Idempotency scope
    UNIQUE (company_id, consumer_type, idempotency_key)
);

-- 동일 object 진행 중 요청 1개 제한
CREATE UNIQUE INDEX tam_requests_active_uniq
    ON tam_approval_requests (company_id, business_object_type, business_object_id)
    WHERE status NOT IN ('APPROVED','REJECTED','CANCELLED');

-- Indexes
CREATE INDEX ix_tam_requests_tenant  ON tam_approval_requests (company_id, consumer_type, status);
CREATE INDEX ix_tam_requests_object  ON tam_approval_requests
    (company_id, business_object_type, business_object_id, status);
CREATE INDEX ix_tam_requests_by      ON tam_approval_requests (requested_by, status);
```

**Idempotency 규칙:**
- 동일 `(company_id, consumer_type, idempotency_key)` + 동일 Payload → 기존 요청 반환 (200)
- 동일 `(company_id, consumer_type, idempotency_key)` + 다른 Payload → 409 IDEMPOTENCY_CONFLICT
- Consumer의 company_id 신뢰 불가: 서버가 인증 컨텍스트에서 company_id 직접 주입

### 3.6 `tam_approval_request_snapshots`

요청 생성 시 결재선 고정. Append-only.

```sql
CREATE TABLE tam_approval_request_snapshots (
    snapshot_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id         UUID        NOT NULL UNIQUE
                                   REFERENCES tam_approval_requests(request_id),
    source_version_id  UUID        REFERENCES tam_approval_route_versions(version_id),
        -- NULL: instance override 또는 ad-hoc route
    snapshot_data      JSONB       NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- snapshot_data schema:
-- {
--   "route_scope": "DOCUMENT_TYPE",
--   "scope_key": "WMS_PUTAWAY_OVERRIDE",
--   "steps": [
--     {
--       "step_order": 1,
--       "step_name": "Safety Officer Review",
--       "step_type": "SEQUENTIAL",
--       "allow_supplement": false,
--       "assignees": [
--         {"user_id": "uuid", "display_name": "홍길동"}
--       ]
--     }
--   ]
-- }

-- Append-only:
-- BEFORE UPDATE → RAISE EXCEPTION
-- BEFORE DELETE → RAISE EXCEPTION

CREATE INDEX ix_tam_snapshots_request ON tam_approval_request_snapshots (request_id);
```

### 3.7 `tam_approval_decisions`

결재 결정 이력. Append-only. 재상신(round) 개념 포함.

```sql
CREATE TABLE tam_approval_decisions (
    decision_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id           UUID        NOT NULL
                                     REFERENCES tam_approval_requests(request_id),
    step_order           INT         NOT NULL,
    decision_round       INT         NOT NULL DEFAULT 1,
        -- 보완요청 후 재상신 시 증가; 같은 결재자가 새 round에서 다시 처리 가능
    actor_user_id        UUID        NOT NULL,  -- 실제 처리한 사람
    on_behalf_of_user_id UUID,                  -- 위임 원 결재자 (대리결재 시)
    delegation_id        UUID,                  -- 사용한 위임 ID
    idempotency_key      TEXT        NOT NULL,  -- Consumer 제공 (중복 결재 방지)
    decision             TEXT        NOT NULL,
        -- 'APPROVED' | 'REJECTED' | 'SUPPLEMENT_REQUESTED' | 'RESUBMITTED'
    comment              TEXT,
    decided_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT tam_decisions_type_chk CHECK (
        decision IN ('APPROVED','REJECTED','SUPPLEMENT_REQUESTED','RESUBMITTED')
    ),
    -- 동일 (request, step, round, actor) 중복 결재 방지
    UNIQUE (request_id, step_order, decision_round, actor_user_id),
    -- 중복 결재 idempotency
    UNIQUE (request_id, step_order, decision_round, idempotency_key)
);

-- Append-only:
-- BEFORE UPDATE → RAISE EXCEPTION
-- BEFORE DELETE → RAISE EXCEPTION

-- Indexes
CREATE INDEX ix_tam_decisions_request ON tam_approval_decisions (request_id, step_order, decision_round);
CREATE INDEX ix_tam_decisions_actor   ON tam_approval_decisions (actor_user_id, decided_at DESC);
```

**decision_round 규칙:**
- 최초 요청: round = 1
- SUPPLEMENT_REQUESTED 후 RESUBMITTED: round += 1
- 이전 round의 결정은 변경 불가 (append-only)
- 같은 결재자도 새 round에서 동일 step 재처리 가능

### 3.8 `tam_approval_delegations`

대리결재 설정.

```sql
CREATE TABLE tam_approval_delegations (
    delegation_id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id            UUID        NOT NULL,
    factory_id            UUID,
    delegator_user_id     UUID        NOT NULL,
    delegate_user_id      UUID        NOT NULL,

    -- 기간: [valid_from, valid_until) 반개구간
    -- tstzrange + Exclusion Constraint 사용 (btree_gist extension 필요)
    validity_range        TSTZRANGE   NOT NULL,

    scope_consumer_type   TEXT,           -- NULL = 전 Consumer
    scope_business_type   TEXT,           -- NULL = 전 문서/프로세스 유형
    is_active             BOOLEAN     NOT NULL DEFAULT true,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by            UUID        NOT NULL,

    CONSTRAINT tam_deleg_no_self CHECK (delegator_user_id != delegate_user_id),
    CONSTRAINT tam_deleg_valid_range CHECK (
        lower(validity_range) IS NOT NULL
        AND upper(validity_range) IS NOT NULL
        AND lower(validity_range) < upper(validity_range)
    )
);

-- btree_gist extension 활성화 필요 (TAI API DB 기존 상태 확인 → OWNER_DECISION_REQUIRED)
-- Exclusion Constraint: 동일 (delegator, delegate, scope) 기간 중복 방지
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE tam_approval_delegations ADD CONSTRAINT tam_deleg_no_overlap
    EXCLUDE USING GIST (
        delegator_user_id   WITH =,
        delegate_user_id    WITH =,
        COALESCE(scope_consumer_type,'') WITH =,
        COALESCE(scope_business_type,'') WITH =,
        validity_range      WITH &&
    )
    WHERE (is_active = true);

-- Note: now()를 Partial Unique Index 조건에 사용하지 않음
-- is_valid() 판정은 application layer에서 수행

-- Indexes
CREATE INDEX ix_tam_deleg_delegator ON tam_approval_delegations (delegator_user_id, is_active);
CREATE INDEX ix_tam_deleg_delegate  ON tam_approval_delegations (delegate_user_id, is_active);
```

**is_valid() 판정 (application layer):**
```python
def is_valid(delegation, now: datetime, request) -> bool:
    return (
        delegation.is_active
        and lower(delegation.validity_range) <= now < upper(delegation.validity_range)
        and (delegation.scope_consumer_type is None
             or delegation.scope_consumer_type == request.consumer_type)
        and (delegation.scope_business_type is None
             or delegation.scope_business_type == request.business_object_type)
    )
```

**대리결재 제약:**
- 자기위임: DB CHECK 금지
- 동일 범위 기간 중복: Exclusion Constraint 금지 (동일 delegator + delegate + scope 조합 기준)
- 순환위임: application layer 검증 (A→B 생성 시 B→A 활성 여부 확인)
- 연쇄위임: 금지 (B가 A에게 받은 권한을 C에게 재위임 불가 — application layer)
- 권한 초과: delegate는 delegator가 assignee로 지정된 범위에서만 처리 가능
- 다중 위임 (동일 위임자가 서로 다른 대리자에게 동일 결재권한 위임): Exclusion Constraint 적용 범위 밖으로 현재 허용됨; 정책 미확정 → G-06

### 3.9 `tam_delegation_revocations`

대리결재 취소 이벤트. Append-only.

```sql
CREATE TABLE tam_delegation_revocations (
    revocation_id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    delegation_id   UUID        NOT NULL
                                REFERENCES tam_approval_delegations(delegation_id),
    revoked_by      UUID        NOT NULL,
    revoked_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason          TEXT,

    UNIQUE (delegation_id)  -- 동일 위임에 중복 취소 방지
);

-- Side effect: INSERT 와 is_active 변경을 반드시 동일 DB 트랜잭션으로 처리:
--   BEGIN;
--     INSERT INTO tam_delegation_revocations (delegation_id, revoked_by, reason) VALUES (...);
--     UPDATE tam_approval_delegations SET is_active = false WHERE delegation_id = ...;
--   COMMIT;
-- Append-only:
-- BEFORE UPDATE → RAISE EXCEPTION
-- BEFORE DELETE → RAISE EXCEPTION
```

### 3.10 `tam_approval_effectiveness_revocations`

**승인 완료 효력 철회.** 완료된 요청의 결재기록은 수정하지 않는다. 별도 이벤트로 효력을 무효화한다.

```sql
CREATE TABLE tam_approval_effectiveness_revocations (
    revocation_id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id      UUID        NOT NULL UNIQUE
                                REFERENCES tam_approval_requests(request_id),
    revoked_by      UUID        NOT NULL,
    revoked_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason          TEXT        NOT NULL,

    -- 효력 철회는 APPROVED 상태의 요청에만 가능
    -- application layer 검증: request.status == 'APPROVED'
);

-- Append-only:
-- BEFORE UPDATE → RAISE EXCEPTION
-- BEFORE DELETE → RAISE EXCEPTION

CREATE INDEX ix_tam_eff_rev_request ON tam_approval_effectiveness_revocations (request_id);
```

**승인 상태 vs. 요청 취소 vs. 효력 철회 구분:**

| 행위 | 대상 상태 | 결과 | 원본 기록 |
|---|---|---|---|
| 요청 취소 (cancel) | PENDING / IN_PROGRESS / SUPPLEMENT_REQUESTED | status → CANCELLED | 변경됨 (status UPDATE) |
| 효력 철회 (revoke) | APPROVED | 원본 APPROVED 유지, 별도 revocation 이벤트 | **불변** |

**effective_approval_valid() 판정 (application layer):**
```python
def effective_approval_valid(request_id: str, now: datetime) -> bool:
    request = get_request(request_id)
    if request.status != 'APPROVED':
        return False
    revocation = get_effectiveness_revocation(request_id)
    if revocation:
        return False
    # TAM_APPROVED 만료 기간은 OWNER_DECISION_REQUIRED
    # expires_at이 구현되면 추가: if now >= request.approved_at + TTL: return False
    return True
```

### 3.11 `tam_approval_audit_events`

전체 감사 이벤트 원장. Append-only.

```sql
CREATE TABLE tam_approval_audit_events (
    audit_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID        NOT NULL,
    request_id      UUID,                   -- route 관리 이벤트는 NULL
    event_type      TEXT        NOT NULL,
    actor_user_id   UUID        NOT NULL,
    event_data      JSONB       NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- event_type 값:
--   ROUTE_CREATED | ROUTE_VERSION_DRAFT_CREATED | ROUTE_VERSION_PUBLISHED
--   REQUEST_SUBMITTED | REQUEST_ACTIVATED
--   STEP_APPROVED | STEP_REJECTED | STEP_SUPPLEMENT_REQUESTED | STEP_RESUBMITTED
--   REQUEST_APPROVED | REQUEST_REJECTED | REQUEST_CANCELLED
--   DELEGATION_CREATED | DELEGATION_REVOKED
--   APPROVAL_EFFECTIVENESS_REVOKED

-- Append-only:
-- BEFORE UPDATE → RAISE EXCEPTION
-- BEFORE DELETE → RAISE EXCEPTION
-- GRANT SELECT, INSERT ON tam_approval_audit_events TO service_role
-- (UPDATE, DELETE GRANT 없음)

CREATE INDEX ix_tam_audit_request    ON tam_approval_audit_events (company_id, request_id, occurred_at DESC);
CREATE INDEX ix_tam_audit_event_type ON tam_approval_audit_events (company_id, event_type, occurred_at DESC);
CREATE INDEX ix_tam_audit_compliance ON tam_approval_audit_events (company_id, occurred_at DESC);
```

**트랜잭션 보장:**
상태 변경(tam_approval_requests UPDATE)과 감사이벤트(tam_approval_audit_events INSERT)는 반드시 동일 PostgreSQL 트랜잭션에서 실행된다.

---

## 4. 결재경로 우선순위

```
우선순위 (높음 → 낮음):
  1. instance_route_id 명시 제공
     → 해당 route_id의 PUBLISHED 버전 사용
     → route 접근 권한 및 필수 단계 검증 필수
  2. process_type route
     → (company_id, factory_id, 'PROCESS_TYPE', scope_key=process_type)
     → factory_id 없으면 (company_id, NULL, 'PROCESS_TYPE', scope_key)
  3. document_type route
     → (company_id, factory_id, 'DOCUMENT_TYPE', scope_key=document_type)
     → factory_id 없으면 (company_id, NULL, 'DOCUMENT_TYPE', scope_key)
  4. factory_default route
     → (company_id, factory_id, 'FACTORY_DEFAULT', NULL)  — factory_id 있을 때만
  5. company_default route
     → (company_id, NULL, 'COMPANY_DEFAULT', NULL)
  6. 없음 → FAIL-CLOSED: 422 NO_APPROVAL_ROUTE_FOUND
```

**Document + Process 동시 해당 충돌 규칙:**
- Consumer가 `route_type_hint: 'DOCUMENT_TYPE' | 'PROCESS_TYPE'` 명시 필수
- 미제공 시 → 422 AMBIGUOUS_ROUTE (자동 선택 없음)

---

## 5. 상태전이 및 결재 실행 계약

### 5.1 상태 정의

```
PENDING              요청 생성, snapshot 미완성 또는 첫 단계 미활성
IN_PROGRESS          결재 진행 중 (첫 단계 활성화됨)
SUPPLEMENT_REQUESTED 보완요청 대기 (요청자 응답 필요, 단계 중단)
APPROVED             모든 단계 완료 [terminal]
REJECTED             단계 반려 [terminal]
CANCELLED            요청 취소 [terminal]
```

### 5.2 허용된 전이

```
PENDING              → IN_PROGRESS           (snapshot 완성 후 자동)
PENDING              → CANCELLED             (요청자 또는 권한자 취소)
IN_PROGRESS          → IN_PROGRESS           (단계 완료 → 다음 단계)
IN_PROGRESS          → SUPPLEMENT_REQUESTED  (결재자 보완요청)
IN_PROGRESS          → APPROVED              (최종 단계 완료)
IN_PROGRESS          → REJECTED              (단계 반려)
IN_PROGRESS          → CANCELLED             (권한자 취소)
SUPPLEMENT_REQUESTED → IN_PROGRESS           (요청자 재상신, round += 1)
SUPPLEMENT_REQUESTED → CANCELLED             (요청자 철회)
APPROVED             → [terminal, no further state change]
REJECTED             → [terminal]
CANCELLED            → [terminal]
```

### 5.3 단계 완료 판정

```
SEQUENTIAL:
  지정 결재자 1명 APPROVED → 단계 완료, 다음 단계 활성화
  REJECTED → 요청 REJECTED

PARALLEL_ANY:
  지정자 중 1명 APPROVED → 단계 완료 (나머지 미처리 결정은 무시)
  1명이라도 REJECTED → 요청 REJECTED

PARALLEL_ALL:
  지정자 전원 APPROVED → 단계 완료
  1명이라도 REJECTED → 요청 REJECTED
  1명이라도 SUPPLEMENT_REQUESTED → 요청 SUPPLEMENT_REQUESTED 전이
```

### 5.4 동시성 제어 (PARALLEL_ALL 마지막 승인자 경합)

```sql
-- 결재 처리 내부 흐름 (단일 DB 트랜잭션):
BEGIN;
  SELECT * FROM tam_approval_requests
    WHERE request_id = $1
    FOR UPDATE;                         -- row lock 획득
  -- obj_version 검증 (optimistic lock)
  -- decision INSERT (append-only)
  -- 단계 완료 판정 (현재 round의 decisions 재계산)
  -- 완료 시: status/current_step_order UPDATE + obj_version += 1
  -- 감사이벤트 INSERT (동일 트랜잭션)
COMMIT;

-- 동시 처리 결과:
-- 첫 번째 transaction: lock → 단계 완료 판정 → APPROVED 기록 → COMMIT
-- 두 번째 transaction: 대기 → lock 해제 후 재조회 → 단계 이미 완료
-- → 409 STEP_ALREADY_COMPLETED (idempotent 반환)
```

### 5.5 재상신(RESUBMIT) 시 round 처리

```
요청 상태: SUPPLEMENT_REQUESTED
재상신 시:
  1. tam_approval_decisions INSERT (decision='RESUBMITTED', step=current_step, round=current_round)
  2. tam_approval_requests UPDATE (status='IN_PROGRESS', current_round += 1)
  3. tam_approval_audit_events INSERT (STEP_RESUBMITTED)
  ← 동일 트랜잭션

다음 round에서 결재자가 다시 처리:
  → tam_approval_decisions INSERT (step=current_step, round=current_round+1, actor=...)
  → 이전 round의 기록은 불변
```

---

## 6. 권한 모델

```
TAM 업무 권한 (6종):
  ROUTE_MANAGER        결재경로 생성, 버전 DRAFT 편집, 버전 발행
  ASSIGNEE_MANAGER     단계별 결재자 지정 (DRAFT 버전 한정)
  REQUEST_SUBMITTER    결재 요청 제출 (Consumer service 또는 end user)
  STEP_APPROVER        단계 결재 처리 (snapshot 명시 지정자 + active delegation)
  DELEGATION_MANAGER   대리결재 생성·취소
  REQUEST_REVOKER      진행 중 요청 취소 / 완료 승인 효력 철회
```

**STEP_APPROVER 검증 순서:**

```python
def can_approve(actor_user_id, request, step_order, now):
    # 1. 요청 상태 확인
    if request.status not in ('IN_PROGRESS', 'SUPPLEMENT_REQUESTED'):
        raise WRONG_STATUS

    # 2. 현재 단계 확인
    if step_order != request.current_step_order:
        raise WRONG_STEP_ORDER

    # 3. 자기승인 금지
    if actor_user_id == request.requested_by:
        raise SELF_APPROVAL_FORBIDDEN

    # 4. snapshot에서 해당 step assignees 조회
    snapshot_assignees = get_snapshot_step_assignees(request.snapshot_id, step_order)

    # 4a. 직접 assignee
    if actor_user_id in snapshot_assignees:
        return True, None  # (가능, delegation_id=None)

    # 4b. 활성 위임 확인
    for delegation in get_active_delegations(delegate_user_id=actor_user_id, now=now):
        if delegation.delegator_user_id in snapshot_assignees:
            if is_valid(delegation, now, request):
                # 권한 초과 검증: delegator가 실제 assignee인지 이미 확인됨
                return True, delegation.delegation_id

    raise FORBIDDEN_NOT_ASSIGNEE
```

**최초 ROUTE_MANAGER 부트스트랩:**
- 회사별 첫 ROUTE_MANAGER 지정 권한자 = `OWNER_DECISION_REQUIRED`
- 결정 전: 모든 route 생성 BLOCK

---

### 6.2 테넌트 격리 무결성

| 엔티티 | company_id 직접 보유 | FK 체인 | 교차회사 참조 위험 |
|---|---|---|---|
| tam_approval_routes | O (NOT NULL) | — | company_id NOT NULL으로 격리 |
| tam_approval_route_versions | X | route_id → routes.company_id | 서비스: route 접근 시 ctx.company_id 검증 |
| tam_approval_route_steps | X | version_id → versions → routes | 서비스: route 체인 추적 |
| tam_approval_step_assignees | X | step_id → steps → versions → routes | 서비스: route 체인 추적 |
| tam_approval_requests | O (NOT NULL) | resolved_route_id → routes | 서비스: routes.company_id == ctx.company_id 검증 필수 |
| tam_approval_request_snapshots | X | request_id → requests.company_id | 서비스: request 접근 시 company_id 검증 |
| tam_approval_decisions | X | request_id → requests.company_id | 서비스: request 접근 시 company_id 검증 |
| tam_approval_delegations | O (NOT NULL) | — | company_id NOT NULL으로 격리 |
| tam_delegation_revocations | X | delegation_id → delegations.company_id | 서비스: delegation 접근 시 company_id 검증 |
| tam_approval_effectiveness_revocations | X | request_id → requests.company_id | 서비스: request 접근 시 company_id 검증 |
| tam_approval_audit_events | O (NOT NULL) | — | company_id NOT NULL으로 격리 |

**DB 수준 교차회사 참조 한계 및 서비스 계층 의무:**
- TAM은 service_role로 실행하므로 RLS 없음
- company_id 직접 보유 엔티티: NOT NULL + 서비스 계층이 `ctx.company_id` 주입으로 강제
- FK 체인 엔티티: DB에 company_id 없음 → 서비스 계층 필수 검증 목록:
  1. route 조회·사용 시: `routes.company_id == ctx.company_id`
  2. request 처리 시: `requests.company_id == ctx.company_id`
  3. delegation 처리 시: `delegations.company_id == ctx.company_id`
  4. version/step/assignee 접근 시: route_id 경유 company_id 검증

---

## 7. Chemical 연동 계약

### 7.1 불변식

```
TAM APPROVED != COMPATIBILITY OK

Fresh Evaluation 흐름 (WP-07I §5.1 준수):
  POST /wms/{type}/{id}/post (Chemical API, with override_approval_id)
    1. TAM effective_approval_valid(tam_request_id) 확인
       → false → 403 WMS_TAM_APPROVAL_NOT_EFFECTIVE
       → network/5xx → FAIL-CLOSED → 503 WMS_TAM_UNAVAILABLE
    2. Fresh Compatibility Evaluation (WmsCompatibilityService)
       → OK     → Existing Posting Gate (변경 없음)
       → WARNING → Existing Acknowledgement Gate (변경 없음)
       → REVIEW_REQUIRED → BLOCK (TAM APPROVED여도 반드시 BLOCK)
       → BLOCK  → BLOCK (TAM APPROVED여도 반드시 BLOCK)
    3. Posting RPC 호출 (wms_post_putaway_v1 / wms_post_transfer_v1 — 수정 금지)
```

### 7.2 Chemical override_approvals 분리 (WP-07I §7.3)

WP-07I의 `override_approvals` 테이블은 **Chemical Supabase DB**에 존재하며 TAM과 별개다.

```
override_approvals (Chemical Supabase DB) — WP-07I §7.3 정의
  override_approval_id  UUID PK
  company_id / factory_id
  material_code / destination_location_id   ← WP-07I override scope
  evaluation_ref                            ← REVIEW_REQUIRED 평가 링크
  tam_request_id        UUID                ← TAM request 참조 (신규 추가 예정)
  approved_by / approved_at
  expires_at            TIMESTAMPTZ         ← DEFAULT now() + INTERVAL '24 hours'
  override_reason       TEXT

override_revocations (Chemical Supabase DB) — WP-07I §7.3 정의
  (별도 append-only 테이블)
```

**TAM → Chemical 연결 경로:**
```
TAM request APPROVED
  → Chemical: POST /tam/requests/{tam_request_id}/approve-context 호출
    (또는 polling GET /tam/requests/{tam_request_id})
  → Chemical: override_approvals INSERT
     (tam_request_id + material_code + destination_location_id + evaluation_ref + expires_at)
  → Chemical: POST /wms/{type}/{id}/post with override_approval_id
```

**override scope (WP-07I §5.2.4 준수):**
- (company_id, factory_id, material_code, destination_location_id, evaluation_ref)
- TAM은 이 scope를 모름; Chemical이 결재 완료 시 scope 바인딩

**override TTL (WP-07I §5.2.5 준수):**
- expires_at = Chemical이 override_approvals 생성 시 결정 (default 24h)
- TAM approval 자체 만료와 독립적 (TAM approval TTL = `OWNER_DECISION_REQUIRED`)

### 7.3 BLOCK 불변식 (WP-07I §4.3 준수)

```
BLOCK은 승인으로 해제할 수 없다.

TAM approval이 APPROVED 상태여도:
  Fresh Evaluation 결과 BLOCK → Posting 거부
  Provider가 BLOCK을 반환한 경우 어떤 override도 존재하지 않는다.
  기존 wms_putaway_post_guard / wms_transfer_post_guard trigger 변경 없음.
```

---

## 8. 교차 DB 정합성 계약

TAM DB(TAI API PostgreSQL)와 Chemical DB(Supabase) 간 분산 트랜잭션 없음.

TAM 승인 조회 후 효력 철회가 발생할 수 있는 TOCTOU 문제는 **"짧은 시간"을 근거로 수용하지 않는다.**

다음 계약을 구현 전에 확정한다:

### 8.1 권한 사용 시점 재검증

```
Chemical Posting Gate (단계 순서):
  1. TAM effective_approval_valid() 동기 확인 (HTTP GET)
  2. Fresh Compatibility Evaluation
  3. wms_post_{type}_v1 RPC (SELECT FOR UPDATE on wms_documents 포함)

(1)과 (3) 사이의 TOCTOU 구간:
  TAM 효력 철회가 이 구간에 발생하면 Chemical은 인식 불가
  → Posting이 완료됨

사후 감지 가능:
  tam_approval_effectiveness_revocations.revoked_at
  vs. Chemical context table의 posted_at 비교로 불일치 탐지 가능
  → 감사 불일치 기록 가능하나 실시간 방지는 불가
```

### 8.2 구현 전 확정 필요 사항 (OWNER_DECISION_REQUIRED)

다음 중 하나 이상을 선택해야 한다:

| 옵션 | 설명 | 트레이드오프 |
|---|---|---|
| A. 수용 + 감사 기록 | TOCTOU 구간 인정, 사후 감사 불일치 기록 | 구현 단순, 미사용 허가가 Posted에 남을 수 있음 |
| B. 짧은 TTL 승인 사용권 | Chemical이 TAM에서 단기(예: 5분) 사용 토큰 발급받아 사용 | 별도 토큰 발급 API 필요 |
| C. 철회·사용 명시적 직렬화 | Chemical POST 전 TAM에 "사용 예약" API 호출, 철회와 직렬화 | TAM API 복잡도 증가 |
| D. Chemical 측 compensating event | Posting 완료 후 TAM에 "사용 완료" 이벤트 → TAM이 이중 사용 방지 | 단방향 이벤트, 사후 reconciliation |

**GPT 판정 (TAM-007 검증 결과):**
- A안 (감사 수용): 승인 철회 후 Posting 진행 가능성 잔존 — **거부**
- B안 (짧은 TTL): 철회와 사용의 원자성 미보장 — **거부**
- C안 (직렬화): Chemical POST 전 TAM에 "사용 예약" 또는 이에 준하는 원자적 직렬화 계약 → 설계 대상
- D안 (compensating event): 단방향 이벤트로 원자성 부족; C안 보완으로 검토 가능

**현재 상태: BLOCKED — C안 이상의 원자적 안전성 계약 확정 전 구현 불가**

### 8.3 장애 계약

```
시나리오 1: TAM APPROVED, Chemical POST 미호출
  → Chemical retry 가능 (idempotency_key 기반)
  → TAM 요청 APPROVED 유지
  → TAM TTL 도입 시: 만료 전 retry 필요

시나리오 2: TAM APPROVED, Chemical fresh eval → REVIEW_REQUIRED
  → Chemical BLOCK (WP-07I §5.1 준수)
  → Consumer: TAM 효력 철회 → 새 요청 제출
  → TAM은 자동 처리 없음; Consumer 명시 취소 필요

시나리오 3: TAM 서비스 불가
  → Chemical FAIL-CLOSED
  → 503 WMS_TAM_UNAVAILABLE
  → Posting 불가; TAM 복구 후 retry

시나리오 4: Chemical Posting 실패 (Supabase 오류)
  → TAM 요청 APPROVED 유지
  → Chemical retry with same idempotency_key
```

---

## 9. API 계약 (요약)

```
Route Management:
  POST   /tam/routes
  POST   /tam/routes/{id}/versions             (DRAFT 생성)
  PATCH  /tam/routes/{id}/versions/{vid}       (DRAFT 편집)
  POST   /tam/routes/{id}/versions/{vid}/publish (PUBLISHED 전이)
  GET    /tam/routes/{id}/versions/{vid}

Request Lifecycle:
  POST   /tam/requests                         (idempotent)
  GET    /tam/requests/{id}
  POST   /tam/requests/{id}/steps/{n}/decide
  POST   /tam/requests/{id}/resubmit
  POST   /tam/requests/{id}/cancel
  POST   /tam/requests/{id}/revoke-effectiveness

Delegation:
  POST   /tam/delegations
  POST   /tam/delegations/{id}/revoke
  GET    /tam/delegations (my active delegations)

Audit:
  GET    /tam/requests/{id}/audit
  GET    /tam/audit (company-level, admin only)
```

---

## 10. 테스트 설계 매핑 (T01–T25)

| ID | 테스트 | TAM 구성요소 |
|---|---|---|
| T01 | 회사 기본 결재선 | route_resolution: COMPANY_DEFAULT |
| T02 | 사업장 기본 결재선 | route_resolution: FACTORY_DEFAULT |
| T03 | 문서별 결재선 | route_resolution: DOCUMENT_TYPE |
| T04 | 프로세스별 결재선 | route_resolution: PROCESS_TYPE |
| T05 | 개별 요청 결재선 | instance_route_id 제공 |
| T06 | 미지정 결재자 접근거부 | STEP_APPROVER 검증 → FORBIDDEN_NOT_ASSIGNEE |
| T07 | 다른 회사 접근거부 | tenant isolation (company_id row filter) |
| T08 | 자기승인 금지 | SELF_APPROVAL_FORBIDDEN check |
| T09 | 순차 결재 | SEQUENTIAL step_type |
| T10 | 병렬 ANY | PARALLEL_ANY: 1명 승인 → 완료 |
| T11 | 병렬 ALL | PARALLEL_ALL: 전원 승인 필요 |
| T12 | 동시 결재 | SELECT FOR UPDATE + obj_version |
| T13 | 보완요청·재상신 | SUPPLEMENT_REQUESTED → RESUBMITTED → round++ |
| T14 | 결재경로 버전 고정 | snapshot_data 불변 검증 |
| T15 | 대리결재 기간만료 | validity_range upper bound 초과 → FORBIDDEN |
| T16 | 대리결재 범위초과 | scope_consumer_type/scope_business_type 불일치 |
| T17 | 대리결재 철회 | tam_delegation_revocations → is_active=false |
| T18 | 원본 승인효력 철회 | tam_approval_effectiveness_revocations; decisions 불변 확인 |
| T19 | 중복 요청·Idempotency | 동일 idempotency_key → 기존 반환 / 다른 payload → 409 |
| T20 | 감사 원장 불변성 | tam_approval_audit_events UPDATE/DELETE → RAISE EXCEPTION |
| T21 | Chemical BLOCK 우회 금지 | TAM APPROVED + fresh BLOCK → Posting 거부 |
| T22 | Chemical REVIEW_REQUIRED 우회 금지 | TAM APPROVED + fresh REVIEW_REQUIRED → Posting 거부 |
| T23 | Chemical 승인 만료 | override_approvals.expires_at 경과 → Posting 거부 |
| T24 | TAM 장애 시 Fail-closed | TAM API 5xx → Chemical 503 반환 |
| T25 | 승인 철회와 Posting 경합 | §8.1 TOCTOU 계약 — 8.2 옵션 확정 후 설계 |

---

## 11. SEMANTIC_CONFLICTS

WP-07I Semantic Contract와 TAM-006 설계 충돌 분석:

| # | 항목 | WP-07I 기준 | TAM-006 설계 | 충돌 여부 | 해소 |
|---|---|---|---|---|---|
| 1 | override_approvals 위치 | Chemical Supabase DB | TAM DB (TAI API PG) | **설계 분리** | override_approvals = Chemical DB (WP-07I 준수); TAM = 결재 상태만 보유; Chemical이 TAM request_id를 override_approvals에 참조 저장 |
| 2 | BLOCK 불변 | BLOCK 승인 해제 금지 | TAM APPROVED → Chemical fresh eval BLOCK 가능 | **일치** | TAM APPROVED ≠ Posting 허용; Fresh eval 결과가 항상 우선 |
| 3 | WMS Posting RPC 수정 금지 | wms_post_putaway_v1 등 수정 금지 | TAM API 별도 경로 | **일치** | TAM은 Posting RPC에 관여 없음 |
| 4 | override 적용 범위 | company_id/factory_id/material_code/destination_location_id/evaluation_ref | TAM request: business_object_id만 | **일치 (분리 설계)** | Scope 바인딩은 Chemical override_approvals 생성 시 Chemical이 수행; TAM은 scope 모름 |
| 5 | 기본 TTL 24h | override expires_at default 24h | TAM approval TTL = OWNER_DECISION_REQUIRED | **부분 충돌** | Chemical override_approvals.expires_at = 24h default (WP-07I 준수); TAM approval TTL은 별도 결정 필요 |
| 6 | is_valid 저장 금지 | effective validity = 매번 계산, 저장 없음 | TAM: effective_approval_valid() = computed | **일치** | TAM도 저장 없이 매 사용 시 계산 |
| 7 | override record 불변 | override_approvals append-only | tam_approval_decisions append-only; effectiveness_revocations 별도 | **일치** | 두 계층 모두 원본 불변 + 별도 revocation 이벤트 |
| 8 | REVIEW_REQUIRED re-eval 필수 | Fresh evaluation 결과가 Posting 결정 | TAM APPROVED + fresh eval 결과 우선 | **일치** | §7.1 계약에 명시 |

---

## 12. OWNER_DECISION_REQUIRED

구현 전 Owner 승인이 필요한 미결정 항목:

| # | 항목 | 옵션 | 비고 |
|---|---|---|---|
| OD-01 | 최초 ROUTE_MANAGER 부트스트랩 권한 | (a) TAI Core company owner role, (b) TAI 플랫폼 관리자 | 결정 전 route 생성 전면 BLOCK |
| OD-02 | TAM APPROVED 효력 만료 기간 | (a) 만료 없음, (b) 24h default, (c) Consumer별 설정 | Chemical override TTL(24h)과 조율 필요 |
| OD-03 | 교차 DB TOCTOU 계약 옵션 | §8.2 옵션 A/B/C/D | T25 테스트 설계 차단 |
| OD-04 | btree_gist extension 상태 | TAI API PostgreSQL에 기존 활성 여부 확인 | 위임 Exclusion Constraint 사용 전제 |
| OD-05 | PostgreSQL 버전 확인 | NULLS NOT DISTINCT (v15+) 지원 여부 | tam_routes_uniq 구현 방식 결정 |
| OD-06 | SUPPLEMENT 최대 재상신 횟수 | (a) 무제한, (b) per-step max 설정 | 무한 루프 방지 |
| OD-07 | 단계 반려 후 재상신 허용 여부 | (a) fail-closed default, (b) per-step allow_retry 플래그 | 현재 설계: fail-closed |
| OD-08 | 감사 이력 보존 기간 | 법령 의무 또는 회사 정책 기준 | 현재 설계: 무기한 (삭제 없음) |
| OD-09 | REQUEST_SUBMITTER 범위 | (a) Consumer service account만, (b) end user도 직접 가능 | 서비스 간 인증 모델 결정 필요 |
| OD-10 | 결재 알림 (Notification) | TAM-006 범위 외 — 별도 WO | Slack/Email 연동 설계 필요 |

---

## 13. OPEN_GAPS

설계 중 발견된 비결정 기술 사항:

| # | 항목 | 내용 |
|---|---|---|
| G-01 | TAI API DB와 Chemical Supabase DB 사이 override_approvals 생성 흐름의 구체적 API | 별도 Chemical Adapter WO 필요 |
| G-02 | Consumer가 TAM 결재 완료를 실시간으로 인식하는 방법 | 폴링 vs. webhook vs. outbox 이벤트 — 별도 설계 |
| G-03 | PARALLEL_ANY 단계에서 1명 승인 후 나머지의 결재 시도 처리 | STEP_ALREADY_COMPLETED 반환; decision INSERT 허용 또는 거부 선택 필요 |
| G-04 | instance_route_id의 접근 권한 검증 방법 | 해당 route가 요청자의 company/factory 범위 내인지 확인 로직 |
| G-05 | Chemical WP-07I-A의 override_approvals 마이그레이션 | tam_request_id 컬럼 추가 — Chemical 별도 WO |
| G-06 | 다중 위임 정책: 동일 위임자가 서로 다른 대리자에게 동일 결재권한 동시 위임 허용 여부 | 정책 미확정; Exclusion Constraint 범위 밖 — 정책 확정 후 서비스 계층 적용 |
```

---

