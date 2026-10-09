---
doc_id: TAI-WO-TAM-008C-AUTHZ-LEDGER-V0.2
title: TAM 공통 결재 권한 원장 상세설계
status: GPT_REVIEW_REQUIRED
version: 0.2
created: 2026-10-09
revised: 2026-10-09
author: GPT (설계) / Claude Code (문서화)
base_design: docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md
base_sha: 1c349397c3052fd496b5270f0f42d82e3e0167e0
---

# TAM 공통 결재 권한 원장 상세설계

## 0. 변경 이력

| 버전  | 일자       | 내용                                                                       | 담당       |
|------|------------|--------------------------------------------------------------------------|-----------|
| 0.1  | 2026-10-09 | 초안 — GPT 확정 설계 기반 문서화                                              | GPT/Claude |
| 0.2  | 2026-10-09 | R1 수정 — FAIL-01~04 + 권한위임·멱등성·감사 정합성 7건 보정                    | GPT/Claude |

---

## 1. 목적 및 범위

### 1.1 목적

TAM(TAI Approval Management)은 결재경로, 결재 요청, 결재 실행을 관리한다.  
이 문서는 TAM 업무 권한의 부여·철회·검증·감사에 관한 데이터 모델과 API 계약을 확정한다.

### 1.2 범위

| 포함                                    | 제외                              |
|----------------------------------------|---------------------------------|
| tam_permission_grants 테이블 명세          | TAM 결재 실행 로직 (TAM-008D 이후)    |
| tam_permission_revocations 테이블 명세     | Chemical WP-07I 연동 계약           |
| Bootstrap API 명세 (활성화 BLOCKED)        | 기존 TAI Core 권한 구조 변경           |
| P01~P25 테스트 설계                        | 운영 DB Migration 실행              |
| Factory Scope 정책                       | OD-01~OD-09 Owner 미결 정책 결정    |
| Factory FK 제약 조사 결과 (DB_CONSTRAINT_BLOCKED) | |

### 1.3 구현 Gate

```
TAM-008C-003 DESIGN = 이 문서 (v0.2)
TAM-008C-003 IMPLEMENTATION = BLOCKED (GPT 독립검증 후 별도 WO 발행)
PR #572 MERGE = OWNER APPROVAL REQUIRED
BOOTSTRAP API ACTIVATION = BLOCKED (OD-01 Owner 승인 필요)
TAM HTTP 쓰기 Gate 해제 = BLOCKED
```

---

## 2. 현재 TAI Core 인증·인가 구조

### 2.1 신원 정보 SoT

TAI Core는 다음 신원 정보를 소유하며 TAM의 상위 신원 기준이다.

| 필드           | 위치            | 설명                                 |
|--------------|---------------|------------------------------------|
| id           | users.id      | 사용자 UUID (PK)                      |
| company_id   | users.company_id | 소속 회사 UUID                       |
| factory_id   | users.factory_id | 소속 사업장 UUID (nullable, 단일 값)  |
| role_code    | users.role_code  | 기존 역할 코드 (TAM 권한으로 자동 변환 금지) |
| status_code  | users.status_code | ACTIVE / PENDING / SUSPENDED / DELETED / INACTIVE |
| is_active    | users.is_active  | Boolean 활성 플래그                   |

**증거:** `routers/auth.py:114-133` — `get_current_user()` 반환값 = users 테이블 전체 행

### 2.2 인증 게이트

```
routers/auth.py:90-110 _require_active_account()
  status_code == ACTIVE AND is_active == True → 통과
  SUSPENDED / DELETED → 403
  기타(INACTIVE, drift) → 403 ACCOUNT_INACTIVE
```

**모든 TAM 작업은 이 게이트를 먼저 통과해야 한다.**

### 2.3 기존 역할 구조

| 구분               | 파일                           | 내용                                         |
|------------------|------------------------------|--------------------------------------------|
| 플랫폼 관리자          | role_permissions.py:20-22    | role_code == "001" 단일 조건                  |
| Company Admin 판별 | company_user_svc.py:213-234  | COMPANY scope + worker-list CRUD all true  |
| 역할 배정 제한         | company_user_svc.py:37       | _EXCLUDED_ROLE_CODES = (001, 031, 032, 033) |
| 데이터 접근범위         | company_scope.py:84-171      | ALL/COMPANY/FACTORY/TEAM/ASSIGNED 5단계      |
| 메뉴 CRUD 권한       | role_menu_permissions table  | role_code × menu_code × 5 actions          |

**`role_code` → TAM 권한 자동 변환은 없다.** TAM 권한은 별도 명시적 원장으로만 부여된다.

### 2.4 Factory 접근 구조

```
users.factory_id = 단일 UUID (nullable)
  - 별도 user_factory_assignments 피벗 테이블 없음
  - company_scope.py:115-127 FACTORY tier: user.factory_id 직접 비교
  - 다중 사업장 배정 원장 없음 → TAM v1은 단일 Factory 접근 기준
```

### 2.5 명시적 지정 패턴 (재사용 근거)

```
services/document_confirm_authz.py:120-125
  runtime_document_data.submitted_by == current_user.id → 역할 없이 신원 일치만으로 확인권
  → TAM STEP_APPROVER 설계의 기반 패턴
```

### 2.6 factories 테이블 제약 조사 결과

**조사 방법:** `supabase/migrations/*.sql` 전수 조회 + `services/tam/routes_svc.py` factory 검증 패턴 확인

**결과:**
```
factories 테이블:
  PRIMARY KEY: id (UUID, 단일)
  company_id: NOT NULL, REFERENCES companies(id)
  UNIQUE(company_id, id) 제약 없음 — 확인됨

서비스 계층 검증 패턴 (routes_svc.py:130-136):
  SELECT id FROM factories WHERE id = %s AND company_id = %s AND status_code = 'ACTIVE'
  → 현재 TAM은 서비스 계층에서 factory 소속 회사를 직접 검증
```

**결론:**
```
COMPOSITE_FK_STATUS = DB_CONSTRAINT_BLOCKED
이유: factories(company_id, id) UNIQUE 제약 부재 → 복합 FK 대상 키 없음
대안: BEFORE INSERT TRIGGER 또는 서비스 계층 강제 (§4.1 참조)
```

---

## 3. TAM 권한 경계

### 3.1 권한 종류

| 권한 코드              | 책임                               | 원장 부여 방식        |
|---------------------|----------------------------------|------------------|
| ROUTE_MANAGER       | 결재경로 생성·버전 편집·발행               | tam_permission_grants |
| ASSIGNEE_MANAGER    | DRAFT 버전 결재자 명시 지정              | tam_permission_grants |
| REQUEST_SUBMITTER   | 결재 요청 제출 (Consumer/end-user 구분) | tam_permission_grants |
| STEP_APPROVER       | 결재 단계 처리 (Snapshot 명시 지정자)     | 원장 부여 아님 — Snapshot |
| DELEGATION_MANAGER  | 대리결재 설정·철회                      | tam_permission_grants |
| REQUEST_REVOKER     | 결재 요청 취소 / 효력 철회                | tam_permission_grants |

### 3.2 STEP_APPROVER 특수 취급

```
STEP_APPROVER는 tam_permission_grants에 부여하지 않는다.

검증 경로:
  tam_approval_requests 생성 시 → tam_approval_route_versions(PUBLISHED)에서
  tam_approval_route_steps + tam_approval_step_assignees를 Snapshot으로 복사
  → tam_approval_request_snapshots.assignee_user_id에 명시적으로 포함된 경우만 결재 가능
  OR
  tam_approval_delegations에 유효한 위임 근거가 있는 경우

근거: docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md:731-760
      services/document_confirm_authz.py 명시적 지정 패턴
```

### 3.3 REQUEST_SUBMITTER 제한

```
OD-09 미결정: Consumer service account 전용 vs end-user 직접 허용
  → 결정 전: end-user 직접 제출 BLOCKED
  → Consumer 서비스 계정은 별도 service account 인증 경로 필요 (설계 대상 외)
```

### 3.4 권한 부여·철회·위임 주체 규칙

TAM 권한에서 "권한을 보유한다"는 것과 "권한을 부여·철회할 수 있다"는 것은 별개이다.
아래 6가지 행위를 구분하며, 각 행위의 허용 주체를 명시한다.

| 행위 코드 | 행위 내용                        | 허용 주체                                                             | 상태         |
|--------|--------------------------------|---------------------------------------------------------------------|------------|
| ACT-01 | TAM 권한 보유 (Hold)              | tam_permission_grants에 유효 Grant가 있는 사용자                         | ACTIVE     |
| ACT-02 | TAM 권한 사용 (Use)               | ACT-01 + TAI Core 활성 사용자                                          | ACTIVE     |
| ACT-03 | 타인에게 TAM 권한 부여 (Grant)       | ROUTE_MANAGER Grant 보유자 (자기 자신 제외) — 부여 가능 권한 범위: OD-03 미결  | BLOCKED    |
| ACT-04 | 타인의 TAM 권한 철회 (Revoke)       | ROUTE_MANAGER Grant 보유자 (동일 회사) — 철회 가능 권한 범위: OD-03 미결      | BLOCKED    |
| ACT-05 | 최초 관리자 지정 (First Bootstrap)   | role_code == "001" 플랫폼 관리자만 (OD-01 미결, API 비활성)               | BLOCKED    |
| ACT-06 | 관리자 복구 (Admin Recovery)       | 별도 절차 — 정책 Owner 결정 전 실행 금지 (OD-06 미결)                       | BLOCKED    |

**OD-03 미결 사항:** ROUTE_MANAGER가 모든 TAM 권한 코드를 부여·철회할 수 있는지,
아니면 특정 권한 코드에만 위임 권한이 있는지 Owner 결정 필요.
결정 전: ROUTE_MANAGER는 Grant/Revoke 실행 불가 (API HTTP Gate = BLOCKED).

**자기 권한 상승 금지 (전체 적용):**
```
subject_user_id == granted_by → 모든 경우 FORBIDDEN
Bootstrap Authority가 자신에게 부여하는 것도 FORBIDDEN
```

---

## 4. 권한 부여 원장 — `tam_permission_grants`

### 4.1 논리 모델

```sql
CREATE TABLE tam_permission_grants (
    grant_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         UUID        NOT NULL
                       REFERENCES companies(id),
    factory_id         UUID        NULL
                       REFERENCES factories(id),
    subject_user_id    UUID        NOT NULL,
    permission_code    TEXT        NOT NULL
                       CHECK (permission_code IN (
                           'ROUTE_MANAGER', 'ASSIGNEE_MANAGER', 'REQUEST_SUBMITTER',
                           'DELEGATION_MANAGER', 'REQUEST_REVOKER'
                       )),
    granted_by         UUID        NOT NULL,
    granted_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_from         TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until        TIMESTAMPTZ NULL,
    grant_reason       TEXT,
    idempotency_key    UUID        UNIQUE,    -- 멱등성 제어 키 (§4.5)
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT tam_grants_valid_period CHECK (
        valid_until IS NULL OR valid_until > valid_from
    )
    -- factory_id 소속 회사 검증은 BEFORE INSERT TRIGGER로 수행한다 (§4.1.1 참조)
);
```

**주의:** `STEP_APPROVER`는 permission_code CHECK에서 제외한다 — Snapshot 경로로만 처리.

#### 4.1.1 Factory 소속 검증 방법

**CHECK 서브쿼리 사용 불가:**
```
PostgreSQL CHECK 제약에서 서브쿼리는 허용되지 않는다.
  → CONSTRAINT tam_grants_company_match CHECK (
        factory_id IN (SELECT id FROM factories WHERE ...)
    ) 형태는 실행 불가능한 구문이다.
```

**복합 FK 사용 불가 (DB_CONSTRAINT_BLOCKED):**
```
FOREIGN KEY (company_id, factory_id) REFERENCES factories(company_id, id)
  → factories(company_id, id) UNIQUE 제약 없음 → 복합 FK 참조 대상 키 부재
  → BLOCKED. 구현 전 Migration에서 UNIQUE(company_id, id) 추가 여부 GPT 결정 필요
```

**현재 채택 방법 — BEFORE INSERT TRIGGER:**
```sql
CREATE OR REPLACE FUNCTION tam_grants_validate_factory_company()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.factory_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM factories
            WHERE id = NEW.factory_id
              AND company_id = NEW.company_id
        ) THEN
            RAISE EXCEPTION 'factory_id % does not belong to company_id %',
                NEW.factory_id, NEW.company_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tam_grants_validate_factory
    BEFORE INSERT ON tam_permission_grants
    FOR EACH ROW EXECUTE FUNCTION tam_grants_validate_factory_company();
```

**서비스 계층 이중 검증도 유지한다** (Layer 2). DB 트리거 실패 = INSERT 전체 ROLLBACK.

### 4.2 Grant 기간 및 중복 방지

#### 4.2.1 유효기간 정의

```
유효기간은 반개방 구간 [valid_from, valid_until) 로 정의한다.
  valid_from  : Grant 효력 시작 시각 (포함)
  valid_until : Grant 효력 종료 시각 (미포함), NULL = 명시적 철회까지 무기한

유효 판정 (실행 시점 기준):
  now() >= valid_from
  AND (valid_until IS NULL OR now() < valid_until)
  AND tam_permission_revocations에 해당 grant_id 없음
```

#### 4.2.2 기간 중복 방지 원칙

Grant는 Append-only를 유지한다. 다음 네 가지 규칙을 준수한다.

**규칙 A — 동일 Idempotency Key + 동일 Payload:**
```
idempotency_key 동일 → 기존 grant_id 반환 (재시도 멱등)
idempotency_key 동일 + Payload 다름 → 409 IDEMPOTENCY_CONFLICT
```

**규칙 B — 기간 중복 검사 범위:**
```
"중복"은 [valid_from, valid_until) 기간이 실제로 겹치는 경우로 정의한다.
  valid_until IS NULL인 Grant A와 [t1, t2) Grant B가 같은 권한에 대해
  t2 > A.valid_from이면 중복이다.

따라서 valid_until IS NULL 조건만 걸린 PARTIAL UNIQUE INDEX는
기간이 겹치는 유기한 Grant를 막지 못한다 — 사용하지 않는다.
```

**규칙 C — 철회된 Grant와 재부여:**
```
철회된 Grant는 새 Grant 부여의 영구 장애물이 되어서는 안 된다.
  → 중복 검사는 "철회되지 않은 유효 기간 내 Grant"만 대상으로 한다.
  → 철회된 Grant의 기간과 겹치는 새 Grant는 허용한다.
```

**규칙 D — 기간 중복 방지 구현 방향:**
```
PostgreSQL tstzrange + EXCLUSION CONSTRAINT가 기간 중복 방지의 기본 방향이다.

  (company_id, factory_id, subject_user_id, permission_code,
   tstzrange(valid_from, valid_until, '[)'))
   WITH GIST index

단, Append-only 철회 원장과 Exclusion Constraint 결합:
  → 철회된 Grant의 기간 범위를 Exclusion에서 제외하려면
    철회된 grant_id를 WHERE 절 Partial Index로 걸어야 하나,
    Exclusion Constraint는 Partial 지원이 제한적이다.
  → 구현 전 GPT가 정확한 제약 형태를 결정한다.
  → 구현 WO 발행 전까지 이 설계를 가정하고 코드를 작성하지 않는다.
```

**규칙 E — 동시 Grant 충돌:**
```
동시 INSERT가 발생하면 EXCLUSION CONSTRAINT가 직렬화를 보장한다.
  → 하나만 성공, 나머지 PostgreSQL serialization error → 409 DUPLICATE_GRANT 변환
  → 서비스 계층에서 IntegrityError 포획 후 응답 변환 필요
```

### 4.3 범위 정책

| factory_id | 의미                                           |
|------------|----------------------------------------------|
| NULL       | 회사 전체 범위 (Company-wide)                    |
| UUID       | 특정 사업장 범위만 (Factory-scoped)               |

**범위 해석 원칙 (FAIL-03 수정):**
```
COMPANY_WIDE_GRANT:
  factory_id = NULL인 Grant
  해당 회사 범위의 TAM 업무권한을 나타낸다.
  다른 Factory Grant가 존재해도 이 Grant의 범위는 변경되지 않는다.

FACTORY_SCOPED_GRANT:
  factory_id = UUID인 Grant
  해당 사업장으로 제한된 TAM 업무권한을 나타낸다.
  이 Grant가 존재해도 다른 Company-wide Grant의 범위는 변경되지 않는다.

Grant 간 상호 간섭 없음:
  여러 Grant가 존재한다고 기존 Grant의 유효 범위가 자동으로 달라지지 않는다.
```

**실효 권한 판정 (Effective Authorization):**
```
TAM 업무 실행 허용 조건 (모두 충족):
  1. TAM Grant 유효 (§5.3)
  2. TAI Core 신원 활성 (users.status_code == ACTIVE AND is_active == true)
  3. TAI Core 데이터 접근범위 통과 (company_scope.py — TAM Grant가 우회 불가)
  4. 대상 업무 객체 Scope 일치
     - Company-wide Grant: user.company_id == 객체.company_id
     - Factory-scoped Grant: user.factory_id == Grant.factory_id == 객체.factory_id

TAM Grant가 있어도 TAI Core 데이터 접근범위 제한은 별도로 적용된다.
TAI Core 데이터 접근범위가 TAM Grant의 factory 범위를 축소하거나 확장하지 않는다.
```

### 4.4 만료 처리

```
valid_until IS NULL → 만료 없음 (명시적 철회까지 유효)
valid_until < now() → 만료 (DENY, PERMISSION_GRANT_EXPIRED 이벤트 기록)

만료 판정은 실행 시점에 수행한다.
만료된 Grant를 자동 삭제하거나 UPDATE하지 않는다 (불변 원칙).
```

### 4.5 Idempotency Key 저장 계약

```
idempotency_key: tam_permission_grants.idempotency_key 컬럼 (UUID, UNIQUE, nullable)
  → 동일 idempotency_key로 INSERT 시 UNIQUE 충돌 → 기존 행 조회 후 반환
  → idempotency_key 없이 요청 가능 (nullable); 이 경우 멱등 보장 없음

동일 요청 재시도 vs 중복 Grant 구분:
  동일 재시도: idempotency_key 동일 + payload 동일 → 기존 grant_id 반환
  중복 Grant: idempotency_key 다름 + 기간 중복 → 409 DUPLICATE_GRANT (§4.2 규칙 E)
  Key 충돌:   idempotency_key 동일 + payload 다름 → 409 IDEMPOTENCY_CONFLICT

철회 API의 idempotency_key:
  tam_permission_revocations에 별도 idempotency_key 컬럼 추가 (UNIQUE, nullable)
  동일 grant_id에 대한 중복 철회 → uq_tam_revocations_grant 제약으로 차단
  멱등 재시도: idempotency_key 동일 → 기존 revocation_id 반환
```

---

## 5. 권한 철회 원장 — `tam_permission_revocations`

### 5.1 논리 모델

```sql
CREATE TABLE tam_permission_revocations (
    revocation_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    grant_id         UUID        NOT NULL
                     REFERENCES tam_permission_grants(grant_id),
    revoked_by       UUID        NOT NULL,
    revoked_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason           TEXT        NOT NULL,
    idempotency_key  UUID        UNIQUE,     -- 철회 멱등성 제어 키
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 동일 Grant에 대한 중복 철회 방지 (멱등성)
CREATE UNIQUE INDEX uq_tam_revocations_grant
    ON tam_permission_revocations (grant_id);
```

### 5.2 불변 원칙

```
Grant는 UPDATE / DELETE하지 않는다.
철회는 tam_permission_revocations INSERT만으로 처리한다.
이미 철회된 Grant에 대한 재철회 요청:
  → idempotency_key 동일: 기존 revocation_id 반환 (멱등)
  → idempotency_key 다름: 409 ALREADY_REVOKED
철회된 Grant는 재활성화하지 않는다.
```

### 5.3 권한 유효성 판정 로직

```
Grant가 유효한 조건 (모두 충족):
  1. tam_permission_grants에 grant_id 존재
  2. tam_permission_revocations에 해당 grant_id 없음
  3. now() >= valid_from
  4. valid_until IS NULL OR now() < valid_until
```

---

## 6. Bootstrap

Bootstrap은 두 가지 별개의 행위로 구분한다.

### 6.1 FIRST_BOOTSTRAP — 회사 최초 관리자 지정

```
정의: 해당 회사에 ROUTE_MANAGER Grant가 한 번도 발행된 적 없을 때 최초 지정
실행 주체: role_code == "001" (플랫폼 관리자) — OD-01 미결, API 비활성
보장:
  - 회사별 최초 1회 (C04: 발행 이력 자체가 없어야 함 — 철회된 과거 Grant 있으면 해당 안 됨)
  - 동시 요청 직렬화 (Advisory Lock 또는 UNIQUE INDEX)
  - 최초 부여 사실 불변 기록 (audit event_data.bootstrap = true)

OD-01 Owner 승인 전: 무조건 503 BOOTSTRAP_NOT_AUTHORIZED
```

#### 6.1.1 FIRST_BOOTSTRAP 허용 조건 (전부 충족 시 실행)

```
C01 요청자 = role_code == "001" AND status_code == ACTIVE
C02 대상 회사 = companies 테이블에 존재 AND 활성 상태
C03 대상 사용자 = 해당 company_id 소속 AND status_code == ACTIVE
C04 해당 회사에 permission_code == ROUTE_MANAGER Grant 발행 이력 자체가 없음
    (철회된 Grant가 있어도 이력이 있으면 FIRST_BOOTSTRAP 불가 → ADMIN_RECOVERY 경로)
C05 Factory 지정 시 해당 factory가 대상 회사 소속임 (TRIGGER 검증)
C06 subject_user_id != granted_by (자기 부여 금지)
C07 동시 Bootstrap 중복 방지 (Idempotency Key 또는 advisory lock)
```

### 6.2 ADMIN_RECOVERY — 관리자 복구

```
정의: 기존에 ROUTE_MANAGER Grant가 있었으나 현재 유효한 Grant가 0건인 회사의 관리자 복구
  → C04 실패 (이력 있음) + 유효 Grant = 0건 = ADMIN_RECOVERY 필요 상태

상태: BLOCKED — OD-06 Owner 결정 전 실행 금지

원칙:
  - 자동 실행 금지
  - FIRST_BOOTSTRAP API와 동일 엔드포인트 사용 불가
  - 별도 관리 콘솔 경로 + 추가 권한 검증 필요
  - 모든 복구 사실 감사 원장에 기록
  - 상세 정책 Owner 결정 전 설계 금지
```

### 6.3 자기 권한 상승 금지

```
모든 Grant 경로에서: subject_user_id == granted_by → FORBIDDEN
Bootstrap 포함: Bootstrap Authority가 자신에게 지정하는 것도 FORBIDDEN
일반 Grant: granted_by는 유효한 ROUTE_MANAGER Grant 보유자여야 함
```

---

## 7. Company/Factory Scope 정책

### 7.1 원칙

```
TAM v1 기준: users.factory_id 단일 컬럼 사용 (다중 사업장 원장 없음)

Grant 범위:
  COMPANY_WIDE (factory_id=NULL): 해당 회사 범위 TAM 업무권한
  FACTORY_SCOPED (factory_id=UUID): 해당 사업장 제한 TAM 업무권한

Grant 간 독립성:
  Company-wide Grant는 Factory-scoped Grant 존재와 무관하게 유효하다.
  Factory-scoped Grant는 Company-wide Grant의 범위를 변경하지 않는다.
  여러 Grant를 동시에 보유해도 각 Grant는 독립적으로 판정한다.

TAI Core 데이터 접근범위 독립성:
  TAM Grant의 factory_id가 TAI Core의 company_scope.py 데이터 접근범위를 변경하지 않는다.
  TAI Core의 FACTORY tier는 여전히 users.factory_id 기준으로 동작한다.
  TAM Grant와 TAI Core 접근범위는 모두 통과해야 실효 권한이 성립한다 (§4.3).
```

### 7.2 교차 회사 차단

```
Grant 부여자(granted_by)의 company_id == Grant의 company_id
  → 다른 회사 사용자가 이 회사의 Grant를 부여/철회 불가
  → 서비스 계층 강제 (Layer 2)

교차 회사 Grant 조회 → 404 (존재 은닉, 정보 누출 방지)
교차 회사 Grant 목록 조회 → 빈 배열
```

### 7.3 Factory 접근 검증 계층

```
Layer 1 — DB 트리거 (§4.1.1):
  tam_permission_grants INSERT 시 factory_id 소속 company_id 일치 확인

Layer 2 — 서비스 계층 검증:
  요청자 users.company_id == Grant.company_id
  Grant.factory_id IS NULL OR Grant.factory_id == 요청 대상 factory
  Factory-scoped 사용 시: 요청자 users.factory_id == Grant.factory_id
```

---

## 8. API 계약

### 8.1 `POST /v1/tam/permissions/grants` — 권한 부여

```
인증: get_current_user() → ACTIVE 필수
권한: granted_by의 ROUTE_MANAGER Grant (OD-03 미결 — ACT-03 BLOCKED)
      또는 Bootstrap Authority (role_code=001, OD-01 BLOCKED)
요청 본문:
  company_id:        UUID (요청자 company_id와 일치 강제)
  factory_id:        UUID | null
  subject_user_id:   UUID
  permission_code:   ROUTE_MANAGER | ASSIGNEE_MANAGER | REQUEST_SUBMITTER |
                     DELEGATION_MANAGER | REQUEST_REVOKER
  valid_from:        ISO8601 | null (null = now())
  valid_until:       ISO8601 | null
  grant_reason:      string
  idempotency_key:   UUID | null (null = 멱등 보장 없음)

응답 201: { grant_id, created_at, is_new: true }
응답 200: { grant_id, created_at, is_new: false }  ← idempotency_key 동일 재시도
응답 409: DUPLICATE_GRANT (기간 중복) | IDEMPOTENCY_CONFLICT (동일 Key + 다른 Payload)
응답 403: FORBIDDEN (권한 없음 / 자기 상승 / 교차 회사)
응답 422: 입력 오류

동일 트랜잭션:
  INSERT tam_permission_grants
  INSERT tam_approval_audit_events (event_type=PERMISSION_GRANTED,
    event_data={"grant_id": ..., "bootstrap": false})

감사 INSERT 실패 → 전체 ROLLBACK (§10.2)
```

### 8.2 `GET /v1/tam/permissions/grants` — 권한 목록 조회

```
인증: get_current_user() → ACTIVE 필수
권한: ROUTE_MANAGER Grant (동일 회사) 또는 Bootstrap Authority
쿼리 파라미터: company_id, factory_id, subject_user_id, permission_code, active_only
응답 200: grant 목록 (is_valid 계산 포함)

교차 회사 요청 → 빈 배열 (정보 은닉)
```

### 8.3 `GET /v1/tam/permissions/grants/{grant_id}` — 권한 상세 조회

```
인증: get_current_user()
권한: ROUTE_MANAGER Grant (동일 회사·사업장) 또는 Bootstrap Authority
응답 200: grant 상세 + revocation 여부 + 유효성 판정
응답 404: 없거나 교차 회사 (존재 은닉)
```

### 8.4 `POST /v1/tam/permissions/grants/{grant_id}/revoke` — 권한 철회

```
인증: get_current_user()
권한: ROUTE_MANAGER Grant (동일 회사) — ACT-04 BLOCKED (OD-03 미결)
요청 본문:
  reason:            string (필수)
  idempotency_key:   UUID | null

응답 200: { revocation_id, revoked_at, is_new: true }
응답 200: { revocation_id, revoked_at, is_new: false }  ← idempotency_key 동일 재시도
응답 409: ALREADY_REVOKED (이미 철회, idempotency_key 없이 재시도한 경우)
응답 403: FORBIDDEN (교차 회사 / 권한 없음)
응답 404: Grant 없음 또는 교차 회사

동일 트랜잭션:
  INSERT tam_permission_revocations
  INSERT tam_approval_audit_events (event_type=PERMISSION_REVOKED,
    event_data={"grant_id": ..., "revocation_id": ...})
```

### 8.5 `POST /v1/tam/permissions/bootstrap` — 최초 관리자 지정

```
인증: get_current_user()
권한: role_code == "001" (플랫폼 관리자) — 이 권한만 이 엔드포인트 접근 가능
요청 본문:
  company_id:        UUID
  factory_id:        UUID | null
  subject_user_id:   UUID
  grant_reason:      string
  idempotency_key:   UUID (필수 — Bootstrap은 멱등 보장 필수)

검증 순서: C01 → C02 → C03 → C04 → C05 → C06 → C07 (§6.1.1)

동일 트랜잭션:
  INSERT tam_permission_grants (permission_code=ROUTE_MANAGER, valid_until=NULL)
  INSERT tam_approval_audit_events (event_type=PERMISSION_GRANTED,
    event_data={"grant_id": ..., "bootstrap": true})

응답 201: { grant_id, is_new: true }
응답 200: { grant_id, is_new: false }  ← idempotency_key 동일 재시도
응답 409: BOOTSTRAP_ALREADY_EXISTS (C04 실패 — 이력 있음 → ADMIN_RECOVERY 경로 안내)
응답 403: FORBIDDEN (role_code != "001" / 자기 부여)

활성화 Gate: OD-01 Owner 승인 전까지 무조건 503 BOOTSTRAP_NOT_AUTHORIZED
```

---

## 9. 동시성·멱등성

### 9.1 Grant 중복 방지

```
tstzrange Exclusion Constraint (§4.2 규칙 D) → 기간 겹침 직렬화
UNIQUE idempotency_key → 동일 재시도 멱등 (§4.5)

IntegrityError(ExclusionViolation) → 409 DUPLICATE_GRANT
IntegrityError(UniqueViolation on idempotency_key) → 기존 행 조회 후 200 반환
```

### 9.2 중복 철회 멱등성

```
동일 grant_id 재철회:
  uq_tam_revocations_grant UNIQUE 제약
  → idempotency_key 동일: 기존 revocation_id 반환 200
  → idempotency_key 없음: 409 ALREADY_REVOKED
```

### 9.3 Bootstrap 동시 요청

```
C04 확인 후 INSERT까지의 race condition:
  SELECT FOR UPDATE on companies row + UNIQUE idempotency_key
  또는 Advisory Lock pg_advisory_xact_lock(company_id_hash)
  → 하나만 성공, 나머지 409 BOOTSTRAP_ALREADY_EXISTS
구체적 구현 방법은 구현 WO에서 GPT 결정
```

### 9.4 감사 실패 처리

```
Grant INSERT와 audit INSERT는 같은 트랜잭션.
audit INSERT 실패 → 전체 트랜잭션 ROLLBACK → Grant 실패 (Fail-closed).
"감사 실패 무시 후 Grant 허용"은 없다.
```

---

## 10. 감사 원장

### 10.1 기준 테이블: `tam_approval_audit_events`

기준 설계: `docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md:574`  
새 별도 감사 테이블을 추가하지 않는다.

```
기존 컬럼 (TAM-006 확정):
  audit_id        UUID        PK
  company_id      UUID        NOT NULL
  request_id      UUID        NULL  ← 권한 이벤트는 NULL
  event_type      TEXT        NOT NULL
  actor_user_id   UUID        NOT NULL
  event_data      JSONB       NOT NULL
  occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now()
```

### 10.2 권한 이벤트 추가 — event_type 확장

TAM-006 기존 event_type 목록에 아래 값을 추가한다 (Migration 시 CHECK 제약 갱신).

```
PERMISSION_GRANTED        -- 권한 부여 (Bootstrap 포함, bootstrap 구분은 event_data)
PERMISSION_REVOKED        -- 권한 철회
PERMISSION_GRANT_EXPIRED  -- 만료된 Grant 사용 시도 (관찰 이벤트)
PERMISSION_USE_DENIED     -- 미보유 권한 사용 시도 (관찰 이벤트)
```

### 10.3 event_data JSONB 계약

```
PERMISSION_GRANTED:
  request_id = NULL
  event_data = {
    "grant_id": "<UUID>",
    "subject_user_id": "<UUID>",
    "permission_code": "<CODE>",
    "company_id": "<UUID>",
    "factory_id": "<UUID>" | null,
    "bootstrap": true | false,
    "valid_from": "<ISO8601>",
    "valid_until": "<ISO8601>" | null
  }

PERMISSION_REVOKED:
  request_id = NULL
  event_data = {
    "grant_id": "<UUID>",
    "revocation_id": "<UUID>",
    "subject_user_id": "<UUID>",
    "permission_code": "<CODE>"
  }

PERMISSION_GRANT_EXPIRED / PERMISSION_USE_DENIED:
  관찰 이벤트 — 상태 변경 없음
  기록 실패 → non-blocking 별도 로깅 (DENY 판정은 이미 완료)
  기록 실패로 인해 DENY가 ALLOW로 바뀌어서는 안 됨
```

**주의:** `bootstrap_flag`라는 별도 컬럼은 없다. Bootstrap 여부는 `event_data.bootstrap`으로 구분한다.

### 10.4 감사 불변 원칙

```
tam_approval_audit_events: append-only (UPDATE / DELETE 금지)
  BEFORE UPDATE → RAISE EXCEPTION (TAM-006 트리거)
  BEFORE DELETE → RAISE EXCEPTION (TAM-006 트리거)
```

---

## 11. 권한 검증 순서

모든 TAM 관리 작업에서 아래 순서로 검증한다.

```
1. TAI Core JWT 검증 (get_current_user)
2. 사용자 ACTIVE 상태 확인 (_require_active_account)
3. 현재 회사 소속 확인 (user.company_id)
4. 요청한 Factory 접근범위 확인 (user.factory_id == 요청 factory, if factory-scoped)
5. 해당 TAM 권한 Grant 확인 (tam_permission_grants 존재 + §5.3 유효 조건)
6. Grant 유효기간 확인 (valid_from <= now() AND (valid_until IS NULL OR now() < valid_until))
7. Revocation 존재 여부 확인 (tam_permission_revocations에 grant_id 없음)
8. 업무 객체의 Company/Factory Scope 확인 (§4.3 실효 권한 판정)
9. 권한 사용 이력 기록 (audit_events; 관찰 이벤트는 non-blocking)

1~8 중 하나라도 실패 → DENY (Fail-closed)
권한 데이터 조회 실패 → DENY (503 또는 403, 허용 불가)
```

---

## 12. P01~P25 테스트 설계

> 이 섹션은 구현 전 테스트 명세이다. 실행 테스트가 아니다.

| ID  | 시나리오                                   | 예상 결과                              | 검증 포인트                                                          |
|-----|----------------------------------------|--------------------------------------|------------------------------------------------------------------|
| P01 | 최초 회사 관리자 Bootstrap                  | 201, grant_id 반환                     | C01~C07 전부 충족 + audit event_data.bootstrap=true               |
| P02 | 중복 Bootstrap 거부                       | 409 BOOTSTRAP_ALREADY_EXISTS           | tam_permission_grants 변경 없음, audit 불변                         |
| P03 | 일반 사용자 Bootstrap 거부                  | 403 FORBIDDEN                         | role_code != "001" → 즉시 거부                                     |
| P04 | role_code만으로 TAM 권한 생성 불가           | tam_permission_grants 변경 없음          | users.role_code UPDATE는 tam_permission_grants 트리거 없음          |
| P05 | ROUTE_MANAGER 명시적 Grant               | 201                                   | tam_permission_grants INSERT + audit, subject != granted_by      |
| P06 | ASSIGNEE_MANAGER 명시적 Grant            | 201                                   | permission_code = ASSIGNEE_MANAGER 유효 확인                       |
| P07 | Company-wide Grant (factory_id=NULL)   | 해당 회사 전체 TAM 업무 접근                  | scoped_filter 연동 확인                                            |
| P08 | Factory-scoped Grant 유효성              | 해당 Factory에서 유효 / 타 Factory 독립      | company-wide Grant 영향 없음 확인                                   |
| P09 | 타 회사 Grant 조회·변경 거부               | 404 (단건) / 빈 배열 (목록)                | company_id 불일치 → 정보 은닉                                        |
| P10 | 타 Factory Grant 사용 거부               | 403                                   | Factory-scoped grant는 지정 factory에서만 작동                        |
| P11 | 만료된 Grant 거부                         | 403, PERMISSION_GRANT_EXPIRED 감사      | valid_until < now() → DENY + 관찰 이벤트 기록                        |
| P12 | 철회된 Grant 거부                         | 403, revocation 확인                   | revocation 존재 → DENY                                            |
| P13 | 비활성 사용자 권한 사용 거부                  | 403 ACCOUNT_INACTIVE                   | _require_active_account 우선 실행                                  |
| P14 | 다른 회사로 이동한 사용자 권한 거부             | 403                                   | users.company_id != grant.company_id → Layer 2 차단               |
| P15 | 자기 자신에 대한 권한 상승 거부               | 403 SELF_GRANT_FORBIDDEN               | subject_user_id == granted_by → 거부 (Bootstrap 포함)              |
| P16 | 동일 idempotency_key 재시도 멱등성          | 200, 기존 grant_id 반환                  | idempotency_key 일치 + payload 동일 → 기존 결과                      |
| P17 | 동일 Key + 다른 Payload                   | 409 IDEMPOTENCY_CONFLICT               | tam_permission_grants 변경 없음                                    |
| P18 | 기간 겹치는 중복 Grant 거부                  | 409 DUPLICATE_GRANT                    | tstzrange exclusion → 두 번째 INSERT 실패                           |
| P19 | 철회된 Grant 기간과 겹치는 새 Grant 허용        | 201                                    | 철회된 Grant는 새 Grant의 기간 중복 검사에서 제외됨                     |
| P20 | 감사 INSERT 실패 시 Grant 전체 ROLLBACK    | Grant 없음 + audit 없음                  | tam_permission_grants INSERT 후 audit INSERT 실패 → 전체 RB         |
| P21 | 권한 철회 감사 원본 불변                     | revocation 삭제·변경 불가                  | DELETE/UPDATE tam_permission_revocations → 실패                    |
| P22 | STEP_APPROVER role 자동 부여 금지          | tam_permission_grants에 없음             | CHECK constraint에 STEP_APPROVER 없음 확인                         |
| P23 | Snapshot에 없는 사용자 결재 거부             | 403 FORBIDDEN_NOT_ASSIGNEE             | 요청 Snapshot.assignee_user_id에 없음 → 거부                        |
| P24 | DB 장애 시 Fail-closed                   | 503 또는 403, 허용 없음                    | Grant 조회 실패 → 예외 DENY (허용 Default 없음)                       |
| P25 | 기존 WP-08B HTTP 403 Gate 회귀           | 모든 TAM 쓰기 엔드포인트 403               | routers/tam_routes.py _require_route_manager() 무조건 403 유지      |

---

## 13. 미결정 Owner 정책 (OD)

| OD    | 내용                              | 후보                                       | 현재 처리                      |
|-------|----------------------------------|------------------------------------------|-----------------------------|
| OD-01 | FIRST_BOOTSTRAP 실행 권한자          | (a) role_code="001" 플랫폼 관리자 (GPT 권고) | BLOCKED — Bootstrap API 비활성 |
| OD-02 | APPROVED 효력 만료 기간              | (a) 만료 없음, (b) 24h, (c) Consumer 설정  | valid_until NULL 기본 유지      |
| OD-03 | ROUTE_MANAGER 위임 가능 권한 범위      | (a) 전체 코드, (b) 제한 코드, (c) 별도 위임 테이블 | BLOCKED — Grant/Revoke API 비활성 |
| OD-06 | ADMIN_RECOVERY 실행 절차 및 권한      | 미정                                       | BLOCKED — Recovery API 비활성   |
| OD-09 | REQUEST_SUBMITTER 범위             | (a) Consumer 서비스 계정만, (b) end-user 직접 | BLOCKED — end-user 차단         |

---

## 14. 기존 설계 정합성 검사

| 항목                                       | 판정            | 근거                                                         |
|------------------------------------------|----------------|-----------------------------------------------------------|
| TAM-006 Route/Version 구조                 | COMPATIBLE      | tam_permission_grants는 별도 테이블, 기존 4테이블 무변경               |
| WP-08B routes_svc.py company_id 검증       | COMPATIBLE      | Grant 부여 시에도 company_id 일치 강제                              |
| TAI Core Identity SoT                    | COMPATIBLE      | Grant는 TAI Core user UUID 참조, SoT 변경 없음                   |
| PRJ 개발거버넌스 append-only 원칙             | COMPATIBLE      | Grant/Revocation 모두 append-only                             |
| Chemical WP-07I-A 불변식                   | COMPATIBLE      | TAM 권한 원장은 Chemical 구조 독립                                  |
| PostgreSQL CHECK 서브쿼리                   | RESOLVED (R1)   | 서브쿼리 제거 → BEFORE INSERT TRIGGER로 대체                        |
| factories UNIQUE(company_id, id) 부재      | DB_CONSTRAINT_BLOCKED | 복합 FK 불가 → Trigger + 서비스 계층 이중 검증                 |
| tam_approval_audit_events bootstrap_flag  | RESOLVED (R1)   | 별도 컬럼 없음 → event_data.bootstrap 으로 저장                     |
| Company/Factory Grant 상호 간섭             | RESOLVED (R1)   | 독립성 원칙 명시 (§4.3, §7.1)                                    |
| Bootstrap 이후 관리자 복구                   | RESOLVED (R1)   | FIRST_BOOTSTRAP / ADMIN_RECOVERY 분리 (§6)                   |

---

## 15. 구현 Gate

```
TAM-008C-003 DESIGN DOCUMENT (v0.2)  = 이 문서 (R1 수정 완료)
IMPLEMENTATION                        = BLOCKED (GPT 독립검증 후 별도 WO)

PR #572 MERGE                         = OWNER APPROVAL REQUIRED
Bootstrap API Activation              = BLOCKED (OD-01 Owner 승인 필요)
ADMIN_RECOVERY API                    = BLOCKED (OD-06 Owner 승인 필요)
Grant/Revoke API 활성화               = BLOCKED (OD-03 Owner 승인 필요)
TAM HTTP 쓰기 Gate 해제               = BLOCKED
CHEMICAL WP-07I-A                     = BLOCKED
PRODUCTION DEPLOY                     = BLOCKED

다음 단계 (GPT 독립검증 후):
  TAM-008C Migration 설계 → Owner 승인 → 구현 WO 발행
```
