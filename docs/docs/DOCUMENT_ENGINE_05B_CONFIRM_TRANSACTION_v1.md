# WP-DOCUMENT-ARCH-05B — Confirm Transaction & Snapshot Seal 정의 문서 (v1)

- 상태: **진행 중** (B0A 배포 완료, B1 구현 + CORR-01 정책 교정 완료, PR/merge 대기)
- 기준 MAIN SHA: `8fdaeca44627bb3ecf76f1f4aa2f14a371039cc6`
- 대상 저장소: `taiengineering/tai-api`
- 대상 DB: Supabase `vwlahtguyggrhvslabax` (taieng)
- 관련 아키텍처 정본: `docs/docs/DOCUMENT_ENGINE_ARCHITECTURE_FINAL_v1.md`

이 문서는 05B 하위 작업(STEP 2 설계 · A1/A2 DDL · B0 조사 · B0A 정책 · B1 조사 ·
B1 구현 · B1-CORR-01 정책 교정)에서 확정된 계약과 실행 결과를 한곳에 모은 정의 문서다.
B1 구현은 이 문서의 계약을 재설계 없이 그대로 따른다.

> **정책 교정 이력 — B1-CORR-01 (Submitter-as-Confirmer)**
> 초기 B0A/B1 은 confirm 권한을 role allowlist(`001`/`011`)로 판정했다. 실제 업무 흐름과
> 맞지 않아 폐기하고, **"문서를 제출한 본인(`submitted_by`)이 그 문서를 Confirm 한다"** 로
> 정정했다. `role_code` 는 confirm 판정 기준이 아니다. 이 문서의 §2.1 · §3.4 · §4 · §5 ·
> §7 · §9 는 교정된 정책을 반영한다.

---

## 0. 목적

confirm(`REVIEW_PENDING → APPROVED_BY_HUMAN`)을 **단일 원자 트랜잭션**으로 수행하여,
확정 시점의 working state 를 불변 스냅샷으로 봉인한다. 봉인은 다음을 한 번에 만든다.

- `runtime_document_archive` 1행 (sealed snapshot, hash 포함)
- `runtime_document_approval` 1행 (snapshot_id 로 archive 를 가리킴)
- `runtime_document_data.status = APPROVED_BY_HUMAN` (seal)

세 가지가 전부 성공하거나 전부 롤백된다. 부분 상태(partial)를 남기지 않는다.

---

## 1. 하위 작업 진행 현황

| 단계 | 내용 | 상태 |
|---|---|---|
| STEP 1 | Confirm 트랜잭션 조사 | PASS / CLOSED |
| STEP 2 | Confirm 트랜잭션 상세 설계 | PASS / DESIGN FIXED |
| A1 | approval.snapshot_id DDL artifact (UP/DOWN/VALIDATION) | PASS / CLOSED |
| A1 dry-run | production transactional dry-run (BEGIN→UP→validation→ROLLBACK) | PASS (영구 mutation 0) |
| A2 | approval.snapshot_id production apply | PASS / CLOSED (LIVE) |
| B0 | Confirm Auth / Data Scope 조사 | PASS / CLOSED |
| B0A | Approval Permission Policy (순수 authz 모듈) | PASS / CLOSED (merged/deployed) |
| B1-0 | Atomic Confirm Pre-Implementation 조사 | PASS (드리프트 0) |
| B1-1 | Atomic Confirm 구현 + 테스트 | PASS / CODE DONE (branch) |
| **B1-CORR-01** | **Submitter-as-Confirmer 정책 교정** | **PASS / CODE DONE (branch)** |
| B1-2 | PR / REVIEW / MERGE | 대기 (다음 단계) |
| B1-3 | DEPLOY VERIFY | 미착수 |
| B1-4 (E2E) | CONTROLLED FIRST CONFIRM (별도 승인) | 미착수 |

---

## 2. 배포된 산출물

### 2.1 코드

merged to main (LIVE):

- `services/document_snapshot_integrity.py` — Q4. `compute_confirmed_snapshot_hash(**fields)`.
  SHA-256 canonical JSON, 10개 키 명시 allowlist, JSON-native only, FAIL-CLOSED.
- `services/document_schema_renderer.py` — 05A. `build_render_artifacts(*, document, schema, fields, checklists)`.
  결정적 렌더 → `{rendered_body, template_identity, source_trace_snapshot, evidence_manifest}`.

branch `wo-document-arch05b-b1-atomic-confirm` (merge 대기):

- `services/document_confirm_authz.py` — B0A + **CORR-01**.
  `authorize_confirm(*, current_user, document, actor_id=None, factory_company_id=None)`.
  순수 인가 정책 함수. DB/clock/network 미접촉.
  **CORR-01: `role_scope` 인자 제거. confirm 권한 = 제출자 identity(`submitted_by`).**
- `services/document_confirm_svc.py` — B1 + CORR-01.
  `confirm_document_atomic(doc_id, *, actor_id, comment, current_user)`.
  psycopg2 원자 트랜잭션. **CORR-01: `role_data_scope` 조회 제거.**
- `routers/document_engine_api.py` — B1 + CORR-01 wiring.
  status route 에 `Depends(get_current_user)`. APPROVED_BY_HUMAN → `confirm_document_atomic`.
  **CORR-01: SUBMITTED_FOR_REVIEW 도 `submitted_by` 를 인증 사용자로 강제(위조 차단).**

### 2.2 DB (A2 apply, LIVE)

- `runtime_document_approval.snapshot_id uuid NULL`
- FK `runtime_document_approval(snapshot_id) → runtime_document_archive(id) ON DELETE RESTRICT`
- index `idx_rda_snapshot_id (snapshot_id)`
- 금지(미적용): `snapshot_hash` 컬럼, `NOT NULL`, `APPROVE ⇒ snapshot_id` CHECK
  (CHECK 은 CODE 배포 후 별도 hardening WP 에서 VALIDATE 와 함께 추가)

---

## 3. 확정 계약 (재설계 금지)

### 3.1 트랜잭션 방식

- **psycopg2 direct transaction** (신규 RPC/DB 함수 없음). `db/direct_sql.py` 의 psycopg2
  관행(`_connect()` + `DATABASE_URL`, try/commit/except-rollback/finally-close)을 재사용한다.
- 단, 기존 함수는 단일 작업·개별 커밋 구조다. B1 은 **한 커넥션에서 여러 문을 실행하고
  마지막에 한 번만 commit** 하는 신규 함수를 둔다(기존 함수 재사용 아님).
- confirm 전용 함수를 **별도 파일** `services/document_confirm_svc.py` 에 둔다
  (`confirm_document_atomic(...)`). `change_status()` 를 비대하게 만들지 않는다.

### 3.2 동시성 · 락

- 대상 `runtime_document_data` 행을 `SELECT ... FOR UPDATE` 로 잠근다 (NOWAIT 미사용).
- render/hash/archive 는 **락 이후 값** 기준으로만 만든다. 락 전 렌더/조회 금지.
- 동시 confirm 시: TX1 락→커밋, TX2 대기 후 최신 status = APPROVED_BY_HUMAN 확인 → 409.

### 3.3 유효 전이

- `REVIEW_PENDING → APPROVED_BY_HUMAN` 만 confirm 대상.
- 전이 규칙 SoT = `runtime_state_transition_rule` (락 이후 같은 TX 에서 확인).

### 3.4 인증 · 신원 · Confirm 권한 (CORR-01 교정)

- confirm 주체 SoT = 인증된 `current_user.id` (`routers/auth.py` 의 `get_current_user`).
- `body.actor_id` 는 **신뢰하지 않는다**. 대조만: 없음→허용, 같음→허용, 다름→403.
- 저장되는 `confirmed_by` / `reviewer_id` / `reviewed_by` 는 전부 `current_user.id`.
- **Confirm 권한 = 제출자 identity (role 아님).**
  `document.submitted_by == current_user.id` 일 때만 confirm 가능.
  - `submitted_by` 가 NULL 이면 REVIEW_PENDING lifecycle 무결성 위반 → **409**.
  - `submitted_by != current_user.id` → **403** (제출자 아님).
  - `role_code`(001/011/012/013/014 …)는 confirm 판정에 **사용하지 않는다**.
    role allowlist(`APPROVE_ROLE_CODES`) · `WIDE_SCOPES` · `role_data_scope` 조회는 전부 제거됨.
- **소유 일치는 사용자의 실제 소속 값으로** 직접 확인한다(role tier 로 승인자 선정 안 함).
  - `user_company` 없음 → 403(fail-closed). `resolved_doc_company != user_company` → 404(존재 은닉).
  - 문서가 factory-level 이면 `user_factory == doc_factory` 필수. 불일치/부재 → 403/404.
- ownership consistency: `doc.company_id` 와 `factory→company` 충돌 시 봉인 불가(404).
  소유주 자체를 특정 못 하면 봉인 불가(404). 제출자가 본인이어도 corrupted ownership 은 봉인 금지.
- **ownership 판정은 반드시 락 이후 값으로** 한다. 락 전 PostgREST 조회 금지(TOCTOU).
- **제출(SUBMITTED_FOR_REVIEW) 시 `submitted_by` 무결성**: confirm 권한이 제출자에 묶이므로,
  제출 시점에 `submitted_by` 가 위조되면 안 된다. 라우터는 SUBMITTED_FOR_REVIEW 전이에서
  `submitted_by` 를 **인증 사용자로 강제**하고, `body.actor_id` 가 다르면 403 으로 막는다
  (`svc.change_status` 자체는 무수정, 라우터가 인증 actor 만 전달).

### 3.5 시각

- `SELECT clock_timestamp()` 를 락 이후 같은 TX 에서 **1회만** 읽는다.
- 그 값을 hash 입력 · `archive.confirmed_at` · `approval.reviewed_at` · `rdd.reviewed_at`
  에 **동일하게** 사용한다. Python now() 와 DB now() 혼용 금지, INSERT 마다 now() 호출 금지.

### 3.6 approval 링크

- `approval.snapshot_id = archive.id` 를 채운다.
- `approval.snapshot_hash` 는 두지 않는다. hash SoT 는 `runtime_document_archive` 하나.

### 3.7 `_approval()` / `_audit()` 경계

- APPROVE 경로는 기존 `_approval()`(`except Exception: pass`)을 **완전히 우회**한다.
  approval INSERT 는 원자 트랜잭션 안에서 직접 수행한다.
- REJECT · 기타 전이는 기존 `change_status()` 경로를 그대로 둔다(이번 범위 밖).
- `_audit()` 는 원자 트랜잭션 안에 넣지 않는다. COMMIT 성공 후 기존 best-effort `_audit()`
  를 1회 호출한다. audit 실패가 confirm 을 되돌리지 않는다.

---

## 4. 트랜잭션 순서 (FIXED, CORR-01 반영)

```
BEGIN
 1. SELECT runtime_document_data WHERE id=%s FOR UPDATE
 2. 없으면 404
 3. (CORR-01) role_data_scope 조회 없음. confirm 권한은 locked.submitted_by 로 판정.
 4. doc.factory_id 있으면 factories.company_id 조회 (같은 TX)
 5. authorize_confirm(current_user, locked doc, actor_id, factory_company_id)
      - submitted_by NULL → 409 / submitted_by != current_user.id → 403
      - ownership 불일치/불능 → 404 / user scope 부족 → 403
      DENY → ROLLBACK + 해당 HTTP status
 6. runtime_state_transition_rule 조회 (locked status → APPROVED_BY_HUMAN)
 7. status==REVIEW_PENDING + rule 허용 아니면 409
 8. reviewer/comment/version 검증
 9. runtime_form_schema 조회
10. runtime_field 조회
11. runtime_checklist_item 조회
12. build_render_artifacts()            (05A)
13. SELECT clock_timestamp()            (1회)
14. compute_confirmed_snapshot_hash()   (Q4)
15. INSERT runtime_document_archive RETURNING id
16. INSERT runtime_document_approval (snapshot_id=archive.id,
      reviewer_id=current_user.id, reviewed_at=clock)
17. UPDATE runtime_document_data (status=APPROVED_BY_HUMAN,
      reviewed_by=current_user.id, reviewed_at=clock, review_comment=comment)
      RETURNING *  — 행이 없으면 무결성 위반 → 500 (조용한 빈 커밋 방지)
18. COMMIT
어느 단계든 실패 → ROLLBACK → partial state 0
```

라우터 결합:

```
POST /document-engine/documents/{doc_id}/status
  current_user = Depends(get_current_user)      # routers.auth
  if body.to_status == "SUBMITTED_FOR_REVIEW":   # CORR-01: submitter 위조 차단
      actor = current_user.id
      if body.actor_id and body.actor_id != actor: 403
      svc.change_status(doc_id, to_status, actor, comment)
  elif body.to_status == "APPROVED_BY_HUMAN":
      document_confirm_svc.confirm_document_atomic(
          doc_id, actor_id=body.actor_id, comment=body.comment, current_user=current_user)
  else:
      기존 svc.change_status(...)
# APPROVE 전 PostgREST document 조회/ownership 확인 금지 (모두 락 이후)
```

---

## 5. HTTP 계약 (CORR-01 반영)

```
401  승인 요청에 토큰 없음 / invalid token / 인증 사용자 id 없음
403  body.actor_id != 인증 사용자 / 제출자 아님(submitted_by != current_user.id) /
     user scope 부족(같은 회사 내 · company/factory 부재)
404  문서 없음 / cross-company(존재 은닉) / 소유 회사 판정 불능 / factory mismatch
409  locked status != REVIEW_PENDING / 동시 승인에서 이미 승인됨 / document_version 충돌 /
     submitted_by NULL (REVIEW_PENDING lifecycle 무결성 위반)
422  review_comment 누락 / version invalid / SchemaRenderError / SnapshotCanonicalizationError
503  DB 연결 불가 / lock timeout / deadlock / transient DB error
500  분류되지 않은 서버 오류 / seal UPDATE 가 행을 반환하지 않음
```

서비스는 FastAPI 를 import 하지 않는다. 도메인 `ConfirmError(http_status, detail)` 를
raise 하고 라우터가 `HTTPException` 으로 변환한다.

---

## 6. archive INSERT 필수 컬럼 (실측)

NOT NULL 이며 default 없음 → B1 이 반드시 채운다:

```
runtime_document_id · runtime_values_snapshot · confirmed_at · confirmed_by
document_version · source_trace_snapshot · rendered_body · snapshot_hash · template_identity
```

생략 가능(default 존재): `id`(gen_random_uuid) · `evidence_links_snapshot`('[]') ·
`is_immutable`(true) · `snapshot_schema_version`(1) · `evidence_manifest`('[]').

봉인 트리거(LIVE): `runtime_document_data` = `trg_rdd_seal_guard`,
`runtime_document_archive` = `trg_rdarch_no_delete` · `trg_rdarch_no_update`.
UNIQUE(`runtime_document_id`, `document_version`) → 중복 confirm 은 409.

---

## 7. B1 테스트 (구현 완료, CORR-01 반영)

authz (`test_document_confirm_authz.py`, 23):

```
A1~A5  다양한 role(014/012/013/011/001) 본인 제출 → 모두 ALLOW (role 무관)
A6~A8  다른 사람이 제출 → 403 (role 무관)
A9     submitted_by NULL → 409
A10    actor spoof → 403
A11    cross-company → 404
A12    factory mismatch → 404
A13    company/factory metadata conflict → 404
A14    ownership unresolved → 404
A15    role_code None/임의값이라도 identity+ownership 정상이면 ALLOW
보강    401(인증 없음/id 없음) · 404(문서 없음) · 403(user company/factory 부재) ·
        company-level ALLOW · actor==user ALLOW
```

atomic svc (`test_document_confirm_svc.py`, 26):

```
1 정상 confirm (archive=1, approval=1, snapshot_id 연결, status=APPROVED_BY_HUMAN, audit 1회)
2 actor spoof 403 · 3 role 012 본인 제출 PASS(반전) · 4 role 011 PASS · 5 cross-company 404
6 ownership conflict 404 · 7 REVIEW_PENDING 아님 409 · 8 rule 없음 409 · 9 comment 없음 422
10 renderer 실패 rollback · 11 hash 실패 rollback · 12 archive insert 실패 rollback(500)
13 approval insert 실패 rollback · 14 rdd seal 실패 rollback · 15 duplicate version 409
16 stale second approval 409 · 17 timestamp 동일 · 18 snapshot_id=archive.id
19 confirmed_by/reviewer/reviewed_by=auth user · 20 기존 _approval() 미호출
B1~B5 submitter-as-confirmer (014/012 self PASS, admin+other submitter 403,
       submitted_by NULL 409, 4자 identity 동일성)
B6 (hardening) seal RETURNING None → 500 + rollback
```

router submit binding (`test_document_engine_status_auth.py`, 5):

```
R1 SUBMITTED_FOR_REVIEW actor 없음 → svc actor = current_user.id
R2 actor == current_user.id → svc actor = current_user.id
R3 actor != current_user.id → 403, svc.change_status 미호출
R4 APPROVED_BY_HUMAN → confirm_document_atomic 분기
R5 그 외 상태(REJECTED) → 기존 svc.change_status 경로 유지
```

회귀: Q4 24 · 05A 25 는 그대로 통과. 총 103/103 (local shim).
`get_current_user` 는 stub 으로 테스트하고 실제 Supabase Auth 호출은 하지 않는다.

---

## 8. FAST-PATH DOWN 경계 (중요)

현재 `archive rows = 0`, `snapshot-linked rows = 0` 인 동안 A1 의 FAST-PATH DOWN 은
계속 유효(OPEN)하다. **첫 실제 confirm 이 성공해 archive 1행이 생기는 순간부터**
FAST-PATH DOWN 은 CLOSED 로 전환된다.

따라서:

- B1 코드가 merge/deploy 되어도 **실제 APPROVED_BY_HUMAN 호출은 금지**.
- 배포 직후 검증은 startup · ImportError · 5xx · route 등록 · production SHA 까지만.
- 실제 첫 confirm 은 별도 승인(`WP-DOCUMENT-ARCH-05B-B1-E2E CONTROLLED FIRST CONFIRM`)
  후에만 수행한다. 현재 유일 문서가 DRAFT 이므로, E2E 시 문서를 REVIEW_PENDING 까지
  올린 뒤 수행한다. (제출자 정책상 그 문서의 `submitted_by` = confirm 수행자여야 한다.)

---

## 9. 후속 (05B 이후 예정)

- APPROVE ⇒ snapshot_id CHECK hardening (CODE 배포 후, VALIDATE 동반)
- 첫 archive 행 생성 후 FAST-PATH DOWN 폐쇄 처리
- render_pdf_gotenberg 재활성 · source_trace KNOWN 채움(fetcher 확장)
- api.taieng.co.kr CORS 실패 (05B 와 무관, 별건)
- 제출자 외 승인 위임이 필요해질 경우(관리자 대리 확정 등)의 정책 확장 WP
  (현재는 제출자 본인만 confirm — role allowlist 는 폐기됨)

---

## 부록 A. 기준 커밋

```
Q4  (document_snapshot_integrity.py)   merge 499fdd18 → main
05A (document_schema_renderer.py)      PR #192 → main bbcbbc07
B0A (document_confirm_authz.py)        PR #193 → main 8fdaeca4
05B 정의 문서                          main 24e81fb5
B1  (atomic confirm 구현)              branch wo-document-arch05b-b1-atomic-confirm
B1-CORR-01 (submitter-as-confirmer)    branch wo-document-arch05b-b1-atomic-confirm
A2  (approval.snapshot_id)             apply_migration wo_document_arch05b_a2_approval_snapshot_id
```

## 부록 B. 검증 한계 (반복)

- 실행 환경 네트워크 차단으로 `pytest`/`psql` 미설치. 테스트는 `pytest.raises` shim 으로
  전량 실행했고, SQL 은 스키마 대조 + guri execute_sql/apply_migration 실행으로 검증했다.
  표준 CI 에서 `pytest` 재확인을 권고한다.
- `/health` HTTP 직접 호출은 세션에서 불가. Railway startup-complete + 2xx + 5xx=0 으로
  간접 확인한다(배포 시).
