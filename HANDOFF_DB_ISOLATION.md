# Handoff — Database Isolation (Phase 1–2 Complete)

> Date: 2026-05-24
> Status: Phase 2 완료. 논리적 boundary 설계 완료. Migration 미수행.

---

## 무엇을 했는가

DB cleanup이 아니라 **DB ownership classification + logical boundary design**을 수행했다.

코드/배포 정리 이후, DB 정리에 진입하기 전에
"무엇이 runtime canonical state인가"를 먼저 확정하는 단계.

### Phase 1 — Ownership Classification

3개 Supabase 프로젝트의 전체 테이블을 조사:

| DB | Tables | Non-empty | Empty |
|---|---|---|---|
| taieng (main) | 550 | 329 | 221 |
| 45cm-ops-db | 16 | 10 | 6 |
| 45cm-prj-db | 2 | 0 | 2 |
| **Total** | **568** | **339** | **229** |

각 테이블을 GitHub code search + CANONICAL_RUNTIME_BOUNDARY.md 기준으로
4개 category로 분류:

1. Runtime Canonical
2. Runtime Queue/State
3. Extraction/Stage
4. Historical/Unknown

모든 테이블의 cleanup allowed = **NO**.

### Phase 2 — Logical Boundary Separation

Phase 1 분류를 기반으로 6개 논리적 boundary를 설계:

| Logical Boundary | Count | Rows (approx) | Status |
|---|---|---|---|
| Runtime Canonical (1A-1F) | ~262 | ~1.2M | ⛔ ACTIVE |
| Extraction/Stage (2A-2H) | ~79 | ~2.4M | ⛔ PRESERVED |
| Historical/Audit (3A-3D) | ~35 | ~64K | ⛔ PRESERVED |
| Legacy/Contaminated (4) | 5 | ~4.4K | 🧊 FROZEN |
| Quarantine (5) | 97 | 0 | 🔍 UNCLASSIFIED |
| Unplaced non-empty | 37 | ~19K | 🔍 배치 필요 |

상세 boundary 설계: `docs/DB_RUNTIME_BOUNDARY_v1.md`

---

## 무엇을 하지 않았는가

- ❌ DROP TABLE — 하지 않음
- ❌ DELETE / TRUNCATE — 하지 않음
- ❌ ALTER TABLE — 하지 않음
- ❌ Schema 이동 (public → runtime 등) — 하지 않음
- ❌ FK / index / RLS 변경 — 하지 않음
- ❌ Migration 실행 — 하지 않음
- ❌ Runtime query 수정 — 하지 않음
- ❌ Services / routers 코드 변경 — 하지 않음

---

## 확정된 사실

### Canonical Runtime Path (변경 없음)

```
[HTTP Request]
  → routers/engine_legal.py
  → routers/compiler_core.py
  → services/legal_engine_svc.py
  → services/legal_runtime.py
  → services/diagnosis_service.py
  → services/runtime_evaluator_svc.py
  → [Supabase runtime tables]
  → [HTTP Response]
```

### 6개 Core Runtime Tables (변경 없음)

| Table | Readers | Writers |
|---|---|---|
| master_building_legal_rules | legal_runtime.py | law_db_insert.py, law_to_rules.py |
| facility_applicability | diagnosis_service.py | run_facility_applicability.py |
| task_candidate | diagnosis_service.py, runtime_evaluator_svc.py | run_task_candidate.py, compiler_core.py |
| schedule_candidate | diagnosis_service.py | run_schedule_candidate.py |
| penalty_obligation_relation | diagnosis_service.py | run_penalty_candidate.py, compiler_core.py |
| compliance_review_queue | diagnosis_service.py | run_compliance_package.py, compiler_core.py |

### Extraction Pipeline (변경 없음)

```
scripts/track_e_phase2_run.py (CLI only)
  → engine/pipeline.py
  → [stage_1_clauses, stage_2_elements, verification_log]
```

No API route. No scheduler. CLI-only.

---

## 다음 단계 (Phase 3 이후)

### 즉시 가능한 작업

1. **Quarantine 97개 테이블 코드 참조 전수 조사**
   - GitHub code search per table
   - 참조 없으면 → quarantine 확정
   - 참조 있으면 → 적절한 boundary로 이동

2. **Unplaced non-empty 37개 배치 확정**
   - 각 테이블의 reader/writer 식별
   - boundary 배치 결정

3. **Legacy contaminated 5개 인간 판단**
   - archive 이동 여부
   - 데이터 보존 필요성 확인

### 인간 승인 필요한 작업

4. **Schema 분리 실행** (Phase 3+)
   - public → runtime/extraction/audit/archive schema 분리
   - 모든 서비스 코드 쿼리 경로 동시 수정 필요
   - 단계적 마이그레이션 계획 수립 필요

5. **Empty table cleanup** (Phase 4+)
   - quarantine 조사 완료 후
   - 코드 참조 없는 empty table에 대해
   - DROP 전 반드시 백업 + 인간 승인

---

## 파일 목록

| File | Purpose |
|---|---|
| `HANDOFF_DB_ISOLATION.md` | 이 문서. Phase 1-2 핸드오프 |
| `docs/DB_RUNTIME_BOUNDARY_v1.md` | 568개 테이블 논리적 boundary 설계 |
| `docs/CANONICAL_RUNTIME_BOUNDARY.md` | 기존 canonical runtime path 문서 (변경 없음) |

---

## 핵심 원칙

```
DB는 "먼저 정리"하면 안 된다.
반드시: 분류 → ownership → freeze → archive → cleanup 순서.
현재 위치: ownership 확정, freeze 선언 완료.
```
