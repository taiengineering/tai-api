# SESSION_HANDOFF_2026-08-23_PARTITION_RETENTION_DOCUMENT

> 작성일: 2026-08-23
> 세션 범위: work_schedules 파티셔닝 cutover 준비 → retention 조사 → 문서엔진 아키텍처 재정의
> 성격: **세션 간 연속성 확보용 이관 문서**

```text
PRODUCTION DB MUTATION = pg_cron active 플래그 3건 (운영자 승인)
PRODUCTION CODE DEPLOY = 문서 1건에 의한 자동배포 1회 (코드 무변경)
MERGE TO MAIN          = 0 (PR #187 draft 유지)
MIGRATION 실행          = 0
```

---

## 0. 이 문서를 읽는 법

이 세션은 세 개의 WP 를 연달아 진행했고, 각각 저장소에 기준 문서를 남겼다.
**새 세션은 이 문서로 현재 위치를 파악한 뒤, 해당 WP 의 기준 문서를 읽으면 된다.**

```text
WP-PARTITION-02C  코드 호환성      → CODE_COMPAT_v1.md
WP-PARTITION-03   cutover runbook  → PRODUCTION_CUTOVER_RUNBOOK_v1.md (REV-B)
WP-RETENTION-01   보존정책 조사     → 이 문서 §4 (별도 문서 없음)
WP-DOCUMENT-ARCH-01 문서엔진 재정의 → DOCUMENT_ENGINE_ARCHITECTURE_FINAL_v1.md
```

---

## 1. 현재 위치 (한 줄)

```text
work_schedules 파티셔닝  = production 적용 직전까지 준비 완료, 조건부 승인
safety_inspection_results 파티셔닝 = HOLD (문서엔진 선결)
문서엔진                 = 아키텍처 B 확정, 구현 미착수
```

---

## 2. Canonical SHA (전부 고정됨)

```text
PATCH BASE SHA
= 0972a18e9f158ce49c5d7163ab31860ebcb4f7db

CURRENT PROD SHA (2026-08-23 실측)
= ed0f47a9eecc5c0e053193f202bc32cf6b5a3212
  deployment 42d0d419 / SUCCESS / health 200 / 0.53s

CODE DRIFT BETWEEN THEM = 0 (문서 1건만 추가)

canonical CODE patch HEAD
= 23d16ac21c87dcbdf5ff2a1b590fd8d797121349

runbook REV-B
= 5b32aafda0633ced213b6a7864d6cccb056d90fa

DB UP    docs/sql/20260822_work_schedules_partition_up.sql
         commit b81e7018 / blob ac8adc58
         sha256 147f75f2864fd3bb261fb6ebedae7b34b5621b311d556e5d0d8e6b028300cca7

DB DOWN  docs/sql/20260822_work_schedules_partition_down.sql
         commit 0972a18e / blob 96da5c88
         sha256 57768a50dd9e7643bb1708ec198e48bfc62d0474852faf433b15ae7f2e9df20d

PR #187  open / draft / DO NOT MERGE
branch   wo-work-schedules-partition-code-compat
```

---

## 3. WP-PARTITION-02C / 03 — 파티셔닝 (조건부 승인)

### 상태

```text
WP-PARTITION-02C REV-1 = PASS / CLOSED
WP-PARTITION-03        = PASS / CLOSED (REV-B)
PRODUCTION APPLY       = CONDITIONALLY APPROVED
CURRENT EXECUTION      = 0
```

### 코드 patch 4건 (전부 커밋됨, 미배포)

| # | file | func | 방식 |
|---|---|---|---|
| 1 | `routers/work_schedules.py` | `_apply_one_update()` | 신규 INSERT 경로에서만 parent 조회 |
| 2 | `routers/worker_check.py` | `submit_check()` | 기존 조회 select 컬럼만 확장 |
| 3 | `routers/legal_engine_patch.py` | `auto_assign_schedules()` | `s["factory_id"]` 재사용 |
| 4 | `routers/inspection_checklist.py` | `start_inspection()` | `ws_res.data[0]` 재사용 |

공통 원칙: **factory 를 모르면 child 를 저장하지 않고 409 로 명시적 실패.**

### 검증 결과

```text
local pytest      497 passed / 11 failed, PATCH-CAUSED = 0
patch 인접        24 passed / 0 failed
DB write compat   C-1~C-5·C-7 PASS, R1-1~R1-4 PASS
                  (C-3·R1-4 는 패치 이전 payload 가 23514 로 거부됨 = 필요성 실증)
pair violation    0 / 0
```

### Writer Inventory 3-Layer (UNCOVERED = 0)

> **교훈**: writer 누락이 네 차례 발견됐다.
> 코드 grep 2회 → pg_cron 1회 → cron_job_master 1회.
> **코드만 보고 writer inventory 를 닫으면 안 된다.**

```text
LAYER 1 APPLICATION  child INSERT 5 → patch 5 커버
LAYER 2 DATABASE     trigger 0 / func 1(비활성) / view·publication 무관
                     pg_cron 10 → job 1 영구정지, 3·4 임시정지
LAYER 3 EXTERNAL     cron-job.org 실행이력 0
                     cron_job_master 32 job, 대상 write 0
```

### ⚠ 이미 적용된 production 변경

```text
pg_cron job 1  daily_assignments  DISABLED (영구)
pg_cron job 3  qa_send            DISABLED (임시 — cutover 후 복구)
pg_cron job 4  qa_collect         DISABLED (임시 — cutover 후 복구)
```

**job 1 은 재활성화 금지.** `asset_id` 컬럼 부재 + 중복 방지 부재 + `factory_id` 미포함 3건을 먼저 고쳐야 한다. 이 job 이 `work_assignments` 5,991행 증식의 유력 원인이다.

### cutover 당일 남은 gate 3개

```text
GATE-PITR     PITR add-on 미구독 → 당일 활성화 + restore point 실제 생성 확인
              7일 $100/월, 시간당 과금 (24~48h ≈ $3.3~6.7)
              ⚠ Spend Cap 미적용 — 끄는 것을 잊으면 계속 청구
GATE-CRON     cron-job.org /overdue/check pause
GATE-SESSION  다른 Claude 세션의 DB 작업 금지 (사람도 writer 다)
```

### 실행 순서 (요약)

```text
PR draft 유지 → local pytest PASS → merge 금지
→ GATE-SESSION / PITR / CRON
→ maintenance → writer stop → active=0
→ PRECHECK 6항목 / schema drift / UP checksum
→ §17-0 PRE_CUTOVER_PROD_SHA capture   ← REV-B 신설
→ GATE-DB-UP → DB UP → POSTCHECK
→ GATE-DEPLOY → PR merge (= 자동배포)
→ health(cold start) → MANUAL smoke A~E
→ GATE-GO-NOGO → job 3·4 재활성화 → maintenance OFF
```

### 권고 시간대

```text
01:00~03:00 KST (대안 04:00~06:00)
회피: 03:34 KST 일일백업 / 09:00 KST 외부 cron
소요: 최소 1.5h, 여유 3h 권고
PITR 은 cutover 2~3시간 전 활성화
```

**cutover 일시는 미정.** 운영자가 2~3시간 집중 가능하고 다른 세션을 닫을 수 있는 시점으로 정한다.

---

## 4. WP-RETENTION-01 — 보존정책 (조사 완료, 결정 유예)

```text
WP-RETENTION-01 = INVESTIGATION PASS / POLICY DECISION DEFERRED
WP-PARTITION-01B REV-1 (results 물리설계) = HOLD
```

### 핵심 발견

**① 법적 보존기간은 단일값이 아니다** (leg-prod `staging.requirement_atom_v3` 실측)

```text
"보존" 포함 ATOM 243건
  1년 5 / 2년 10 / 3년 28 / 5년 17 / 10년 73
  기간 미명시 145 (60%)
```

`runtime_evidence_retention_policy` 의 `INSPECTION_RESULT = 3년` 은
`source_trace = MANUAL_CONFIG` 이며 **법적 정본이 아니다.**
3년은 243건 중 28건(11.5%)에 불과하고 10년이 최다다.

```text
LEGAL RETENTION = ESTABLISHED BUT PLURAL
```

**② provenance 가 끊겨 있다**

```text
sir.inspection_set_item_id   FK 없음, 실측 62.5% NULL
isi.inspection_set_id        FK 없음
sets.legal_rule_code         2.4% 만 보유

Q1 row → 법적 의무 → retention 복원 = PARTIAL
→ 의무별 차등 retention 자동화 불가
```

**③ 문서가 원본에 의존한다**

```text
DOCUMENT DEPENDENCY = A (confirmed 이후에도 source results 필요)
→ HOT 에서 result 를 내리면 과거 문서 재출력 불가
```

**④ structured archive destination 이 없다**

```text
Supabase Storage 20 버킷 / 1,623 객체 = binary/file 용
structured evidence archive = NOT AVAILABLE
```

### 정책 후보

```text
A GLOBAL CONSERVATIVE   NOT SELECTED (과잉 일반화)
B DIFFERENTIATED        NOT IMPLEMENTABLE (provenance PARTIAL)
C HOT + ARCHIVE + UNKNOWN   LEADING CANDIDATE
    HOT     = 공통 운영 구간
    ARCHIVE = KNOWN → 의무별 / UNKNOWN → 삭제 금지·미분류 보존
    현재 실행 수단 부재 (Q2·Q3 blocker)
```

### 데이터 실태

```text
safety_inspection_results  8행 / 80 kB   ← 용량 근거로 사용 불가
CAPACITY MODEL             설계 envelope 로만 사용
                           NORMAL 15.6M/yr, HIGH 156M/yr
```

### 재개 조건

```text
1. WP-DOCUMENT-ARCH-02 완료 (snapshot contract)
2. WP-SIR-PROVENANCE-01 범위 확정
3. structured archive contract 결정
→ 그 다음 WP-RETENTION-01 재개 → WP-PARTITION-01B REV-1
```

---

## 5. WP-DOCUMENT-ARCH-01 — 문서엔진 (아키텍처 확정)

```text
WP-DOCUMENT-ARCH-01 = PASS / CLOSED
ARCHITECTURE = B. LAZY SOURCE + CONFIRMED SNAPSHOT (APPROVED)
```

기준 문서: `docs/docs/DOCUMENT_ENGINE_ARCHITECTURE_FINAL_v1.md` (main, ed0f47a9)

### 최대 발견 — 문서엔진은 완성된 적이 없다

```text
PATH 1  익명 무료진단 → activation 1,540 → PENDING 1,526 → [consumer 없음]
PATH 2  runtime lifecycle → runtime_document_data 1행, approval 0, archive 0
        generate_document() 는 PDF 없이 기록만 INSERT
PATH 3  즉시 렌더 → PDF StreamingResponse → DB·storage 저장 0 (휘발)

form-outputs 버킷 객체 = 0     ← PDF 가 하나도 없다
storage_path = 1,543건 전건 NULL
```

```text
PENDING CAUSE = B. ACTIVE PRODUCER / CONSUMER MISSING
producer = anonymous_diagnosis.py 의 Document Activation Hook (동작 중)
consumer = 없음 (pg_cron 0 / cron_job_master 0 / trigger 0 / function 0)
```

### 확정된 계약

```text
DRAFT       = source 를 실시간 조회해서 조립
CONFIRMED   = source 와 독립된 immutable snapshot
REPRINT     = confirmed snapshot 우선
PDF         = snapshot 에서 생성 (derived output)
SOURCE      = confirmed 이후 재출력 필수 의존성에서 제거

runtime_document_data = WORKING DOCUMENT STATE (법적 확정본 저장소 아님)
```

### Reprint Drift Risk = HIGH

`inspection_fetcher.fetch()` 가 재출력마다 원본 5개 테이블을 재조회하며 **전부 mutable** 이다.
담당자 이름·사업장명·회사명이 바뀌면 **과거 점검 문서 내용이 소급 변경된다.**

### Superseded

```text
D-09 runtime_document_data legacy 격리 = REJECT / SUPERSEDED
D-02 / D-03 / D-04 / D-05 = KEEP
  단 D-03(delta) 는 현재 구현(full overwrite)과 불일치
```

---

## 6. 다음 작업 — WP-DOCUMENT-ARCH-02

```text
WP-DOCUMENT-ARCH-02
Confirmed Snapshot Contract & Storage Design

MODE = DESIGN / READ ONLY
DB MUTATION = 0 / CODE MUTATION = 0 / DDL = 0
```

### 답해야 할 5가지

```text
1. 무엇을 snapshot JSON 안에 봉인할 것인가?
2. source ID/provenance 를 어떤 구조로 남길 것인가?
3. snapshot 자체를 어디에 저장할 것인가?
4. PDF/object 와 snapshot 을 어떻게 1:1 추적할 것인가?
5. CONFIRM 을 언제 성공으로 인정할 것인가?
```

핵심 결정: `runtime_document_data` 를 snapshot 저장소로 그대로 쓸지, 별도 sealed snapshot store 가 필요한지를 **컬럼·제약·version/hash·immutability 관점에서** 결정한다.

### 참고 — 이미 있는 snapshot 코드

`document_engine_svc.py` `_approval()` 이 `runtime_snapshot` / `evidence_snapshot` 을 저장한다.
다만 `source_trace_snapshot` 이 항상 `{}` 이고 rendered body·template_version·checksum 이 없다.
**참고 구현으로만 보고 최종 contract 로 승인하지 않는다.**

---

## 7. 실행 대기열 (전체)

```text
1. WP-DOCUMENT-ARCH-02   snapshot contract & storage design   ← 다음
2. WP-SIR-PROVENANCE-01  inspection result legal provenance
3. structured archive contract
4. WP-RETENTION-01 재개  HOT/ARCHIVE/PERMANENT DELETE 확정
5. WP-PARTITION-01B REV-1  safety_inspection_results 물리설계
6. work_schedules cutover 실행 (일시 확정 시)
7. WP-PARTITION-04       post-cutover cleanup
```

`work_schedules cutover` 는 위 순서와 독립이며 언제든 실행 가능하다(조건부 승인 상태).

---

## 8. WP-PARTITION-04 예약 (observation 종료 후)

```text
[ ] PITR 비활성화            ← Spend Cap 미적용, 잊으면 월 $100
[ ] pg_cron job 3·4 재활성화
[ ] pg_cron job 1 비활성 유지 확인 (재활성화 금지)
[ ] work_schedules_old cleanup
[ ] _mig_ws_* 스냅샷 테이블 7종 정리
```

---

## 9. 미해결 이슈 목록

### 문서엔진

```text
ISSUE-DOC-ENGINE-INCOMPLETE-01      producer 有 / consumer 無 / 산출물 0
ISSUE-DOC-DUAL-PATH-01              3-path disconnected
ISSUE-DOC-AUDIT-SILENT-FAIL-01      _audit·_approval 이 except: pass
ISSUE-DOC-REPRINT-DRIFT-01          모든 source mutable → 과거 문서 소급 변경
ISSUE-DOC-TYPE-NONDETERMINISTIC-01  doc_type 을 호출자가 지정, 자동 결정 없음
ISSUE-GENDOC-STORAGE-PATH-NULL-01   1,543행 전건 storage_path NULL
```

### 파티셔닝 / 데이터

```text
ISSUE-SIR-PROVENANCE-BROKEN-01      법령 역추적 FK 부재, 62.5% NULL
ISSUE-SIR-NO-TIME-INDEX-01          시간 기반 인덱스 0개
ISSUE-SIR-ITEM-FK-MISSING-01        inspection_set_item_id FK 없음
ISSUE-RETENTION-POLICY-OVERSIMPLIFIED-01  3년 전역화가 법령 실측과 불일치
ISSUE-WS-SCHEMA-DRIFT-01            resolved_at·cycle_code·is_active 부재
ISSUE-WS-SILENT-INSERT-FAILURE-01   auto_assign INSERT 실패 은폐
ISSUE-CRON-GEN-DAILY-ASSIGN-01      [DISABLED] 재활성화 전 3건 수정 필수
ISSUE-CRON-QA-PAUSED-01             [TEMP] cutover 후 job 3·4 복구 필수
RISK-WS-EC-PARTIAL-NULL-01          equipment_checkins pair CHECK 없음
```

### 인프라 / 개발환경

```text
ISSUE-CI-DISABLED-01                GitHub Actions 4개월 미실행
ISSUE-TEST-COLLECTION-ERROR-01      mock 미구현으로 pytest 전체 중단
ISSUE-PROD-STEP2-500-01             /legal-engine/diagnose/step2 현재 500
ISSUE-REPO-MERGE-CONFLICT-01        로컬 main diverged (cutover 무관 확정)
ISSUE-ROUTE-DUPLICATE-01            generate_schedules_from_diagnosis 중복
ISSUE-STORAGE-PUBLIC-INSPECTION-01  inspections·inspection-images public=true
                                    POTENTIAL SECURITY EXPOSURE
                                    SEPARATE SECURITY REVIEW REQUIRED
LESSON-PARTITION-DEPLOY-01          main documentation commit 도 자동배포 유발
```

### 배제 확인

```text
evidence_normalized (283,175행) / evidence_token (237,892행) = UNRELATED
  법령 조문 토큰 정규화 구조(part_id, source_span_*). 문서엔진과 무관.
ISSUE-LEGAL-SOT-MISSING-01 = CANCELLED (조회 위치 오류. 법령 SoT 는 leg-prod)
```

---

## 10. 이 세션에서 배운 것

```text
1. writer inventory 는 3-layer 로 닫아야 한다
   application / database(pg_cron·trigger·function) / external(자체 스케줄러)
   코드 grep 만으로는 4번 놓쳤다.

2. main 의 documentation commit 도 production 배포를 일으킨다
   cutover 기준 SHA 가 중요한 기간에는 브랜치에서만 문서를 고친다.

3. rollback anchor 를 고정 SHA 로 하드코딩하지 않는다
   cutover-day capture 값(PRE_CUTOVER_PROD_SHA)으로 정의한다.

4. 구조가 있다는 것과 동작한다는 것은 다르다
   runtime_document_data 는 컬럼이 완비돼 있으나 1행이다.
   테이블 존재·FK 구조가 아니라 실제 row count 와 코드 경로를 봐야 한다.

5. "전수 조사 완료" 는 집합을 열거했을 때만 쓴다
   검색어를 바꿔 더 나오면 그것은 전수가 아니었다.
```

---

## 11. 참조 문서

```text
main 브랜치 (ed0f47a9)
  docs/docs/DOCUMENT_ENGINE_ARCHITECTURE_FINAL_v1.md
  docs/docs/DOCUMENT_ENGINE_ARCHITECTURE_DECISIONS_v1.md  (의사결정 이력)

partition 브랜치 (wo-work-schedules-partition-code-compat)
  docs/docs/WORK_SCHEDULES_PARTITION_DESIGN_FINAL_v1.md
  docs/docs/WORK_SCHEDULES_PARTITION_CODE_COMPAT_v1.md
  docs/docs/WORK_SCHEDULES_PARTITION_PRODUCTION_CUTOVER_RUNBOOK_v1.md  (REV-B)
  docs/sql/20260822_work_schedules_partition_up.sql
  docs/sql/20260822_work_schedules_partition_down.sql
  docs/sql/verify_02c_write_compat.sql
  docs/docs/SESSION_HANDOFF_2026-08-23_PARTITION_RETENTION_DOCUMENT.md  (이 문서)
```

---

## 12. 환경 정보

```text
Railway   project tai-api 7c3ab53b / env production 9dacb6f0
          service tai-api-prod 4cf52678 / DOCKERFILE / health /health
          sleep when inactive = true (cold start 주의)
          도메인 api.taieng.co.kr
          ⚠ main merge = 자동배포

Supabase  taieng      vwlahtguyggrhvslabax   운영 DB (PostgreSQL 17.6, pro)
          leg-prod    wrfcedzgdrfupenzqhur   법령 SoT (law_*, requirement_atom_v3)
          governance  iapzwbysfzootqnldtan   개발 거버넌스 (법령 없음)

로컬      ~/tai-api            기존 작업 디렉터리 (merge conflict 잔존)
          ~/tai-api-partition  파티션 전용 clean clone
```

**법령을 taieng DB 나 governance 스키마에서 찾지 않는다. leg-prod 다.**
