---
title: DOC260 DATE Gate B — Evidence 승인 작업지시서
wo: WO-DOC260-DATE-GATE-B-EVIDENCE-APPROVAL-001
status: WP_G_B03_SOT_IV_PASS_WITH_GUARDS_OWNER_GATE
collected_by: Claude Code
created_date: 2026-10-30
revision: R6
review_required: OWNER_SOT_DECISION_Q1_Q2_Q3
gpt_r1_verdict: PASS_WITH_GUARDS (2026-10-30)
gpt_r2_verdict: PASS (2026-10-30)
gpt_r3_verdict: STOP_SOT_MISMATCH (2026-10-30)
gpt_r4_verdict: PASS_WITH_GUARDS (2026-10-31)
wp_g_b01_status: CLOSED_FINAL (PR#742 1ce3c559 MERGED 2026-10-30)
wp_g_b02_status: COMPLETE (2026-10-30)
wp_g_b02_db_project: vwlahtguyggrhvslabax (taieng)
wp_g_b03_status: SOT_RECONCILIATION_IN_PROGRESS (2026-10-30)
wp_g_b03_governance_stop: 45cm-prj-db/governance = 45CM 자체 거버넌스 룰 (한국 법령 없음)
wp_g_b03_leg_prod_project: wrfcedzgdrfupenzqhur (leg-prod, created 2026-06-11)
wp_g_b03_provisional_source_match: 72
wp_g_b03_data_semantic_gap: 17
wp_g_b03_leg_reference_missing: 23
---

# WO-DOC260-DATE-GATE-B-EVIDENCE-APPROVAL-001

**선행 Gate:** Gate A — PR #741 Squash Commit `99381050` MERGED (2026-10-30)  
**목적:** DATE evidence 104건을 법령 승인 근거와 연결하여, 적법하게 검증된 대상만  
`CANDIDATE` → `APPROVED_BY_HUMAN`으로 전환할 수 있는 승인 계약과 실행 조건을 확정한다.

**CODE_CHANGE = 0 / DB_CHANGE = 0 / DEPLOY = 0** (이 문서는 설계 계약만 확정)  
**실제 104건 상태 변경: 별도 Owner 승인 Gate 필요**

---

## 1. 배경 및 범위

### 1.1 Gate A 완료 사항

| 항목 | 내용 |
|------|------|
| 구현 | `services/document_confirm_svc.py` DATE family 확정 경로 |
| 병합 | PR #741 → main Squash Commit `99381050` |
| 테스트 | 75/75 PASS |
| GPT IV | `GPT_DATE_GATE_A_SOURCE_IV_FINAL = PASS` |

### 1.2 Gate B 목적

DATE evidence 104건이 현재 전부 `CANDIDATE` 상태다. 확정 호출(confirm)은 Gate A로  
코드 경로가 열렸으나, evidence 자체의 법령 승인 없이는 FAIL-CLOSED(422)다.  
Gate B는 이 승인 경로를 계약·검증·실행 조건 수준에서 확정한다.

---

## 2. 기존 자산 재사용 (B-01 소스 확인 결과)

### 2.1 승인 API 현황 (소스 직접 확인: `routers/review_bridge.py`)

| API | 경로 | 상태 |
|-----|------|------|
| Evidence Candidate 승인 | `POST /bridge/evidence-approve` | **구현됨 — DATE 사용 가능** |
| Runtime Evidence 승인 | `POST /bridge/evidence-runtime-approve` | **구현됨 — DATE 사용 불가 (Gap 존재)** |

### 2.2 `/bridge/evidence-approve` 계약

- 대상: `evidence_field_candidate.id`
- 선행: `role_code ∈ {"003", "012"}` (SAFETY_MANAGER)
- 권한: `runtime_review_authority WHERE review_domain='EVIDENCE' AND authority_status='ACTIVE' AND approver_role='SAFETY_MANAGER' AND approval_scope LIKE '%증빙%'`
- 전이: `CANDIDATE | NEEDS_HUMAN_REVIEW` → `APPROVED_BY_HUMAN`
- 원자: `runtime_review_decision INSERT` + `evidence_field_candidate.status UPDATE`
- 중복: 이미 처리된 상태 → 409

### 2.3 `/bridge/evidence-runtime-approve` 계약 및 DATE Gap

현재 소스 (라인 449~461):
```python
# [3] evidence_family / upload_type 검증
if ev["evidence_family"] != "ATTACHMENT":
    raise HTTPException(422, f"evidence_family={ev['evidence_family']!r} not supported (only ATTACHMENT allowed)")
if ev["upload_type"] != "attachment":
    raise HTTPException(422, f"upload_type={ev['upload_type']!r} not supported (only attachment allowed)")
```

**DATE evidence:**
- `evidence_family = "DATE"` → 422 차단
- `upload_type = "timestamp_auto"` → 422 차단

**결론: 기존 `evidence-runtime-approve`는 DATE family를 지원하지 않는다.**

### 2.4 `_RUNTIME_EV_ALLOWLIST` 현황

```python
_RUNTIME_EV_ALLOWLIST: frozenset = frozenset({
    "fd3f3c99-62cd-4336-bf23-dda92a4b2a43",  # DOC-CHEM-001
    "e1793f5c-aba8-4700-9dce-2ae2b449117b",  # DOC-FAC-022
})
```

DATE 104건은 미등재. Allowlist 확장은 별도 Owner Gate 필수.

---

## 3. 법령 SoT 경계 (B-02)

| 항목 | 계약 |
|------|------|
| 법령 SoT | Supabase Project `45cm-prj-db`, Schema `governance` |
| 접근 경로 | 승인된 RPC 경유 |
| 위치 기준 | `GOVERNANCE_SOURCE_OF_TRUTH.md` |
| D1 법령 조회 | **금지** |
| PRJ 개발거버넌스 → 법령 SoT 대체 | **금지** |
| 근거 없는 LEG 승인 추정 | **금지** |
| CANDIDATE를 승인 상태로 간주 | **금지** |

---

## 4. 104건 READ-ONLY 조사 사전 결과 (B-03)

### 4.1 알려진 사실 (설계 문서 기준)

| 항목 | 값 | 출처 |
|------|----|------|
| DATE evidence 수 | **104건** | P0 evidence matrix 실측 |
| 상태 | 전부 `CANDIDATE` | Gate 002 확인 |
| `evidence_family` | `"DATE"` | P0 matrix 실측 |
| `upload_type` | `"timestamp_auto"` | P0 matrix 실측 |
| 연결 서식 수 | 97종 | Gate 002 확인 |
| `APPROVED_BY_HUMAN` 건수 | **0건** | Gate 002 확인 |
| LEG Gate 통과 | **0건** | Gate 002 확인 |
| DATA_SEMANTIC_GAP | 13건 | GPT IV R1-01 |
| law_ref NULL | 15건 | GPT IV R1-01 |

> **주의:** 이 수치는 Gate 002 (2026-10-30) 기준이다.  
> Gate B 실행 전 READ-ONLY SQL로 현재값을 재확인해야 한다.

### 4.2 Gate B 실행 전 필수 READ-ONLY 확인 쿼리 (실행 불가, 작업 계획용)

```sql
-- 1. DATE evidence 현황 전수 조회
SELECT
  efc.id              AS efc_id,
  efc.status          AS efc_status,
  ref.id              AS ref_id,
  ref.status          AS ref_status,
  ref.evidence_family,
  ref.upload_type,
  rf.id               AS runtime_field_id,
  rf.input_type,
  rfs.id              AS schema_id,
  rfs.status          AS schema_status,
  rfs.form_name
FROM evidence_field_candidate efc
JOIN runtime_evidence_field ref ON ref.evidence_candidate_id = efc.id
JOIN runtime_field rf
  ON rf.field_candidate_id = efc.field_candidate_id
JOIN runtime_form_schema rfs ON rfs.id = ref.form_schema_id
WHERE ref.evidence_family = 'DATE'
ORDER BY efc.id;
```

```sql
-- 2. law_ref NULL 현황
SELECT COUNT(*) AS null_count
FROM evidence_field_candidate
WHERE id IN (
  SELECT evidence_candidate_id FROM runtime_evidence_field WHERE evidence_family = 'DATE'
)
-- law_ref 컬럼 존재 확인 필요 (스키마 의존)
;
```

```sql
-- 3. schema_status 분포 확인
SELECT rfs.status, COUNT(*) AS cnt
FROM runtime_form_schema rfs
JOIN runtime_evidence_field ref ON ref.form_schema_id = rfs.id
WHERE ref.evidence_family = 'DATE'
GROUP BY rfs.status;
```

---

## 5. API Gap 분석 및 Gate B 설계 결정 (B-04)

### 5.1 발견된 Gap (G-B01)

| Gap | 내용 | 심각도 |
|-----|------|--------|
| **G-B01** | `evidence-runtime-approve`가 `evidence_family='DATE'` → 422 차단 | **CRITICAL — Gate B 진입 차단** |

### 5.2 해결 경로 (Owner 결정 필요)

**경로 A: `evidence-runtime-approve` DATE 지원 확장**
- `evidence_family = 'DATE' AND upload_type = 'timestamp_auto'` 허용 분기 추가
- Allowlist에 DATE evidence ID 104건 등재
- 기존 ATTACHMENT 검증(input_type=file, sha256)과 구분
- DATE 전용 검증: `input_type = 'date'`

**경로 B: 별도 DATE 전용 승인 엔드포인트 신설**
- `POST /bridge/date-evidence-runtime-approve`
- DATE family 전용 계약, 독립 Allowlist

**경로 C: `evidence-approve` 만으로 Gate B 완결**
- `evidence_field_candidate` 승인 → efc.status = `APPROVED_BY_HUMAN`
- `runtime_evidence_field` 승인(runtime-approve)은 별도 Gate C로 이연
- 제약: confirm 루프에서 `ev_candidate_status` 체크가 먼저, `ev_field.status` 체크가 두 번째
  - efc 승인만으로 `ev_candidate_status = APPROVED_BY_HUMAN` → 통과
  - `runtime_evidence_field.status` 체크는 `ev_field.status`를 봄 → CANDIDATE 상태 유지 시 422

> **설계 제약 확인 필요:** Gate B에서 efc만 승인하면 confirm이 통과하는지, 아니면  
> `runtime_evidence_field.status = APPROVED_BY_HUMAN` 도 필요한지 코드에서 확인해야 한다.

### 5.3 확인 필요 코드 계약 (`document_confirm_svc.py`)

```python
# _resolve_evidence_connections() — runtime_evidence_field.status 체크
if ev_status not in _ALLOWED_EVIDENCE_FIELD_STATUSES:  # {"APPROVED_BY_HUMAN"}
    raise ConfirmError(422, f"not approved")  # ← ref.status = CANDIDATE → 차단

# confirm 루프 — evidence_field_candidate.status 체크  
if ev_candidate_status not in _ALLOWED_EVIDENCE_CANDIDATE_STATUSES:  # {"APPROVED_BY_HUMAN"}
    raise ConfirmError(422, "confirm blocked until evidence approval gate passes")  # ← efc.status = CANDIDATE → 차단
```

**결론: confirm 통과를 위해 두 상태 모두 `APPROVED_BY_HUMAN` 필요:**
1. `evidence_field_candidate.status = APPROVED_BY_HUMAN` (`/bridge/evidence-approve`)
2. `runtime_evidence_field.status = APPROVED_BY_HUMAN` (`/bridge/evidence-runtime-approve` — **현재 DATE 차단**)

경로 C(efc만 승인)는 `runtime_evidence_field.status`가 CANDIDATE이면 여전히 422 발생.  
경로 A 또는 B가 필요하다.

---

## 6. 승인 실행 계약 설계 (B-04 승인 시퀀스)

**전제: G-B01 해소(경로 A 또는 B) + Owner 별도 승인 후 진행**

### 6.1 단건 승인 시퀀스

```
For each DATE evidence (efc_id, ref_id):
  Step 1: LEG 근거 확인 (Supabase governance RPC)
          → law_ref NOT NULL + LEG status = APPROVED
          → 미충족 → SKIP (법령 미승인 대상)

  Step 2: /bridge/evidence-approve
          payload: evidence_field_candidate_id=efc_id, review_reason="..."
          성공 → efc.status = APPROVED_BY_HUMAN
          실패 → 로그 기록, 다음 건 진행 (부분 성공 허용 — 단건 원자성)

  Step 3: /bridge/evidence-runtime-approve (G-B01 해소 후)
          payload: runtime_evidence_field_id=ref_id, review_reason="..."
          선행 조건: efc.status = APPROVED_BY_HUMAN (Step 2 완료 필수)
          성공 → ref.status = APPROVED_BY_HUMAN
          실패 → 로그 기록

  Step 4: 상태 확인
          efc.status + ref.status 모두 APPROVED_BY_HUMAN → 완료 집계
```

### 6.2 일괄 처리 제약

- 104건 전체를 단일 트랜잭션으로 일괄 승인하지 않는다.
- 단건씩 처리하여 부분 성공을 허용한다.
- 실패 건은 격리하여 재시도 또는 개별 검토 경로로 이관한다.
- DATA_SEMANTIC_GAP 13건, law_ref NULL 15건은 별도 분류 후 처리한다.

### 6.3 멱등성

- `/bridge/evidence-approve`: 이미 APPROVED_BY_HUMAN → 409. 재시도 불필요.
- `/bridge/evidence-runtime-approve`: 이미 승인 → 409. 재시도 불필요.

---

## 7. Gate B 산출물 목록 (WP 계획)

| WP | 내용 | 조건 |
|----|------|------|
| WP-G-B01 | G-B01 해소 — `evidence-runtime-approve` DATE 지원 (경로 A) 또는 별도 엔드포인트 (경로 B) | Owner 경로 선택 후 |
| WP-G-B02 | 104건 READ-ONLY DB 조사 (실제 쿼리 실행) | DB 접근 승인 |
| WP-G-B03 | LEG SoT 기준 승인 가능 대상 분류 | Supabase governance RPC 접근 |
| WP-G-B04 | 승인 Allowlist 확장 (Owner Gate) | WP-G-B01 + WP-G-B03 완료 |
| WP-G-B05 | 104건 실제 승인 실행 | 별도 Owner 승인 Gate |

---

## 8. STOP 조건

| 조건 | 처리 |
|------|------|
| G-B01 미해소 | `evidence-runtime-approve` 호출 불가 → Gate B BLOCKED |
| LEG SoT 미연결 | 법령 근거 없는 승인 실행 금지 |
| law_ref NULL 15건 | 개별 LEG 판정 전 승인 금지 |
| DATA_SEMANTIC_GAP 13건 | 의미 분류 확정 전 승인 금지 |
| Allowlist 미확장 | runtime-approve 호출 불가 |
| Owner 별도 승인 미수신 | 실제 DB 상태 변경 금지 |

---

## 9. 유지되는 차단

| 항목 | 상태 |
|------|------|
| DATE 104건 실제 승인 | **이 WO에서 실행 안 함** |
| 운영 DB INSERT/UPDATE | **금지** |
| `_RUNTIME_EV_ALLOWLIST` 임의 확장 | **금지** |
| tai-admin PR #181 병합 | **HOLD** |
| Gate C 진입 | **BLOCKED** |

---

## 10. 다음 단계 (R1 기준 — R2에서 갱신)

```
R1 기준 다음 단계는 §11 R2 보정 결과로 대체된다.
```

---

## 11. R2 계약 보정 (WO-DOC260-DATE-GATE-B-CONTRACT-R2-CORRECTION-002)

**선행:** `GPT_GATE_B_CONTRACT_IV = PASS_WITH_GUARDS` (2026-10-30)  
**범위:** 설계 계약 보정만. CODE_CHANGE = 0 / DB_CHANGE = 0 / DEPLOY = 0

---

### R2-01. `runtime_review_decision.review_status` 정합성 — **DB_VERIFY_REQUIRED**

#### 소스 정적 조사 결과

| 항목 | 소스 증거 | 위치 |
|------|-----------|------|
| `/bridge/evidence-approve` INSERT 컬럼 | `review_domain, source_entity_id, reviewer_id, review_action, review_reason, review_started_at, source_trace` — **`review_status` 미포함** | `review_bridge.py:290-293` |
| `/bridge/evidence-runtime-approve` 선행 체크 | `AND review_status = 'APPROVED'` — 이 컬럼이 `'APPROVED'`이어야 Step 5 통과 | `review_bridge.py:491` |
| `runtime_review_decision` CREATE TABLE | **로컬 마이그레이션 없음** — Supabase 클라우드 DB에서만 존재 | 전체 migrations/ 검색 결과 |
| DB DEFAULT 확인 | **소스로 증명 불가** — 마이그레이션 부재로 `review_status DEFAULT 'APPROVED'` 여부 미확인 | — |
| 테스트 `RT-T06B` | `prior_approve_decision=False`로 `review_status=APPROVED` 결과 없으면 409 차단 확인 | `test_evidence_runtime_approve.py:354-359` |

#### 결론 (R2-01)

- `evidence-approve` INSERT에 `review_status` 미포함 → DB DEFAULT 또는 Trigger에 의존
- DB DDL이 로컬에 없어 DEFAULT 값을 정적으로 확인 불가
- `review_status = 'APPROVED'` DEFAULT가 없으면 INSERT 후 `evidence-runtime-approve` Step 5에서 409 발생
- **분류: DB READ-ONLY 검증 필요** — 운영 DB에서 `runtime_review_decision` 스키마 조회 전 이 경로를 안전하다고 단정할 수 없음

```sql
-- DB READ-ONLY 확인 쿼리 (실행 불가 — DB 접근 승인 필요)
SELECT column_name, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'runtime_review_decision'
  AND column_name = 'review_status';
```

> **임의 구현 금지.** DB 접근 승인 후 위 쿼리 실행 결과로 판정.

---

### R2-02. 409 처리 계약 보정

#### R1 계약의 문제점

R1 §6.3에서 409를 "멱등 성공"으로 기술했다. GPT IV 지적이 맞다:

- 409는 "이미 처리됨" 응답이지, 멱등 성공이 아니다
- 특히 승인 계약에서 409는 반드시 **현재 상태 검증 후** 처리해야 한다

#### R2 보정 계약

**`/bridge/evidence-approve` 409 처리 (efc 승인):**

| 409 시나리오 | 발생 조건 | 처리 |
|-------------|-----------|------|
| 중복 APPROVE decision 존재 | `runtime_review_decision` 이미 APPROVE 기록 | 현재 `efc.status` 확인 → APPROVED_BY_HUMAN이면 **SKIP (이미 완료)** |
| `efc.status` UPDATE 실패 | 동시 수정 (rowcount ≠ 1) | **FAIL — 재시도 경로 이관** |

**`/bridge/evidence-runtime-approve` 409 처리 (ref 승인):**

| 409 시나리오 | 발생 조건 | 처리 |
|-------------|-----------|------|
| Step 5: 선행 APPROVE decision 없음 | `review_status = 'APPROVED'` 행 없음 | **FAIL — R2-01 DB 검증 선행** |
| Step 8: 중복 RUNTIME_EVIDENCE_APPROVE | 이미 이 ref에 runtime approve 기록 | 현재 `ref.status` 확인 → APPROVED_BY_HUMAN이면 **SKIP** |
| Step 10: UPDATE 실패 | 동시 수정 | **FAIL — 재시도 경로 이관** |

**전체 승인 과정 비원자성 명시:**

```
Step 2 (efc 승인)와 Step 3 (ref 승인)은 각각 독립 트랜잭션.
중간 실패(Step 2 완료, Step 3 실패) 상태가 가능하다.

재개 규칙:
  - efc.status = APPROVED_BY_HUMAN + ref.status = CANDIDATE → Step 3만 재시도
  - efc.status = CANDIDATE → Step 2부터 재시작
  - 양쪽 APPROVED_BY_HUMAN → 완료로 집계 (재시도 불필요)
```

---

### R2-03. LEG 승인 연결 계약

#### 현재 승인 API의 법령 검증 부재

`/bridge/evidence-approve`는 **승인자 역할·권한만 검증**하고, 해당 evidence의 법령 SoT 승인 여부를 조회하지 않는다.

#### R2 계약 정의

Gate B 승인 시퀀스에 **LEG 사전 검증 단계**를 명시한다:

```
Step 0 (LEG 사전 검증 — 서버 외부, Gate B 실행 전 계획 단계):
  Supabase governance RPC 경유 조회:
    → 조회 대상: 45cm-prj-db / governance 스키마
    → 확인 항목:
        A. 법령 참조 존재 여부 (law_ref NULL 여부 — §4.1 기준 15건 NULL)
        B. 법령 승인 완료 여부 (LEG status = APPROVED)
    → 미충족 → SKIP 목록으로 분류 (승인 실행 대상 제외)
    → 충족 → 승인 실행 대상 목록 확정
```

#### 미확정 사항 (DB 접근 승인 전 보류)

| 항목 | 상태 |
|------|------|
| governance RPC 명칭 | **미확인 — 실제 정본에서 확인 필요** |
| evidence별 law_ref 컬럼 위치 | **미확인** — `evidence_field_candidate` 로컬 스키마에 없음 (§R2-04 참조) |
| LEG 응답 상태 코드 | **미확인** — `governance` 스키마 조회 전 추정 금지 |
| 법령 근거 존재 vs. 법령 승인 완료 | 서로 다른 상태 — 둘 다 확인 필요 |

> **임의 추정 금지.** governance RPC 접근 승인 후 실제 정본 기준으로 확정.

---

### R2-04. READ-ONLY SQL 보정

#### R1 SQL의 문제점

1. `evidence_field_candidate`에 `law_ref` 컬럼이 없음 (로컬 스키마 기준 — 마이그레이션 `20261026110000`에 없음)
2. 104건 COUNT 기준 불명확 (`COUNT(*)` vs `COUNT(DISTINCT ref.id)`)
3. SQL-2에서 `law_ref` 컬럼 존재 확인 조건이 주석으로 처리됨
4. DATA_SEMANTIC_GAP 13건 + law_ref NULL 15건 중복 여부 불명확

#### R2 보정 SQL

```sql
-- [R2-SQL-1] DATE evidence 현황 (form_schema_id 조건 추가)
SELECT
  efc.id              AS efc_id,
  efc.status          AS efc_status,
  ref.id              AS ref_id,
  ref.status          AS ref_status,
  ref.evidence_family,
  ref.upload_type,
  rf.id               AS runtime_field_id,
  rf.input_type,
  rf.form_schema_id   AS rf_form_schema_id,
  rfs.id              AS schema_id,
  rfs.status          AS schema_status,
  rfs.form_name
FROM evidence_field_candidate efc
JOIN runtime_evidence_field ref
  ON ref.evidence_candidate_id = efc.id
JOIN runtime_field rf
  ON rf.field_candidate_id = efc.field_candidate_id
 AND rf.form_schema_id = ref.form_schema_id   -- 동일 form_schema_id 조건 추가 (R2-04)
JOIN runtime_form_schema rfs ON rfs.id = ref.form_schema_id
WHERE ref.evidence_family = 'DATE'
ORDER BY efc.id;

-- [R2-SQL-2] DATE evidence 집계 (기준 명확화)
SELECT
  COUNT(DISTINCT ref.id)  AS date_ref_count,
  COUNT(DISTINCT efc.id)  AS date_efc_count
FROM runtime_evidence_field ref
JOIN evidence_field_candidate efc ON efc.id = ref.evidence_candidate_id
WHERE ref.evidence_family = 'DATE';

-- [R2-SQL-3] law_ref 컬럼 존재 확인 (실행 전 스키마 검증)
-- law_ref가 evidence_field_candidate에 없으면 다른 경로(governance RPC)로 확인해야 함
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('evidence_field_candidate', 'runtime_evidence_field')
  AND column_name LIKE '%law%'
ORDER BY table_name, column_name;

-- [R2-SQL-4] schema_status 분포
SELECT rfs.status, COUNT(*) AS cnt
FROM runtime_form_schema rfs
JOIN runtime_evidence_field ref ON ref.form_schema_id = rfs.id
WHERE ref.evidence_family = 'DATE'
GROUP BY rfs.status;
```

> 모든 SQL은 READ-ONLY. DB 접근 승인 전 실행 불가.

#### DATA_SEMANTIC_GAP vs law_ref NULL 중복 여부

두 분류는 다른 기준에서 도출됐을 수 있다:
- law_ref NULL 15건: `evidence_field_candidate` 또는 연결 테이블의 law_ref 컬럼 NULL
- DATA_SEMANTIC_GAP 13건: GPT IV R1-01 기준 의미 분류 미확정

교집합 가능성 있음 — DB 조회 전 교집합/차집합 확정 불가. R2-SQL-3 이후 재분류.

---

### R2-05. G-B01 경로 A 계약 고정안 (Owner 권고안)

**GPT IV R1 권고: 경로 A (기존 API 확장)**을 Owner 권고안으로 확정한다.

#### 경로 A 계약

```
대상 API: POST /bridge/evidence-runtime-approve
위치: routers/review_bridge.py

변경 범위 (G-B01 해소):
  현재 [3] 검증 (라인 449-461):
    if ev["evidence_family"] != "ATTACHMENT": → 422
    if ev["upload_type"] != "attachment": → 422

  R2 변경안:
    ATTACHMENT 분기 (기존 유지):
      if ev["evidence_family"] == "ATTACHMENT":
        if ev["upload_type"] != "attachment": → 422  # 교차조합 차단
        if rf["input_type"] != "file": → 422          # [7] 기존 유지
        → ATTACHMENT 처리 경로 계속

    DATE 분기 (신규):
      elif ev["evidence_family"] == "DATE":
        if ev["upload_type"] != "timestamp_auto": → 422  # 교차조합 차단
        if rf["input_type"] != "date": → 422             # [7] DATE 전용
        → DATE 처리 경로 계속

    기타 family → 422 (기존 동작 유지)

보존 계약 (변경 없음):
  - 역할·권한 검증 ([1]) 유지
  - runtime_review_authority 검증 ([1b]) 유지
  - runtime_evidence_field.status = CANDIDATE 전제 ([3]) 유지
  - evidence_field_candidate.status = APPROVED_BY_HUMAN 선행 체크 ([4]) 유지
  - review_status = 'APPROVED' 선행 decision 존재 확인 ([5]) 유지
  - runtime_form_schema.status = APPROVED_FOR_RUNTIME_USE ([6]) 유지
  - form_schema_id 일치 field connection 검증 ([7]) 유지
  - 중복 RUNTIME_EVIDENCE_APPROVE decision 차단 ([8]) 유지
  - runtime_review_decision INSERT ([9]) 유지
  - runtime_evidence_field.status UPDATE ([10]) 유지
  - 감사 로그 _audit() 유지

_RUNTIME_EV_ALLOWLIST 계약:
  - 기존 2건 (fd3f3c99, e1793f5c) 유지
  - 104건 일괄 등록 금지
  - 법령 검증된 대상별 별도 Owner Gate로 범위 확대
  - DATE family 허용 = Allowlist 확장 아님
    (family 분기 추가는 API 계약 확장 / Allowlist는 특정 ID 단위 보안 게이트)
```

#### Allowlist vs. family 분기 구분 (중요)

> `_RUNTIME_EV_ALLOWLIST`는 **특정 evidence ID 단위** Owner 보안 게이트다.  
> `evidence_family = 'DATE'` 분기 추가는 **API 계약 확장**으로 별개 개념이다.  
> 경로 A 구현 시 DATE 전용 ID Allowlist를 별도로 정의하거나,  
> 기존 Allowlist에 DATE 대상 ID를 Owner 승인 후 추가해야 한다.  
> **둘 다 Owner 별도 승인 Gate 필요.**

---

## 12. R2 후 다음 단계 (→ WP-G-B02 완료로 갱신)

```
R2 산출물:
  - §11 R2-01~R2-05 계약 보정 완료
  - G-B01 경로 A 계약 고정 → Owner 결정 Gate로 이관

WP-G-B01: CLOSED_FINAL (PR#742 1ce3c559 MERGED 2026-10-30)

WP-G-B02: COMPLETE (2026-10-30) — §13 참조
  - R2-01 review_status: DB_TRIGGER_HANDLES_IT (RESOLVED)
  - law_ref: evidence_field_candidate.law_ref 컬럼 확인 (RESOLVED)
  - DATE evidence: 112건 전부 CANDIDATE / prior decision 0건

현재 차단 사유 (WP-G-B05 실행 불가):
  1. efc_status = CANDIDATE (112건 전부) — 선행 EFC 승인 필요
  2. prior APPROVE decision = 0건 — 선행 EVIDENCE APPROVE decision 없음
  3. _RUNTIME_EV_ALLOWLIST 미등록 — 112건 ID 미포함
  4. law_ref NULL 23건 — LEG 연결 미확보

다음 Gate:
  → WP-G-B03: LEG SoT 분류 (governance RPC 접근 승인 필요)
  → WP-G-B04: Allowlist 확장 (WP-G-B02/03 완료 후 Owner 승인)
  → WP-G-B05: 실제 승인 실행 (Owner 별도 승인 Gate)
```

---

## 13. WP-G-B02 DB 조사 결과 (2026-10-30)

**조사 DB:** Supabase `vwlahtguyggrhvslabax` (taieng, ap-northeast-2, ACTIVE_HEALTHY)  
**조사 유형:** READ-ONLY SELECT  
**Goal:** `G-mvuwvdxl-00d5cc`

### 13.1 R2-01: runtime_review_decision.review_status

| 항목 | 결과 |
|------|------|
| `review_status` DEFAULT | `'PENDING'::text` |
| BEFORE INSERT 트리거 | `trg_validate_review_authority` → `fn_validate_review_authority()` |
| 트리거 핵심 동작 | `review_action = 'APPROVE'` → `review_status = 'APPROVED'` 자동 설정 |

**결론: DB_TRIGGER_HANDLES_IT (RESOLVED)**  
`evidence-approve` INSERT에 `review_status`를 포함하지 않아도 트리거가 자동 설정한다.  
R2-01 우려 사항 해소 — 소스 코드 수정 불필요.

#### 트리거 함수 요약 (`fn_validate_review_authority`)

```
1. review_domain에 ACTIVE authority 존재 확인 → 없으면 RAISE EXCEPTION
2. 동일 entity에 APPROVED/REJECTED 중복 decision 차단 → 중복이면 RAISE EXCEPTION
3. review_action 기반 review_status 자동 설정:
   APPROVE → review_status = 'APPROVED', review_completed_at = now()
   REJECT  → review_status = 'REJECTED', review_completed_at = now()
   ESCALATE     → 'ESCALATED'
   REOPEN       → 'REOPENED'
   RETURN_FOR_EDIT → 'PENDING'
```

### 13.2 R2-SQL-2: DATE evidence 현황

| 항목 | 값 |
|------|-----|
| 총 건수 | **112건** (계약 기준 104건 → +8건) |
| status | 112건 전부 `CANDIDATE` |
| upload_type | 112건 전부 `timestamp_auto` |
| efc_status | 112건 전부 `CANDIDATE` (APPROVED_BY_HUMAN = 0건) |
| form_schema_id 연결 | 112건 전부 연결 (schema_missing = 0) |
| evidence_candidate_id | 112건 전부 연결 (efc_null = 0) |
| law_ref NULL | **23건** (89건은 채워짐) |
| prior APPROVE decision | **0건** (112건 전부 없음) |

> 계약 기준값 수정: 104건 → **112건**  
> law_ref NULL 기준값 수정: 15건 → **23건**

### 13.3 R2-SQL-3: law_ref 컬럼 위치

```
law_ref 컬럼 존재 테이블 (public 스키마):
  - evidence_field_candidate.law_ref  ← DATE evidence 기준 핵심 테이블
  - field_candidate.law_ref
  - checklist_item_candidate.law_ref
  - document_forms.law_ref
```

**결론:** `evidence_field_candidate.law_ref` 컬럼 확인 (RESOLVED)  
로컬 마이그레이션 부재로 확인 불가였던 R2-04 미확정 항목 해소.

### 13.4 R2-SQL-4: 연결 무결성 및 차단 사유

**WP-G-B05 실행 전 해소 필요 항목:**

| 차단 사유 | 건수 | 해소 경로 |
|-----------|------|-----------|
| efc_status = CANDIDATE | 112건 전부 | WP-G-B04: 선행 EFC 승인 필요 |
| prior APPROVE decision 없음 | 112건 전부 | 선행 EFC 승인 완료 후 자동 생성 |
| _RUNTIME_EV_ALLOWLIST 미등록 | 112건 전부 | WP-G-B04: Owner 승인 후 확장 |
| law_ref NULL | 23건 | WP-G-B03: LEG SoT 연결 후 재확인 |

> **DATA_SEMANTIC_GAP vs law_ref NULL 교집합:** 실측 기준으로 재분류.  
> law_ref NULL = 23건. DATA_SEMANTIC_GAP(GPT R1 분류 13건)과 직접 교집합 쿼리는  
> governance RPC 접근 후 확인 가능 (WP-G-B03 범위).

### 13.5 WP-G-B02 결론

| 항목 | 상태 |
|------|------|
| R2-01 review_status 정합성 | ✅ RESOLVED — 트리거 자동 처리 |
| DATE evidence 수 | ✅ 확인 — 112건 (수정) |
| law_ref 컬럼 위치 | ✅ RESOLVED — evidence_field_candidate.law_ref |
| 선행 승인 부재 | ⚠️ 확인 — 112건 전부 미승인 (WP-G-B03/04 필요) |
| WP-G-B05 실행 가능 여부 | ❌ BLOCKED — 4개 차단 사유 미해소 |

---

---

## 14. WP-G-B03 LEG READ-ONLY 조사 결과 (2026-10-30)

**WO:** WO-DOC260-DATE-GATE-B-WP-G-B03-LEG-READONLY-008  
**Owner Approval:** APPROVED (WP_G_B03_GOVERNANCE_RPC_READONLY = APPROVED)  
**Goal:** `G-mvuwvdxl-00d5cc`  
**CODE_CHANGE = 0 / DB_MUTATION = 0 / DEPLOY = 0**

---

### 14.1 STOP 조건 1 — governance SoT 불일치

**STOP 발동:** `45cm-prj-db` (`iapzwbysfzootqnldtan`) `governance` 스키마에 한국 법령 없음.

| 항목 | 결과 |
|------|------|
| governance items 총 수 | 408건 (CONSTITUTION 27 / CONTRACT 43 / GUIDE 42 / POLICY 202 / RULE 94) |
| governance items 내용 | 45CM 자체 개발 거버넌스 룰 (ACS-×, AI-×, R-× 등) |
| 한국 법령 데이터 | **없음** |
| governance RPC 호출 여부 | **중단** — 한국 법령 검증에 사용 불가 |

**실제 한국 법령 SoT:** `vwlahtguyggrhvslabax` (tai-api DB, taieng)  
테이블: `law_master`, `law_alias`, `law_article`, `legal_obligations` 등 66종  
이 DB는 WP-G-B02에서 이미 승인된 READ-ONLY 접근 범위 내.

---

### 14.2 B02 증거 재확인 (B02-01)

| 항목 | WP-G-B02 보고 | 재확인 결과 | 일치 |
|------|--------------|------------|------|
| DATE evidence 총 수 | 112건 | **112건** | ✅ |
| efc distinct count | 112건 | **112건** | ✅ |
| efc_status = CANDIDATE | 112건 | **112건** | ✅ |
| efc_status = APPROVED_BY_HUMAN | 0건 | **0건** | ✅ |
| law_ref = NULL | 23건 | **23건** | ✅ |
| prior APPROVE decision | 0건 | **0건** | ✅ |
| form_schema 연결 정상 | 112건 | **112건** | ✅ |

**B02 수치 전부 재확인 일치.**

---

### 14.3 B02-02 review_status Trigger 판정

**판정: `R2_01_RESOLVED`**

| 검증 항목 | 결과 |
|-----------|------|
| DEFAULT | `'PENDING'::text` — 트리거 없이 INSERT 시 PENDING 유지 |
| 트리거명 | `trg_validate_review_authority` (BEFORE INSERT) |
| 함수명 | `fn_validate_review_authority()` |
| 권한 검증 | `runtime_review_authority` WHERE `authority_status = 'ACTIVE'` → 없으면 RAISE EXCEPTION |
| 중복 차단 | 동일 entity + domain + action의 APPROVED/REJECTED 중복 → RAISE EXCEPTION |
| review_status 전환 조건 | `review_action = 'APPROVE'` → `review_status = 'APPROVED'` (자동, 명시적 action 필요) |
| 비공개 자동 승인 여부 | **없음** — authority 검증 + 명시적 APPROVE action 모두 필요 |

> 트리거는 구조적 안전장치이며 unguarded auto-approval이 아님.  
> `evidence-approve` INSERT에 `review_status` 미포함 → 트리거가 자동 설정 = 정합.

---

### 14.4 B02-03 DATA_SEMANTIC_GAP vs law_ref NULL 교집합

| 항목 | 결과 |
|------|------|
| 원본 DATA_SEMANTIC_GAP 13건 ID 집합 | **복원 불가** — GPT R1 분류 기준 문서에 없음 |
| 현재 law_ref NULL | **23건** (WP-G-B02 기준값 수정: 15→23) |
| 교집합 여부 | **UNVERIFIED** — 원본 ID 집합 없어 비교 불가 |

> 이후 분류: law_ref NULL = `LEG_REFERENCE_MISSING`, 법령 특정 불가 = `DATA_SEMANTIC_GAP`으로 재분류.

---

### 14.5 한국 법령 SoT 구조

**`law_master` (tai-api DB):**
- `law_key`, `law_name`, `law_name_short`, `law_status_code`, `is_active`
- `law_status_code = 'ACTIVE'` + `is_active = true` = 현행법 (승인 상태)

**`law_alias`:**
- 약칭 → 정식명 매핑 (15건 확인)
- 주요 매핑: `산안법` → `산업안전보건법`, `소방시설법` → `소방시설 설치 및 관리에 관한 법률`, `승강기안전관리법` → `승강기 안전관리법` 등

**`evidence_field_candidate` 연결 방식:**
- 직접 FK 없음 — `law_ref` text 필드만 존재
- 법령 매핑은 alias 경유 text 비교로만 가능

---

### 14.6 B03 112건 대상별 법령 분류

#### 최종 분류 요약

| 분류 | 건수 | 기준 |
|------|------|------|
| **PROVISIONAL_SOURCE_MATCH** | **72** | law_ref → law_master ACTIVE 확인 (정본 SoT 미확정 — §15 참조) |
| **DATA_SEMANTIC_GAP** | **17** | law_ref 있으나 법령 특정 불가 (시행규칙/법 번호만 기재) |
| **LEG_REFERENCE_MISSING** | **23** | law_ref = NULL |
| LEG_NOT_APPROVED | 0 | — |
| UNVERIFIED | 0 | — |
| **합계** | **112** | |

#### PROVISIONAL_SOURCE_MATCH 72건 — law_ref별 law_master 매핑

| law_ref | 건수 | law_master 정식명 | law_status_code |
|---------|------|------------------|-----------------|
| 건설기술진흥법 | 3 | 건설기술 진흥법 | ACTIVE |
| 건설기술진흥법 시행규칙 | 2 | 건설기술 진흥법 시행규칙 | ACTIVE |
| 건설기술진흥법 제62조 | 4 | 건설기술 진흥법 | ACTIVE |
| 건설기술진흥법 제62조의2제2항 | 1 | 건설기술 진흥법 | ACTIVE |
| 건설산업기본법 | 1 | 건설산업기본법 | ACTIVE |
| 고압가스안전관리법 | 2 | 고압가스 안전관리법 | ACTIVE |
| 고압가스안전관리법 제15조 | 2 | 고압가스 안전관리법 | ACTIVE |
| 고압가스안전관리법 제16조 | 1 | 고압가스 안전관리법 | ACTIVE |
| 산안법 시행규칙 제11조제2항, 제23조제2항 | 1 | 산업안전보건법 시행규칙 | ACTIVE |
| 산안법 시행규칙 제9조 | 1 | 산업안전보건법 시행규칙 | ACTIVE |
| 산안법 제125조 | 1 | 산업안전보건법 | ACTIVE |
| 산안법 제129조 | 2 | 산업안전보건법 | ACTIVE |
| 산안법 제24조 | 1 | 산업안전보건법 | ACTIVE |
| 산안법 제36조, 위험성평가 지침 | 1 | 산업안전보건법 ACTIVE (복합 참조: 지침 부분 미검증) | ACTIVE |
| 산안법 제42조 | 1 | 산업안전보건법 | ACTIVE |
| 산안법 제52조 | 2 | 산업안전보건법 | ACTIVE |
| 산안법 제54조 | 2 | 산업안전보건법 | ACTIVE |
| 산안법 제54조제2항 | 1 | 산업안전보건법 | ACTIVE |
| 산안법 제57조 | 1 | 산업안전보건법 | ACTIVE |
| 산안법 제62조 | 1 | 산업안전보건법 | ACTIVE |
| 산안법 제64조제1항 | 1 | 산업안전보건법 | ACTIVE |
| 석면안전관리법 시행규칙 제31조제2항, 별지 제17호서식 | 1 | 석면안전관리법 시행규칙 | ACTIVE |
| 소방시설법 제20조 | 2 | 소방시설 설치 및 관리에 관한 법률 | ACTIVE |
| 소방시설법 제25조 | 2 | 소방시설 설치 및 관리에 관한 법률 | ACTIVE |
| 승강기법 시행규칙 | 1 | 승강기 안전관리법 시행규칙 | ACTIVE |
| 승강기안전관리법 | 1 | 승강기 안전관리법 | ACTIVE |
| 승강기안전관리법 제13조 | 1 | 승강기 안전관리법 | ACTIVE |
| 승강기안전관리법 제32조 | 1 | 승강기 안전관리법 | ACTIVE |
| 승강기안전관리법 제48조 | 1 | 승강기 안전관리법 | ACTIVE |
| 시설물안전법 | 2 | 시설물의 안전 및 유지관리에 관한 특별법 | ACTIVE |
| 시설물안전법 제12조 | 1 | 시설물의 안전 및 유지관리에 관한 특별법 | ACTIVE |
| 시설물안전법 제6조 | 1 | 시설물의 안전 및 유지관리에 관한 특별법 | ACTIVE |
| 안전보건규칙 제619조 | 1 | 산업안전보건기준에 관한 규칙 | ACTIVE |
| 에너지이용합리화법 | 5 | 에너지이용 합리화법 | ACTIVE |
| 에너지이용합리화법 시행규칙 별지 | 2 | 에너지이용 합리화법 시행규칙 | ACTIVE |
| 위험물안전관리법 | 1 | 위험물안전관리법 | ACTIVE |
| 위험물안전관리법 시행규칙 | 1 | 위험물안전관리법 시행규칙 | ACTIVE |
| 위험물안전관리법 제13조 | 1 | 위험물안전관리법 | ACTIVE |
| 위험물안전관리법 제15조 | 2 | 위험물안전관리법 | ACTIVE |
| 위험물안전관리법 제18조 | 1 | 위험물안전관리법 | ACTIVE |
| 위험물안전관리법 제9조 | 1 | 위험물안전관리법 | ACTIVE |
| 전기안전관리법 | 2 | 전기안전관리법 | ACTIVE |
| 전기안전관리법 제17조 | 2 | 전기안전관리법 | ACTIVE |
| 중대재해법 시행령 제4조제7호 | 1 | 중대재해 처벌 등에 관한 법률 시행령 | ACTIVE |
| 중대재해법 제4조제1항제2호 | 1 | 중대재해 처벌 등에 관한 법률 | ACTIVE |
| 화학물질관리법 시행규칙 | 1 | 화학물질관리법 시행규칙 | ACTIVE |
| 화학물질관리법 제29조 | 1 | 화학물질관리법 | ACTIVE |
| 화학물질관리법 제31조 | 1 | 화학물질관리법 | ACTIVE |
| 화학물질관리법 제43조 | 1 | 화학물질관리법 | ACTIVE |
| 화학물질관리법 제44조 | 1 | 화학물질관리법 | ACTIVE |

> `PROVISIONAL_SOURCE_MATCH`은 정본 SoT 연결 증명 전 잠정 분류이며, evidence 승인 완료 아님.  
> GPT III STOP_SOT_MISMATCH → Owner SoT 결정 전까지 `LEG_VERIFIED_ELIGIBLE`로 사용 금지. §15 참조.

#### DATA_SEMANTIC_GAP 17건 — law_ref별

| law_ref | 건수 | 차단 사유 |
|---------|------|-----------|
| 시행규칙 제11조 | 8 | 어느 법의 시행규칙인지 특정 불가 |
| 시행규칙 제23조 | 4 | 어느 법의 시행규칙인지 특정 불가 |
| 법 제17조 | 1 | 법 명칭 없음 — 특정 불가 |
| 법 제29조 | 1 | 법 명칭 없음 — 특정 불가 |
| 별지 | 1 | 서식 부호만 기재 — 법령 특정 불가 |
| 시행규칙 별지 제30호서식 | 1 | 어느 법의 시행규칙인지 특정 불가 |
| 시행규칙 제16조 별지서식 | 1 | 어느 법의 시행규칙인지 특정 불가 |

#### LEG_REFERENCE_MISSING 23건 — 추가 차단 현황

| 추가 차단 | 건수 |
|-----------|------|
| schema_status = CANDIDATE (이중 차단) | **8건** |
| schema_status = APPROVED_FOR_RUNTIME_USE | 15건 |

---

### 14.7 WP-G-B03 §7 완료 보고

```
WO = WO-DOC260-DATE-GATE-B-WP-G-B03-LEG-READONLY-008

OWNER_APPROVAL = APPROVED
CODE_CHANGE = 0
DB_MUTATION = 0
DEPLOY = 0

B02_DATE_COUNT = 112 (재확인)
B02_EFC_DISTINCT_COUNT = 112 (재확인)
B02_LAW_REF_NULL_COUNT = 23 (재확인)
B02_CONNECTION_GAPS = 0 (schema/efc 연결 정상)
B02_PRIOR_APPROVE_COUNT = 0 (재확인)
B02_EVIDENCE_SOURCE = vwlahtguyggrhvslabax READ-ONLY SELECT
B02_TRIGGER_VERDICT = R2_01_RESOLVED

LEG_SOT_PROJECT = 45cm-prj-db (governance) → STOP: 한국 법령 없음
LEG_SOT_ACTUAL = vwlahtguyggrhvslabax (tai-api DB: law_master/law_alias)
GOVERNANCE_RPC_NAME = N/A (governance 스키마에 한국 법령 없음 — RPC 중단)
GOVERNANCE_RPC_READONLY_VERIFIED = N/A (STOP 조건 1 발동)
LEG_REFERENCE_MAPPING = law_alias 경유 text 비교 (직접 FK 없음)

PROVISIONAL_SOURCE_MATCH = 72
LEG_REFERENCE_MISSING = 23
LEG_NOT_APPROVED = 0
DATA_SEMANTIC_GAP = 17
UNVERIFIED = 0
CLASSIFICATION_TOTAL = 112

ALLOWLIST_CHANGED = NO
EFC_APPROVAL_EXECUTED = NO
RUNTIME_APPROVAL_EXECUTED = NO

NEXT_GATE = GPT_WP_G_B03_INDEPENDENT_VERIFICATION
```

---

### 14.8 WP-G-B04/05 진입 전 조건

| 분류 | 건수 | WP-G-B04 진입 가능 여부 |
|------|------|------------------------|
| PROVISIONAL_SOURCE_MATCH | 72 | 정본 SoT 확정 + Owner 승인 후 Allowlist 확장 후보 (§15) |
| DATA_SEMANTIC_GAP | 17 | law_ref 정정 후 재분류 필요 |
| LEG_REFERENCE_MISSING | 23 | law_ref 보완 필요 (8건 schema도 CANDIDATE) |

**전체 112건 공통 차단 사유 (미해소):**
1. efc_status = CANDIDATE (112건 전부) — 선행 EFC 승인 필요
2. prior APPROVE decision = 0건
3. `_RUNTIME_EV_ALLOWLIST` 미등록 (112건 전부)

---

---

## 15. WP-G-B03 SoT Reconciliation (WO-DOC260-WP-G-B03-SOT-RECONCILIATION-009)

**GPT III 판정:** `STOP_SOT_MISMATCH` (2026-10-30)  
**원인:** WP-G-B03에서 `45cm-prj-db/governance` 대신 `vwlahtguyggrhvslabax/law_master`를 사용한 분류가 비승인 SoT 대체 적용으로 판정됨.  
**CODE_CHANGE = 0 / DB_MUTATION = 0 / DEPLOY = 0**

---

### 15.1 S-01: Supabase 프로젝트 토폴로지 (전체)

| 프로젝트 ID | 이름 | 역할 | 상태 |
|------------|------|------|------|
| `vwlahtguyggrhvslabax` | taieng | tai-api 운영 DB (runtime evidence 승인 저장소) | ACTIVE_HEALTHY |
| `iapzwbysfzootqnldtan` | 45cm-prj-db | 45CM 거버넌스 items SoT (`governance` 스키마: Constitution/Contract/Policy/Rule/Guide 408건) | ACTIVE_HEALTHY |
| `wrfcedzgdrfupenzqhur` | leg-prod | 한국 법령 전용 DB (2026-06-11 생성) | ACTIVE_HEALTHY |
| `dtuzacscxjaqrcuxzosc` | 45cm-ops-db | 운영 지원 DB | ACTIVE_HEALTHY |
| `xfcjqahwzcncmtfosjwu` | 45cm-mkt-db | 마케팅 DB | ACTIVE_HEALTHY |
| `mlovagrawlaaffdgismb` | tai-chemical | 화학물질 관리 DB | ACTIVE_HEALTHY |

### 15.2 S-01: 4-Role SoT 맵핑 (현재 파악된 사실)

| 역할 | 현재 파악 | 정본 여부 |
|------|-----------|-----------|
| 한국 법령 원본 데이터 저장 | `wrfcedzgdrfupenzqhur` (leg-prod) — 한국 법령 전용 프로젝트, 2026-06-11 생성 | **미확정 — Owner 승인 필요** |
| 45CM 법령 거버넌스 SoT | `iapzwbysfzootqnldtan` (45cm-prj-db) `governance` 스키마 | **확정** (GOVERNANCE_SOURCE_OF_TRUTH.md 기준) |
| 법령 질의 API/RPC | `governance-api` (`api.gov.45cm.com`) — 현재 `45cm-prj-db` 경유 (단, 한국 법령은 governance 스키마 없음) | **법령 질의 경로 미확정** |
| runtime evidence 승인 저장소 | `vwlahtguyggrhvslabax` (taieng) — `runtime_review_decision` 등 | **확정** (WP-G-B02 기준) |

> **key finding:** `GOVERNANCE_SOURCE_OF_TRUTH.md`의 "법령" = **45CM 거버넌스 items 계층**이며 한국 법령(statute)이 아님.  
> `vwlahtguyggrhvslabax`에 `law_master`/`law_alias` 등이 있으나 법령 SoT로 승인된 이력 없음.  
> `leg-prod`(`wrfcedzgdrfupenzqhur`)가 한국 법령 전용 DB로 별도 존재 — Owner 확인 필요.

---

### 15.3 S-02: SoT 미선언 원칙

> **금지:** Owner 승인 없이 어떤 프로젝트도 한국 법령 SoT로 선언하지 않는다.  
> `vwlahtguyggrhvslabax/law_master` = 한국 법령 SoT 아님 (현재 판정).  
> `wrfcedzgdrfupenzqhur` (leg-prod) = 전용 DB 존재 확인, 역할 확정 = Owner Gate.

---

### 15.4 S-03: 72건 분류 재지정

| 원 분류 | 재지정 분류 | 적용 범위 |
|---------|-------------|-----------|
| `LEG_VERIFIED_ELIGIBLE` | **`PROVISIONAL_SOURCE_MATCH`** | §14.6 전체 (72건) |

**이유:** `vwlahtguyggrhvslabax/law_master` text 비교는 정본 SoT 연결 증명이 아님.  
law_ref → law_master ACTIVE 매핑은 **잠정 매핑**이며 법령 승인 근거 아님.

**사용 금지:** `LEG_VERIFIED_ELIGIBLE` 용어는 정본 SoT 연결 + Owner 승인 전까지 사용 불가.

---

### 15.5 §7 SoT Reconciliation 완료 보고

```
WO = WO-DOC260-WP-G-B03-SOT-RECONCILIATION-009

SOURCE_MAP_PATH = /Users/taiwangsim/dev-gov/docs/gov/_general/GUIDE_governance-source-of-truth_v1.md
                 (Last verified: 2026-06-08)

SUPABASE_TOPOLOGY_VERIFIED = YES (supabase_list_projects 실행, 2026-10-30)

LEGAL_DATA_STORAGE_CANDIDATE = wrfcedzgdrfupenzqhur (leg-prod, created 2026-06-11)
LEGAL_DATA_STORAGE_SOT_CONFIRMED = NO → OWNER_GATE_REQUIRED

LEGAL_GOVERNANCE_SOT = iapzwbysfzootqnldtan / 45cm-prj-db / governance 스키마
                      (45CM governance items: Constitution/Contract/Policy/Rule/Guide — 한국 법령 아님)

RUNTIME_EVIDENCE_STORAGE = vwlahtguyggrhvslabax (taieng)

PROVISIONAL_SOURCE_MATCH = 72
DATA_SEMANTIC_GAP = 17
LEG_REFERENCE_MISSING = 23

SOT_MISMATCH_RESOLUTION = OWNER_GATE_REQUIRED
  → Owner 결정 사항:
     Q1. 한국 법령 정본 SoT = leg-prod(wrfcedzgdrfupenzqhur) vs. taieng(vwlahtguyggrhvslabax)?
     Q2. vwlahtguyggrhvslabax/law_master와 wrfcedzgdrfupenzqhur 관계 (복사본/미러/독립)?
     Q3. 72건 PROVISIONAL_SOURCE_MATCH → LEG_VERIFIED_ELIGIBLE 승격 기준?

NEXT_GATE = OWNER_SOT_DECISION → WP-G-B04 재진입
```

---

### 15.6 WP-G-B04/05 진입 전 추가 차단 사유

| 차단 | 내용 |
|------|------|
| 한국 법령 SoT 미확정 | `leg-prod` vs. `taieng/law_master` Owner 결정 전 72건 LEG 승인 근거 불확실 |
| PROVISIONAL_SOURCE_MATCH 격상 미승인 | Owner Q3 결정 없이 72건 Allowlist 진입 불가 |

---

---

## 16. GPT R4 IV 결과 — GPT_WP_G_B03_SOT_IV (2026-10-31)

**판정:** `PASS_WITH_GUARDS`  
**WO:** WO-DOC260-WP-G-B03-SOT-RECONCILIATION-009

### 16.1 검증 결과

| 항목 | 판정 |
|------|------|
| R5 문서 보정 (PROVISIONAL_SOURCE_MATCH, §15) | **PASS** |
| WP-G-B02 핵심 집계 독립검증 (운영 DB 직접 조회) | **PASS** |
| 72건 잠정 재분류 | **PASS** |
| 한국 법령 SoT 확정 | **PENDING** |
| 112건 개별 Evidence UUID × 법령 참조 매핑표 | **PENDING** |
| WP-G-B04 Allowlist 확장 | **HOLD** |

### 16.2 WP-G-B02 독립검증 수치 대조

| 항목 | Claude 보고 | GPT 실측 | 일치 |
|------|------------|---------|------|
| DATE Runtime Evidence | 112 | 112 | ✅ |
| DISTINCT EFC | 112 | 112 | ✅ |
| Runtime CANDIDATE | 112 | 112 | ✅ |
| EFC CANDIDATE | 112 | 112 | ✅ |
| law_ref NULL | 23 | 23 | ✅ |
| 서식 연결 누락 | 0 | 0 | ✅ |
| 기존 APPROVE 결정 | 0 | 0 | ✅ |

### 16.3 Trigger 보완 사항

트리거 `fn_validate_review_authority`는 도메인에 ACTIVE 승인 권한 존재 여부만 확인하며, 개별 승인자 신원·역할까지 검사하지 않는다. **기존 API의 사용자별 역할·권한 검사(role_code, reviewer_id)는 반드시 유지해야 한다.**

### 16.4 미제출 증거 (PENDING)

| 항목 | 상태 |
|------|------|
| 112건 개별 Evidence UUID × 법령 참조 연결 원본 분류표 | **미제출** — 법령 참조 문자열별 집계만 존재 |
| GOVERNANCE_SOURCE_OF_TRUTH.md 원본 파일 SHA | **미제출** — 로컬 경로만 보고됨 |

### 16.5 Q1~Q3 Owner 결정 권고 (GPT)

| 결정 | GPT 권고 |
|------|---------|
| **Q1. 한국 법령 SoT** | `45cm-prj-db/governance` 정본 계약 유지. `leg-prod`는 후보로만 취급 — 정본 변경 선언 보류 |
| **Q2. taieng ↔ leg-prod 관계** | 데이터 계보·동기화 방향·원천 식별자·최종 수정 이력 READ-ONLY 비교 후 결정 |
| **Q3. 72건 승격 기준** | `law_master ACTIVE` 불충분. 정본 출처 + 조문·버전·시행일 + 의미 일치 + 승인 상태 + 서식 승인 상태 건별 확인 필요 |

> **복합 참조 주의:** `산안법 제36조, 위험성평가 지침`처럼 일부 근거만 확인된 항목은 전체 검증으로 처리 불가.

### 16.6 다음 단계 (GPT 권고)

> "정본을 즉시 바꾸는 것이 아니라 `leg-prod`와 `taieng`의 READ-ONLY 데이터 계보 비교를 별도 Owner Gate로 승인하는 것."

**Owner Gate 승인 요청 내용:**
- `leg-prod`(`wrfcedzgdrfupenzqhur`) + `taieng`(`vwlahtguyggrhvslabax`) READ-ONLY 데이터 계보 비교
- 목적: Q1~Q3 결정 근거 확보 + 112건 개별 매핑표 작성
- 결과물: Q1~Q3 결정 + 72건 건별 검증 매핑표 → WP-G-B04 Allowlist 확장 진입 근거

---

*R1 생성: Claude Code 2026-10-30 / PR #741 Squash Commit `99381050` MERGED 이후*  
*R2 보정: 2026-10-30 / GPT R2 IV PASS*  
*R3 업데이트: 2026-10-30 / WP-G-B01 CLOSED_FINAL (PR#742) + WP-G-B02 DB 조사 완료*  
*R4 업데이트: 2026-10-30 / WP-G-B03 LEG READ-ONLY 조사 완료*  
*R5 업데이트: 2026-10-30 / WP-G-B03 SOT Reconciliation (WO-009) — PROVISIONAL_SOURCE_MATCH 재지정 + §15 추가*  
*R6 업데이트: 2026-10-31 / GPT R4 SOT IV PASS_WITH_GUARDS + §16 추가 — Owner Gate 진입*
