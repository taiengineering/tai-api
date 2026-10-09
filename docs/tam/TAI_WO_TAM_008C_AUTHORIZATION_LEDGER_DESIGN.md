---
doc_id: TAI-WO-TAM-008C-AUTHZ-LEDGER-V0.1
title: TAM 공통 결재 권한 원장 상세설계
status: GPT_REVIEW_REQUIRED
version: 0.1
created: 2026-10-09
author: GPT (설계) / Claude Code (문서화)
base_design: docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md
base_sha: 1c349397c3052fd496b5270f0f42d82e3e0167e0
---

# TAM 공통 결재 권한 원장 상세설계

## 0. 변경 이력

| 버전  | 일자       | 내용                       | 담당       |
|------|------------|--------------------------|-----------|
| 0.1  | 2026-10-09 | 초안 — GPT 확정 설계 기반 문서화 | GPT/Claude |

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

### 1.3 구현 Gate

```
TAM-008C-003 DESIGN = 이 문서
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
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT tam_grants_company_match CHECK (
        factory_id IS NULL OR
        factory_id IN (SELECT id FROM factories WHERE company_id = tam_permission_grants.company_id)
    ),
    CONSTRAINT tam_grants_valid_period CHECK (
        valid_until IS NULL OR valid_until > valid_from
    )
);
```

**주의:** `STEP_APPROVER`는 permission_code CHECK에서 제외한다 — Snapshot 경로로만 처리.

### 4.2 중복 방지 제약

시간 조건이 있는 Partial Unique Index에 `now()`를 사용하지 않는다.  
아래 두 가지 접근 중 하나를 구현 시 결정한다.

**옵션 A — 동일 기간 내 중복 UNIQUE INDEX (구현 단순):**

```sql
-- 같은 회사·사업장·사용자·권한에 대해 valid_until IS NULL인 활성 Grant는 1개만 허용
CREATE UNIQUE INDEX uq_tam_grants_active
    ON tam_permission_grants (company_id, COALESCE(factory_id, '00000000-0000-0000-0000-000000000000'), subject_user_id, permission_code)
    WHERE valid_until IS NULL;
```

**옵션 B — Trigger 기반 중복 검사 (기간 겹침 전체 처리):**
```
BEFORE INSERT: 동일 (company_id, factory_id, subject_user_id, permission_code)에 대해
  valid_from < NEW.valid_until AND (valid_until IS NULL OR valid_until > NEW.valid_from)
  인 미철회 Grant가 있으면 RAISE EXCEPTION
```

구현 시 옵션 선택 → GPT 검토 후 확정. **이 문서에서는 옵션 A를 기본 방향으로 명시한다.**

### 4.3 범위 정책

| factory_id | 의미                                           |
|------------|----------------------------------------------|
| NULL       | 회사 전체 범위 (Company-wide) — 해당 회사 모든 사업장 적용 |
| UUID       | 특정 사업장 범위만 — 해당 factory에서만 유효              |

```
Company-wide Grant가 있어도 특정 Factory Grant가 있는 경우
  → 더 제한적인 범위(Factory) 우선 적용
  → 단, 회사 범위 Grant로 다른 Factory에서도 동작하는지는 OD 미결
  → 현재: Factory-scoped route는 Factory-scoped Grant 있어야 접근 가능
```

### 4.4 만료 처리

```
valid_until IS NULL → 만료 없음 (명시적 철회까지 유효)
valid_until < now() → 만료 (DENY, PERMISSION_GRANT_EXPIRED 이벤트 기록)

만료 판정은 실행 시점에 수행한다.
만료된 Grant를 자동 삭제하거나 UPDATE하지 않는다 (불변 원칙).
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
이미 철회된 Grant에 대한 재철회 요청 → 409 ALREADY_REVOKED (멱등 처리).
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

### 6.1 정책

최초 ROUTE_MANAGER Grant는 검증된 TAI 플랫폼 관리자만 생성한다.

```
Bootstrap Authority = role_code == "001" (플랫폼 관리자)
  단, role_code="001"이 자동으로 ROUTE_MANAGER를 갖는 것은 아님
  플랫폼 관리자는 Bootstrap Grant만 생성할 수 있는 별도 경로로 동작
```

**OD-01 최종 Owner 승인 전까지 Bootstrap API는 활성화하지 않는다.**

### 6.2 Bootstrap 허용 조건 (전부 충족 시 실행)

```
C01 요청자 = role_code == "001" AND status_code == ACTIVE
C02 대상 회사 = companies 테이블에 존재 AND status_code ACTIVE (또는 유사 활성 상태)
C03 대상 사용자 = 해당 company_id 소속 AND status_code == ACTIVE
C04 해당 회사의 permission_code == ROUTE_MANAGER Grant가 아직 없음
C05 Factory 지정 시 해당 factory가 대상 회사 소속임
C06 동시 Bootstrap 요청 중복 방지 (Idempotency Key 또는 advisory lock)
```

### 6.3 자기 권한 상승 금지

```
Bootstrap: subject_user_id == granted_by (자기 자신에게 부여) → FORBIDDEN
  단, Bootstrap Authority가 자신에게 부여하는 것도 금지
  (Bootstrap Authority ≠ ROUTE_MANAGER 소유자)
일반 Grant: granted_by == subject_user_id → 금지 (C 조건 추가 필요)
```

### 6.4 Bootstrap 이후 관리

```
Bootstrap 이후 추가 ROUTE_MANAGER Grant는 기존 ROUTE_MANAGER가 부여 가능
  → 단, 이 범위는 TAM-008C 구현에서 확정
Bootstrap API와 일반 Grant API는 별도 경계 유지
```

---

## 7. Company/Factory Scope 정책

### 7.1 원칙

```
TAM v1 기준: users.factory_id 단일 컬럼 사용 (다중 사업장 원장 없음)
Company-wide Grant (factory_id=NULL): 해당 회사 모든 사업장에서 유효
Factory-scoped Grant (factory_id=UUID): 해당 사업장에서만 유효
Factory-scoped Grant가 있다고 TAI Core의 factory 데이터 접근범위가 변경되지 않음
권한 충돌 시 더 제한적인 범위 적용
```

### 7.2 교차 회사 차단

```
Grant 부여자(granted_by)의 company_id == Grant의 company_id
  → 다른 회사 사용자가 이 회사의 Grant를 부여/철회 불가
  → DB 트리거 또는 서비스 계층 강제 (Layer 1 + Layer 2)

교차 회사 Grant 조회 → 404 (존재 은닉, 정보 누출 방지)
```

### 7.3 Factory 접근 검증 계층

```
Layer 1 — Grant 데이터 범위:
  tam_permission_grants.factory_id = 요청 대상 factory
  tam_permission_grants.company_id = 요청자 company_id

Layer 2 — 서비스 계층 검증:
  요청자 users.company_id == Grant.company_id
  Grant.factory_id IS NULL OR Grant.factory_id == 요청 대상 factory
  요청자 users.factory_id == Grant.factory_id (Factory tier일 경우)
```

---

## 8. API 계약

### 8.1 `POST /v1/tam/permissions/grants` — 권한 부여

```
인증: get_current_user() → ACTIVE 필수
권한: granted_by의 ROUTE_MANAGER Grant 또는 Bootstrap Authority (role_code=001)
요청 본문:
  company_id:        UUID (요청자 company_id와 일치 강제)
  factory_id:        UUID | null
  subject_user_id:   UUID
  permission_code:   ROUTE_MANAGER | ASSIGNEE_MANAGER | REQUEST_SUBMITTER |
                     DELEGATION_MANAGER | REQUEST_REVOKER
  valid_from:        ISO8601 | null (null = now())
  valid_until:       ISO8601 | null
  grant_reason:      string
  idempotency_key:   UUID (중복 요청 방지)

응답 201: grant_id, created_at
응답 409: DUPLICATE_GRANT (활성 Grant 존재)
응답 403: FORBIDDEN (권한 없음 / 자기 상승 / 교차 회사)
응답 422: 입력 오류

동일 트랜잭션:
  INSERT tam_permission_grants
  INSERT tam_approval_audit_events (PERMISSION_GRANTED)

Idempotency: idempotency_key로 동일 요청 재시도 시 기존 grant_id 반환
```

### 8.2 `GET /v1/tam/permissions/grants` — 권한 목록 조회

```
인증: get_current_user() → ACTIVE 필수
권한: ROUTE_MANAGER Grant 또는 Bootstrap Authority
쿼리 파라미터: company_id, factory_id, subject_user_id, permission_code, active_only
응답 200: grant 목록 (is_valid 계산 포함)

교차 회사 요청 → 빈 배열 (404 아님 — 목록 조회는 존재 은닉 대신 빈 결과)
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
권한: ROUTE_MANAGER Grant (동일 회사) 또는 Bootstrap Authority
요청 본문:
  reason:            string (필수)
  idempotency_key:   UUID

응답 200: revocation_id, revoked_at
응답 409: ALREADY_REVOKED (이미 철회된 경우 멱등 반환)
응답 403: FORBIDDEN (교차 회사 / 권한 없음)
응답 404: Grant 없음 또는 교차 회사

동일 트랜잭션:
  INSERT tam_permission_revocations
  INSERT tam_approval_audit_events (PERMISSION_REVOKED)
```

### 8.5 `POST /v1/tam/permissions/bootstrap` — 최초 관리자 부여

```
인증: get_current_user()
권한: role_code == "001" (플랫폼 관리자) — 이 권한만 이 엔드포인트 접근 가능
요청 본문:
  company_id:        UUID
  factory_id:        UUID | null
  subject_user_id:   UUID
  grant_reason:      string
  idempotency_key:   UUID

검증 순서:
  C01 요청자 role_code == "001"
  C02 대상 회사 존재 및 활성
  C03 대상 사용자 해당 회사 소속 ACTIVE
  C04 해당 회사 ROUTE_MANAGER Grant 없음
  C05 Factory 지정 시 소속 확인
  C06 subject_user_id != granted_by (자기 부여 금지)

동일 트랜잭션:
  INSERT tam_permission_grants (permission_code = ROUTE_MANAGER, valid_until = NULL)
  INSERT tam_approval_audit_events (PERMISSION_GRANTED, bootstrap_flag = true)

응답 201: grant_id
응답 409: BOOTSTRAP_ALREADY_EXISTS
응답 403: FORBIDDEN (role_code != "001" / 자기 부여)

활성화 Gate: OD-01 Owner 승인 전까지 무조건 503 BOOTSTRAP_NOT_AUTHORIZED
```

---

## 9. 동시성·멱등성

### 9.1 중복 Grant 방지

```
동시 Grant 생성 (같은 company/factory/user/permission):
  방법 A: UNIQUE INDEX + PostgreSQL INSERT … ON CONFLICT DO NOTHING
  방법 B: FOR UPDATE 잠금 후 중복 확인

방법 A를 기본으로 한다 (원자성 보장, 구현 단순).
충돌 시 응답: 409 DUPLICATE_GRANT (기존 grant_id 포함)
```

### 9.2 중복 철회 멱등성

```
동일 grant_id 재철회 요청:
  tam_permission_revocations.grant_id UNIQUE 제약 (uq_tam_revocations_grant)
  → 첫 번째 INSERT 성공 후 동일 요청 → 409 ALREADY_REVOKED
  idempotency_key 제공 시 기존 revocation_id 반환 (멱등)
```

### 9.3 Bootstrap 동시 요청

```
Bootstrap은 company_id + permission_code = ROUTE_MANAGER를 기준으로
UNIQUE INDEX 또는 SELECT FOR UPDATE로 직렬화한다.
동시 Bootstrap → 하나만 성공, 나머지 409 BOOTSTRAP_ALREADY_EXISTS
```

### 9.4 감사 실패 처리

```
Grant INSERT와 audit INSERT는 같은 트랜잭션.
audit INSERT 실패 → 전체 트랜잭션 ROLLBACK → Grant 실패.
"감사 실패로 인한 Grant 허용"은 없다 (보안 우선).
```

---

## 10. 감사 원장

### 10.1 테이블: `tam_approval_audit_events`

기준 설계: `docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md:780`  
새 별도 감사 테이블을 추가하지 않는다.

```sql
-- 기존 TAM_006 설계의 tam_approval_audit_events를 권한 이벤트도 수용하도록 확장
-- event_type CHECK에 아래 이벤트 추가 (Migration 시 결정)

PERMISSION_GRANTED    -- 권한 부여 (Bootstrap 포함)
PERMISSION_REVOKED    -- 권한 철회
PERMISSION_GRANT_EXPIRED  -- 만료된 Grant 사용 시도 (관찰 이벤트)
PERMISSION_USE_DENIED     -- 미보유 권한 사용 시도 (관찰 이벤트)
```

### 10.2 이벤트 기록 원칙

```
PERMISSION_GRANTED / PERMISSION_REVOKED:
  Grant / Revocation INSERT와 동일 트랜잭션 필수
  실패 → 전체 ROLLBACK

PERMISSION_GRANT_EXPIRED / PERMISSION_USE_DENIED:
  이 두 이벤트는 상태 변경 없는 관찰 이벤트
  기록 실패 시 동작:
    DENY 응답은 이미 결정됨 (실패 이전에 판정 완료)
    기록 실패 자체는 별도 로깅 (non-blocking)
    단, 기록 실패로 인해 DENY가 ALLOW로 바뀌어서는 안 됨
```

### 10.3 감사 불변 원칙

```
tam_approval_audit_events는 append-only (UPDATE / DELETE 금지)
근거 패턴: services/document_confirm_svc.py:260-267 runtime_document_approval
```

---

## 11. 권한 검증 순서

모든 TAM 관리 작업에서 아래 순서로 검증한다.

```
1. TAI Core JWT 검증 (get_current_user)
2. 사용자 ACTIVE 상태 확인 (_require_active_account)
3. 현재 회사 소속 확인 (user.company_id)
4. 요청한 Factory 접근범위 확인 (user.factory_id == 요청 factory)
5. 해당 TAM 권한 Grant 확인 (tam_permission_grants 존재)
6. Grant 유효기간 확인 (valid_from <= now() AND (valid_until IS NULL OR now() < valid_until))
7. Revocation 존재 여부 확인 (tam_permission_revocations에 grant_id 없음)
8. 업무 객체의 Company/Factory Scope 확인
9. 권한 사용 이력 기록 (audit_events, 관찰 이벤트는 non-blocking)

1~7 중 하나라도 실패 → DENY (Fail-closed)
권한 데이터 조회 실패 → DENY (503 또는 403, 허용 불가)
```

---

## 12. P01~P25 테스트 설계

> 이 섹션은 구현 전 테스트 명세이다. 실행 테스트가 아니다.

| ID  | 시나리오                               | 예상 결과                          | 검증 포인트                                                      |
|-----|--------------------------------------|----------------------------------|--------------------------------------------------------------|
| P01 | 최초 회사 관리자 Bootstrap               | 201 Created, grant_id 반환         | C01~C06 전부 충족 시 tam_permission_grants INSERT + audit INSERT  |
| P02 | 중복 Bootstrap 거부                    | 409 BOOTSTRAP_ALREADY_EXISTS       | tam_permission_grants 변경 없음, audit 불변                      |
| P03 | 일반 사용자 Bootstrap 거부               | 403 FORBIDDEN                     | role_code != "001" → 즉시 거부                                  |
| P04 | role_code만으로 TAM 권한 생성 불가         | tam_permission_grants 변경 없음      | users.role_code UPDATE는 tam_permission_grants 트리거 없음       |
| P05 | ROUTE_MANAGER 명시적 Grant              | 201 Created                       | tam_permission_grants INSERT + audit, subject != granted_by   |
| P06 | ASSIGNEE_MANAGER 명시적 Grant           | 201 Created                       | permission_code = ASSIGNEE_MANAGER 유효 확인                    |
| P07 | 회사 범위 권한 검증 (factory_id=NULL)     | 해당 회사 모든 경로 접근 가능                | scoped_filter 연동 확인                                         |
| P08 | Factory 범위 권한 검증                   | 해당 Factory에서만 유효, 타 Factory 차단   | grant.factory_id != request.factory_id → 403                  |
| P09 | 타 회사 Grant 조회·변경 거부              | 404 (목록) / 403 (변경)              | company_id 불일치 → 정보 은닉                                     |
| P10 | 타 Factory Grant 사용 거부               | 403                               | Factory-scoped grant는 지정 factory에서만 작동                    |
| P11 | 만료된 Grant 거부                       | 403, PERMISSION_GRANT_EXPIRED 감사  | valid_until < now() → DENY + 관찰 이벤트 기록                    |
| P12 | 철회된 Grant 거부                       | 403, tam_permission_revocations 확인 | revocation 존재 → DENY                                        |
| P13 | 비활성 사용자 권한 사용 거부                | 403 ACCOUNT_INACTIVE               | _require_active_account 우선 실행                               |
| P14 | 다른 회사로 이동한 사용자 권한 거부          | 403                               | users.company_id != grant.company_id → Layer 2 차단             |
| P15 | 자기 자신에 대한 권한 상승 거부             | 403 SELF_GRANT_FORBIDDEN            | subject_user_id == granted_by → 거부 (Bootstrap 포함)           |
| P16 | 동일 Grant 중복 요청 멱등성              | 409 or 기존 grant_id 반환            | idempotency_key 일치 시 기존 결과 반환                             |
| P17 | 동시 Grant 생성 중복 방지               | 하나만 201, 나머지 409               | UNIQUE INDEX 경합 → first INSERT 승리, 나머지 CONFLICT            |
| P18 | 철회 중 권한 사용 경쟁                   | 철회 후 사용 → 403                   | tam_permission_revocations INSERT COMMIT 이후 조회 → DENY       |
| P19 | 감사 INSERT 실패 시 Grant 전체 ROLLBACK | Grant 없음 + audit 없음              | tam_permission_grants INSERT 후 audit INSERT 실패 → 전체 RB      |
| P20 | 권한 철회 감사 원본 불변                  | revocation 삭제·변경 불가             | DELETE/UPDATE tam_permission_revocations → 실패                 |
| P21 | STEP_APPROVER role 자동 부여 금지       | tam_permission_grants에 STEP_APPROVER 없음 | CHECK constraint에 STEP_APPROVER 없음 확인             |
| P22 | Snapshot에 없는 사용자 결재 거부          | 403 FORBIDDEN_NOT_ASSIGNEE          | 요청 Snapshot.assignee_user_id에 없음 → 거부                    |
| P23 | Consumer service 인증과 end-user 구분  | end-user 직접 제출 → 503 (OD-09 미결) | REQUEST_SUBMITTER 경로: Consumer account만 허용                 |
| P24 | DB 장애 시 Fail-closed                | 503 또는 403, 허용 없음               | Grant 조회 실패 → 예외 DENY (허용 Default 없음)                    |
| P25 | 기존 WP-08B HTTP 403 Gate 회귀        | 모든 TAM 쓰기 엔드포인트 403           | routers/tam_routes.py _require_route_manager() 무조건 403 유지  |

---

## 13. 미결정 Owner 정책 (OD)

| OD    | 내용                              | 후보                                       | 현재 처리              |
|-------|----------------------------------|------------------------------------------|----------------------|
| OD-01 | 최초 ROUTE_MANAGER Bootstrap 권한자 | (a) role_code="001" 플랫폼 관리자 (GPT 권고) | BLOCKED — Bootstrap API 비활성 |
| OD-02 | APPROVED 효력 만료 기간              | (a) 만료 없음, (b) 24h, (c) Consumer 설정  | valid_until NULL 기본 유지 |
| OD-09 | REQUEST_SUBMITTER 범위             | (a) Consumer 서비스 계정만, (b) end-user 직접 | BLOCKED — end-user 차단 |

---

## 14. 기존 설계 정합성 검사

### 검사 결과

| 항목                                       | 판정       | 근거                                                |
|------------------------------------------|------------|---------------------------------------------------|
| TAM-006 Route/Version 구조                 | COMPATIBLE | tam_permission_grants는 별도 테이블, 기존 4테이블 무변경  |
| WP-08B routes_svc.py company_id 검증       | COMPATIBLE | Grant 부여 시에도 company_id 일치 강제                 |
| TAI Core Identity SoT                    | COMPATIBLE | Grant는 TAI Core user UUID 참조, SoT 변경 없음       |
| PRJ 개발거버넌스 append-only 원칙             | COMPATIBLE | Grant/Revocation 모두 append-only                  |
| Chemical WP-07I-A 불변식                   | COMPATIBLE | TAM 권한 원장은 Chemical 구조 독립                     |
| PostgreSQL 트랜잭션 패턴 (SELECT FOR UPDATE) | COMPATIBLE | Grant 중복 방지에 UNIQUE INDEX + ON CONFLICT 사용 예정 |

### 발견된 충돌 없음

현재 0건. 구현 단계에서 재확인 필요.

---

## 15. 구현 Gate

```
TAM-008C-003 DESIGN DOCUMENT  = 이 문서
IMPLEMENTATION                = BLOCKED (GPT 독립검증 후 별도 WO)

PR #572 MERGE                 = OWNER APPROVAL REQUIRED
Bootstrap API Activation      = BLOCKED (OD-01 Owner 승인 필요)
TAM HTTP 쓰기 Gate 해제        = BLOCKED
CHEMICAL WP-07I-A             = BLOCKED
PRODUCTION DEPLOY             = BLOCKED

다음 단계 (GPT 독립검증 후):
  TAM-008C Migration 설계 → Owner 승인 → 구현 WO 발행
```
