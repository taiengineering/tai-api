---
doc_id: TAI-TAM-MODULE-DEFINITION-20261010
title: "TAI 공통 결재 모듈(TAM) 정의 및 구현 현황"
document_type: implementation_definition
status: REVIEW_FOR_MERGE
as_of: "2026-10-10 KST"
repository: taiengineering/tai-api
verified_main_sha: 69a061b261ca1352f155e6cc7c94312e874f95d0
scope: "TAM-006/007, TAM-008B, TAM-008C, HTTP READ C2"
owner_direction: "결재권한 설정 화면 접근은 프론트 페이지/메뉴 권한으로 단순화"
---

# TAI 공통 결재 모듈(TAM) — 정의·로직·구축 내역·특이사항

> **문서 성격:** 2026-10-10 시점의 **실제 구현 현황 기록(As-built)** 및 아직 구현되지 않은 **설계 목표(To-be)**의 차이를 설명하는 정의문서다. PRJ 개발거버넌스나 기존 TAM 설계 SoT를 대체하지 않는다. 작성 기준 소스는 GitHub main SHA 69a061b261ca1352f155e6cc7c94312e874f95d0이다. 해당 시점 이후의 코드는 재검증해야 한다.
>
> **진실원천(SoT) 구분:** 개발 절차/승인은 PRJ, 법령 SoT는 LEG, TAI 사용자의 신원과 회사·사업장 권한은 기존 TAI Core, TAM의 결재경로/결재 및 권한 원장은 TAI API의 TAM 스키마가 담당한다. TAM은 법적 의무 자체를 판단하거나 Consumer 업무 데이터를 소유하지 않는다.

## 1. 목적, 경계 및 재사용 원칙

TAM(TAI Approval Management / 공통 결재 모듈)은 TAI SAFE 및 TAI CHEMICAL 등 여러 Consumer가 **공통 결재 흐름과 승인 근거를 재사용**하기 위한 TAI API 내부 모듈이다. 새 서버·별도 TAM 데이터베이스를 두지 않고 기존 TAI API FastAPI 및 기존 TAI Core PostgreSQL과 결합한다. 업무 객체의 의미, 법령 적용 여부, 실제 업무 효력은 Consumer/LEG의 책임으로 남긴다.

**현재 구현(확인):** 결재경로(Route)·버전·단계·담당자 기반 테이블과 서비스, 권한 Grant/Revocation/Audit 원장, Grant 조회 서비스, 4계층 유효 인가 서비스, 내부 Route 인가 후보 어댑터, 차단 상태의 HTTP 라우터 코드.

**설계만 존재(미구현/미활성):** 결재 요청·스냅샷·결정·위임·취소·효력 철회의 전체 실행 엔진 및 Consumer 연동, 최초 권한 Bootstrap/Grant/Revoke HTTP API. 설계 문서의 테이블과 엔드포인트를 현재 Production에 존재하는 것으로 해석하지 않는다.

### 논리적 구성

~~~text
TAI SAFE / TAI CHEMICAL (업무 사실, 요청, 최종 효력 판단)
                      |
                 TAI API / TAM
  +--------------------------------------------------------+
  | [경로 관리] Route -> Version -> Step -> Assignee       |
  | [권한 원장] Grant -> Revocation + Audit (append-only)  |
  | [내부 인가] TAI Core Identity/Scope + Business Scope   |
  |             + Effective TAM Grant                      |
  | [향후 실행] Request -> Snapshot -> Decision            |
  |             -> Delegation/Revocation/Audit             |
  +--------------------------------------------------------+
           |                    |
     TAI Core 사용자/역할    기존 TAI API PostgreSQL
~~~

## 2. 소스 및 책임 분리

| 구성 | 현재 소스 | 책임 / 상태 |
|---|---|---|
| 라우터 선언 | router_registry/tam.py | TAM 라우터 1개 스펙 정의, **main.py 미등록** |
| HTTP API | routers/tam_routes.py | GET 2개, POST 5개; **POST는 무조건 403** |
| 경로 서비스 | services/tam/routes_svc.py | Route·Draft Version·Step·Assignee 생성, Publish 및 GET; **HTTP 쓰기 미활성** |
| 권한 원장 조회 | services/tam/permissions_svc.py | 유효한 Grant의 read-only 검증 |
| 유효 인가 | services/tam/authz_svc.py | Core Identity + Core Role Scope + 업무 객체 Scope + TAM Grant |
| Route 인가 어댑터 | services/tam/route_authz_adapter.py | 서버 조회 Route를 인가에 연결; candidate만 반환, **write_enabled=False** |
| Core 인증 | routers/auth.py | Bearer 인증, TAI Core users 조회, ACTIVE 및 is_active 검증 |
| 공통 가드 | services/permission_guard.py | 기존 플랫폼 공통 미들웨어; TAM 단독 보안근거로 사용하지 않음 |
| 앱 엔트리포인트 | main.py | TAM 그룹 불러오지 않음; /v1/tam/* 미노출 |
| DB 스키마 | supabase/migrations/20261009010000~10002_*.sql | 아래 3개 Production Migration 적용 완료 |

설계 문서의 오래된 BLOCKED/PR 대기 문구는 작성 당시 이력이다. 현재 구현·병합·적용 상태는 이 문서의 **기준 SHA와 운영 Migration History**를 우선하며, 미결 Owner 정책은 별도로 유지한다.

## 3. 현재 DB 테이블 7개 (Production 적용 완료)

| 테이블 | 주요 데이터 / 의미 | 변경 불변식 |
|---|---|---|
| tam_approval_routes | company_id, factory_id, route_scope, scope_key, display_name, current_version_id | Scope 중복 방지, 현행 버전은 동일 Route의 PUBLISHED 버전만 참조 |
| tam_approval_route_versions | route_id, version_number, DRAFT/PUBLISHED, published_at/by | PUBLISHED 변경 금지, 버전 삭제 금지 |
| tam_approval_route_steps | version_id, step_order, step_type, allow_supplement | DRAFT에서만 Step 편집 |
| tam_approval_step_assignees | step_id, user_id, assigned_by/at | DRAFT에서만 담당자 편집; 동일 Step/사용자 중복 방지 |
| tam_approval_audit_events | company_id, request_id(권한 이벤트는 NULL), event_type, event_data, actor_user_id | Append-only, UPDATE/DELETE 차단 |
| tam_permission_grants | 회사/사업장/대상 사용자/권한코드, 부여자, 유효기간, 사유, idempotency_key | Append-only, 권한 코드 제한, 기간 CHECK, 회사·사업장 복합 FK |
| tam_permission_revocations | grant_id, revoked_by/at, reason, idempotency_key | Append-only, Grant당 철회 1건 UNIQUE |

- **Factory Option A:** 기존 factories에 UNIQUE(company_id, id)를 먼저 추가하고, tam_permission_grants의 (company_id, factory_id) 복합 FK로 교차회사 사업장 권한을 차단한다. company_id가 NULL인 기존 Factory 행을 일괄 보정하거나 삭제하지 않는다.
- **RLS·ACL:** TAM 7개 테이블에서 RLS 활성화; PUBLIC/anon/authenticated 직접 테이블 권한 회수. service_role은 원장 3개 테이블에 SELECT+INSERT, Route/Version에는 SELECT+INSERT+UPDATE, Step/Assignee에는 SELECT+INSERT+UPDATE+DELETE만 명시적으로 허용한다. 데이터 API에 정책을 추가해 개방하는 설계가 아니다.
- **DB 트리거:** Route PUBLISHED 포인터 확인 1, Version 불변성 1, Step DRAFT 편집 1, Assignee DRAFT 편집 1, Append-only 불변성 3 = **총 7개**. 트리거 함수에 대한 PUBLIC/anon/authenticated/service_role의 불필요한 직접 EXECUTE 권한을 회수한다.
- **동일 회사/사업장 범위:** NULL factory_id는 회사 전체, 지정된 factory_id는 해당 사업장 범위로 취급한다. 모든 단계에서 회사 일치·사업장 귀속 검증이 필요하다.

### 적용된 정식 Migration (반드시 이 순서)

1. 20261009010000_tam_factories_option_a_composite_unique.sql
2. 20261009010001_tam_approval_route_foundation_security.sql
3. 20261009010002_tam_permission_ledger_foundation_security.sql

운영 Supabase 프로젝트는 **vwlahtguyggrhvslabax (taieng)**. 2026-10-10 읽기 전용 독립조회 결과 3개 Migration 모두 적용됨, TAM 7개 테이블 모두 **0행**, factories 6,003행(회사 ID NULL 5,061행). 이 값은 **조회 시점 스냅샷**이며 지속적인 불변 수치가 아니다. Chemical의 별도 Supabase 프로젝트와 혼동 금지.

## 4. 경로 생성·버전·발행 로직 (현재 서비스 구현)

### 4.1 Route 선택과 Scope

Route Scope 4종:

- COMPANY_DEFAULT: 회사 기본 경로; scope_key NULL
- FACTORY_DEFAULT: 사업장 기본 경로; factory_id 필수, scope_key NULL
- DOCUMENT_TYPE: 문서유형별 경로; scope_key 필수
- PROCESS_TYPE: 업무/프로세스 유형별 경로; scope_key 필수

동일 (company_id, factory_id, route_scope, scope_key)의 중복은 UNIQUE 인덱스로 차단한다. factory_id NULL과 scope_key NULL은 COALESCE 정규화하여 중복 판단한다.

**설계된 자동 경로 탐색 우선순위(아직 결재 실행 엔진 미구현):** 명시적인 instance_route_id → process_type → document_type → factory_default → company_default → 없음은 NO_APPROVAL_ROUTE_FOUND. Process와 Document가 동시에 해당하면 Consumer의 명시적 route_type_hint가 필요하고, 없으면 AMBIGUOUS_ROUTE로 차단한다. 이 규칙은 docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md §4의 목표 계약이지 현재 자동 라우팅 배포 증거가 아니다.

### 4.2 DRAFT → PUBLISHED

~~~text
Route 생성
 -> DRAFT Version 생성 (route별 version_number 증가)
 -> Step 추가 (1부터 연속된 step_order)
 -> Step별 Assignee 1명 이상 지정
 -> Publish 요청
    -> Route row SELECT FOR UPDATE
    -> Version row SELECT FOR UPDATE
    -> 같은 Route/동일 회사/DRAFT 여부 확인
    -> Step 연속성 및 담당자 존재 확인
    -> Version DRAFT -> PUBLISHED
    -> Route current_version_id = PUBLISHED Version
 -> COMMIT
~~~

- 발행은 **동일 트랜잭션**으로 처리한다. 검증 실패는 롤백한다.
- 신규 버전을 발행해도 과거 PUBLISHED 이력은 삭제/변조하지 않는다. SUPERSEDED로 과거 행을 UPDATE하지 않고 Route의 current_version_id 포인터만 새 PUBLISHED 버전으로 이동한다.
- Route → Version 순서의 행 잠금 및 Step/Assignee 트리거의 버전 잠금으로 발행과 편집의 경쟁을 직렬화한다.
- 지원 Step 종류: SEQUENTIAL / PARALLEL_ANY / PARALLEL_ALL. **현재는 Route 정의 모델**이며 승인/반려에 따른 실제 상태전이는 향후 Execution Layer에서 구현한다.
- HTTP POST 5개가 403으로 차단돼 있으므로 현재 Production UI에서 Route 관리 기능이 동작한다고 주장할 수 없다.

## 5. TAM 권한 모델과 내부 인가 로직

### 5.1 권한 코드

| 권한 | 용도 | 현재 Grant 원장 |
|---|---|---|
| ROUTE_MANAGER | Route 생성·편집·발행 권한 | 허용 코드 |
| ASSIGNEE_MANAGER | 결재자 지정·관리 권한 | 허용 코드 |
| REQUEST_SUBMITTER | 결재 요청 제출 | 허용 코드; 호출 주체 정책 미결 |
| DELEGATION_MANAGER | 결재 위임·철회 | 허용 코드; 실제 API 미활성 |
| REQUEST_REVOKER | 요청 취소·효력 철회 | 허용 코드; 실제 API 미활성 |
| STEP_APPROVER | 지정 Step의 실제 승인 | **Grant 코드에서 제외**, 향후 Snapshot 지정자/유효 위임 근거로 판단 |

역할 코드(role_code)를 ROUTE_MANAGER로 자동 매핑하지 않는다. 페이지/메뉴 접근권한과 TAM 업무행위 권한 원장은 다른 개념이다.

### 5.2 Grant 유효성

**check_tam_permission_grant(user, company_id, factory_id, permission_code):**

1. Core user id/company_id 및 활성 상태 검사.
2. 대상 회사와 사용자 회사가 일치해야 함.
3. Grant의 5개 허용 권한 코드 검증; STEP_APPROVER 요청은 별도 거부.
4. company_id, subject_user_id, permission_code, 회사전체 또는 일치 사업장 Scope 조회.
5. 현재시각이 valid_from 이상이고 valid_until 미만(또는 NULL)인지 확인.
6. tam_permission_revocations에 해당 grant_id의 철회가 없어야 함.
7. 조건 충족 시 grant_valid=true / grant_id, 아니면 DENY. DB 실패 시 503 fail-closed.

**주의:** grant_valid=true는 최종 업무 인가가 아니다.

### 5.3 4계층 최종 인가

**check_tam_effective_authorization(user, resource, permission_code):**

~~~text
(1) Core Identity: ACTIVE, is_active, company/role 필수
 AND
(2) Core Role Scope: role_data_scope 실 DB 조회
 AND
(3) Business Object Scope: Company/Factory/Team 검증
 AND
(4) 현재 유효 TAM Permission Grant
 => authorized=true
~~~

- Resource는 서버가 신뢰하는 객체에서 구성하고 id/company_id/factory_id/team_id 키를 갖춰야 한다.
- Core Scope 종류: ALL / COMPANY / FACTORY / TEAM / ASSIGNED. **ASSIGNED는 현 단계 ASSIGNMENT_SCOPE_NOT_READY로 거부**.
- Factory가 지정되면 동일 회사 소속, ACTIVE, deleted_at IS NULL을 검증한다.
- 권한 조회 실패·DB 장애는 허용으로 전환하지 않는다.

### 5.4 Route 인가 후보 Adapter

**assess_tam_route_authorization_candidate(user, route_id, dsn):**

Route UUID 검증 → user.company_id 범위 안에서 서버측 Route 조회 → trusted Resource 생성 → 4계층 인가 검사. 결과는 candidate_valid와 code, grant_id를 포함할 수 있지만 **write_enabled는 모든 경로에서 False**. HTTP 라우터에 연결하지 않았고, 이 서비스를 호출했다고 쓰기를 활성화할 수 없다.

### 5.5 Grant/Revoke 생성 로직의 범위

설계문서에는 Company 행 FOR UPDATE 잠금에 의한 Grant/Revoke/Bootstrap 직렬화, idempotency_key, 감사 이벤트와 동일 트랜잭션 원칙, 자기 자신에게 권한 부여 금지, 최초 Bootstrap과 ADMIN_RECOVERY 분리가 정의돼 있다. **이 프로토콜의 HTTP Grant/Revoke/Bootstrap 실행은 아직 구현·활성화되지 않았다.** 현재 구현 확인 대상은 DB Foundation과 **읽기 전용 인가** 서비스다.

## 6. HTTP API 현황 (main 기준)

| Method | Path | 현재 코드 동작 | Production 노출 |
|---|---|---|---|
| GET | /v1/tam/routes | 인증 후 같은 회사/사업장 범위 list_routes | **미등록** |
| GET | /v1/tam/routes/{route_id} | 인증 후 같은 회사/사업장 범위 get_route | **미등록** |
| POST | /v1/tam/routes | 무조건 403 ROUTE_MANAGER_PERMISSION_REQUIRED | **미등록** |
| POST | /v1/tam/routes/{route_id}/versions | 무조건 403 | **미등록** |
| POST | /v1/tam/routes/{route_id}/versions/{version_id}/steps | 무조건 403 | **미등록** |
| POST | /v1/tam/routes/{route_id}/versions/{version_id}/steps/{step_id}/assignees | 무조건 403 | **미등록** |
| POST | /v1/tam/routes/{route_id}/versions/{version_id}/publish | 무조건 403 | **미등록** |

라우터는 routers/tam_routes.py에 정의되어 있으나 **main.py의 _load_all_modules()가 router_registry.tam을 로드하지 않는다**. 따라서 현재 API에 TAM Route HTTP 엔드포인트가 등록되지 않았다. 테스트는 별도의 FastAPI 앱에 라우터를 삽입해서 수행됐다.

**GET의 현재 보안:** Depends(get_current_user)로 JWT·활성계정 확인, 회사 및 공장 ID 범위 검사. **GET에 Core Role Scope / TAM Grant 검사까지 결합된 것은 아니다.** 반면 내부 authz 서비스에는 그 검사 로직이 존재한다. 이를 동일하게 취급하지 말 것.

**C2 오류보안(병합 완료):** get_route()는 DB 접속 전에 UUID 형식을 검증(422 INVALID_ROUTE_ID); DB 연결/SQL 처리 오류는 외부에 정적 503 SERVICE_UNAVAILABLE로 반환하며 SQL·DSN 등 상세정보와 traceback을 외부 응답/보완된 오류 로그에 노출하지 않는다. DB 설정 누락의 정적 DB_NOT_CONFIGURED 계약은 유지한다.

## 7. Front-end 결재권한 설정 페이지 접근 원칙 (Owner 방향)

**2026-10-10 Owner 의견:** 결재권한 수정 화면의 진입은 **프론트 페이지/메뉴 접근권한으로 단순하게 처리**한다. 즉 화면 노출과 메뉴 진입의 판단을 TAM Grant 검사 자체와 혼합하지 않는 방향이다.

- 우선 기존 TAI 메뉴/페이지 권한(role_menu_permissions 등의 Core 체계)의 **재사용을 검토**하고, TAM 전용 중복 프론트 권한 원장을 만들지 않는다.
- 진입이 허용된 관리자는 결재경로·담당자 설정 화면을 이용할 수 있게 UI를 설계한다. 실제 메뉴 코드, 조회 가능 사용자 범위, 수정/발행 동작 정책은 별도 세부 설계·검증 대상이다.
- **프론트 제어만으로 보안이 완성되는 것은 아니다.** 화면 URL이나 API를 직접 호출할 수 있으므로 서버는 최소한 JWT, ACTIVE, 회사·사업장 격리와 각 **쓰기 동작의 서버 인가**를 계속 강제해야 한다. 페이지 진입 권한이 곧 서버측 ROUTE_MANAGER 업무권한이라는 뜻도 아니다.
- GET API에 ROUTE_MANAGER Grant를 별도로 필수화하자는 과거 **GPT 권고는 Owner가 채택한 확정 정책으로 기록하지 않는다**. Owner의 이번 단순화 방향을 반영해 페이지 Gate와 안전한 API 조회 계약을 별도 결정한다.
- **현재 프론트 페이지의 구체적 코드/권한 설정이 구현됐다고 주장하지 않는다.** 이번 변경은 정책 방향 문서화이지 UI/HTTP 활성화가 아니다.

## 8. 구현 이력 / PR 추적

| 단계 | PR 및 Squash SHA | 내용 | 최신 상태 |
|---|---|---|---|
| TAM-006/007 | [#570](https://github.com/taiengineering/tai-api/pull/570) · 8fa4c9a2 | 전체 결재 모델/상태/Consumer 분장 설계 정합화 | MERGED, 설계 기준 |
| TAM-008B | [#572](https://github.com/taiengineering/tai-api/pull/572) · a0d4b9dc | Route Foundation, 4개 테이블 초안·Route/Publish 서비스·HTTP 403 | MERGED |
| TAM-008C-003 | [#573](https://github.com/taiengineering/tai-api/pull/573) · 07fb097c | Grant/Revoke/Bootstrap 권한 원장 v0.6 설계 | MERGED, 일부 정책 미결 |
| TAM-008C-004 | [#574](https://github.com/taiengineering/tai-api/pull/574) · 42009f7f | 원장 3개 테이블 구현·격리 DB 테스트 | MERGED |
| TAM-008C-005 | [#575](https://github.com/taiengineering/tai-api/pull/575) · b185c717 | Permission Grant read-only 검증 | MERGED |
| TAM-008C-006 | [#576](https://github.com/taiengineering/tai-api/pull/576) · 3a8586ba | TAI Core 4계층 Effective Authorization | MERGED |
| TAM-008C-007 | [#577](https://github.com/taiengineering/tai-api/pull/577) · 95cad790 | Route 인가 후보 Adapter, write_enabled=False | MERGED |
| DB Security | [#579](https://github.com/taiengineering/tai-api/pull/579) · 334e4bf4 | 3개 정식 Migration, RLS/ACL/트리거 함수 보안 | MERGED + DB APPLIED |
| DRIFT-01 | [#580](https://github.com/taiengineering/tai-api/pull/580) · e3941abd | Production에는 있고 Git에 빠진 비-TAM 기존 Migration 2건 원문 복구 | MERGED, DRIFT CLOSED |
| HTTP READ C2 | [#581](https://github.com/taiengineering/tai-api/pull/581) · 69a061b2 | GET UUID/DB 오류 응답·로그 보안, 격리 테스트 | MERGED + 자동 배포 보고 |

이력상 #572/#574의 원본 migrations/ 초안과 **실제 운영 적용된 supabase/migrations 정식 Migration**을 구분한다. 구현 기록의 과거 "미적용"은 현재의 적용완료 상태와 혼동하지 않는다.

### 운영 적용·배포 증거

- 2026-10-09 Owner 승인 후 **supabase db push --linked**로 TAM 3개 Migration 적용. GitHub history drift는 PR #580으로 복구 후 적용했다. Supabase MCP apply_migration, history repair, 수동 SQL write는 사용하지 않았다.
- GPT 읽기 전용 독립검증: TAM Migration 3/3, 테이블 7/7, RLS 7/7, ACL 147개 기대권한 일치, 트리거/함수 7/7, Factory 기존 총량·NULL 보존.
- #581 자동 배포에 대해 Claude Code는 Railway 프로젝트 tai-api / 환경 production / 서비스 tai-api-prod, Deployment fd6d3e8b-4591-4156-b75c-78d0ddfa6aeb SUCCESS, Build SHA 69a061b2, /health 200 version 6.0.2를 보고했다. **GPT는 GitHub SHA와 코드를 독립검증했지만 Railway Health를 직접 재확인하지 못했으므로 Railway 상태는 실행보고 근거로 분류**한다.
- **main 병합이 Railway Production 자동배포를 유발할 수 있다.** 문서/코드 PR 병합도 Owner 승인·배포 영향을 고려해야 한다.

## 9. 테스트 현황 및 증거의 한계

| 검증 범위 | 확인된 결과 | 해석 |
|---|---|---|
| HTTP READ C2 신규 테스트 | Claude 실행보고 20 PASS / 0 FAIL / 0 SKIP | GPT는 변경 코드·테스트 설계를 독립 검토; 동일 pytest 직접 재실행과 구분 |
| 관련 기존 TAM 회귀 | Claude 실행보고 49 PASS, 55 SKIP | 일부 실행 조건 미충족 |
| TAM-008C Route Adapter DB 테스트 | 20 ENV_BLOCKED | TAM_008C_PG_DSN 및 _tam_test_isolation_marker 없는 환경에서 파괴적 DDL 실행 차단; **PASS가 아님** |
| 기존 TAM HTTP 쓰기 차단 | Isolated FastAPI 테스트에서 5개 POST 403 | 실제 Production API 노출 검증이 아니라 테스트 라우터 검증 |
| DB Security | Production에서 RLS/권한/트리거/제약 카탈로그 독립조회 PASS | 데이터 변경 없이 읽기만 수행 |

- DB를 사용하는 격리 테스트는 운영 DATABASE_URL을 사용해서는 안 된다. 분리된 DSN, 명시적 DB명·마커 확인 후에만 파괴적 Fixture를 실행한다.
- 테스트가 빠졌거나 환경 차단된 수치를 PASS로 합산하지 않는다.
- 아직 TAM 결재 업무 E2E, 실제 권한설정 프론트, 소비자 서비스 연결, Bootstrap 실행을 검증한 증거는 없다.

## 10. 특이사항·설계 결정을 잘못 해석하기 쉬운 부분

1. **설계 vs 구현:** 문서에 11개 결재 실행 관련 테이블이 설계되어도 Production에 생성된 TAM 테이블은 현재 7개뿐이다. 7개는 Route 4 + Audit 1 + Permission Ledger 2이다. 설계 문서에 등장하는 tam_approval_requests, snapshots, decisions, delegations, effectiveness revocations 등은 지금 운영에 없다고 간주하고 실제 구현 전 재확인한다.
2. **역할 ≠ 업무 Grant:** TAI Core role_code와 TAM Permission Grant는 서로 자동 전환하지 않는다. 프론트 페이지 접근권한은 또 다른 축이다.
3. **결재자 ≠ Grant:** STEP_APPROVER를 원장에 발행하지 않는다. 향후 Request Snapshot의 지정자와 유효 위임만 인정한다.
4. **경로 발행은 이력 불변:** DRAFT/PUBLISHED 두 상태만 사용한다. 과거 PUBLISHED는 보존, Route의 current_version_id만 변경한다.
5. **회사 단위와 사업장 단위:** company_id/factory_id의 조합 무결성을 복합 FK와 서비스 조회로 모두 확인한다. 특히 기존 factories의 company_id NULL 행이 다수여도 이를 자동 수정하지 않는다.
6. **권한 원장 불변:** Grant/Revoke/Audit는 UPDATE/DELETE가 아닌 append-only로 보존한다. 만료나 철회는 판정 논리 또는 Revocation 기록으로 처리한다.
7. **HTTP가 곧 구현 완료는 아님:** Router 파일이 있어도 main.py에 등록되지 않았고 쓰기 함수는 무조건 403. 내부 어댑터의 candidate_valid=true도 write_enabled=false이다.
8. **공통 미들웨어가 모든 것을 막지 않음:** permission_guard는 일부 오류에서 fail-open하고 /v1/tam의 resource 분류는 기존 production ENFORCE 목록에 포함되지 않는 것으로 조사됐다. 해당 가드를 단독 TAM 인가 근거로 사용하지 않는다.
9. **DSN 분장:** routes_svc는 DATABASE_URL; permissions_svc/authz_svc는 TAM_PG_DSN 또는 DATABASE_URL fallback; adapter는 DSN 명시인자. 배포 환경과 DB 사용자 권한의 실제 동작은 별도 통합검증이 필요하다.
10. **문서 간 OD 번호 보존:** OD-06은 ADMIN_RECOVERY, OD-09는 REQUEST_SUBMITTER Scope다. Railway/환경변수 항목을 OD 번호로 재정의하지 않는다.

## 11. 아직 열려 있는 Owner 정책 및 후속 작업

| 구분 | 내용 | 현재 |
|---|---|---|
| OD-01 | FIRST_BOOTSTRAP 실행 주체 (설계 권고: 플랫폼 관리자 role_code 001) | Owner 세부결정·HTTP 실행 미승인 |
| OD-02 | APPROVED 효력 만료 기간 | 설계상 미결 |
| OD-03 | ROUTE_MANAGER의 Grant/Revoke 위임 가능 범위 | 미결 / API 비활성 |
| OD-06 | ADMIN_RECOVERY 절차 및 권한 | 미결 / API 비활성 |
| OD-09 | REQUEST_SUBMITTER 대상(서비스 계정/최종 사용자) | 미결 / API 비활성 |
| Front-end | 결재권한 수정 페이지 접근 Gate를 Core 메뉴/페이지 권한으로 단순화 | **Owner 방향 기록, 상세 정책·UI 구현 미검증** |
| HTTP GET | 페이지 접근과 서버측 조회권한의 정합성, Scope/노출 필드 검증 | 미활성 / 세부계약 필요 |
| HTTP POST | Bootstrap 및 서버 동작별 업무권한 강제, 쓰기 Gate 해제 | BLOCKED |
| 실행 엔진 | Request/Snapshot/Decision/Delegation/Revocation 및 Consumer E2E | 설계만, 미구현 |
| 테스트 | 격리 DB를 구성해 ENV_BLOCKED 20건 재검증 | 미실행 |

### 제안 진행 순서(승인이 필요한 단계)

1. 프론트 결재권한 설정 화면의 **기존 메뉴/페이지 권한 연결 방법과 대상 사용자**를 명시한다. 중복 권한 원장을 새로 만들지 않는다.
2. GET 응답 필드 및 서버측 회사·사업장 격리 계약을 검증한다. 프론트만으로 API 접근통제가 완료됐다고 주장하지 않는다.
3. GET만 별도 활성화할 경우 Router 등록·통합테스트·Owner 승인·Railway 자동배포 영향을 독립적으로 관리한다.
4. OD-01/03 등 정책을 정한 뒤 Grant/Revoke/Bootstrap 동작 및 HTTP 쓰기 Gate를 별도 WO로 구현·검증한다.
5. 실행 엔진 및 TAI SAFE/CHEMICAL 연동은 TAM-008D 이후 범위를 독립적인 설계/검증/승인 단위로 진행한다.

## 12. 참고자료 / 소스 링크

- [전체 모듈 설계 정합화(TAM-006/007)](../TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md)
- [권한 원장 상세설계(TAM-008C v0.6)](TAI_WO_TAM_008C_AUTHORIZATION_LEDGER_DESIGN.md)
- [실제 정식 Migration: factories UNIQUE](../../supabase/migrations/20261009010000_tam_factories_option_a_composite_unique.sql)
- [실제 정식 Migration: Route Foundation](../../supabase/migrations/20261009010001_tam_approval_route_foundation_security.sql)
- [실제 정식 Migration: Permission Ledger](../../supabase/migrations/20261009010002_tam_permission_ledger_foundation_security.sql)
- [GET / Route service](../../services/tam/routes_svc.py)
- [Grant read-only verification](../../services/tam/permissions_svc.py)
- [Effective Authorization](../../services/tam/authz_svc.py)
- [Route candidate adapter](../../services/tam/route_authz_adapter.py)
- [HTTP Router](../../routers/tam_routes.py)
- [TAM Router Registry](../../router_registry/tam.py)
- [App startup (미등록 확인)](../../main.py)
- [HTTP C2 regression tests](../../tests/test_tam_http_read_errors.py)
- [DB Security tests](../../tests/test_tam_008c_db_security.py)
- [TAM 전체 관련 PR 검색](https://github.com/taiengineering/tai-api/pulls?q=TAM)

---

**변경 통제:** 이 문서는 상태 정의 및 Owner 방향 기록 목적의 **DOCS ONLY**이다. 문서 병합 자체가 GET/POST 엔드포인트 등록, DB 변경, 배포 명령, 권한 부여·철회 승인을 의미하지 않는다. 이후 개발의 판단·설계·작업지시·독립검증은 GPT, 실행·증거수집은 Claude Code, Production 변경 승인은 Owner라는 PRJ 역할분장을 따른다.
