# TAI E2E2000 / WP01-D 법령의무 변경관리 정의서

> **문서 성격:** 구현된 SaaS 법령의무 변경관리의 로직·작업 이력·특이사항·운영 경계를 기록하는 **소비자(consumer) 정의서**. 법령의 법적 효력이나 LEG 정본을 변경·판정하는 법령 SoT 문서가 아니다.
>
> **기준일:** 2026-10-17 · **문서 버전:** v1.0 · **개발 상태:** `SOURCE IMPLEMENTATION COMPLETE / FROZEN` · **운영 상태:** `NOT APPROVED / NOT DEPLOYED` (본 WP 변경분 기준)

## 0. 문서 관리 및 기준점

| 항목 | 고정 내용 |
|---|---|
| 과제 | `E2E2000 / WP01-D`, `WO-E2E2000-WP01-D-P0-FULLSTACK-REMEDIATION-010` |
| 법령 SoT | **LEG**. 이 문서는 법령 자체의 의무·적용조건·해석을 새로 정하지 않는다. |
| 개발거버넌스 | **PRJ**. 승인된 파이프라인 정의·역할·검증 게이트를 따른다. |
| GPT | 분석·설계·작업지시·독립검증 |
| Claude Code | 소스 조사·실행·테스트·증거 수집(설계 승인 권한 없음) |
| Owner | 설계·DB Migration·병합·배포·활성화 승인 |
| API PR | [tai-api #631](https://github.com/taiengineering/tai-api/pull/631) — **Draft / 미병합** |
| API 고정 HEAD | `bcc316dc75c959f0cd8ebe29090826589ed29d21` |
| Admin PR | [tai-admin #155](https://github.com/taiengineering/tai-admin/pull/155) — **Draft / 미병합** |
| Admin 고정 HEAD | `284efad0c41c3483af3a33aa8b247061e57edeb5` |
| 테스트 | Python 테스트 함수 **95개 소스 존재**; **95/95 PASS는 Claude Code 실행 보고**. GPT가 테스트를 직접 실행한 증거는 별개. |
| 기준 확정 | WP01-D 소스 작업 종료·PATCH-4 기준점 FROZEN(Owner 보고 기준). 추가 PATCH/재설계 현재 범위에서 열지 않음. |

**문서의 우선순위:** LEG 법령 SoT → PRJ 승인 파이프라인·개발거버넌스 → 승인된 데이터/API 계약 → 본 WP01-D 구현 정의서. 본 문서와 상위 정본이 충돌하면 상위 정본과 실측 소스를 우선하고, 차이를 기록한 후 Owner에게 올린다.

## 1. 용어와 적용 범위

### 1.1 서로 다른 두 종류의 '변경'

1. **법령 정본 변경(LEG 변경):** 법령 개정, 시행일·적용 조건·의무 내용 등의 정본 변경. LEG의 근거·검증·승인 파이프라인에서만 처리해야 한다. WP01-D는 법령을 해석하거나 LEG DB를 고치지 않는다. 이 종류의 변경이 C10 결과에 어떻게 반영되는지에 대한 LEG 내부 구현은 **본 문서 검증 범위 밖**이다.
2. **사업장 법령의무 결과 변경(WP01-D):** 같은 회사/사업장이 재진단한 **이전 C10 결과**와 **최신 C10 결과**의 의무 atom 집합을 비교해 신규·유지·제외 후보를 표시하고, 승인된 사용자가 해당 일정을 제외하는 SaaS 소비자 기능이다. 입력(회사·사업장·현장·공정·설비·작업)의 변화나 LEG 결과의 변화가 원인일 수 있지만, **원인 규명과 법적 적용제외 확정은 diff만으로 자동 수행하지 않는다**.

### 1.2 세 가지 변경 분류

- `ADDED`: 최신 결과에만 있는 법령 의무 `atom_id`.
- `RETAINED`: 이전·최신 결과에 모두 있는 `atom_id`.
- `REMOVAL_CANDIDATE`: 이전 결과에 있고 최신 결과에 없는 `atom_id`. **단순 비교상의 제외 후보**이지 '법적으로 면제 확정'은 아니다.

### 1.3 제외 처리 범위

- **Scope A:** 지정된 `work_schedule_id` 한 회차만 제외.
- **Scope B:** `application_date` 이후의 반복 회차 중단. 예약 중단일은 `inspection_sets.scope_b_deactivation_date`에 기록하는 설계이며, **신규 컬럼 Migration 미승인·미적용 상태에서는 운영 불가**.
- **Scope C:** 변경하지 않고 다이얼로그 종료. DB write 없음.

## 2. 논리적 데이터 흐름

```text
회사/사업장/현장/공정/설비/작업 정보의 변경 또는 LEG 정본을 반영한 재진단
    ↓
기존 공식 진단·C10 경로 (WP01-D가 LEG 내부 의무판정을 대체하지 않음)
    ↓
SaaS C10 결과: anonymous_diagnosis_results
  - source_type = saas, status = ACTIVE
  - inspection_materialization_status = MATERIALIZED
  - full_result.obligations_raw[atom_id]
  - input_data.factory_id / sector / site_id
    ↓
이전 C10 vs 최신 C10 비교
    ├─ ADDED
    ├─ RETAINED
    └─ REMOVAL_CANDIDATE
          ↓ 현재 LEGAL_ENGINE 점검세트와 연결, 후보 재검증
      inspection_sets(source=LEGAL_ENGINE)
          ↓ 관리자가 검토 및 범위 결정
      ├─ Scope C : 변경 없음
      ├─ Scope A : work_schedules 1회차 제외
      └─ Scope B : 지정일 이후 회차 중단 + inspection_sets 중단일 기록
          ↓
기존 공식 OTR / 일정 생성 경로가 중단일 이후 신규 회차를 만들지 않도록 가드
```

> **전이 경로의 증거 수준:** `run_saas_c10_and_materialize()` → `materialize_canonical_inspection_sets()` → `_record_materialization_status()`는 Claude Code의 조사 보고다. 본 정의서에서는 함수명·개념을 기록하되, 운영 DB에서 실제 `MATERIALIZED` 전이를 확인했다고 주장하지 않는다.

## 3. 변경 비교의 실제 구현 로직

### 3.1 입력·기준 자료

- 비교 API 입력: `factory_id`, `diagnosis_id`, 선택적 `site_id`.
- 신규 진단은 전달된 `diagnosis_id`로 찾으며 `source_type='saas'`, `status='ACTIVE'`, `inspection_materialization_status='MATERIALIZED'`, `input_data->>factory_id`를 검사한다.
- 이전 기준은 **신규 진단 이전 시점의** MATERIALIZED 결과 중 같은 공장, 요청 시 같은 sector/site 범위의 최신 이전 결과를 찾는다.
- 건설업 CONSTRUCTION은 변경 요약에서 `site_id` 필수다. 저장된 `site_id`와 요청 값이 상충하면 거부한다.
- 이전 MATERIALIZED 기준이 없는 최초 진단은 `has_previous_baseline=false`; 제외 후보를 유도하는 기준으로 사용하지 않는다.

### 3.2 집합 비교 공식

```python
previous = extract_atom_ids(previous_C10.obligations_raw)
current  = extract_atom_ids(current_C10.obligations_raw)

ADDED             = current - previous
RETAINED          = current & previous
REMOVAL_CANDIDATE = previous - current
```

- 결과의 `removal_candidate_atom_ids`와 `inspection_sets`의 `legal_obligation_atom_id`를 연결해 명칭, 법령명, 법조문, 세트 ID 등을 화면에 제공한다.
- 점검세트 조회 조건은 `factory_id`, `source='LEGAL_ENGINE'`, `is_active=True`.
- 처리·Preview 전 `_is_current_removal_candidate()`를 서버에서 **다시 호출**한다. 단순 프론트 표시 상태만으로 DB 변경하지 않는다.
- 후보 재검증은 활성 LEGAL_ENGINE 세트, 유효 atom, 최신 MATERIALIZED C10의 atom 부재, 이전 MATERIALIZED C10의 atom 존재를 확인한다.

### 3.3 데이터 무결성 특이사항

- `obligations_raw=[]`는 정상적인 의무 0건과 구분해 취급해야 한다.
- **현재 PATCH-4 소스의 잔여 동작:** `obligations_raw=None` 또는 필드 누락 시 WARNING을 남기지만 일부 비교 경로는 `[]`로 계속 진행한다. 누락을 안전한 0건으로 확정한 것이 아니다. 운영 활성화 검증에서 보완/차단 판단 필요.
- `extract_atom_ids()`는 각 요소가 `.get()`을 가진 dict형이라는 사실을 가정한다. 잘못된 원소 구조에 대한 독립된 수용검증은 확인되지 않았다.
- `load_current_removal_candidates()`의 단순 '최신 C10에 없는 활성 세트' 판정은 `_is_current_removal_candidate()`의 이전 기준 검증보다 느슨하다. **실제 DB write의 최종 승인 근거로 단순 목록 함수를 사용하지 않는다**.
- 같은 공장에 여러 건설현장/섹터가 포함된 경우 세트 ID의 정확한 site 귀속은 현재 정본 모델에서 완전히 입증되지 않았다(B01).

## 4. 관리자 API 계약

| Method·Path | 목적 | 권한·보호 | 운영에서의 효과 |
|---|---|---|---|
| `POST /obligation-change/change-summary` | C10 전후 diff 및 후보 목록 | 회사 소유 factory 확인 | READ-ONLY |
| `POST /obligation-change/preview-impact` | 제외 영향 미리보기 | ALL/COMPANY 관리자 및 회사 소유 factory, 최신 후보 재검증 | READ-ONLY |
| `POST /obligation-change/process-scope-a` | 한 회차 제외 | ALL/COMPANY 관리자·factory·연결 세트·후보 검증 | `work_schedules` 변경 |
| `POST /obligation-change/process-scope-b` | 지정일 이후 반복 중단 | ALL/COMPANY 관리자·factory·후보 검증 | `work_schedules`·`inspection_sets` 변경(미승인) |

> 역할 코드의 판정은 로컬 브라우저 값이 아니라 백엔드 `role_data_scope` 기반이다. 프론트 `isAdmin`은 표시 힌트일 뿐 권한 판정 근거가 아니다. 현재 라우터의 회사 소유권 검사에서는 ALL 역할이라도 `company_id`와 대상 공장의 일치를 요구한다.

## 5. Scope A: 단일 회차 제외

**입력:** `factory_id`, `work_schedule_id`, `reason`.

**처리 순서(현재 구현):**

1. 관리자/회사 공장 접근 검사.
2. 일정에서 `inspection_set_id`를 찾는다. 미발견은 404, 연결 세트 없음 또는 유효 후보가 아님은 409.
3. 일정의 `active_yn`과 `status_code`를 읽어 완료/진행 중·이미 비활성 회차를 제외한다.
4. 배정·안전점검·장비 체크인 등의 자식 기록이 있으면 제외하지 않는다.
5. 조건부 UPDATE 수행: factory와 schedule ID, 활성 여부, 보호 상태를 함께 가드한다.
6. 실제 UPDATE 결과 행이 없으면 `processed=0` 및 `skipped_reason`을 반환한다.
7. 성공이면 `is_excluded=True`, `excluded_reason=reason`, `active_yn=False`, `status_code='EXCLUDED'`로 변경한다. **DELETE하지 않는다**.

**기록 특성:** `reason`은 단건 일정의 `excluded_reason`에 저장된다. 프론트는 HTTP 200이어도 `processed=0`이면 성공 메시지 대신 경고를 표시한다.

**보호 상태:** 정본 `completed`, `in_progress`; 이행 기간 구값 `done`/`DONE` 등은 기존 status vocabulary와 `_apply_preserve_guard()`를 통해 처리한다. 조회 후 UPDATE까지의 자식 연결 경합은 여러 API 호출만으로 원자적으로 차단했다고 증명되지 않았다.

## 6. Scope B: 지정일 이후 반복 중단

**입력:** `factory_id`, `inspection_set_id`, `application_date(YYYY-MM-DD)`, `reason`.

**현재 소스 설계:**

1. 관리자·회사 공장·현재 제외 후보 재검증.
2. LEGAL_ENGINE 활성 세트인지 검사하고, 날짜를 파싱한다.
3. `effective_from = max(application_date, date.today())`로 소급 취소를 제한한다.
4. 해당 일자 이후 활성 일정 중 완료·진행 중 및 연결 이력 존재 회차를 보존하고, 나머지 일정의 `active_yn=False`를 시도한다.
5. `inspection_sets.scope_b_deactivation_date`와 `scope_b_reason`을 기록한다.
6. `application_date <= today`이면 세트 `is_active=False`; 미래 날짜는 세트의 활성 상태를 유지하면서 중단일 가드로 미래 회차 생성을 막도록 설계됐다.
7. 세트 UPDATE 결과가 0행이면 `is_set_updated=False`, API 응답 `status='partial_success'`, UI 경고를 반환한다.

**중요:** 개별 일정 UPDATE와 세트 UPDATE는 **여러 트랜잭션/호출로 분리**되어 있다. `partial_success`는 감지·사용자 경고 기능이지 원자성 보장이 아니다. 일정별 일부 0행·예외·동시 처리 발생 시 전부 성공 또는 전부 롤백이라는 증거가 없다.

**날짜 주의:** `date.today()`는 서버 실행 환경의 날짜다. 공식 KST 업무일 계약과 항상 동일하다고 독립 검증되지 않았다. 이 문제로 과거 회차를 소급 수정해서는 안 된다.

**신규 일정 차단:** 공식 OTR 생성기 `law_engine.py`는 별도 조회로 `scope_b_deactivation_date`를 읽고 생성 예정일이 적용일 이상이면 건너뛴다. Migration 미적용으로 컬럼이 없으면 빈 딕셔너리로 후퇴하는 코드가 있으므로 **신규 컬럼을 적용하지 않은 환경에서 Scope B 중단 계약이 성립했다고 주장할 수 없다**. 일반 DB 오류는 재발생시켜 일정 생성 경로를 차단하는 방향으로 PATCH-3에서 보정됐다.

**운영 판정:** Scope B는 `NOT ACTIVATED`. 활성화, Migration, 원자성 설계는 별도의 Owner 승인 사항이다.

## 7. Scope C 및 프론트 사용자 동선

- 진단의 `MATERIALIZED` 결과가 반환되면 `diagnosisId`를 전달하여 변경 요약을 읽는다. 세트 목록을 정상적으로 갱신하지 못한 상태(`MATERIALIZED_REFRESH_FAILED`)와 완전 성공은 별도 구분한다.
- `/my-inspection`에 제외 후보 배너·테이블·처리 다이얼로그가 있고, 처리 범위는 실제 UI 기준 **A=이번 회차만 제외, B=지정일 이후 반복 중단, C=취소(변경 없음)**이다.
- `Scope C`를 선택하면 API 변경 요청을 보내지 않고 닫는다.
- 프론트에서 다른 공장으로 이동하면 기존 후보를 초기화하고, `changeSummaryGeneration`으로 뒤늦은 이전 요청 결과를 억제한다. 단, 일정/Preview/다른 조회까지 동일한 세대 관리가 완전히 적용되었다고 입증된 것은 아니다.
- 최종 처리 권한은 서버에서 재검증한다. localStorage의 `role_code`는 버튼 표시 힌트만 제공한다.
- `Scope A processed=0`은 경고, `Scope B status='partial_success'`는 경고로 표시한다.
- `lastDiagnosisId`는 공장별 브라우저 저장값을 이용해 재조회할 수 있다. **브라우저 캐시가 법적 증거나 정본이 아니다.**

## 8. 변경 영역 및 데이터 쓰기 경계

| 저장소 / 위치 | 역할 | 쓰기 경계 |
|---|---|---|
| `anonymous_diagnosis_results` | C10 진단 snapshot 입력 | WP01-D는 비교에 사용; 자체적으로 LEG 판정·snapshot 재작성하지 않음 |
| `inspection_sets` | LEGAL_ENGINE 법령의무 정본 세트·중단일 | Scope B를 제외하면 의무 변경관리에서 정본 데이터 변경 금지. B는 운영 미승인 |
| `work_schedules` | 의무의 실제 실행 회차 | Scope A 단건 soft exclude / Scope B 적용일 이후 비활성화(미승인) |
| `work_assignments` | 자식 배정 근거 | 존재 시 보존; 이력 삭제 금지 |
| `safety_inspections` | 수행/점검 증거 | 존재 시 보존; 이력 삭제 금지 |
| `equipment_checkins` | 설비 체크인 증거 | 존재 시 보존; 이력 삭제 금지 |
| LEG DB·법령 SoT | 법령 정본·적용 근거 | 본 WP에서 수정하지 않음 |
| PRJ 개발거버넌스 | 공식 파이프라인·승인 규칙 | 본 WP에서 변경하지 않음 |

**기존 스키마 특성:** `inspection_sets`의 LEGAL_ENGINE atom 고유키는 `(factory_id, legal_obligation_atom_id)`이다. 원래 정본은 site별 중복 세트를 당연히 지원하는 구조가 아니다. `site_id` 컬럼 추가만으로 귀속 문제를 해결했다고 보아서는 안 된다.

## 9. 작업 이력 / PATCH 변경 기록

| 단계 | 구현/검증 작업 | 기록 수준 |
|---|---|---|
| `WP01-D` 초기 구현, WO-008 | 변경 diff, Preview, Scope A/B API, UI, Migration 초안, 초기 테스트 | PR 최초 설명; 이후 구현이 변경돼 PR 본문 일부 설명은 **오래된 정보** |
| `PATCH-1` | 최초 소스 검증에서 Scope A UPDATE 결과, 후보 baseline, Scope B 부분 성공, FE race, Migration 미적용 위험 등 확인 | GPT 원격 소스 리뷰 이력 |
| `PATCH-2` | OTR 신규 컬럼 조회 분리, Scope A UPDATE 결과 확인, 소급 취소 방지, Preview 후보 재검증, FE generation, 테스트 강화 | API HEAD `c58773c9b2d4308e85b4fb5ada257641daf536c9`; Admin `c1cb0216fce4ff29a4b016b8fc5540518d8fc37f`; Claude 80/80 보고 |
| `PATCH-3` | 컬럼 미존재/DB 오류 구분, 이전 C10 baseline 확인, Scope A 연결 세트 강제, Scope B 부분 성공 감지, A 0건 UI 경고 | API `7d89f43e91d25e88c2504b35af5c09f061586386`; Admin `cae8170300a822aabcc27c90748899a405ea9efe`; Claude 86/86 보고 |
| `PATCH-4` | 소문자 상태 보호 가드, Preview 3종 이력 재사용, Scope B 부분 성공 경고, `obligations_raw=None` 경고 기록 | API **`bcc316dc75c959f0cd8ebe29090826589ed29d21`**; Admin **`284efad0c41c3483af3a33aa8b247061e57edeb5`**; Claude 95/95 보고 |
| `2026-10-17` | Owner 보고에 따라 PATCH-4를 **SOURCE FROZEN** 기준으로 고정; Draft PR 미병합, DB/배포 미승인 | 본 종료 기록 |

### 변경 이력 기록 규칙

향후 LEG 정본 또는 관련 consumer가 변경되면 매번 **(a)** 변경 사유/법령 근거·적용일(LEG), **(b)** 이전/새 atom 및 C10 진단 범위, **(c)** 기존 의무·회차·증빙의 영향, **(d)** 수정 소스·고정 SHA, **(e)** 테스트·DB·운영 실행 증거, **(f)** Owner 승인·롤백을 구분해 별도 이력 행을 추가한다. 법령 조문의 단순 문자 변경과 사업장 데이터 재진단을 혼동하지 않는다.

## 10. 특이사항, 잔여 위험 및 승인 게이트

| ID | 특이사항 / 미해결 항목 | 현재 처리 |
|---|---|---|
| `B01` | 동일 공장 내 다중 현장/섹터의 동일 atom에 대해 inspection_set의 현장 귀속을 직접 증명하기 어려움. 기존 unique index가 공장+atom 중심 | **현장별 자동 제외 확정 불가.** 구조 변경은 별도 설계/Owner 승인 과제. 현재 WP 재설계 없음 |
| `B02` | Scope B 일정별 UPDATE와 세트 UPDATE가 원자적이지 않음 | 부분 성공 경고는 구현됐으나 **Scope B 운영 활성화 보류**. 별도 Owner 승인 필요 |
| `B03` | scope_b 컬럼 미존재를 오류 문자열로 판단하며 명시적 활성화/version 계약 없음 | 신규 Migration 미승인; Scope B 미활성. 명시적 활성화 확인 전 운영 투입 금지 |
| `B04` | C10 `MATERIALIZED` 소스 경로가 보고됐지만 실제 대상 API DB 연결·운영 결과는 미검증 | 운영 수용 E2E 별도 게이트로 남김 |
| `D01` | `obligations_raw=None`에서 WARNING 후 `[]`로 계속 처리되는 경로 | 자료 누락을 의무 0건의 법적 근거로 삼지 않음. 실제 처리 전 차단 검증 필요 |
| `D02` | Preview/처리 중 새로운 자식 증빙 생성 또는 회차 상태가 동시 갱신될 수 있음 | 소스 레벨 선행 검사만으로 DB 트랜잭션 보장 주장 금지 |
| `D03` | 서버 `date.today()`와 한국 업무일 KST 동치 미입증 | 적용일 경계 처리 실측 필요 |
| `D04` | Admin·API 현재 코드에 Scope A/B를 독립적으로 통제하는 확정된 feature flag가 확인되지 않음 | **PR 병합만으로 안전한 비활성 보장 불가**. 무단 merge/deploy 금지 |
| `D05` | 현행 PR 설명 본문에는 초기 테스트 수·Scope 명칭·Scope B 즉시 비활성 등 과거 설계 설명 존재 | **고정 HEAD 실제 소스와 본 정의서 우선**, PR 본문 최신화는 병합 전 별도 문서 변경으로 수행 |

### 실측된 DB 특이사항(해당 조회 프로젝트 한정)

2026-10-17 READ-ONLY 조회에서 한 `taieng` Supabase 프로젝트는 `inspection_sets`의 신규 `scope_b_deactivation_date`, `scope_b_reason` 컬럼이 없었고, ACTIVE SaaS 진단 57건의 materialization 상태가 모두 NULL이었다. 또한 LEGAL_ENGINE inspection_set 395건은 `site_equipment_set_id`, `equipment_set_id`가 모두 NULL이었다. **이 프로젝트가 배포 대상 API와 동일한지 확인되지 않았으므로 운영 전역의 사실로 확대하지 않는다.**

## 11. 테스트/검증 완료의 정확한 의미

- **소스 증거:** GitHub 위 두 PR의 고정 HEAD에서 관련 파일·테스트 정의를 확인했다.
- **테스트 실행:** `95/95 PASS`는 Claude Code 제출 보고다. 독립 실행 및 CI 상태 검증은 별도다.
- **실제 DB WRITE/실서비스 E2E:** 수행·승인하지 않았다. `DB_WRITE=0`, `MIGRATION_APPLY=0`, `MERGE=0`, `DEPLOY=0`.
- **운영 법령 적용 정합성:** 실제 법령 문구, 효력일, 경과규정 등은 LEG의 검증 대상으로 본 WP의 95개 단위테스트만으로 확인할 수 없다.

## 12. 향후 법령 변경 시 처리 원칙(운영 정의)

1. **LEG 우선:** 법령·고시·시행일·적용조건 변경은 LEG에서 출처·법조문·효력일·승인과 함께 확정. WP01-D consumer가 법령 정본을 임의 생성·수정하지 않는다.
2. **C10 snapshot 구분:** 변경 전/후 진단의 `factory_id`, `sector`, `site_id`, 발생 시점 및 MATERIALIZED 여부를 증명. 최초 진단과 이전 진단 없음은 '제외' 사유가 아니다.
3. **Atom diff는 '후보'까지만:** `REMOVAL_CANDIDATE`는 사용자에게 검토를 요청한다. 법령 면제 확정/법률 자문 자동화가 아니다.
4. **과거 이력 보존:** 완료/진행·배정/점검/체크인 근거는 보호. 물리 삭제 금지. 소급 제외 금지.
5. **기능별 승인:** 읽기전용 요약·Preview와 DB write 처리(Scope A/B)를 분리하여 독립검증. 기능 플래그 부재 시 전체 PR merge가 쓰기 경로를 함께 노출한다는 점에 주의.
6. **변경 추적:** 새로운 법령 변경 사건마다 변경근거 → 영향 범위 → diff → 개별 회차 → 테스트 → Owner 승인 → 배포 → 롤백/감사 로그까지 한 건의 작업이력으로 연결.
7. **본선 재진입:** 현재 WP01-D 소스는 FROZEN. 새로운 법령 변경이나 운영 승인 과제는 명시적 별도 WO 및 PRJ 파이프라인 게이트에서만 열고, 여기서 구현을 반복하지 않는다.

## 13. 코드·증거 바로가기(고정 SHA)

### API

- [차이 계산·C10 기준·후보 재검증](https://github.com/taiengineering/tai-api/blob/bcc316dc75c959f0cd8ebe29090826589ed29d21/services/wp01_obligation_change/change_tracker.py)
- [Preview 및 Scope A/B](https://github.com/taiengineering/tai-api/blob/bcc316dc75c959f0cd8ebe29090826589ed29d21/services/wp01_obligation_change/removal_processor.py)
- [4개 API 및 권한 게이트](https://github.com/taiengineering/tai-api/blob/bcc316dc75c959f0cd8ebe29090826589ed29d21/routers/obligation_change.py)
- [요청 스키마](https://github.com/taiengineering/tai-api/blob/bcc316dc75c959f0cd8ebe29090826589ed29d21/schemas/obligation_change.py)
- [기존 공식 OTR 중단일 가드](https://github.com/taiengineering/tai-api/blob/bcc316dc75c959f0cd8ebe29090826589ed29d21/services/inspection_sets_svc/law_engine.py)
- [Scope B 컬럼 Migration — 적용 미승인](https://github.com/taiengineering/tai-api/blob/bcc316dc75c959f0cd8ebe29090826589ed29d21/supabase/migrations/20261017000001_wp01d_inspection_sets_scope_b.sql)
- [Python 테스트(95개 함수)](https://github.com/taiengineering/tai-api/blob/bcc316dc75c959f0cd8ebe29090826589ed29d21/tests/test_wp01d_obligation_change.py)

### Admin

- [화면 상태·API 호출·처리 경고](https://github.com/taiengineering/tai-admin/blob/284efad0c41c3483af3a33aa8b247061e57edeb5/vue3/src/pages/my-inspection/useMyInspectionList.ts)
- [제외 후보·Scope A/B/C UI](https://github.com/taiengineering/tai-admin/blob/284efad0c41c3483af3a33aa8b247061e57edeb5/vue3/src/pages/my-inspection/index.vue)
- [진단 MATERIALIZED 연계](https://github.com/taiengineering/tai-admin/blob/284efad0c41c3483af3a33aa8b247061e57edeb5/vue3/src/pages/my-inspection/runLegCore.ts)
- [프론트 계약 테스트](https://github.com/taiengineering/tai-admin/blob/284efad0c41c3483af3a33aa8b247061e57edeb5/vue3/src/pages/my-inspection/__tests__/wp01d_obligation_change.test.ts)

## 14. 최종 상태 기록

```text
WP01-A = CLOSED FINAL  (기존 승인 상태 유지)
WP01-B = CLOSED FINAL  (기존 승인 상태 유지)
WP01-C = SOURCE PASS    (기존 승인 상태 유지)
WP01-D = SOURCE IMPLEMENTATION COMPLETE / FROZEN
PATCH-4 API HEAD = bcc316dc75c959f0cd8ebe29090826589ed29d21
PATCH-4 ADMIN HEAD = 284efad0c41c3483af3a33aa8b247061e57edeb5
TESTS = 95/95 PASS (CLAUDE CODE REPORTED; GPT DID NOT RERUN)
B01 = DEFERRED / OWNER DESIGN APPROVAL REQUIRED
B02 = DEFERRED / OWNER DESIGN APPROVAL REQUIRED
B03 = MIGRATION/ACTIVATION CONTRACT UNVERIFIED
B04 = PRODUCTION MATERIALIZED E2E UNVERIFIED
PR #631 = DRAFT / UNMERGED
PR #155 = DRAFT / UNMERGED
DB MIGRATION APPLY = NOT APPROVED
MERGE = NOT APPROVED
DEPLOY = NOT APPROVED
SCOPE A/B PRODUCTION ACTIVATION = NOT APPROVED
E2E2000 = RESUME ONLY IN PREVIOUSLY APPROVED, WP01-D-INDEPENDENT SCOPE
```

---

### 저장소 반영 시 권장 경로(문서 전용)

`taiengineering/tai-api/docs/TAI_E2E2000_WP01D_LEGAL_OBLIGATION_CHANGE_DEFINITION_2026-10-17.md`

본 파일은 GPT가 문서로 작성한 **검증 가능한 종료 산출물**이며 GitHub 저장소에 자동으로 commit/push하지 않았다. Claude Code는 Owner의 별도 문서 반영 지시 시 **위 내용 그대로 문서 전용 커밋**으로 저장하고, 문서 파일 SHA와 Git commit SHA를 제출한다. 이때 기능 코드·Migration·PR 상태는 변경하지 않는다.
