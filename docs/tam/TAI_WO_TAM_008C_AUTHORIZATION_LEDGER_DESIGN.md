---
doc_id: TAI-WO-TAM-008C-AUTHZ-LEDGER-V0.3
title: TAM 공통 결재 권한 원장 상세설계
status: GPT_REVIEW_REQUIRED
version: 0.3
created: 2026-10-09
revised: 2026-10-09
author: GPT (설계) / Claude Code (문서화)
base_design: docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md
base_sha: 1c349397c3052fd496b5270f0f42d82e3e0167e0
---

# TAM 공통 결재 권한 원장 상세설계

## 0. 변경 이력

| 버전  | 일자       | 내용                                                                                   | 담당       |
|------|------------|--------------------------------------------------------------------------------------|-----------|
| 0.1  | 2026-10-09 | 초안 — GPT 확정 설계 기반 문서화                                                          | GPT/Claude |
| 0.2  | 2026-10-09 | R1 수정 — FAIL-01~04 + 권한위임·멱등성·감사 정합성 7건 보정                                | GPT/Claude |
| 0.3  | 2026-10-09 | R2 추가 — 논리 키 잠금 모델, 직렬화 흐름, Factory 무결성 옵션, Idempotency 보완, P26~P35 | GPT/Claude |

---

## 1. 목적 및 범위

### 1.1 목적

TAM(TAI Approval Management)은 결재경로, 결재 요청, 결재 실행을 관리한다.  
이 문서는 TAM 업무 권한의 부여·철회·검증·감사에 관한 데이터 모델과 API 계약을 확정한다.

### 1.2 범위

| 포함                                            | 제외                              |
|------------------------------------------------|---------------------------------|
| tam_permission_grants 테이블 명세                  | TAM 결재 실행 로직 (TAM-008D 이후)    |
| tam_permission_revocations 테이블 명세             | Chemical WP-07I 연동 계약           |
| Bootstrap API 명세 (활성화 BLOCKED)                | 기존 TAI Core 권한 구조 변경           |
| P01~P35 테스트 설계                                | 운영 DB Migration 실행              |
| Factory Scope 정책                               | OD-01~OD-09 Owner 미결 정책 결정    |
| Factory FK 제약 조사 결과 및 옵션 비교 (§7.4)           |                                   |
| Grant 논리 키 잠금 모델 (§4.6)                       |                                   |
| Grant 생성·철회 직렬화 흐름 (§4.7, §5.4)              |                                   |

### 1.3 구현 Gate

```
TAM-008C-003 DESIGN = 이 문서 (v0.3)
TAM-008C-003 IMPLEMENTATION = BLOCKED (GPT 독립검증 후 별도 WO 발행)
PR #572 MERGE = OWNER APPROVAL REQUIRED
BOOTSTRAP API ACTIVATION = BLOCKED (OD-01 Owner 승인 필요)
TAM HTTP 쓰기 Gate 해제 = BLOCKED
```

---

## 2. 현재 TAI Core 인증·인가 구조

### 2.1 신원 정보 SoT

TAI Core는 다음 신원 정보를 소유하며 TAM의 상위 신원 기준이다.

| 필드           | 위치               | 설명                                 |
|--------------|------------------|------------------------------------|
| id           | users.id         | 사용자 UUID (PK)                      |
| company_id   | users.company_id | 소속 회사 UUID                         |
| factory_id   | users.factory_id | 소속 사업장 UUID (nullable, 단일 값)    |
| role_code    | users.role_code  | 기존 역할 코드 (TAM 권한으로 자동 변환 금지)  |
| status_code  | users.status_code | ACTIVE / PENDING / SUSPENDED / DELETED / INACTIVE |
| is_active    | users.is_active  | Boolean 활성 플래그                     |

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

**조사 방법:** `supabase/migrations/*.sql` 전수 조회 + `services/company_scope.py` + `routers/factories.py`

**결과:**
```
factories 테이블:
  PRIMARY KEY: id (UUID, 단일) — 모든 migrations에서 REFERENCES factories(id) 패턴
  company_id: 필수 필드 — FactoryCreate.company_id: str (Optional 아님)
  deleted_at: NULL = 활성, NOT NULL = 소프트 삭제 (migration 20260728145433)
  UNIQUE(company_id, id) 제약: 없음 — 전체 migration 검색에서 미발견
  company_id NOT NULL: DB 제약 미확인 (응용계층에서는 항상 NOT NULL 처리)

서비스 계층 검증 패턴 (company_scope.py:222):
  f = sb.table("factories").select("company_id").eq("id", factory_id).limit(1).execute()
  if not f.data or f.data[0].get("company_id") != current.get("company_id"): → 404
  → 현재 TAM은 SELECT WHERE id=X AND company_id=Y 패턴으로 검증
```

**복합 FK 상태:** → §7.4에서 상세 비교

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

| 행위 코드 | 행위 내용                          | 허용 주체                                                           | 상태      |
|--------|----------------------------------|--------------------------------------------------------------------|---------|
| ACT-01 | TAM 권한 보유 (Hold)                | tam_permission_grants에 유효 Grant가 있는 사용자                       | ACTIVE  |
| ACT-02 | TAM 권한 사용 (Use)                 | ACT-01 + TAI Core 활성 사용자                                        | ACTIVE  |
| ACT-03 | 타인에게 TAM 권한 부여 (Grant)         | ROUTE_MANAGER Grant 보유자 (자기 자신 제외) — 부여 가능 권한 범위: OD-03 미결 | BLOCKED |
| ACT-04 | 타인의 TAM 권한 철회 (Revoke)         | ROUTE_MANAGER Grant 보유자 (동일 회사) — 철회 가능 권한 범위: OD-03 미결   | BLOCKED |
| ACT-05 | 최초 관리자 지정 (First Bootstrap)     | role_code == "001" 플랫폼 관리자만 (OD-01 미결, API 비활성)             | BLOCKED |
| ACT-06 | 관리자 복구 (Admin Recovery)         | 별도 절차 — 정책 Owner 결정 전 실행 금지 (OD-06 미결)                     | BLOCKED |

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
    -- factory_id 소속 회사 검증은 BEFORE INSERT TRIGGER로 수행한다 (§4.1.1)
    -- 기간 중복 방지는 논리 키 잠금 + 서비스 계층 직렬화로 수행한다 (§4.6, §4.7)
);
```

**주의:** `STEP_APPROVER`는 permission_code CHECK에서 제외한다 — Snapshot 경로로만 처리.

#### 4.1.1 Factory 소속 검증 방법

**CHECK 서브쿼리 사용 불가:**
```
PostgreSQL CHECK 제약에서 서브쿼리는 허용되지 않는다.
  → 서브쿼리 형태 CHECK는 실행 불가능한 구문이다.
```

**복합 FK 상태:** → §7.4에서 Option A / B 비교 참조

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

Trigger EXISTS 조회는 factory 행의 company_id 변경 경합을 완전히 방어하지 못하는 한계가 있다.
→ 이 경합 처리는 §7.4 Option A(복합 FK) 또는 Option B(FOR SHARE Trigger) 채택으로 해결한다.

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
idempotency_key 동일 + payload 동일 → 기존 grant_id 반환 (재시도 멱등)
idempotency_key 동일 + payload 다름 → 409 IDEMPOTENCY_CONFLICT
```

**규칙 B — 기간 중복 검사 범위:**
```
"중복"은 [valid_from, valid_until) 기간이 실제로 겹치는 경우로 정의한다.
  두 구간 A = [a1, a2), B = [b1, b2)는 a1 < b2 AND b1 < a2 이면 겹친다.
  valid_until IS NULL은 무한대(+∞)로 취급한다.

단순 valid_until IS NULL 조건만 걸린 PARTIAL UNIQUE INDEX는
기간이 겹치는 유기한 Grant를 막지 못한다 — 이 방식은 채택하지 않는다.
```

**규칙 C — 철회된 Grant와 재부여:**
```
철회된 Grant는 새 Grant 부여의 영구 장애물이 되어서는 안 된다.
  → 중복 검사는 "철회되지 않은 유효 기간 내 Grant"만 대상으로 한다.
  → 철회된 Grant의 기간과 겹치는 새 Grant는 허용한다.
```

**규칙 D — EXCLUSION CONSTRAINT 단독 사용 금지:**
```
tam_permission_revocations가 별도 테이블인 구조에서
EXCLUSION CONSTRAINT만으로 철회된 Grant를 제외한 기간 중복 방지를 구현할 수 없다.
  → Exclusion Constraint는 동일 테이블의 기간 겹침만 검사한다
  → 철회 여부를 반영한 중복 방지는 §4.6~§4.7 논리 키 잠금 + 서비스 계층 검사로 처리한다.
```

**규칙 E — 동시 Grant 충돌 직렬화:**
```
동시 INSERT 경합은 §4.6 논리 키 잠금 모델로 직렬화한다.
  → 동일 논리 키에 대한 두 번째 Grant 시도는 첫 번째가 COMMIT된 후 재검사
  → 재검사 후 중복이면 409 DUPLICATE_GRANT
```

### 4.3 범위 정책

| factory_id | 의미                                |
|------------|-----------------------------------|
| NULL       | 회사 전체 범위 (Company-wide)           |
| UUID       | 특정 사업장 범위만 (Factory-scoped)       |

**범위 해석 원칙:**
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
  여러 Grant가 존재해도 기존 Grant의 유효 범위가 자동으로 달라지지 않는다.
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
저장 위치: tam_permission_grants.idempotency_key (UUID, UNIQUE, nullable)
  → 동일 idempotency_key + 동일 정규화 Payload → 기존 grant_id 반환
  → idempotency_key 없이 요청 가능 (nullable); 이 경우 멱등 보장 없음

정규화 Payload (동일성 비교 기준):
  {
    company_id:        UUID (lowercase),
    factory_id:        UUID (lowercase) | null,
    subject_user_id:   UUID (lowercase),
    permission_code:   string (exact),
    valid_from:        ISO8601 (UTC, 초 단위),
    valid_until:       ISO8601 (UTC, 초 단위) | null
  }
  * granted_by / grant_reason은 정규화 Payload에 포함하지 않는다.

동일 요청 재시도 vs 중복 Grant 구분:
  동일 재시도:   idempotency_key 동일 + payload 동일 → 기존 grant_id 반환 (200)
  Key 충돌:      idempotency_key 동일 + payload 다름 → 409 IDEMPOTENCY_CONFLICT
  중복 Grant:    idempotency_key 다름 + 기간 중복    → 409 DUPLICATE_GRANT (§4.2 규칙 E)

적용 범위:
  idempotency_key는 API 작업 종류(Grant / Revoke)와 Company scope를 암묵적으로 포함한다.
  → 같은 UUID를 Grant API와 Revoke API에 사용해도 각각 별도 테이블의 UNIQUE 제약이 적용되므로
    DB 수준에서는 충돌하지 않는다.
  → 단, 동일 UUID를 서로 다른 API에 재사용하면 감사 추적이 어려워지므로 권장하지 않는다.
    클라이언트는 API 작업 종류별로 독립적인 UUID를 생성해야 한다.

철회 API의 idempotency_key:
  tam_permission_revocations.idempotency_key 컬럼 (UUID, UNIQUE, nullable)
  동일 grant_id에 대한 중복 철회 → uq_tam_revocations_grant 제약으로 차단
  멱등 재시도: idempotency_key 동일 → 기존 revocation_id 반환

동시 동일 Key 요청:
  두 요청이 동시에 동일 idempotency_key로 INSERT 시도
  → 하나만 INSERT 성공; 나머지는 UniqueViolation → SELECT 기존 행 → 200 반환
  → 감사 이벤트는 첫 번째 트랜잭션에서만 INSERT (재시도에서 중복 감사 없음)
```

### 4.6 Grant 논리 키 잠금 모델

#### 4.6.1 설계 원칙

READ COMMITTED 환경에서 동시 Grant 생성이 Write Skew를 유발할 수 있다.

```
문제 시나리오:
  Tx A: SELECT 중복 Grant → 없음 확인 (READ)
  Tx B: SELECT 중복 Grant → 없음 확인 (READ)
  Tx A: INSERT Grant (WRITE) → COMMIT
  Tx B: INSERT Grant (WRITE) → COMMIT
  결과: 동일 논리 키에 두 Grant 삽입됨 (Write Skew)
```

이를 방지하기 위해 전용 잠금 앵커 테이블을 도입한다.

#### 4.6.2 논리 키 정의

```
논리 키 = (company_id, factory_key, subject_user_id, permission_code)
  factory_key = factory_id IS NULL ? SENTINEL_UUID : factory_id
  SENTINEL_UUID = '00000000-0000-0000-0000-000000000000'
    (Company-wide Grant의 factory_id=NULL을 동일 키 공간으로 정규화)
```

#### 4.6.3 잠금 앵커 테이블

```sql
CREATE TABLE tam_permission_grant_locks (
    company_id      UUID    NOT NULL REFERENCES companies(id),
    factory_key     UUID    NOT NULL,
    subject_user_id UUID    NOT NULL,
    permission_code TEXT    NOT NULL
                    CHECK (permission_code IN (
                        'ROUTE_MANAGER', 'ASSIGNEE_MANAGER', 'REQUEST_SUBMITTER',
                        'DELEGATION_MANAGER', 'REQUEST_REVOKER'
                    )),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, factory_key, subject_user_id, permission_code)
);
```

**이 테이블의 역할:**
- 권한 원장이 아니다 — Grant 발행·철회 기록을 담지 않는다.
- 동시성 제어 전용이다 — 논리 키별로 SELECT FOR UPDATE 잠금 앵커를 제공한다.
- 행은 최초 Grant 또는 Revoke 시도 시 자동 생성(UPSERT)된다.
- 행 삭제는 금지한다 (잠금 앵커 소실 시 UPSERT가 재생성하므로 문제없지만, 삭제하면 잠금 이력이 끊긴다).

#### 4.6.4 잠금 키 충돌과 독립성

```
같은 논리 키 = 같은 잠금 앵커 행 → 직렬화됨
다른 논리 키 = 다른 잠금 앵커 행 → 완전히 독립적, 서로 차단하지 않음

Advisory Lock 사용하지 않는 이유:
  pg_advisory_xact_lock(hashtext(...))은 해시 공간(2^32)에서 충돌 가능
  → 서로 다른 논리 키가 동일 advisory lock을 경쟁 → False Contention
  → 잠금 앵커 행 방식은 논리 키 충돌이 불가능
```

### 4.7 Grant 생성 직렬화 흐름

모든 Grant INSERT는 아래 8단계를 순서대로 수행한다.

```
STEP 1: 트랜잭션 시작
  BEGIN;

STEP 2: 잠금 앵커 행 확보 (UPSERT)
  INSERT INTO tam_permission_grant_locks
    (company_id, factory_key, subject_user_id, permission_code)
  VALUES ($company_id, $factory_key, $subject_user_id, $permission_code)
  ON CONFLICT DO NOTHING;
  -- 행이 이미 존재하면 아무 것도 하지 않는다

STEP 3: 논리 키 행 잠금 획득 (FOR UPDATE)
  SELECT * FROM tam_permission_grant_locks
  WHERE company_id = $company_id
    AND factory_key = $factory_key
    AND subject_user_id = $subject_user_id
    AND permission_code = $permission_code
  FOR UPDATE;
  -- 동일 논리 키를 처리하는 다른 트랜잭션을 BLOCK한다
  -- BLOCK된 트랜잭션은 COMMIT 후 재개되어 STEP 4부터 다시 수행한다

STEP 4: Idempotency Key 확인 (제공된 경우)
  SELECT grant_id, <정규화_payload_컬럼들>
  FROM tam_permission_grants
  WHERE idempotency_key = $idempotency_key;
  → 기존 행 있음 + payload 동일: 기존 grant_id 반환, ROLLBACK (200)
  → 기존 행 있음 + payload 다름: ROLLBACK (409 IDEMPOTENCY_CONFLICT)
  → 없음: 계속

STEP 5: 부여자 권한 유효성 확인 (OD-03 활성화 후 적용)
  -- 현재 API HTTP Gate = BLOCKED; 이 단계는 Gate 해제 후 구현
  -- 부여자 ROUTE_MANAGER grant를 SELECT FOR UPDATE로 잠금:
  SELECT g.grant_id FROM tam_permission_grants g
  WHERE g.subject_user_id = $granted_by
    AND g.permission_code = 'ROUTE_MANAGER'
    AND g.company_id = $company_id
    AND NOT EXISTS (SELECT 1 FROM tam_permission_revocations r WHERE r.grant_id = g.grant_id)
    AND now() >= g.valid_from
    AND (g.valid_until IS NULL OR now() < g.valid_until)
  FOR UPDATE;
  -- 잠금 순서: 논리 키 앵커(STEP 3) → 부여자 Grant 행(STEP 5) 순서 고정 (Deadlock 방지)

STEP 6: 기간 중복 검사
  SELECT g.grant_id
  FROM tam_permission_grants g
  WHERE g.company_id = $company_id
    AND COALESCE(g.factory_id::text, '00000000-0000-0000-0000-000000000000') = $factory_key::text
    AND g.subject_user_id = $subject_user_id
    AND g.permission_code = $permission_code
    AND NOT EXISTS (
        SELECT 1 FROM tam_permission_revocations r WHERE r.grant_id = g.grant_id
    )
    AND (
        -- [valid_from, valid_until) ∩ [$new_from, $new_until) ≠ ∅
        g.valid_from < COALESCE($new_until, 'infinity'::timestamptz)
        AND COALESCE(g.valid_until, 'infinity'::timestamptz) > $new_from
    )
  LIMIT 1;
  → 결과 있음: ROLLBACK (409 DUPLICATE_GRANT)
  → 없음: 계속

STEP 7: Grant + 감사 INSERT (동일 트랜잭션)
  INSERT INTO tam_permission_grants (...) RETURNING grant_id;
  INSERT INTO tam_approval_audit_events (...);
  -- 감사 INSERT 실패 → 전체 ROLLBACK

STEP 8: COMMIT
  -- 잠금 해제, 대기 중인 STEP 3 트랜잭션 재개
```

**직렬화 보장:**
```
Tx A가 STEP 3에서 잠금 획득 후 STEP 8에서 COMMIT하면,
Tx B는 STEP 3에서 BLOCK되다가 Tx A COMMIT 후 재개된다.
Tx B의 STEP 6에서 Tx A가 삽입한 Grant가 보이므로 중복이면 거부된다.
→ Write Skew 없음 (READ COMMITTED 환경에서도 안전)
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
  → idempotency_key 동일: 기존 revocation_id 반환 (멱등, 200)
  → idempotency_key 없음 또는 다름: 409 ALREADY_REVOKED
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

### 5.4 Grant 철회 직렬화 흐름

```
STEP 1: 트랜잭션 시작
  BEGIN;

STEP 2: 대상 Grant 조회
  SELECT g.grant_id, g.company_id, g.factory_id, g.subject_user_id, g.permission_code
  FROM tam_permission_grants g
  WHERE g.grant_id = $grant_id;
  → 없거나 다른 회사: ROLLBACK (404)

STEP 3: 논리 키 잠금 앵커 확보 (UPSERT)
  factory_key = COALESCE(g.factory_id, SENTINEL_UUID)
  INSERT INTO tam_permission_grant_locks
    (company_id, factory_key, subject_user_id, permission_code)
  VALUES (g.company_id, factory_key, g.subject_user_id, g.permission_code)
  ON CONFLICT DO NOTHING;

STEP 4: 논리 키 잠금 획득 (FOR UPDATE)
  SELECT * FROM tam_permission_grant_locks WHERE ... FOR UPDATE;
  -- Grant 생성과 동일 논리 키 잠금 앵커를 경쟁 → 직렬화 보장

STEP 5: 대상 Grant 행 잠금 (FOR UPDATE)
  SELECT * FROM tam_permission_grants WHERE grant_id = $grant_id FOR UPDATE;
  -- 잠금 순서: 논리 키 앵커(STEP 4) → 특정 Grant 행(STEP 5) 순서 고정 (Deadlock 방지)

STEP 6: 이미 철회됐는지 확인
  SELECT revocation_id, idempotency_key
  FROM tam_permission_revocations WHERE grant_id = $grant_id;
  → 있고 idempotency_key 동일: ROLLBACK (기존 revocation_id 반환, 200)
  → 있고 idempotency_key 다름 또는 없음: ROLLBACK (409 ALREADY_REVOKED)
  → 없음: 계속

STEP 7: Revocation + 감사 INSERT (동일 트랜잭션)
  INSERT INTO tam_permission_revocations (...) RETURNING revocation_id;
  INSERT INTO tam_approval_audit_events (...);

STEP 8: COMMIT
```

**잠금 순서 (Deadlock 방지):**
```
모든 작업의 잠금 획득 순서:
  1. tam_permission_grant_locks FOR UPDATE (논리 키 앵커)
  2. tam_permission_grants FOR UPDATE (특정 Grant 행, 필요한 경우)

이 순서를 항상 지키면 순환 잠금이 발생하지 않는다.
  Tx A: 논리 키 → Grant 행
  Tx B: 논리 키 → Grant 행
  → 논리 키가 같으면 하나가 먼저 획득 → 직렬화
  → 논리 키가 다르면 독립 → Deadlock 없음
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
  - 동시 요청 직렬화 (논리 키 잠금 앵커 FOR UPDATE)
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
C07 동시 Bootstrap 중복 방지 (논리 키 잠금 앵커 FOR UPDATE + C04 재확인)
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

### 7.4 Factory 무결성 — Option A / B 비교

#### 7.4.1 현황

```
현재 상태:
  factories.id: PK (단일 UUID) — 모든 migrations에서 REFERENCES factories(id) 패턴
  factories.company_id: 서비스 계층에서 NOT NULL 처리 (FactoryCreate.company_id: str 필수)
  DB 제약에서 company_id NOT NULL: 미확인 (원본 테이블 DDL 미발견)
  UNIQUE(company_id, id): 없음 — 전체 migration 검색에서 미발견
  deleted_at: NULL=활성 / NOT NULL=소프트삭제 (migration 20260728145433)
  factory 소속 회사 변경 엔드포인트: 없음 (routers/factories.py PATCH에서 company_id 미노출)
```

#### 7.4.2 Option A — `factories(company_id, id)` UNIQUE + 복합 FK

**GPT 권고: Option A**

```sql
-- Migration (별도 WO, 구현 단계):
ALTER TABLE factories ADD CONSTRAINT uq_factories_company_id UNIQUE (company_id, id);

-- TAM Grant 테이블의 복합 FK:
FOREIGN KEY (company_id, factory_id) REFERENCES factories(company_id, id)
-- → factory_id가 실제로 해당 company_id에 속하는지 DB가 직접 보장
```

**Option A 적용 전 확인 사항:**
```
CHECK-A1: factories.company_id DB 수준 NOT NULL 확인 (Production 스키마 조회 필요)
CHECK-A2: 기존 factories 행에 company_id = NULL인 행이 없음 확인
CHECK-A3: deleted_at IS NOT NULL 소프트 삭제 행에 UNIQUE 제약 문제 없음 확인
          → (company_id, id) UNIQUE는 소프트 삭제와 충돌 없음 (id PK가 이미 고유)
CHECK-A4: 기존 서비스에서 REFERENCES factories(id) FK를 사용하는 테이블 목록
          → 복합 FK 추가는 기존 단일 FK를 대체하지 않으며, 기존 코드와 충돌 없음
CHECK-A5: 신규 UNIQUE 인덱스 생성의 Production 영향
          → CREATE UNIQUE INDEX CONCURRENTLY로 잠금 없이 추가 가능
```

**Option A 채택 이점:**
```
- factory_id 소속 회사 검증을 DB FK로 완전히 보장
- factory 행의 company_id 변경 경합 자동 방어
  (FK는 참조 컬럼에 대해 SHARE ROW EXCLUSIVE 잠금 획득)
- 현재 BEFORE INSERT TRIGGER 제거 가능 (또는 단순 중복 검사로 교체)
```

#### 7.4.3 Option B — Factory 행 잠금 기반 Trigger

```sql
-- Option A 채택이 불가능한 경우의 상세 설계
CREATE OR REPLACE FUNCTION tam_grants_validate_factory_company_locked()
RETURNS TRIGGER AS $$
DECLARE
    v_company_id UUID;
BEGIN
    IF NEW.factory_id IS NOT NULL THEN
        -- FOR SHARE: factory 행의 company_id 변경(UPDATE)을 차단
        SELECT company_id INTO v_company_id
        FROM factories
        WHERE id = NEW.factory_id
        FOR SHARE;

        IF v_company_id IS NULL OR v_company_id != NEW.company_id THEN
            RAISE EXCEPTION 'factory_id % does not belong to company_id %',
                NEW.factory_id, NEW.company_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

**Option B 한계:**
```
FOR SHARE는 동시 UPDATE를 차단하지만,
factories.company_id가 실제로 변경 가능한지, 변경 시 어떤 제어가 있는지
별도 정책 확인 필요.
현재 routers/factories.py에 company_id 변경 엔드포인트가 없으므로
실질적 위험은 낮지만 DB 보증은 아니다.
```

#### 7.4.4 결정

```
OPTION_A_FEASIBILITY = CHECK-A1~A5 확인 후 결정 (구현 WO에서)
GPT_RECOMMENDATION = Option A
CURRENT_IMPLEMENTATION = BEFORE INSERT TRIGGER (§4.1.1, Option B 경량 버전)
  → CHECK-A1~A5 통과 시 Option A로 업그레이드
  → 통과 실패 시 Option B 상세 설계 후 GPT 재승인
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

내부 처리: §4.7 8단계 직렬화 흐름

동일 트랜잭션:
  INSERT tam_permission_grants
  INSERT tam_approval_audit_events (event_type=PERMISSION_GRANTED,
    event_data={"grant_id": ..., "bootstrap": false, ...})

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

내부 처리: §5.4 8단계 직렬화 흐름

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
내부 처리: §4.7 8단계 흐름 적용 (STEP 5 부여자 권한 검사는 Skip — Bootstrap Authority)

동일 트랜잭션:
  INSERT tam_permission_grants (permission_code=ROUTE_MANAGER, valid_until=NULL)
  INSERT tam_approval_audit_events (event_type=PERMISSION_GRANTED,
    event_data={"grant_id": ..., "bootstrap": true, ...})

응답 201: { grant_id, is_new: true }
응답 200: { grant_id, is_new: false }  ← idempotency_key 동일 재시도
응답 409: BOOTSTRAP_ALREADY_EXISTS (C04 실패 — 이력 있음 → ADMIN_RECOVERY 경로 안내)
응답 403: FORBIDDEN (role_code != "001" / 자기 부여)

활성화 Gate: OD-01 Owner 승인 전까지 무조건 503 BOOTSTRAP_NOT_AUTHORIZED
```

---

## 9. 동시성·멱등성

### 9.1 Grant 직렬화

```
논리 키 잠금 앵커 (§4.6) + SELECT FOR UPDATE (§4.7 STEP 3) → Write Skew 방지
동시 동일 논리 키 Grant 시도 → 직렬화 (순차 처리)
IntegrityError(UniqueViolation on idempotency_key) → 기존 행 조회 후 200 반환
```

### 9.2 중복 철회 멱등성

```
동일 grant_id 재철회:
  uq_tam_revocations_grant UNIQUE 제약
  → idempotency_key 동일: 기존 revocation_id 반환 200
  → idempotency_key 없음 또는 다름: 409 ALREADY_REVOKED
```

### 9.3 Bootstrap 동시 요청

```
논리 키 앵커 (ROUTE_MANAGER, company_id, SENTINEL_UUID, subject) FOR UPDATE +
  STEP 6 C04 재확인 (이력 있음 → ROLLBACK)
  → 동시 Bootstrap 두 요청 → 하나만 성공, 나머지 409 BOOTSTRAP_ALREADY_EXISTS
```

### 9.4 Grant/Revoke 경합

```
Grant 생성 Tx와 Grant 철회 Tx가 동일 논리 키에서 경합:
  → 두 Tx 모두 논리 키 앵커 FOR UPDATE 획득을 시도
  → 먼저 획득한 Tx가 COMMIT 후 두 번째 Tx 재개
  → 직렬화 결과가 결정적으로 확정됨 (§4.7 / §5.4)

부여자 ROUTE_MANAGER 철회 중 새 Grant 생성 경합 (OD-03 활성화 후 적용):
  Grant 생성 Tx의 STEP 5에서 부여자 Grant 행 FOR UPDATE 잠금
  잠금 순서: 논리 키 앵커(STEP 3) → 부여자 Grant 행(STEP 5)
  → Revoke Tx의 STEP 4(논리 키 앵커) → STEP 5(대상 Grant 행) 순서와 일치
  → 순환 잠금 없음, Deadlock 없음
```

### 9.5 감사 실패 처리

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

재시도 감사 이벤트 중복 방지:
  idempotency_key 동일 재시도 → 기존 행 반환 경로 (ROLLBACK 후 SELECT)
  → 새 감사 이벤트 INSERT 없음 (트랜잭션 내 INSERT가 ROLLBACK되므로)
```

**주의:** `bootstrap_flag`라는 별도 컬럼은 없다. Bootstrap 여부는 `event_data.bootstrap`으로 구분한다.

### 10.4 감사 불변 원칙

```
tam_approval_audit_events: append-only (UPDATE / DELETE 금지)
  BEFORE UPDATE → RAISE EXCEPTION (TAM-006 트리거)
  BEFORE DELETE → RAISE EXCEPTION (TAM-006 트리거)
```

---

## 11. 권한 검증 순서 및 잠금 정책

### 11.1 일반 인가 판정 (읽기/사용 경로)

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

### 11.2 Grant 생성 경로 잠금 정책

```
잠금 획득 순서 (항상 이 순서 준수):
  1. 논리 키 앵커 FOR UPDATE (§4.7 STEP 3)
  2. 부여자 ROUTE_MANAGER Grant 행 FOR UPDATE (§4.7 STEP 5, OD-03 활성화 후)

TOCTOU 방지:
  부여자 권한 확인(STEP 5)은 논리 키 잠금 획득(STEP 3) 이후에 수행한다.
  STEP 3 이전에 부여자 권한을 확인하면,
  잠금 획득 전 철회가 발생해도 검사 결과가 stale하게 남는다.
  → STEP 3 이후의 STEP 5에서 부여자 권한을 FOR UPDATE로 재확인한다.
```

### 11.3 Revoke 경로 잠금 정책

```
잠금 획득 순서:
  1. 논리 키 앵커 FOR UPDATE (§5.4 STEP 4)
  2. 대상 Grant 행 FOR UPDATE (§5.4 STEP 5)

철회 COMMIT 이후 시작된 작업은 이전 Grant를 사용할 수 없다:
  READ COMMITTED에서 COMMIT된 revocation은 이후 모든 조회에서 보인다.
  → 인가 판정 경로(§11.1)는 잠금 없이 SELECT만 수행하므로,
    Revoke COMMIT 이후 시작된 판정은 revocation을 반드시 보게 된다.
```

---

## 12. P01~P35 테스트 설계

> 이 섹션은 구현 전 테스트 명세이다. 실행 테스트가 아니다.

### 12.1 P01~P25 (기존)

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
| P18 | 기간 겹치는 중복 Grant 거부                  | 409 DUPLICATE_GRANT                    | §4.7 STEP 6 중복 검사 거부                                          |
| P19 | 철회된 Grant 기간과 겹치는 새 Grant 허용        | 201                                    | 철회된 Grant는 STEP 6 중복 검사에서 제외됨                             |
| P20 | 감사 INSERT 실패 시 Grant 전체 ROLLBACK    | Grant 없음 + audit 없음                  | tam_permission_grants INSERT 후 audit INSERT 실패 → 전체 RB         |
| P21 | 권한 철회 감사 원본 불변                     | revocation 삭제·변경 불가                  | DELETE/UPDATE tam_permission_revocations → 실패                    |
| P22 | STEP_APPROVER role 자동 부여 금지          | tam_permission_grants에 없음             | CHECK constraint에 STEP_APPROVER 없음 확인                         |
| P23 | Snapshot에 없는 사용자 결재 거부             | 403 FORBIDDEN_NOT_ASSIGNEE             | 요청 Snapshot.assignee_user_id에 없음 → 거부                        |
| P24 | DB 장애 시 Fail-closed                   | 503 또는 403, 허용 없음                    | Grant 조회 실패 → 예외 DENY (허용 Default 없음)                       |
| P25 | 기존 WP-08B HTTP 403 Gate 회귀           | 모든 TAM 쓰기 엔드포인트 403               | routers/tam_routes.py _require_route_manager() 무조건 403 유지      |

### 12.2 P26~P35 (R2 추가 — 동시성·직렬화)

> 각 항목은 초기 DB 상태 / Connection A / Connection B / 잠금 순서 / COMMIT 순서 / 기대 API 오류 / 기대 최종 DB 상태를 명시한다.

---

**P26 — 동시 동일 권한 Grant 생성**

```
초기 DB 상태:
  tam_permission_grant_locks: 없음
  tam_permission_grants: 없음 (company=C1, factory=null, user=U1, ROUTE_MANAGER)

Connection A: POST /grants (C1, null, U1, ROUTE_MANAGER, valid_from=t0, valid_until=null)
Connection B: POST /grants (C1, null, U1, ROUTE_MANAGER, valid_from=t0, valid_until=null)

잠금 순서:
  A: STEP 2(UPSERT lock) → STEP 3(FOR UPDATE lock 획득)
  B: STEP 2(UPSERT lock, ON CONFLICT DO NOTHING) → STEP 3(FOR UPDATE — BLOCKS)
  A: STEP 6(중복 없음 확인) → STEP 7(INSERT G1) → STEP 8(COMMIT)
  B: 재개 → STEP 6(G1 발견 → DUPLICATE) → ROLLBACK

COMMIT 순서: A COMMIT → B ROLLBACK
기대 API 오류: B → 409 DUPLICATE_GRANT
기대 최종 DB 상태:
  tam_permission_grant_locks: 1행 (C1, SENTINEL, U1, ROUTE_MANAGER)
  tam_permission_grants: 1행 (G1)
  tam_approval_audit_events: 1행 (PERMISSION_GRANTED, grant_id=G1)
```

---

**P27 — 기간 중복 Grant 거부**

```
초기 DB 상태:
  tam_permission_grants: G1 (C1, null, U1, ROUTE_MANAGER, valid_from=t0, valid_until=t2)

Connection A: POST /grants (C1, null, U1, ROUTE_MANAGER, valid_from=t1, valid_until=t3)
              where t0 < t1 < t2 < t3 (기간 중복)

잠금 순서:
  A: STEP 3(FOR UPDATE lock 획득)
  A: STEP 6(G1 발견 — [t0,t2) ∩ [t1,t3) = [t1,t2) ≠ ∅ → DUPLICATE) → ROLLBACK

Connection B: 없음

기대 API 오류: A → 409 DUPLICATE_GRANT
기대 최종 DB 상태:
  tam_permission_grants: 여전히 G1만 존재
  tam_approval_audit_events: 변경 없음
```

---

**P28 — 철회 이후 동일 권한 재발급 성공**

```
초기 DB 상태:
  tam_permission_grants: G1 (C1, null, U1, ROUTE_MANAGER, valid_from=t0, valid_until=null)
  tam_permission_revocations: R1 (grant_id=G1)

Connection A: POST /grants (C1, null, U1, ROUTE_MANAGER, valid_from=t1, valid_until=null)
              (새 idempotency_key 사용)

잠금 순서:
  A: STEP 3(FOR UPDATE lock 획득)
  A: STEP 6(G1 검사 → R1 존재 → 철회됨 → 중복 검사 제외 → 중복 없음) → INSERT G2

COMMIT 순서: A COMMIT
기대 API 오류: 없음 (201)
기대 최종 DB 상태:
  tam_permission_grants: G1(revoked), G2(active)
  tam_permission_revocations: R1 (G1 철회)
  tam_approval_audit_events: 기존 + PERMISSION_GRANTED(G2)
```

---

**P29 — 동시 Grant 생성과 기존 Grant 철회 경합**

```
초기 DB 상태:
  tam_permission_grants: G1 (C1, null, U1, ROUTE_MANAGER, valid_from=t0, valid_until=null)
  tam_permission_revocations: 없음

Connection A: POST /grants/{G1}/revoke (G1 철회)
Connection B: POST /grants (C1, null, U1, ROUTE_MANAGER, valid_from=t1, valid_until=null)

시나리오 1 (A가 먼저 잠금 획득):
  A: STEP 3 lock 획득 (논리 키) → STEP 5(G1 FOR UPDATE)
  B: STEP 3 BLOCKS
  A: STEP 7(INSERT R1) → STEP 8 COMMIT
  B: 재개 → STEP 6(G1 확인 → 철회됨 → 제외 → 중복 없음) → INSERT G2

시나리오 2 (B가 먼저 잠금 획득):
  B: STEP 3 lock 획득 → STEP 6(G1 활성 → 기간 중복 → ROLLBACK) → 409 DUPLICATE_GRANT
  A: STEP 3 획득 → STEP 7(INSERT R1) → COMMIT

두 시나리오 모두 최종 DB 상태는 결정적:
  시나리오 1: G1(revoked) + G2(active), 2 audit events
  시나리오 2: G1(active), R1(revoke), 1 audit event (PERMISSION_REVOKED)
잠금 순서 보장으로 Deadlock 없음
```

---

**P30 — 부여자 권한 철회 중 Grant 생성 경합 (OD-03 활성화 후 적용)**

```
초기 DB 상태:
  tam_permission_grants: G_M (Manager M의 ROUTE_MANAGER, C1)
  tam_permission_grants: 없음 (U1에 대한 Grant)

Connection A: POST /grants (M이 U1에게 ASSIGNEE_MANAGER 부여)
Connection B: POST /grants/{G_M}/revoke (M의 ROUTE_MANAGER 철회)

잠금 순서 (A의 대상: (C1,SENTINEL,U1,ASSIGNEE_MANAGER) / B의 대상: (C1,SENTINEL,M,ROUTE_MANAGER)):
  A: STEP 3(U1/ASSIGNEE_MANAGER 논리 키 잠금)
     STEP 5(G_M FOR UPDATE — M의 권한 확인)
  B: STEP 3(M/ROUTE_MANAGER 논리 키 잠금 — 다른 키이므로 A와 독립)
     STEP 5(G_M FOR UPDATE — BLOCKS, A가 이미 잠금)

  A: STEP 6(중복 없음) → STEP 7(INSERT G_U1) → STEP 8 COMMIT (G_M 잠금 해제)
  B: 재개 → STEP 7(INSERT R_M) → COMMIT

결과: G_U1(active) + G_M(revoked)
이유: G_U1은 M의 권한이 유효할 때 생성됐으므로 사후 무효화 없음 (append-only 원칙)

기대 최종 DB 상태:
  G_M: revoked / G_U1: active
  audit: PERMISSION_GRANTED(G_U1) + PERMISSION_REVOKED(G_M)
```

---

**P31 — 동일 Idempotency Key 동시 재시도**

```
초기 DB 상태:
  tam_permission_grants: 없음 (idempotency_key=K1)

Connection A: POST /grants (..., idempotency_key=K1)
Connection B: POST /grants (..., idempotency_key=K1)  ← 동일 payload

잠금 순서:
  두 Tx 모두 STEP 7에서 INSERT 시도
  A: INSERT 성공 → G1 생성
  B: UniqueViolation(idempotency_key) → 예외 포획 → SELECT WHERE idempotency_key=K1 → G1 반환

COMMIT 순서: A COMMIT → B ROLLBACK (내부 처리 후 200 반환)
기대 API 응답: A → 201 {grant_id=G1, is_new=true} / B → 200 {grant_id=G1, is_new=false}
기대 최종 DB 상태:
  tam_permission_grants: G1 (1행)
  tam_approval_audit_events: 1행 (A 트랜잭션에서만 INSERT됨)
```

---

**P32 — 동일 Idempotency Key + 다른 Payload 차단**

```
초기 DB 상태:
  tam_permission_grants: G1 (idempotency_key=K1, valid_until=null)

Connection A: POST /grants (..., idempotency_key=K1, valid_until=2027-01-01T00:00:00Z)

잠금 순서:
  A: STEP 4(SELECT WHERE idempotency_key=K1 → G1 발견)
     payload 비교: G1.valid_until=null vs 요청.valid_until=2027-01-01 → MISMATCH
     ROLLBACK

기대 API 오류: 409 IDEMPOTENCY_CONFLICT
기대 최종 DB 상태: G1 변경 없음
```

---

**P33 — 다른 논리 키 독립성**

```
초기 DB 상태:
  tam_permission_grants: 없음

Connection A: POST /grants (C1, null, U1, ASSIGNEE_MANAGER)
              논리 키 = (C1, SENTINEL, U1, ASSIGNEE_MANAGER)
Connection B: POST /grants (C1, F2, U1, ROUTE_MANAGER)
              논리 키 = (C1, F2, U1, ROUTE_MANAGER)

잠금 순서:
  A: STEP 3(논리 키 A 잠금 획득 — 즉시)
  B: STEP 3(논리 키 B 잠금 획득 — 즉시, A와 독립)
  A, B: 병렬로 STEP 6~8 수행

COMMIT 순서: 순서 무관, 두 트랜잭션 독립 처리
기대 API 응답: A → 201 G1 / B → 201 G2 (둘 다 성공, 순서 무관)
기대 최종 DB 상태:
  tam_permission_grants: G1(ASSIGNEE_MANAGER) + G2(ROUTE_MANAGER)
  tam_approval_audit_events: 2행
```

---

**P34 — Factory 소속 변경과 Grant 생성 경합**

```
초기 DB 상태:
  factories: F1 (company_id=C1, id=F1_UUID)
  tam_permission_grants: 없음

Connection A: POST /grants (C1, F1_UUID, U1, ROUTE_MANAGER)
              → TRIGGER: SELECT FROM factories WHERE id=F1 AND company_id=C1

Connection B: UPDATE factories SET company_id=C2 WHERE id=F1_UUID
              (factories.company_id 변경 가능 여부는 별도 정책)

시나리오 (Option A — 복합 FK 채택 시):
  A: FK 검사 — factories(C1, F1_UUID) 참조 → F1의 company_id가 C1이면 성공
  B: F1의 company_id를 C2로 변경하려 하면
     → A의 FK가 F1 행에 SHARE ROW EXCLUSIVE 잠금 유지 중
     → B BLOCKS 또는 DEADLOCK 방지 로직에 의해 순서 결정

시나리오 (Option B — Trigger FOR SHARE 사용 시):
  A: SELECT FROM factories WHERE id=F1 FOR SHARE (SHARE 잠금)
  B: UPDATE factories ... (SHARE 잠금과 충돌 → BLOCKS)
  A: COMMIT → B 재개

결과 (두 옵션 모두):
  A가 먼저 COMMIT: G1(C1,F1) 생성 후 B가 F1의 company_id 변경 (G1은 이미 유효)
  B가 먼저 COMMIT: F1.company_id=C2 → A의 factory 검증 실패 → A ROLLBACK (422)

기대 최종 DB 상태:
  A 먼저: G1(C1, F1) 유효, F1.company_id=C2 (기존 G1의 참조는 변경 안 됨)
  B 먼저: G1 없음
```

---

**P35 — 감사 INSERT 실패 시 트랜잭션 전체 ROLLBACK**

```
초기 DB 상태:
  tam_permission_grants: 없음
  tam_approval_audit_events: 없음

Connection A: POST /grants (C1, null, U1, ROUTE_MANAGER)
              내부: STEP 7 — INSERT tam_permission_grants 성공 → INSERT tam_approval_audit_events 실패
              (시뮬레이션: event_type CHECK 위반 또는 DB 오류)

결과:
  트랜잭션 전체 ROLLBACK (§10.2)

기대 API 오류: 500 INTERNAL_SERVER_ERROR (감사 실패 = 전체 실패)
기대 최종 DB 상태:
  tam_permission_grants: 0행 (ROLLBACK으로 취소됨)
  tam_approval_audit_events: 0행 (ROLLBACK으로 취소됨)
```

---

## 13. 미결정 Owner 정책 (OD)

| OD    | 내용                              | 후보                                       | 현재 처리                         |
|-------|----------------------------------|------------------------------------------|---------------------------------|
| OD-01 | FIRST_BOOTSTRAP 실행 권한자          | (a) role_code="001" 플랫폼 관리자 (GPT 권고) | BLOCKED — Bootstrap API 비활성   |
| OD-02 | APPROVED 효력 만료 기간              | (a) 만료 없음, (b) 24h, (c) Consumer 설정  | valid_until NULL 기본 유지         |
| OD-03 | ROUTE_MANAGER 위임 가능 권한 범위      | (a) 전체 코드, (b) 제한 코드, (c) 별도 위임 테이블 | BLOCKED — Grant/Revoke API 비활성 |
| OD-06 | ADMIN_RECOVERY 실행 절차 및 권한      | 미정                                       | BLOCKED — Recovery API 비활성     |
| OD-09 | REQUEST_SUBMITTER 범위             | (a) Consumer 서비스 계정만, (b) end-user 직접 | BLOCKED — end-user 차단           |

---

## 14. 기존 설계 정합성 검사

| 항목                                       | 판정              | 근거                                                          |
|------------------------------------------|------------------|-------------------------------------------------------------|
| TAM-006 Route/Version 구조                 | COMPATIBLE        | tam_permission_grants는 별도 테이블, 기존 4테이블 무변경               |
| WP-08B routes_svc.py company_id 검증       | COMPATIBLE        | Grant 부여 시에도 company_id 일치 강제                              |
| TAI Core Identity SoT                    | COMPATIBLE        | Grant는 TAI Core user UUID 참조, SoT 변경 없음                   |
| PRJ 개발거버넌스 append-only 원칙             | COMPATIBLE        | Grant/Revocation 모두 append-only                             |
| Chemical WP-07I-A 불변식                   | COMPATIBLE        | TAM 권한 원장은 Chemical 구조 독립                                  |
| PostgreSQL CHECK 서브쿼리                   | RESOLVED (R1)     | 서브쿼리 제거 → BEFORE INSERT TRIGGER로 대체                        |
| factories UNIQUE(company_id, id) 부재      | DB_PENDING (R2)   | Option A(UNIQUE 추가) vs Option B 비교 문서화 (§7.4). 구현 WO에서 결정  |
| tam_approval_audit_events bootstrap_flag  | RESOLVED (R1)     | 별도 컬럼 없음 → event_data.bootstrap으로 저장                      |
| Company/Factory Grant 상호 간섭             | RESOLVED (R1)     | 독립성 원칙 명시 (§4.3, §7.1)                                    |
| Bootstrap 이후 관리자 복구                   | RESOLVED (R1)     | FIRST_BOOTSTRAP / ADMIN_RECOVERY 분리 (§6)                   |
| READ COMMITTED Write Skew                | RESOLVED (R2)     | 논리 키 잠금 앵커 + FOR UPDATE 직렬화 (§4.6, §4.7)                  |
| Grant/Revoke 경합 Deadlock 방지             | RESOLVED (R2)     | 잠금 순서 고정: 논리 키 → Grant 행 (§5.4, §11)                      |
| Idempotency payload 정규화                 | RESOLVED (R2)     | 정규화 payload 명세 + API 작업 종류별 독립 키 권고 (§4.5)               |

---

## 15. 구현 Gate

```
TAM-008C-003 DESIGN DOCUMENT (v0.3)  = 이 문서 (R2 추가 완료)
IMPLEMENTATION                        = BLOCKED (GPT 독립검증 후 별도 WO)

PR #572 MERGE                         = OWNER APPROVAL REQUIRED
Bootstrap API Activation              = BLOCKED (OD-01 Owner 승인 필요)
ADMIN_RECOVERY API                    = BLOCKED (OD-06 Owner 승인 필요)
Grant/Revoke API 활성화               = BLOCKED (OD-03 Owner 승인 필요)
TAM HTTP 쓰기 Gate 해제               = BLOCKED
CHEMICAL WP-07I-A                     = BLOCKED
PRODUCTION DEPLOY                     = BLOCKED

Option A 채택 전 필수 확인 (구현 단계):
  CHECK-A1: factories.company_id DB NOT NULL 확인
  CHECK-A2: 기존 factories 행 company_id=NULL 없음 확인
  CHECK-A3~A5: 소프트삭제·서비스·인덱스 영향 확인

다음 단계 (GPT 독립검증 후):
  TAM-008C Migration 설계 → Option A/B 최종 선택 → Owner 승인 → 구현 WO 발행
```
