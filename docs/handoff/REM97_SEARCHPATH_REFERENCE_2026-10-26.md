# TAI REM97 — Supabase search_path 보안 정비 기준 참고문서

> 기준일: **2026-10-26 KST** · 범위: **REM97** · 상태: **A/B/C 실행 Wave 종료, 잔여 HOLD 33건**  
> 저장소: [taiengineering/tai-api](https://github.com/taiengineering/tai-api)  
> **목적:** 새 GPT/Claude Code 세션에서 최초 기획의 취지, 설계 계약, 실행 이력, 핵심 로직, 증거와 승인 경계, 현재 상태를 다시 조사하지 않고 정확하게 승계한다.  
> **공개 저장소 문서:** 미해소 HOLD 33건의 전체 함수별 세부 위험·권한 정보, 고객 데이터, 비밀값 및 내부 테스트 접속 정보는 의도적으로 제외한다.

## 1. 한눈에 보는 현재 상태

| 항목 | 2026-10-26 확인 상태 |
|---|---|
| 대상 이슈 | Supabase Security Advisor: **function_search_path_mutable** |
| REM97 진행 비교 기준 | **58 → 33건**, 순감 **25건** |
| A 그룹 | W1·W2·W3·W5 및 보류됐던 **A-W4 종료** |
| B 그룹 | B-W1~B-W4 및 별도 B19 종료 |
| C 그룹 | C-W1~C-W5 종료 |
| A-W4 최종 | **CLOSED_FINAL**, [PR #711](https://github.com/taiengineering/tai-api/pull/711) MERGED 및 운영 적용 확인 |
| A-W4 운영 Migration | **20261027020000** 등록·정합성 직접 확인 |
| A-W4 기술 GPT IV | **PASS** (OID/MD5/proconfig/ACL/트리거/Advisor) |
| 잔여 | **33건 모두 HOLD**, 변경 권한 없음 |
| 다음 승인 Gate | **REM97_HOLD33_OWNER_DECISION** |
| STOP | **TRUE** — 별도 Owner 결정 전 신규 수정·PR·운영 적용 금지 |

**수치 해석 주의:** 과거 최초 감사(2026-10-19)의 Advisor 전체 351건 및 search_path 105건, REM97 C1 인벤토리 97개, 후속 운영 진척 비교 기준 58건은 **시점과 분모가 서로 다르다.** 58→33의 25건을 모든 A/B/C Wave의 총 처리 함수 수로 역산하거나 서로 더하지 않는다.

## 2. 원 기획과 설계 취지

### 2.1 보안 감사의 출발점

- **2026-10-19 최초 계획:** Supabase 보안 감사 및 Security Advisor 경고 정비. 당시 스냅샷의 전체 Advisor는 351건, 그중 mutable search_path 관련 105건으로 인계됐다.
- **2026-10-22 보정 계획:** 기존 완료 Gate 보존, 함수별 위험·의존성·소스 기준선 확인, 변경 전후 회귀/운영 검증 분리.
- **REM97 C1 범위 분류:** **A 20 / B 24 / C 20 / HOLD 33 = 97**. 이는 분류된 후보 인벤토리이며 최신 Advisor 건수와 동의어가 아니다.
- 원본 계획·보정 계획·C1/C2 설계는 당시 인수인계 번들에 보존됐으며, 이 저장소에서 확인되지 않은 원본 URL은 만들어 적지 않는다.

### 2.2 해결하려는 문제

PostgreSQL 함수에 고정되지 않은 search_path가 있으면 비한정 객체 이름(함수, 테이블, 시퀀스 등)의 해석이 호출 환경에 영향을 받을 수 있다. REM97의 목표는 **해당 함수가 기대한 스키마의 객체를 일관되게 해석하도록 함수 설정을 고정**하면서, 애플리케이션 업무 로직과 호출 권한을 변경하지 않는 것이다.

일반적인 메타데이터 전용 패턴:

~~~sql
ALTER FUNCTION public.some_function(...)
  SET search_path = pg_catalog, public, pg_temp;
~~~

위 구문은 **모든 함수에 일괄 적용할 공통 처방이 아니다.** 기존 함수가 public 이외의 스키마를 참조하면 별도 경로·호출자 권한·RLS 계약이 필요하다. 특히 B19처럼 격리 스키마 의존성이 있는 항목은 일반 public 경로로 기계적 일괄 변경하지 않는다.

### 2.3 변경 금지 원칙

- 함수 본문 의미, 공개 API, 업무 판단, LEG 법령 SoT를 변경하지 않는다.
- 함수의 OID·본문 MD5·인자/반환형·Owner·ACL·SECURITY INVOKER/DEFINER·VOLATILITY·PARALLEL·트리거 연결을 변경 전후 비교한다.
- DB 함수 설정, Migration 이력, 격리 회귀, 운영 Advisor를 **서로 다른 증거**로 검증한다.
- 단순 Security Advisor 경고 감소만으로 업무 회귀 PASS를 선언하지 않는다.

## 3. 역할, 거버넌스 및 Gate 설계

| 주체 | 역할 |
|---|---|
| **Owner** | 작업 범위, C3 소스, PR Merge, 운영 Migration 및 예외를 단계별 별도 승인 |
| **GPT** | 원 기획/기준선 분석, 설계, 작업지시, 소스·운영 **독립검증** |
| **Claude Code** | 승인된 범위에서 구현·격리 실행·Git 증거·운영 실행 및 STOP 보고 |
| **PRJ** | 개발거버넌스 기준 |
| **LEG** | 법령 SoT; REM97 변경 대상으로 사용하지 않음 |

**Gate:** C1 신원/소스 기준선 → C2 의존성·격리 회귀 계약 → C3 한정된 소스·Migration → GPT Source IV → Owner Merge → Owner 운영 적용 → GPT Production IV → CLOSED_FINAL. C2 PASS는 C3·Merge·운영 적용 승인이 아니다.

~~~mermaid
flowchart LR
  A[C1: 함수 신원·의존성] --> B[C2: 격리 회귀·계약]
  B --> C{Owner C3 승인}
  C -->|승인| D[C3: 소스·Migration]
  C -->|보류| H[HOLD / STOP]
  D --> E[GPT 소스 독립검증]
  E --> F{Owner Merge 승인}
  F -->|승인| G[PR Merge]
  F -->|보류| H
  G --> I{Owner 운영 승인}
  I -->|승인| J[운영 단일 Migration 적용]
  I -->|보류| H
  J --> K[GPT 운영 DB·Advisor 검증]
  K --> L[CLOSED_FINAL]
~~~

**STOP 규칙:** UNVERIFIED / HOLD / SOURCE_NOT_FOUND는 자동 PASS가 아니다. 이미 종료한 C1/C2 및 과거 Wave를 반복하지 않고, 후속 검증은 변경된 Delta만 다룬다.

## 4. Wave별 작업과 GitHub 원본

다음 PR은 코드·Migration·테스트의 **검증 가능한 구현 원본**이다. 숫자는 당시 각 PR의 기술적 대상 수이며, 최신 Advisor 잔여 건수와 혼합하지 않는다.

| 분류 | 작업 | PR | 개요 |
|---|---|---|---|
| A | W1 | [#684](https://github.com/taiengineering/tai-api/pull/684) | 타임스탬프 트리거 8개 |
| A | W2 | [#687](https://github.com/taiengineering/tai-api/pull/687) | 유틸리티 함수 4개 |
| A | W3 | [#688](https://github.com/taiengineering/tai-api/pull/688) | 도움말 순환 방지 트리거 2개 |
| A | W5 | [#691](https://github.com/taiengineering/tai-api/pull/691) | reindex_help |
| B | B-W1 | [#693](https://github.com/taiengineering/tai-api/pull/693) | 불변 가드 4개 |
| B | B-W2A | [#694](https://github.com/taiengineering/tai-api/pull/694) | 런타임 검증 트리거 3개 |
| B | B-W2B | [#695](https://github.com/taiengineering/tai-api/pull/695) | 상태 전이 검증 트리거 2개 |
| B | B-W3A | [#696](https://github.com/taiengineering/tai-api/pull/696) | 도메인 트리거 4개 |
| B | B-W3B | [#697](https://github.com/taiengineering/tai-api/pull/697) | 동기화 트리거 3개 |
| B | B-W4A | [#698](https://github.com/taiengineering/tai-api/pull/698) | 일반 RPC·분석 함수 7개; B19 별도 Gate |
| B | B19 | [#702](https://github.com/taiengineering/tai-api/pull/702) | get_precompiled_factory_ids: 격리 스키마/호출자 계약 분리 |
| C | C-W1 | [#703](https://github.com/taiengineering/tai-api/pull/703) | 검색 인덱스 outbox 함수 5개 |
| C | C-W2 | [#704](https://github.com/taiengineering/tai-api/pull/704) | generate_daily_assignments |
| C | C-W3 | [#706](https://github.com/taiengineering/tai-api/pull/706) | 외부 스냅샷 함수 9개 |
| C | C-W4 | [#707](https://github.com/taiengineering/tai-api/pull/707) | net HTTP 관련 3개 |
| C | C-W5 | [#710](https://github.com/taiengineering/tai-api/pull/710) | sieve_executor / diagnose_clauses_common 2개 |
| A | **A-W4** | **[#711](https://github.com/taiengineering/tai-api/pull/711)** | 코드 생성 트리거 5개, 보류 해제 및 최종 운영 반영 |
| 공통 | 격리 검증 | [#699](https://github.com/taiengineering/tai-api/pull/699) | 역할/RLS 관련 격리 테스트 증거 보강 |

**C-W5 예외적 경계:** public.sieve_executor 및 public.diagnose_clauses_common을 고정했으나 호출자 public.run_common_sieve는 수정하지 않았고, 이후 Advisor 잔여 HOLD 범위에 유지됐다. LEG 정본 법령 파이프라인 수정으로 간주하지 않는다.

### 대표 Migration 원본

- [C-W4: 20261027000000](https://github.com/taiengineering/tai-api/tree/main/supabase/migrations) — PR #707에서 확인.
- [C-W5: 20261027010000](https://github.com/taiengineering/tai-api/pull/710) — 운영 적용 GPT IV PASS.
- [A-W4: 20261027020000](https://github.com/taiengineering/tai-api/blob/92119955b0a419b754dacc7d200fda3ad9d55af7/supabase/migrations/20261027020000_sec_searchpath_rem97_aw4_code_generate_triggers.sql) — 운영 반영 및 이력 정합성 확인.

## 5. A-W4 상세: 기획, 함수 로직, C2→C3→운영

### 5.1 대상 객체와 불변 기준선

A-W4는 원래 **코드 생성 트리거·시퀀스 회귀의 증거 부족**으로 BLOCKED였고, Owner가 5개 함수만 C2 격리 검증 범위로 승인한 뒤 진행했다.

| 함수 (public, 인자 없음, RETURNS trigger) | OID | 코드 생성 규칙 | 시퀀스 |
|---|---:|---|---|
| fn_generate_asset_code | 18557 | AST + LPAD(6) | seq_asset_code |
| fn_generate_company_code | 18558 | COMP + LPAD(5) | seq_company_code |
| fn_generate_site_code | 18559 | 일반: SITE + 최소 5자리 / 임시: TMP-UUID | seq_site_code |
| fn_generate_team_code | 18560 | TEAM + LPAD(5) | seq_team_code |
| fn_generate_user_code | 18561 | USR + LPAD(6) | seq_user_code |

각 함수는 관련 테이블(equipment_assets / companies / factories / teams / users)의 **BEFORE INSERT FOR EACH ROW** 트리거에 하나씩 연결된다. 코드를 주지 않거나 공백으로 주면 자동 생성하고, 기존 코드가 있으면 덮어쓰지 않는다.

함수 본문 MD5 운영 기준선:

| 함수 | MD5(prosrc) |
|---|---|
| asset | 716c1df59ef2b3e4a20d8d810598732f |
| company | ad17d81156ae5c1a66f9c2b6216c15d7 |
| site | 7bd5a931ad8963226f17847c3ca1a1a3 |
| team | 270ed9eb57d7718a8316e774a8257cf0 |
| user | df3a1f47e3516edc1030bd8590ad7dc2 |

공통 불변: Owner postgres, SECURITY INVOKER, VOLATILE, PARALLEL UNSAFE, plpgsql, ACL 및 트리거 연결. 운영 OID와 격리 DB의 OID는 동일할 필요가 없다.

### 5.2 사업장(site) 예외 로직

임시 상태 **ANON_TEMP, E2E_TEMP, REGA_TEMP, REGB_TEMP, E2E_TEST**에서는 코드를 **TMP- + 하이픈 없는 UUID v4 32자리**로 만든다. 이 분기에서는 seq_site_code를 소비하지 않는다. 일반 상태에서는 시퀀스 기반 SITE 코드를 생성한다. 이미 site_code가 있으면 상태에 관계없이 보존한다.

### 5.3 시퀀스와 격리 검증의 핵심

**nextval()은 트랜잭션 ROLLBACK으로 취소되지 않는다.** 따라서 실패한 INSERT의 행은 롤백되더라도 시퀀스 번호는 소비될 수 있다. PRE/POST 동등성은 숫자의 절댓값이 아니라 접두어·포맷·기존값 보존·분기·소비 여부로 비교한다.

C2 증거는 세 묶음으로 보강됐고 GPT가 순서대로 독립 검토했다.

1. **C2 초기:** 격리 PostgreSQL 15에서 PRE/POST 코드 생성·시퀀스·트리거 검증.
2. **R1:** SAVEPOINT 및 실패 단언, UUID v4/variant, 함수·트리거 메타데이터 강화.
3. **ACL 보정:** PRE/POST proacl 값을 원본과 비교하고 불일치 시 예외 발생.

증거 패키지 SHA256(실행 자료 원본은 이 Git 문서에 포함하지 않음):

- C2: **74ee4aa56bacc5a9df9132fd7fb7e8349adf3c54491400710795b886917e9021**
- R1: **6b722a5c1f7d2006c0c87b247ab57e0b8cd34d255a6ead16071423dc383f2dbd**
- ACL: **30a7e1f561be34921c63499a9d2c366e4006c9420dedd6547dd4967383a1dabe**

**Gate:** GPT_REM97_AW4_C2_FINAL_IV = PASS → REM97_AW4_C2 = CLOSED_FINAL. 이 검증은 C3 변경 자동 승인이 아니다.

### 5.4 PR #711의 기술 구현 계약

[PR #711](https://github.com/taiengineering/tai-api/pull/711)의 핵심 Migration은 **정확히 5개 ALTER FUNCTION**과 Fail-Closed 전후 단언이다.

~~~text
BEGIN
  PRE: OID / 이름 / MD5 / proconfig=NULL / Owner / ACL / 보안 속성 / 반환형 검증
  PRE ACL 스냅샷
  ALTER FUNCTION ×5: SET search_path = pg_catalog, public, pg_temp
  POST: search_path 정확성 / MD5 / Owner / 보안 속성 검증
  POST ACL 변화 없음 확인
COMMIT
~~~

Migration 소스: [20261027020000_sec_searchpath_rem97_aw4_code_generate_triggers.sql](https://github.com/taiengineering/tai-api/blob/92119955b0a419b754dacc7d200fda3ad9d55af7/supabase/migrations/20261027020000_sec_searchpath_rem97_aw4_code_generate_triggers.sql)

변경되지 않은 Migration Git Blob SHA: **73c24bb3a6f443efb99e353c6e76c3051bdb0513**.

### 5.5 격리 테스트 Guard R1

처음 추가된 테스트 SQL은 격리 DB 여부 확인 전에 DROP TABLE을 수행할 수 있어 위험했다. 이후 Owner는 PR #711에 한해 **테스트 파일 2개에 Fail-Closed Guard를 추가하는 보정만 승인**했다.

- [setup_aw4.sql](https://github.com/taiengineering/tai-api/blob/92119955b0a419b754dacc7d200fda3ad9d55af7/tests/isolated/setup_aw4.sql): ON_ERROR_STOP + 트랜잭션 + Guard → DDL → COMMIT
- [run_aw4_regression.sql](https://github.com/taiengineering/tai-api/blob/92119955b0a419b754dacc7d200fda3ad9d55af7/tests/isolated/run_aw4_regression.sql): ON_ERROR_STOP + 독립 Guard → PRE 16 / ALTER 5 / POST 13 / 메타데이터 3 항목
- 검사 조건: DB명이 aw4_test인지, **외부에서 설정한 격리 허가값**이 유효한지, Supabase 운영에서 사용하는 핵심 내부 스키마가 없는지.
- 부정 테스트 6개(잘못된 DB, 허가 누락/불일치, 내부 스키마 존재) PASS, 정상 테스트 2개 PASS가 Claude 실행 보고로 제출됐다. **실행 로그 원본의 GitHub CI 독립 검증은 별도 확인되지 않았다.**
- GPT는 보정 HEAD **b547e270b54dc42bcf264fd7164d06eb2da9338a**에서 허용된 두 테스트 파일만 수정되고 Migration Blob은 불변임을 소스 독립검증했다.

테스트 SQL은 격리 환경 전용이다. 운영 DB에서 실행하거나 범용 안전장치로 재사용하지 않는다.

### 5.6 Merge, 운영 반영, 이력 정합성

- PR #711 Merge: **92119955b0a419b754dacc7d200fda3ad9d55af7** ([PR 링크](https://github.com/taiengineering/tai-api/pull/711)).
- 운영 함수 5개: **proconfig = [search_path=pg_catalog, public, pg_temp]**, OID/MD5/ACL/Owner/보안 속성·트리거 연결 기존 값 유지.
- 적용 직후 Migration 이력 버전이 **20261026212137**로 잘못 등록됐지만, 이력의 SQL은 원본 Migration과 끝의 줄바꿈 한 개를 제외하고 일치했다.
- 후속 이력 보정으로 **20261027020000**으로 정상 등록됐고 이전 버전은 소멸했다. 재적용·재보정하지 않는다.
- Advisor search_path 경고: **38 → 33**, A-W4 대상 5개 경고 0건.
- **기술 Gate:** GPT_PRODUCTION_TECHNICAL_IV=PASS, REM97_AW4_TECHNICAL=CLOSED_FINAL.
- **거버넌스 이력:** C3 생성/PR 및 Merge·운영 적용의 원래 단계별 승인 순서 예외가 있었다. 사후 Owner 예외 수용 **보고**가 존재하지만, 사전 승인 원문과 시점은 이 문서의 독립 증거로 확보되지 않았다. 이 사실을 삭제하거나 ‘정상 사전 승인’으로 재해석하지 않는다.

## 6. C-W5 로직과 A-W4와의 차이

- [PR #710](https://github.com/taiengineering/tai-api/pull/710)은 **public.sieve_executor(text)**, **public.diagnose_clauses_common()**의 고정 작업.
- 호출자 **public.run_common_sieve()**는 변경하지 않음: 해당 호출자는 잔여 HOLD 중 하나다.
- [C-W5 운영 Migration](https://github.com/taiengineering/tai-api/pull/710): **20261027010000**, 적용 IV PASS, 경고 **40 → 38**.
- A-W4는 함수 본문 속 **시퀀스/임시 UUID/트리거 부작용** 때문에 C2 격리 동등성의 중요도가 특히 높았다. 두 Wave의 회귀 계약은 서로 대체할 수 없다.

## 7. 잔여 HOLD 33건과 다음 Gate

최종 운영 Security Advisor에 REM97 관련 mutable search_path 경고 **33건**이 남아 있다. A-W4 5개는 더 이상 잔여에 없다.

검증 시점의 **객체 유형별 개수**:

| 구분 | 건수 | 특징 |
|---|---:|---|
| e2e_gov | 7 | 파이프라인/정책/증거 보호 트리거 |
| public 일반 트리거 | 19 | 법령·마스터·상태/데이터 보호 등 |
| public Event Trigger | 2 | DDL/주석 검사 |
| public 호출형 함수 | 5 | 조회·분석·QA/보조 작업 |
| **합계** | **33** | **모두 HOLD 유지** |

> **보안상 공개 문서에는 미해소 함수 33개 전체 명칭과 세부 공격 표면을 나열하지 않는다.** HOLD 원인, 소유권, 의존성, 호출자 계약, 필요한 테스트는 승인된 내부 증거·운영 DB의 읽기 전용 확인에 의해 개별 판정해야 한다. 이 분류만으로 일괄 수정할 권한이 생기지 않는다.

**NEXT_GATE = REM97_HOLD33_OWNER_DECISION**. Owner 결정 이전에는 HOLD 33건을 대상으로 새로운 SQL·Migration·테스트 코드, PR, 운영 DB 변경, LEG·PRJ 변경을 수행하지 않는다. 과거 A/B/C 완료 Wave 재조사도 금지한다.

향후 Owner가 HOLD 해제를 승인한다면 순서는 (1) 기존 원 계획과 개별 HOLD 사유 확인 (2) 함수별 관할·소스/호출자 확인 (3) 승인된 격리 회귀 계약 (4) GPT IV (5) 단계별 Owner 실행/병합/운영 승인이다.

## 8. 새 창 인수용 체크리스트

1. **이 문서는 참조/인수인계 자료**이고, 법령 SoT LEG나 PRJ 승인 기록 자체를 대체하지 않는다.
2. 실제 운영값이 필요한 경우 **읽기 전용**으로 Security Advisor, pg_proc·pg_trigger, supabase_migrations.schema_migrations의 현재 값을 다시 확인한다. 문서 날짜 이후 변동 가능성을 인정한다.
3. 최신 Git main, 직전 PR과 Migration SHA를 확인하되 병렬 작업으로 main이 전진한 것을 자동 오염으로 판정하지 않는다.
4. 운영 Migration 20261027020000은 이미 적용·등록됐다. **재실행/중복 push/repair 금지**.
5. GPT=분석·설계·작업지시·독립검증, Claude Code=실행, Owner=별도 승인. Claude의 PASS·CLOSED_FINAL 보고는 GPT IV와 구분한다.
6. **현재 정지점: HOLD33_OWNER_DECISION / STOP=TRUE.** Owner 범위 결정을 받기 전에 다음 C1/C2/C3, PR, DB 변경을 시작하지 않는다.

### 인수용 고정 계약

~~~text
WORKSTREAM = REM97_SEARCHPATH
REPO = taiengineering/tai-api
DATE = 2026-10-26

C1_COHORT = 97
C1_GROUPS = A20 / B24 / C20 / HOLD33
TRACKED_ADVISOR = function_search_path_mutable
TRACKED_PROGRESS = 58 -> 33
TRACKED_NET_RESOLVED = 25

AW4_PR = 711
AW4_MERGE_SHA = 92119955b0a419b754dacc7d200fda3ad9d55af7
AW4_MIGRATION = 20261027020000
AW4_FUNCTIONS = 5/5
AW4_PROD_TECHNICAL_IV = PASS
AW4 = CLOSED_FINAL

OWNER_SEQUENCE_EXCEPTION = RECORDED
OWNER_EXCEPTION_ACCEPTANCE = REPORTED_NOT_INDEPENDENTLY_ATTESTED
REMAINING_HOLD = 33
NEXT_GATE = REM97_HOLD33_OWNER_DECISION
NEW_WORK_APPROVAL = NONE
STOP = TRUE
~~~

## 9. 출처 우선순위와 링크

**우선순위:** (1) 최신 Owner 승인 원문 및 PRJ Gate (2) 운영 DB / Advisor 직접 검증 (3) GitHub Merge SHA의 Migration·테스트 소스 (4) GPT 독립검증 원문/증거 ZIP SHA (5) Claude 실행 보고. 충돌 시 추론으로 맞추지 말고 불일치를 기록한다.

- [tai-api PR #711 (A-W4 최종)](https://github.com/taiengineering/tai-api/pull/711)
- [tai-api PR #710 (C-W5)](https://github.com/taiengineering/tai-api/pull/710)
- [tai-api PR #707 (C-W4)](https://github.com/taiengineering/tai-api/pull/707)
- [tai-api PR #702 (B19)](https://github.com/taiengineering/tai-api/pull/702)
- [45CM Federation Architecture v1](https://github.com/taiengineering/tai-api/blob/main/docs/45CM_Federation_Architecture_v1.md)
- 원래 인수인계 자료(별도 보관): **TAI_REM97_B19_HANDOFF_20261025.md**, **TAI_SUPABASE_SECURITY_AUDIT_PLAN_2026-10-19_ORIGINAL.md**, **TAI_SUPABASE_SECURITY_AUDIT_PLAN_2026-10-22_AMENDED.md**, **REM97_C1_SOURCE_CLOSEOUT_R2_20261022.txt**, **REM97_C2_DESIGN_20261023.txt**, **REM97_C2_IV_R2_20261023.txt**. 저장소에 실재하지 않는 원본 URL은 의도적으로 만들지 않았다.

---

**문서 변경 정책:** 상태가 바뀌면 실제 Merge/운영 DB/Advisor/Owner 승인 증거를 확보한 뒤 **참고문서의 스냅샷 날짜와 Gate를 함께 개정**한다. 본 문서를 근거로 자동 코드·DB 변경하지 않는다.
