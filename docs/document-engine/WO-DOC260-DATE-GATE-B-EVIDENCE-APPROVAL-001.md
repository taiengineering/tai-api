---
title: DOC260 DATE Gate B — Evidence 승인 작업지시서
wo: WO-DOC260-DATE-GATE-B-EVIDENCE-APPROVAL-001
status: DRAFT_R2_PENDING_GPT_IV
collected_by: Claude Code
created_date: 2026-10-30
revision: R2
review_required: GPT_GATE_B_CONTRACT_R2_IV
gpt_r1_verdict: PASS_WITH_GUARDS (2026-10-30)
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

## 12. R2 후 다음 단계

```
R2 산출물:
  - §11 R2-01~R2-05 계약 보정 완료
  - 미확정 항목: R2-01(review_status DEFAULT), R2-03(governance RPC), R2-04(law_ref 컬럼)
  - G-B01 경로 A 계약 고정 → Owner 결정 Gate로 이관

GPT_GATE_B_CONTRACT_R2_IV 요청:
  - R2-01: review_status DB_VERIFY_REQUIRED 분류 타당성
  - R2-02: 409 비멱등 + 중간 실패 재개 규칙 안전성
  - R2-03: LEG 연결 계약 미확정 항목 처리
  - R2-04: SQL 보정 및 law_ref 컬럼 조회 전략
  - R2-05: 경로 A 계약 고정안 검토

GPT R2 IV PASS 후:
  → Owner: G-B01 경로 A 구현 승인
  → WP-G-B01: evidence-runtime-approve DATE 분기 추가 (Claude Code)
  → WP-G-B02: READ-ONLY DB 조사 (DB 접근 승인)
    - runtime_review_decision review_status DEFAULT 확인
    - evidence_field_candidate / runtime_evidence_field law_ref 컬럼 여부
    - DATE evidence 104건 현황 재확인
  → WP-G-B03/04: LEG 분류 + governance RPC 연결 + Allowlist 확장 (Owner 승인)
  → WP-G-B05: 실제 승인 실행 (Owner 별도 승인 Gate)
```

---

*R1 생성: Claude Code 2026-10-30 / PR #741 Squash Commit `99381050` MERGED 이후*  
*R2 보정: Claude Code 2026-10-30 / GPT_GATE_B_CONTRACT_IV = PASS_WITH_GUARDS 이후*
