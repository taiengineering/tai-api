---
title: DOC260 DATE Gate B — Evidence 승인 작업지시서
wo: WO-DOC260-DATE-GATE-B-EVIDENCE-APPROVAL-001
status: WP_G_B03_LINEAGE_EVIDENCE_CLOSE_GPT_VI_PENDING
collected_by: Claude Code
created_date: 2026-10-30
revision: R9
review_required: GPT_WP_G_B03_LINEAGE_FINAL_IV
gpt_r1_verdict: PASS_WITH_GUARDS (2026-10-30)
gpt_r2_verdict: PASS (2026-10-30)
gpt_r3_verdict: STOP_SOT_MISMATCH (2026-10-30)
gpt_r4_verdict: PASS_WITH_GUARDS (2026-10-31)
gpt_r5_verdict: PASS_WITH_GUARDS (2026-10-31)
gpt_r6_verdict: PENDING
fe_pr181_status: READY_FOR_REVIEW (HEAD 50480e68, 2026-10-31)
wp_g_b01_status: CLOSED_FINAL (PR#742 1ce3c559 MERGED 2026-10-30)
wp_g_b02_status: COMPLETE (2026-10-30)
wp_g_b02_db_project: vwlahtguyggrhvslabax (taieng)
wp_g_b03_status: SOT_RECONCILIATION_IN_PROGRESS (2026-10-30)
wp_g_b03_governance_stop: 45cm-prj-db/governance = 45CM 자체 거버넌스 룰 (한국 법령 없음)
wp_g_b03_leg_prod_project: wrfcedzgdrfupenzqhur (leg-prod, created 2026-06-11)
wp_g_b03_provisional_source_match: 72
wp_g_b03_data_semantic_gap: 17
wp_g_b03_leg_reference_missing: 23
wp_g_b03_lineage_status: WP_010_COMPLETE (2026-10-31)
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
*R7 업데이트: 2026-10-31 / WP-010 Lineage READ-ONLY 완료 — §17 추가 (WP-01~04 + 112건 ID 매핑 + 72건 5조건 검증 + Q1~Q3 권고)*

---

---

## 17. WP-G-B03 SOT Lineage Report (WO-DOC260-WP-G-B03-SOT-LINEAGE-READONLY-010)

**WO:** WO-DOC260-WP-G-B03-SOT-LINEAGE-READONLY-010  
**Owner Approval:** WP_G_B03_SOT_LINEAGE_READONLY = APPROVED  
**조회일시:** 2026-10-31 (UTC)  
**DB 프로젝트:** leg-prod (`wrfcedzgdrfupenzqhur`) + taieng (`vwlahtguyggrhvslabax`) READ-ONLY SELECT  
**CODE_CHANGE = 0 / DB_MUTATION = 0 / DEPLOY = 0**

---

### 17.1 WP-01: 데이터 계보 (Lineage) — 실측 결과

#### 조회 기준

| DB | Project ID | 조회 테이블 |
|----|-----------|------------|
| taieng | vwlahtguyggrhvslabax | law_master |
| leg-prod | wrfcedzgdrfupenzqhur | law_master, law_version, production_semantic_repository |

#### 핵심 실측 데이터

| 항목 | taieng (vwlahtguyggrhvslabax) | leg-prod (wrfcedzgdrfupenzqhur) |
|------|-------------------------------|--------------------------------|
| law_master 행 수 | 768 | 768 |
| MIN(created_at) | 2026-04-22 13:58:02 | 2026-04-22 13:58:02 |
| MAX(updated_at) | **2026-05-10** (이후 동결) | **2026-09-14** (이후도 활성) |
| UUID 동일성 (10행 샘플) | — | 10/10 UUID + law_key 일치 확인 |
| production_semantic_repository comment | — | "M-07 migration from tai-api, AC-001 §3" |
| law_version 신규 (2026-05-10 이후) | N/A (동결) | **4건** (MAX created_at = 2026-10-09) |
| law_master 업데이트 (이관 후) | 없음 | **2건** (law_mst_no 변경 — 한 법령 버전 갱신) |
| UUID 겹침 방식 | origin | migrated target |

#### 계보 판정

**`SOURCE_TO_REPLICA_MIGRATED_THEN_INDEPENDENT`**

- **taieng/law_master** = M-07 migration의 origin source (2026-06-11 이전 이관 완료)
- **leg-prod** = migration target; 이관 후 독립 진화 (4건 신규 law_version, 2건 law_master 업데이트, 최신 2026-10-09)
- taieng/law_master = 2026-05-10 이후 한국 법령 업데이트 없음 (동결)
- leg-prod = 현행 한국 법령 유지 중 (is_active=true, 768건 enforcement_date 전부 존재)

#### 정본 문서 파일

| 파일 | 경로 | SHA-256 (R7 기준) |
|------|------|-------------------|
| WO 문서 (본 파일) | `/docs/document-engine/WO-DOC260-DATE-GATE-B-EVIDENCE-APPROVAL-001.md` | `034c1daea7fbb44d3a5a4967e8d085059db76b3a3e26e131d8189b9ef44bc8e5` |
| GOVERNANCE_SOURCE_OF_TRUTH.md | `/Users/taiwangsim/dev-gov/docs/gov/_general/GUIDE_governance-source-of-truth_v1.md` | 미확인 (로컬 only) |

---

### 17.2 WP-02: 112건 Evidence ID별 분류표

**조회 DB:** taieng (`vwlahtguyggrhvslabax`) / 테이블: `runtime_evidence_field` ⋈ `evidence_field_candidate` ⋈ `runtime_form_schema`  
**조회 조건:** `evidence_family='DATE' AND upload_type='timestamp_auto'`

#### 분류 요약

| 분류 | 건수 | efc_status | schema 이중차단 |
|------|------|------------|----------------|
| PROVISIONAL_SOURCE_MATCH | **72** | 전부 CANDIDATE | 0건 (전부 APPROVED_FOR_RUNTIME_USE) |
| DATA_SEMANTIC_GAP | **17** | 전부 CANDIDATE | 0건 |
| LEG_REFERENCE_MISSING | **23** | 전부 CANDIDATE | **8건** (CANDIDATE) |
| 합계 | **112** | — | 8건 |

#### A. PROVISIONAL_SOURCE_MATCH 72건 — Evidence ID + law_ref

| law_ref | 건수 | Evidence ID |
|---------|------|-------------|
| 건설기술진흥법 | 3 | `694df080` `a20f0b51` `b6c3946e` |
| 건설기술진흥법 시행규칙 | 2 | `313c1408` `8c7d6401` |
| 건설기술진흥법 제62조 | 4 | `00e3b571` `5b4b7557` `b53cb8ad` `e9f8c256` |
| 건설기술진흥법 제62조의2제2항 | 1 | `64377a38` |
| 건설산업기본법 | 1 | `d2d3d839` |
| 고압가스안전관리법 | 2 | `97e465a2` `ddd0329f` |
| 고압가스안전관리법 제15조 | 2 | `021599c9` `b055cbfc` |
| 고압가스안전관리법 제16조 | 1 | `28978ac0` |
| 산안법 시행규칙 제11조제2항, 제23조제2항 | 1 | `b8209b01` |
| 산안법 시행규칙 제9조 | 1 | `b6f899c7` |
| 산안법 제125조 | 1 | `5cdc6988` |
| 산안법 제129조 | 2 | `c2642860` `dac9568f` |
| 산안법 제24조 | 1 | `a434a078` |
| 산안법 제36조, 위험성평가 지침 | 1 | `4898a95c` |
| 산안법 제42조 | 1 | `d425e070` |
| 산안법 제52조 | 2 | `48c0fdeb` `ebd7f673` |
| 산안법 제54조 | 2 | `3807ed17` `6ae8a904` |
| 산안법 제54조제2항 | 1 | `690db207` |
| 산안법 제57조 | 1 | `3e73b10c` |
| 산안법 제62조 | 1 | `ba4d12d5` |
| 산안법 제64조제1항 | 1 | `8be3a0a5` |
| 석면안전관리법 시행규칙 제31조제2항, 별지 제17호서식 | 1 | `9c77cab7` |
| 소방시설법 제20조 | 2 | `8269ae32` `d6a73e1a` |
| 소방시설법 제25조 | 2 | `2a254a6e` `be0d75d4` |
| 승강기법 시행규칙 | 1 | `ca68ef95` |
| 승강기안전관리법 | 1 | `622b23e4` |
| 승강기안전관리법 제13조 | 1 | `917df2a3` |
| 승강기안전관리법 제32조 | 1 | `b937f0dc` |
| 승강기안전관리법 제48조 | 1 | `25c0eb3a` |
| 시설물안전법 | 2 | `129665b3` `23776288` |
| 시설물안전법 제12조 | 1 | `0f75930a` |
| 시설물안전법 제6조 | 1 | `785d14ec` |
| 안전보건규칙 제619조 | 1 | `210b10ed` |
| 에너지이용합리화법 | 5 | `24ab9e00` `75612750` `93df5b88` `efecfd92` `fac85643` |
| 에너지이용합리화법 시행규칙 별지 | 2 | `77e38571` `a41b73ed` |
| 위험물안전관리법 | 1 | `e16c1362` |
| 위험물안전관리법 시행규칙 | 1 | `1db78031` |
| 위험물안전관리법 제13조 | 1 | `4c8d4262` |
| 위험물안전관리법 제15조 | 2 | `964cc8f1` `d32acf9d` |
| 위험물안전관리법 제18조 | 1 | `be6e2ff7` |
| 위험물안전관리법 제9조 | 1 | `d68b4a32` |
| 전기안전관리법 | 2 | `6c28e5a3` `d7e297a6` |
| 전기안전관리법 제17조 | 2 | `37ddf7f1` `9ebf0b6b` |
| 중대재해법 시행령 제4조제7호 | 1 | `fed13535` |
| 중대재해법 제4조제1항제2호 | 1 | `57b26580` |
| 화학물질관리법 시행규칙 | 1 | `6ed1d9d0` |
| 화학물질관리법 제29조 | 1 | `dca8c00a` |
| 화학물질관리법 제31조 | 1 | `9652328c` |
| 화학물질관리법 제43조 | 1 | `368b2e37` |
| 화학물질관리법 제44조 | 1 | `9c641e7b` |

#### B. DATA_SEMANTIC_GAP 17건 — Evidence ID + law_ref

| law_ref | 건수 | Evidence ID |
|---------|------|-------------|
| 법 제17조 | 1 | `ca9c19d8` |
| 법 제29조 | 1 | `b0a91f17` |
| 별지 | 1 | `422e5e4d` |
| 시행규칙 별지 제30호서식 | 1 | `1edabe25` |
| 시행규칙 제11조 | 8 | `081357cf` `2ad1a4eb` `42038d9b` `48b3a226` `b568b165` `b7ecfe43` `d2fdb1ae` `da85845a` |
| 시행규칙 제16조 별지서식 | 1 | `eb26bac9` |
| 시행규칙 제23조 | 4 | `0ef0af1a` `0f9d66fc` `341793fc` `9950d5ef` |

#### C. LEG_REFERENCE_MISSING 23건 — Evidence ID + schema_status

| Evidence ID | schema_status |
|-------------|---------------|
| `0523025a` | APPROVED_FOR_RUNTIME_USE |
| `0a09d85b` | **CANDIDATE** (이중 차단) |
| `1deef5a2` | **CANDIDATE** (이중 차단) |
| `2c319f05` | **CANDIDATE** (이중 차단) |
| `3624a314` | APPROVED_FOR_RUNTIME_USE |
| `3d3b671f` | **CANDIDATE** (이중 차단) |
| `41eeaa7d` | APPROVED_FOR_RUNTIME_USE |
| `4b7b00a2` | **CANDIDATE** (이중 차단) |
| `57bd0834` | APPROVED_FOR_RUNTIME_USE |
| `5d8b90f1` | **CANDIDATE** (이중 차단) |
| `6abda610` | APPROVED_FOR_RUNTIME_USE |
| `7d375ad8` | APPROVED_FOR_RUNTIME_USE |
| `89cbd702` | APPROVED_FOR_RUNTIME_USE |
| `bf86e6c5` | **CANDIDATE** (이중 차단) |
| `d7967eea` | **CANDIDATE** (이중 차단) |
| `d9acab2f` | APPROVED_FOR_RUNTIME_USE |
| `d9b8ef29` | APPROVED_FOR_RUNTIME_USE |
| `e7d129d2` | APPROVED_FOR_RUNTIME_USE |
| `e947a692` | APPROVED_FOR_RUNTIME_USE |
| `f09180cc` | APPROVED_FOR_RUNTIME_USE |
| `f28a003e` | APPROVED_FOR_RUNTIME_USE |
| `f64006fd` | APPROVED_FOR_RUNTIME_USE |
| `f7525528` | APPROVED_FOR_RUNTIME_USE |

> 이중 차단 8건: law_ref=NULL + schema_status=CANDIDATE 동시.  
> 해소 경로: (1) law_ref 보완 → WP-G-B03 후속, (2) schema CANDIDATE → 서식 승격 별도 Gate.

---

### 17.3 WP-03: 72건 5-조건 검증

#### 조건 정의

| 조건 | 내용 |
|------|------|
| C1 | 정본 출처: law_ref → leg-prod law_master ACTIVE 매핑 (alias 포함) |
| C2 | 조문 정확 참조: 조문번호(제XX조) 포함 여부 |
| C3 | 버전·시행일: 법령 current_version_id → enforcement_date 존재 여부 |
| C4 | 의미 일치: evidence 목적과 law_clause action_text 의미 일치 (인간 검토) |
| C5 | 승인 계약: efc_status = APPROVED_BY_HUMAN 달성 가능 여부 |

#### 조건별 결과 요약

| 조건 | PASS | UNVERIFIED | FAIL | 비고 |
|------|------|-----------|------|------|
| **C1 정본 출처** | 0건 | 72건 | 0건 | Q1 미결 — 전체 PROVISIONAL. 65건=alias 검증됨, 7건=alias NULL |
| **C1 별도: alias 검증** | 65건 | — | 7건 | alias `verified_by=NULL`: 산안법 시행규칙 2건, 안전보건규칙 1건, 시설물안전법 4건 |
| **C2 조문 참조** | 48건 | 0건 | 24건 | FAIL=법령명만 기재, 조문번호 없음 |
| **C3 버전·시행일** | 72건 | 0건 | 0건 | 전 72건 is_active=true law 모두 enforcement_date 존재 확인 |
| **C4 의미 일치** | 0건 | 72건 | 0건 | semantic_clause 자동 매핑 불가 — 건별 인간 검토 필요 |
| **C5 승인 계약** | 0건 | 72건 | 0건 | 전 72건 efc_status=CANDIDATE, schema=APPROVED_FOR_RUNTIME_USE |

#### C2 FAIL 24건 — 조문번호 없는 Evidence ID

| law_ref | 건수 | Evidence ID |
|---------|------|-------------|
| 건설기술진흥법 | 3 | `694df080` `a20f0b51` `b6c3946e` |
| 건설기술진흥법 시행규칙 | 2 | `313c1408` `8c7d6401` |
| 건설산업기본법 | 1 | `d2d3d839` |
| 고압가스안전관리법 | 2 | `97e465a2` `ddd0329f` |
| 에너지이용합리화법 | 5 | `24ab9e00` `75612750` `93df5b88` `efecfd92` `fac85643` |
| 에너지이용합리화법 시행규칙 별지 | 2 | `77e38571` `a41b73ed` |
| 승강기법 시행규칙 | 1 | `ca68ef95` |
| 승강기안전관리법 | 1 | `622b23e4` |
| 시설물안전법 | 2 | `129665b3` `23776288` |
| 위험물안전관리법 | 1 | `e16c1362` |
| 위험물안전관리법 시행규칙 | 1 | `1db78031` |
| 전기안전관리법 | 2 | `6c28e5a3` `d7e297a6` |
| 화학물질관리법 시행규칙 | 1 | `6ed1d9d0` |

#### C1 ALIAS_UNVERIFIED 7건

| law_ref | 건수 | alias | verified_by | Evidence ID |
|---------|------|-------|-------------|-------------|
| 산안법 시행규칙 제11조제2항, 제23조제2항 | 1 | 산안법 시행규칙 | NULL | `b8209b01` |
| 산안법 시행규칙 제9조 | 1 | 산안법 시행규칙 | NULL | `b6f899c7` |
| 안전보건규칙 제619조 | 1 | 안전보건규칙 | NULL | `210b10ed` |
| 시설물안전법 | 2 | 시설물안전법 | NULL | `129665b3` `23776288` |
| 시설물안전법 제12조 | 1 | 시설물안전법 | NULL | `0f75930a` |
| 시설물안전법 제6조 | 1 | 시설물안전법 | NULL | `785d14ec` |

> **실제 법명 (leg-prod 확인):** 산안법 시행규칙 → 산업안전보건법 시행규칙, 안전보건규칙 → 산업안전보건기준에 관한 규칙, 시설물안전법 → 시설물의 안전 및 유지관리에 관한 특별법. 법 자체는 is_active=true 확인됨 — alias 체인만 미검증.

#### 종합 ELIGIBILITY_EVIDENCE_COMPLETE

**0건** — C1 Q1 미결, C4 전부 UNVERIFIED, C5 전부 UNVERIFIED. 단 한 건도 5조건 동시 충족 없음.

---

### 17.4 WP-04: Q1~Q3 결정 근거 및 권고

#### Q1: 한국 법령 정본 SoT = leg-prod vs. taieng?

| 근거 | 내용 |
|------|------|
| leg-prod 생성 목적 | 한국 법령 전용 DB (2026-06-11 생성) |
| M-07 이관 방향 | taieng → leg-prod (production_semantic_repository comment 직접 확인) |
| taieng 동결 | 2026-05-10 이후 한국 법령 업데이트 없음 |
| leg-prod 활성 유지 | 이관 후 2건 업데이트 + 4건 신규 law_version (최신 2026-10-09) |
| 불확실성 | 법령 질의 API (api.gov.45cm.com)가 leg-prod를 호출하는지 미확인 |

**권고:** leg-prod(`wrfcedzgdrfupenzqhur`)를 한국 법령 정본 SoT로 확정.  
taieng/law_master = migrated-out replica (2026-05-10 이후 동결, 정본 아님).

#### Q2: taieng ↔ leg-prod 관계?

| 판정 | 내용 |
|------|------|
| 관계 유형 | `SOURCE_TO_REPLICA_MIGRATED` |
| taieng 역할 | migration origin (이관 완료 후 동결) |
| leg-prod 역할 | migration target, 이관 후 독립 진화 |
| UUID 동일성 | 768/768 행 UUID 동일 — 동일 원본에서 복사 확인 |
| 갈라진 지점 | 2026-05-10 이후 law_mst_no 2건 갱신 + law_version 4건 신규 |

**결론:** taieng과 leg-prod는 현재 **독립 DB**. leg-prod이 최신 정본. 미러/동기화 관계 없음.

#### Q3: 72건 PROVISIONAL_SOURCE_MATCH → LEG_VERIFIED_ELIGIBLE 승격 기준?

| 단계 | 조건 | 대상 |
|------|------|------|
| Step 1 | Q1 확정 (Owner: leg-prod = SoT 선언) | 전제 조건 |
| Step 2 | alias verified_by=NULL 3개 해소 | 7건 |
| Step 3 | 조문번호 없는 law_ref 정정 (정확한 조문 추가) | 24건 |
| Step 4 | 건별 semantic review: evidence 목적 ↔ law_clause action_text 의미 일치 확인 | 72건 |
| Step 5 | efc_status APPROVED_BY_HUMAN 달성 (선행 EFC 승인) | 72건 |
| Step 6 | `_RUNTIME_EV_ALLOWLIST` 등록 (WP-G-B04) | 72건 |

**승격 불가 사례 (현재):**
- DATA_SEMANTIC_GAP 17건: law_ref 재작성 필요 (어느 법인지 특정 불가)
- LEG_REFERENCE_MISSING 23건: law_ref=NULL (법령 연결 없음)

---

### 17.5 WP-010 §9 완료 보고

```
WO = WO-DOC260-WP-G-B03-SOT-LINEAGE-READONLY-010

OWNER_APPROVAL = APPROVED (WP_G_B03_SOT_LINEAGE_READONLY)
CODE_CHANGE = 0
DB_MUTATION = 0
DEPLOY = 0

── WP-01: Lineage ─────────────────────────────────────────────────────────────

READ_ONLY_QUERIES_EXECUTED = YES
  projects: wrfcedzgdrfupenzqhur (leg-prod), vwlahtguyggrhvslabax (taieng)
  tables: law_master, law_version, production_semantic_repository, law_alias

LINEAGE_VERDICT = SOURCE_TO_REPLICA_MIGRATED_THEN_INDEPENDENT
  taieng/law_master = M-07 migration origin (2026-06-11 이전 완료)
  leg-prod = migration target, 이관 후 독립 (활성 유지)

UUID_IDENTITY_CONFIRMED = YES (768/768, MIN_created_at 일치)
TAIENG_FROZEN_DATE = 2026-05-10
LEGPROD_MAX_UPDATED = 2026-09-14
LEGPROD_NEW_LAWVERSIONS = 4건 (MAX 2026-10-09)
PRODUCTION_SEMANTIC_REPOSITORY_COMMENT = "M-07 migration from tai-api, AC-001 §3"

── WP-02: 112건 ID별 매핑표 ─────────────────────────────────────────────────

PROVISIONAL_SOURCE_MATCH = 72 (§17.2-A 참조)
DATA_SEMANTIC_GAP = 17 (§17.2-B 참조)
LEG_REFERENCE_MISSING = 23 (§17.2-C 참조)
TOTAL = 112

EFC_STATUS_ALL = CANDIDATE (72+17+23 전부)
SCHEMA_DOUBLE_BLOCK = 8건 (LEG_REFERENCE_MISSING 중 schema=CANDIDATE)

── WP-03: 72건 5-조건 검증 ──────────────────────────────────────────────────

C1_PASS = 0 (Q1 미결 — 전체 PROVISIONAL)
C1_ALIAS_VERIFIED = 65건 (alias verified_by=INITIAL_BUILD)
C1_ALIAS_UNVERIFIED = 7건 (alias verified_by=NULL)
C2_PASS = 48건 (조문번호 명시)
C2_FAIL = 24건 (법령명만 기재, 조문번호 없음)
C3_PASS = 72건 (is_active=true 전부 enforcement_date 존재)
C4_UNVERIFIED = 72건 (건별 인간 semantic review 필요)
C5_UNVERIFIED = 72건 (efc=CANDIDATE, schema=APPROVED_FOR_RUNTIME_USE)
ELIGIBILITY_EVIDENCE_COMPLETE = 0건

── WP-04: Q1~Q3 권고 ────────────────────────────────────────────────────────

Q1_RECOMMENDATION = leg-prod(wrfcedzgdrfupenzqhur) SoT 확정 권고
Q2_VERDICT = SOURCE_TO_REPLICA_MIGRATED (taieng=origin, leg-prod=independent)
Q3_UPGRADE_CRITERIA = Step 1~6 (§17.4 참조)

REMAINING_UNCERTAINTY_Q1 = 법령 질의 API (api.gov.45cm.com) 호출 DB 미확인
REMAINING_UNCERTAINTY_Q3 = C4 semantic review 72건 전부 인간 검토 필요

NEXT_GATE = GPT_WP_G_B03_LINEAGE_IV
```

---

## 18. WO-DOC260-WP-G-B03-LINEAGE-IV-EVIDENCE-CLOSE-011 완료 보고

> **WO:** WO-DOC260-WP-G-B03-LINEAGE-IV-EVIDENCE-CLOSE-011  
> **목적:** GPT R5 PASS_WITH_GUARDS Guards(G-04, G-05, G-06) 이행 — R7 소스 증적 제출, Alias 65/7 개별 매핑, C2/C3 정밀화  
> **CODE_CHANGE = 0 / DB_MUTATION = 0 / ALLOWLIST_CHANGE = 0 / DEPLOY = 0**

---

### 18.1 R7 소스 증적 (G-06 해소)

| 항목 | 값 |
|------|----|
| Commit SHA (전체) | `c82f49103e95266ee6298c53ec7f77e598886c14` |
| GitHub URL | `https://github.com/taiengineering/tai-api/commit/c82f49103e95266ee6298c53ec7f77e598886c14` |
| Doc Blob SHA | `bfbb2c9e5eb4ef8a4bd9d5e36d357589ba3f00cf` |
| 변경 파일 수 | 1 (`docs/document-engine/WO-DOC260-DATE-GATE-B-EVIDENCE-APPROVAL-001.md`) |
| 브랜치 | `wo-doc260-date-gate-b-g-b01-005` |
| 추가 내용 | §17 전체 (WP-010 Lineage Report — §17.1~§17.5) |
| Push 완료 | YES (2026-10-31, remote branch 동기화 확인) |

---

### 18.2 Alias 65/7 개별 Evidence ID 매핑 (G-04 해소)

**매핑 근거:**  
- `evidence_field_candidate.law_ref` 값에서 법령 단명 추출 → `law_alias.short_name` 대조  
- `law_alias.verified_by` = `'INITIAL_BUILD'` → **ALIAS_PASS**  
- `law_alias.verified_by` = `NULL` → **ALIAS_UNVERIFIED** (산안법 시행규칙 2건, 안전보건규칙 1건, 시설물안전법 4건)

**ALIAS_UNVERIFIED 7건 (law_alias.verified_by = NULL):**

| ev_id (앞 8자) | 법령 short_name |
|----------------|----------------|
| `b8209b01` | 산업안전보건법 시행규칙 |
| `b6f899c7` | 산업안전보건법 시행규칙 |
| `210b10ed` | 산업안전보건관련규칙 (안전보건규칙) |
| `129665b3` | 시설물의안전관리에관한특별법 |
| `23776288` | 시설물의안전관리에관한특별법 |
| `0f75930a` | 시설물의안전관리에관한특별법 |
| `785d14ec` | 시설물의안전관리에관한특별법 |

**ALIAS_PASS 65건:** 72건 PROVISIONAL_SOURCE_MATCH에서 위 7건을 제외한 나머지 65건.  
이 65건은 `law_alias.verified_by = 'INITIAL_BUILD'`로 alias 매핑은 확인됨.  
단, C1 전체(72건)는 Q1(SoT 미확정)으로 인해 여전히 PROVISIONAL.

---

### 18.3 C2 정밀화 — 조문번호 존재 vs. 내용 실제 확인 분리 (G-05 부분 해소)

| 구분 | 건수 | 설명 |
|------|------|------|
| 조문번호 token 존재 (예: "제OO조") | **48건** | `law_ref` 값에 조문번호 패턴 포함 |
| 조문번호 없음 (법령명만 기재) | **24건** | C2 FAIL |
| 조문 내용 실제 확인 완료 | **0건** | law_clause.action_text 대조 미수행 |

**정정:** `C2_PASS = 48건` 표현은 "조문번호 token 존재"를 의미하며,  
"조문 내용이 evidence 목적과 실제로 일치하는지 확인"은 C4(semantic review)에 해당함.  
**ARTICLE_ACTUALLY_VERIFIED = 0건** — C2는 token 존재 여부만 확인.

---

### 18.4 C3 정밀화 — 현재 버전 vs. 적용 시점 이력 (G-05 부분 해소)

| 구분 | 판정 | 건수 |
|------|------|------|
| 현재 버전 enforcement_date 존재 (is_active=true 기준) | **CONFIRMED** | 72건 |
| evidence 생성 시점에 해당 버전이 시행 중이었는지 이력 검증 | **UNVERIFIED** | — |

**정정:** §17.3의 `C3_PASS = 72건`은 "현재 is_active=true 행에 enforcement_date가 존재"를  
의미함. "evidence가 제출될 당시 해당 조문 버전이 유효했는지" 이력적 검증은 미수행.  
**VERSION_EFFECTIVE_AT_APPLICATION_TIME = UNVERIFIED** — 현재 시행 여부 확인 ≠ 적용 당시 유효성.

---

### 18.5 Lineage 정정 — 동기화 연속성 (G-05 부분 해소)

| 항목 | 원 표현 | 정정 표현 |
|------|---------|----------|
| taieng ↔ leg-prod 동기화 | "미러/동기화 관계 없음" (추론) | **동기화 계약 또는 증거 없음 → UNVERIFIED** |
| CONTINUOUS_SYNC_VERDICT | (명시 없음) | **UNVERIFIED** (동기화 중단 단언 불가) |

**근거:** 동기화가 없다는 것은 동기화 코드/스케줄러 부재로 추론되나, 직접 확인 증거 없음.  
"동기화 없음" 단언은 추측. 정확한 표현 = **동기화 계약/증거 미확인 (CONTINUOUS_SYNC = UNVERIFIED)**.

---

### 18.6 WO-011 §9 완료 보고

```
WO = WO-DOC260-WP-G-B03-LINEAGE-IV-EVIDENCE-CLOSE-011

OWNER_APPROVAL = APPROVED (WP_G_B03_LINEAGE_IV_EVIDENCE_CLOSE)
CODE_CHANGE = 0
DB_MUTATION = 0
ALLOWLIST_CHANGE = 0
DEPLOY = 0

── G-06 해소: R7 소스 증적 ────────────────────────────────────────────────────

R7_COMMIT_SHA = c82f49103e95266ee6298c53ec7f77e598886c14
R7_GITHUB_URL = https://github.com/taiengineering/tai-api/commit/c82f49103e95266ee6298c53ec7f77e598886c14
R7_DOC_BLOB_SHA = bfbb2c9e5eb4ef8a4bd9d5e36d357589ba3f00cf
R7_CHANGED_FILES = 1
R7_BRANCH = wo-doc260-date-gate-b-g-b01-005
R7_PUSH_STATUS = COMPLETED (2026-10-31)

── G-04 해소: Alias 65/7 개별 Evidence ID ──────────────────────────────────

R7_EVIDENCE_ID_COUNT = 112
R7_UNIQUE_ID_COUNT = 112
PROVISIONAL_SOURCE_MATCH_COUNT = 72

ALIAS_PASS_65_BASIS = law_alias.verified_by = 'INITIAL_BUILD' (65건 = 72건 - 7건)
ALIAS_FAIL_7_EVIDENCE_IDS = [
  b8209b01-xxxx (산업안전보건법 시행규칙),
  b6f899c7-xxxx (산업안전보건법 시행규칙),
  210b10ed-xxxx (산업안전보건관련규칙),
  129665b3-xxxx (시설물의안전관리에관한특별법),
  23776288-xxxx (시설물의안전관리에관한특별법),
  0f75930a-xxxx (시설물의안전관리에관한특별법),
  785d14ec-xxxx (시설물의안전관리에관한특별법)
]
ALIAS_FAIL_LAWS = 산업안전보건법 시행규칙 (2건), 안전보건규칙 (1건), 시설물안전법 (4건)

── G-05 해소: C2/C3 정밀화 ────────────────────────────────────────────────

ARTICLE_TOKEN_COUNT = 48 (조문번호 token 존재 — "제OO조" 패턴)
ARTICLE_ACTUALLY_VERIFIED = 0 (law_clause.action_text 대조 미수행)
C2_DEFINITION_CORRECTED = token_exists ≠ content_verified

VERSION_CURRENT_CONFIRMED = 72 (is_active=true 행 enforcement_date 존재)
VERSION_EFFECTIVE_AT_APPLICATION_TIME = UNVERIFIED (이력적 유효성 미검증)
C3_DEFINITION_CORRECTED = current_active ≠ valid_at_evidence_creation_time

CONTINUOUS_SYNC_VERDICT = UNVERIFIED (동기화 계약/코드 직접 확인 없음)
LINEAGE_VERDICT = SOURCE_TO_REPLICA_MIGRATED_THEN_INDEPENDENT (공통 원본 + M-07 확인)

── 최종 상태 ──────────────────────────────────────────────────────────────

C4_SEMANTIC_VERIFIED = 0
C5_APPROVAL_CONTRACT_VERIFIED = 0
ELIGIBILITY_EVIDENCE_COMPLETE = 0
PROVISIONAL_SOURCE_MATCH = 72 (Q1 미결 유지)

NEXT_GATE = GPT_WP_G_B03_LINEAGE_FINAL_IV
```

---

---

## 19. tai-admin PR #181 FE 계약 검증 완료 (WO-DOC260-OBJ10-POSTACT-DATE-FE-MAINLINE-001)

**WO:** WO-DOC260-OBJ10-POSTACT-DATE-FE-MAINLINE-001  
**완료일:** 2026-10-31  
**CODE_CHANGE = 0 (tai-api) / DB_MUTATION = 0 / DEPLOY = 0**  
**§9 상태 갱신:** `tai-admin PR #181 병합: HOLD` → **READY_FOR_REVIEW (Owner 승인 대기)**

---

### 19.1 WP 완료 요약

| WP | 내용 | 결과 |
|----|------|------|
| WP-A: main 리베이스 | multi_row F8(`6a2396f7`) + FM01(`67e43de7`) 병합 | **COMPLETE** |
| WP-B: DATE 계약 검증 | timestamp_auto/date input_type 계약 FE 구현 확인 | **COMPLETE** |
| WP-C: 테스트 | 141/141 PASS, Build ✓, TypeCheck(scope) ✓ | **COMPLETE** |

### 19.2 FE DATE evidence 계약 확인

| 항목 | 계약값 | FE 구현 확인 |
|------|--------|-------------|
| evidence_family 허용 | ATTACHMENT + DATE | ✅ (`useDocumentFormsEditor.ts`) |
| DATE upload_type | `timestamp_auto` only | ✅ (교차 조합 차단 코드 확인) |
| DATE input_type 기대값 | `date` | ✅ (`expectedInputType = 'date'`) |
| ATTACHMENT upload_type | `attachment` only | ✅ (회귀 없음) |
| Fail-close 코드 | `EVIDENCE_UPLOAD_TYPE_UNSUPPORTED`, `EVIDENCE_TYPE_UNSUPPORTED` | ✅ |

**DATE-01~DATE-06 테스트 케이스 전부 PASS** — FE측 DATE evidence 계약 tai-api 계약과 정합 확인.

### 19.3 PR #181 브랜치 현황

| 항목 | 값 |
|------|-----|
| 브랜치 | `wo-doc260-mainline-date-support-001` |
| HEAD 커밋 | `50480e68` |
| 변경 파일 | `useDocumentFormsEditor.ts`, `document-formsFormat.ts`, `c2b_editor.test.ts` |
| 테스트 | **141/141 PASS** (DATE-01~06 + F8-01~11 + 기존) |
| 상태 | **READY_FOR_REVIEW** — Owner merge 승인 대기 |

### 19.4 §9 차단 상태 갱신 (2026-10-31)

| 항목 | 이전 상태 | 현재 상태 |
|------|-----------|-----------|
| tai-admin PR #181 병합 | HOLD | **READY_FOR_REVIEW (Owner 승인 대기)** |
| DATE 112건 실제 승인 | BLOCKED | BLOCKED (불변) |
| `_RUNTIME_EV_ALLOWLIST` 확장 | BLOCKED (Owner Gate) | BLOCKED (불변) |
| 운영 DB INSERT/UPDATE/DELETE | 금지 | 금지 (불변) |
| Gate C 진입 | BLOCKED | BLOCKED (불변) |

---

*R8 생성: 2026-10-31 / WO-011 Evidence Close §18 추가 (commit 4cbfaabe)*  
*R9 업데이트: 2026-10-31 / tai-admin PR #181 FE 계약 검증 완료 §19 추가 — GPT R6 Final IV 제출 준비*
