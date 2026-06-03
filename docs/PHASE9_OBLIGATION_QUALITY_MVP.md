# Phase 9 — Obligation Quality Layer MVP

> 검증된 의무 → **운영 가능한 의무**로 전환. Check 결과를 소비해 운영 흐름(스케줄 생성)에 연결하는 첫 단계. **새 엔진 아님** — 서비스 레이어 + 스키마 + Admin API.

## 검증 상태

| 구성요소 | 상태 | 근거 |
|----------|------|------|
| Quality Evaluator (순수 로직) + 35 fixture | **VERIFIED** | 아래 pytest 실행 로그 |
| obligation_quality / admin_obligation_queue 스키마 | PENDING | 마이그레이션 적용 필요 |
| Quality Store / Admin Queue API / Schedule Gate (런타임) | PENDING | DB 연결 + 통합 실행 필요 |

### VERIFIED — Quality Evaluator (2026-06-03, 사용자 터미널)

실행 명령:
```
python -m pytest tests/test_obligation_quality_evaluator.py -v
```
실제 출력 (Python 3.14.3, pytest 9.0.3):
```
collected 6 items
test_fixture_count PASSED
test_each_case_status_and_reason PASSED   # 35 fixture 전수 검증
test_all_three_categories_present PASSED
test_required_reason_categories_present PASSED
test_batch_duplicate_detection PASSED
test_is_schedulable_only_ready PASSED
6 passed in 0.02s
```
순수 함수 `evaluate_quality` / `evaluate_batch` / `is_schedulable` 의 매핑·우선순위·중복감지·스케줄 게이트 판정이 35 fixture(READY/TRACE_REQUIRED/CORRECTION_REQUIRED, 중복·근거누락·조치누락 포함)에서 전수 일치. **추측 없이 실행 로그로 확인.**

### PENDING — 런타임(DB) 부분

Store/Admin API/Schedule Gate는 Supabase 연결 + 마이그레이션 적용 후에만 동작. 본 pytest는 순수 로직만 검증했으므로 이 부분은 아직 UNVERIFIED.

## 산출물

1. **obligation_quality / admin_obligation_queue** — `sql/20260603_obligation_quality_layer.sql` (CREATE TABLE + index + RLS enable)
2. **Quality Evaluator** — `services/obligation_quality_evaluator.py` (순수: `evaluate_quality`, `evaluate_batch`, `is_schedulable`) — **VERIFIED**
3. **Quality Store** — `services/obligation_quality_store.py` (`record_evaluation`/`record_batch`: obligation_quality upsert + CORRECTION 시 admin 큐 생성)
4. **Schedule Filter** — `routers/schedule_pipeline.py` `generate-schedules` 에 `enforce_quality` 게이트
5. **Admin Queue API** — `routers/admin_obligation_queue.py` (GET 목록/상세, PATCH 상태) + `router_registry/legal_engine.py` 등록
6. **테스트** — `tests/test_obligation_quality_evaluator.py` + `tests/fixtures/obligation_quality_cases.json` (35개) — **VERIFIED**

## 상태 3개

| 조건 | quality_status | reason 코드 |
|------|----------------|-----------|
| 사용 가능 | READY | OK |
| 근거 부족 | TRACE_REQUIRED | EVIDENCE_INSUFFICIENT |
| 조치 부족 | TRACE_REQUIRED | ACTION_INSUFFICIENT |
| 중복 의무 | CORRECTION_REQUIRED | DUPLICATE_OBLIGATION |
| Claim 오류 | CORRECTION_REQUIRED | CLAIM_ERROR |
| 법령 연결 오류 | CORRECTION_REQUIRED | LAW_LINK_ERROR |
| Scope 밖 | CORRECTION_REQUIRED | OUT_OF_SCOPE |
| 데이터 오류 | CORRECTION_REQUIRED | DATA_ERROR |

Check EvidenceReport의 `status_summary`(claim/evidence/chain) + 의무 자체 필드(law_name/article, 중복)만 소비. 우선순위: DATA_ERROR → CORRECTION → TRACE → READY.

## 스케줄 게이트 (작업 4)

`POST /legal-engine/generate-schedules/{factory_id}?enforce_quality=true`
- READY 의무만 `work_schedules` 생성
- TRACE_REQUIRED / CORRECTION_REQUIRED → 생성 제외(`skipped_not_ready`)
- 미평가(품질 레코드 없음) → 생성 제외(`skipped_unevaluated`)

**안전 결정:** `enforce_quality` 기본값 **False** — 기존 운영 무중단. obligation_quality 백필 후 기본값 True 전환 권장. (기본 True로 바로 전환 원하시면 지시 주십시오.)

## 성공 기준 대응

- READY 의무만 스케줄 생성 — `is_schedulable` (VERIFIED) + `enforce_quality=true` 게이트 (런타임 PENDING)
- TRACE_REQUIRED → 추적 대상으로 관리(생성 제외, 품질상태 저장)
- CORRECTION_REQUIRED → admin_obligation_queue로 이동(`record_evaluation` 자동 생성)

## 금지사항 준수

Check Engine 수정 / LEG 수정 / 새 엔진 생성 / 법령 재판단: **없음**. 운영 서비스 레이어만 추가, Check/LEG 결과는 소비만 함.

## 적용 순서 (사람)

1. [완료] 테스트 실행 — evaluator 6 passed (VERIFIED)
2. 마이그레이션 적용: `sql/20260603_obligation_quality_layer.sql` → Supabase `taieng`
3. 품질 평가 배치(record_batch)로 obligation_quality 채움
4. 런타임 통합 확인 후 `enforce_quality=true` 전환 검토

## Merge

evaluator는 VERIFIED. 런타임(DB) 부분은 마이그레이션·통합 검증 전까지 PENDING. Merge 여부는 사람이 결정.
