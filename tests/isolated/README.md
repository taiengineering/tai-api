# Isolated Regression: B-W2B + B-W3B search_path Fix

WO: **WO-TAI-SEC-SEARCHPATH-REM97-ISOLATED-FIDELITY-R1-003**

## Purpose

격리 환경에서 B-W2B / B-W3B 대상 함수 5개에 대해
`ALTER FUNCTION ... SET search_path = pg_catalog, public, pg_temp` 적용 전후
동작 동등성을 검증한다.

프로덕션 DB 접근 없이 로컬 격리 컨테이너만 사용한다.

---

## Constraints

| 항목 | 값 |
|------|-----|
| PRODUCTION_DB_WRITE | 0 |
| SOURCE_MIGRATION_CHANGE | 0 |
| MAIN_CHANGE | 0 |
| EXACT_MIGRATION_EXECUTED | FALSE (로컬 OID ≠ 운영 OID) |
| PG_VERSION | 로컬 PG 15.19 / 운영 PG 17.6 |

---

## Container

```
docker run -d \
  --name rem97_isolated_test \
  -e POSTGRES_PASSWORD=test_pass \
  -e POSTGRES_DB=rem97_test \
  -p 55432:5432 \
  postgres:15-alpine
```

---

## Files

| 파일 | 역할 |
|------|------|
| `setup_isolated.sql` | 격리 스키마 구성: 테이블 + 함수(prosrc MD5 일치) + 트리거 |
| `run_regression.sql` | PHASE1(pre-ALTER) → ALTER → PHASE2(post-ALTER) 회귀 실행 |

---

## Run

```bash
# 1. 격리 컨테이너 스키마 초기화 (최초 또는 재실행 전)
PGPASSWORD=test_pass psql -h localhost -p 55432 -U postgres -d rem97_test \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 2. 스키마 구성 (MD5 + 트리거 검증 포함)
PGPASSWORD=test_pass psql -h localhost -p 55432 -U postgres -d rem97_test \
  -f tests/isolated/setup_isolated.sql

# 3. 회귀 실행
PGPASSWORD=test_pass psql -h localhost -p 55432 -U postgres -d rem97_test \
  -f tests/isolated/run_regression.sql
```

---

## Pass Criteria

```
FUNCTION_BODY_MD5_MATCH = 5/5
TRIGGER_DEFINITION_MATCH = 6/6
PHASE1 = 18/18 PASS
PHASE2 = 18/18 PASS
ERROR 0건
```

---

## Target Functions

### B-W2B (B05 / B07)

| 함수 | 운영 OID | 운영 MD5 | 트리거 |
|------|---------|---------|--------|
| `fn_validate_inspection_reviewer` | 69146 | `d11c6e83fc4105683304bfed9679ba47` | `trg_validate_inspection_reviewer` — BEFORE INSERT on `runtime_inspection_review` |
| `fn_validate_reviewer_not_assignee` | 68962 | `2b7fbd47bb00b04b5e52e5a177ba8e97` | `trg_validate_reviewer` — BEFORE INSERT on `runtime_work_order_review` |

### B-W3B (B12 / B13 / B14)

| 함수 | 운영 OID | 운영 MD5 | 트리거 |
|------|---------|---------|--------|
| `sync_construction_notification_time` | 18576 | `c69e276c1cd46e449f64b1ec145923fd` | `trg_sync_construction_notif_time` — AFTER UPDATE OF notification_time on `construction_sites` |
| `sync_construction_worker_to_registry` | 245046 | `8db8ee7d30d5484f0f573cde2234bce4` | `trg_sync_cw_registry_ins` — BEFORE INSERT on `construction_workers`<br>`trg_sync_cw_registry_upd` — BEFORE UPDATE OF worker_name, worker_phone, role_code, worker_type, subcontractor_id, is_active on `construction_workers` |
| `sync_factory_notification_time_to_cs` | 18577 | `9c8c095278619c15fd243c7da50c02db` | `trg_sync_factory_notif_time_to_cs` — AFTER UPDATE OF notification_time on `factories` |

---

## Scenarios

### B-W2B (7개)

| ID | 명칭 | 결과 |
|----|------|------|
| B2B-01 | SELF_REVIEW_BLOCK | PASS (PHASE1/2) |
| B2B-02 | APPROVE_UPDATES_SESSION | PASS (PHASE1/2) |
| B2B-03 | REJECT_UPDATES_SESSION | PASS (PHASE1/2) |
| B2B-04 | ASSIGNEE_REVIEW_BLOCK | PASS (PHASE1/2) |
| B2B-05 | WO_APPROVE_UPDATES_STATUS | PASS (PHASE1/2) |
| B2B-06 | TRANSACTION_ROLLBACK | PASS (PHASE1/2) |
| B2B-07 | ROLE_RLS_EQUIVALENCE | **ROLE_RLS_UNVERIFIED** (documented gap) |

### B-W3B (11개)

| ID | 명칭 | 결과 |
|----|------|------|
| B3B-01 | CONSTRUCTION_SYNC | PASS (PHASE1/2) |
| B3B-02 | GENERAL_NO_SYNC | PASS (PHASE1/2) |
| B3B-03 | NULL_NAME_SKIP | PASS (PHASE1/2) |
| B3B-04 | NULL_PHONE_SKIP | PASS (PHASE1/2) |
| B3B-05 | INSERT_CREATES_REGISTRY | PASS (PHASE1/2) |
| B3B-06 | UPDATE_SYNCS_REGISTRY | PASS (PHASE1/2) |
| B3B-07 | SUBCONTRACTOR_SYNC | PASS (PHASE1/2) |
| B3B-08 | NO_SUBCONTRACTOR_DIRECT | PASS (PHASE1/2) |
| B3B-09 | FACTORY_CONSTRUCTION_SYNC | PASS (PHASE1/2) |
| B3B-10 | TRANSACTION_ROLLBACK | PASS (PHASE1/2) |
| B3B-11 | ROLE_RLS_EQUIVALENCE | **ROLE_RLS_UNVERIFIED** (documented gap) |

---

## Known Gaps

**B2B-07 / B3B-11 ROLE_RLS_UNVERIFIED**

프로덕션에서 `runtime_inspection_review` / `runtime_work_order_review`는
`anon` 역할에 대해 SELECT만 허용(INSERT 차단)된다.
격리 환경에는 `anon` / `authenticated` 역할 분리가 없으므로
RLS 동등성 검증은 불가하다. 해당 함수는 `service_role` 경유로만
프로덕션에서 호출된다. 기능 동등성(PHASE1/2 동작)은 별도 시나리오로 검증 완료.

**EXACT_MIGRATION_EXECUTED = FALSE**

로컬 OID가 운영 OID와 다르므로 Migration SQL의 OID 기준선 검사는
격리 환경에서 수행되지 않는다. Migration 파일 자체의 SHA256 불변은
`tests/test_sec_searchpath_rem97_bw2b_*.py` / `bw3b_*.py`에서 검증된다.

**PG 15 vs PG 17 prosrc trailing whitespace**

운영 PG 17.6은 일부 함수 본문에 trailing space를 보존한다.
로컬 PG 15.19는 이를 제거하므로 `setup_isolated.sql`에서
해당 trailing space를 명시적으로 삽입하여 프로덕션 MD5와 일치시킨다.
영향 함수: `sync_construction_notification_time` / `sync_factory_notification_time_to_cs`.

---

## Migration SHA256 (불변 기준선)

| Migration | SHA256 |
|-----------|--------|
| B-W2B: `20261024094500_sec_searchpath_rem97_bw2b_review_triggers.sql` | `c9598ab60537698c8ff58b64b94deebb959ebe0521b2fe11f6a9c03b787fc02e` |
| B-W3B: `20261024101500_sec_searchpath_rem97_bw3b_sync_triggers.sql` | `92ec79cca4b2d0eaeef9793f9920cb2f538a9ab8559ec883be93dfd9a0df6644` |
