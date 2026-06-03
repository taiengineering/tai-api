# Phase 9 — Obligation Quality Layer MVP

> 검증된 의무 → **운영 가능한 의무**로 전환. Check 결과를 소비해 운영 흐름(스케줄 생성)에 연결하는 첫 단계. **새 엔진 아님** — 서비스 레이어 + 스키마 + Admin API.

## 상태: UNVERIFIED (본 세션 코드 실행 불가)

코드/마이그레이션/테스트 **작성 완료**. 테스트 실행 결과는 없으며, 실행 로그로만 사실 기록한다(추측 PASS 금지).

```bash
python -m pytest tests/test_obligation_quality_evaluator.py -q
```

## 산출물

1. **obligation_quality / admin_obligation_queue** — `sql/20260603_obligation_quality_layer.sql` (CREATE TABLE + index + RLS enable)
2. **Quality Evaluator** — `services/obligation_quality_evaluator.py` (순수 함수 `evaluate_quality`, `evaluate_batch`, `is_schedulable`)
3. **Quality Store** — `services/obligation_quality_store.py` (`record_evaluation`/`record_batch`: obligation_quality upsert + CORRECTION 시 admin 큐 생성)
4. **Schedule Filter** — `routers/schedule_pipeline.py` `generate-schedules` 에 `enforce_quality` 게이트
5. **Admin Queue API** — `routers/admin_obligation_queue.py` (GET 목록/상세, PATCH 상태) + `router_registry/legal_engine.py` 등록
6. **테스트** — `tests/test_obligation_quality_evaluator.py` + `tests/fixtures/obligation_quality_cases.json` (35개)

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

- READY 의무만 스케줄 생성 — `enforce_quality=true` 게이트 + `is_schedulable` (테스트 작성)
- TRACE_REQUIRED → 추적 대상으로 관리(생성 제외, 품질상태 저장)
- CORRECTION_REQUIRED → admin_obligation_queue로 이동(`record_evaluation` 자동 생성)

## 금지사항 준수

Check Engine 수정 / LEG 수정 / 새 엔진 생성 / 법령 재판단: **없음**. 운영 서비스 레이어만 추가, Check/LEG 결과는 소비만 함.

## 적용 순서 (사람)

1. 마이그레이션 적용: `sql/20260603_obligation_quality_layer.sql` → Supabase `taieng`
2. `python -m pytest tests/test_obligation_quality_evaluator.py -q` 실행 → 결과 확인
3. 품질 평가 배치(record_batch)로 obligation_quality 채움
4. 검증 후 `enforce_quality=true` 전환 검토

## Merge

본 PR은 검토용(Draft). 테스트 실행 로그 확인 전 Review Ready/Merge 안 함.
