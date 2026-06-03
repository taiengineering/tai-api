# Phase 10 — Quality Coverage Report

> 상태: **PENDING** — 아래 숫자는 `scripts/run_quality_batch.py` 실제 실행 후 채운다. 추측 금지.

## 의무 출처 (실데이터 확정)

진단 기반 수집은 이 환경에서 0건(최신 진단의 result_data에 `inspection_required` 없음, `rules`/`key_obligations` 사용). 실제 운영 의무 원장 = **`work_schedules` (LEGAL, 60건 관측)**, distinct `rule_code`. 따라서 기본 출처를 work_schedules로 설정.

## 1. 실행 명령
```bash
PYTHONPATH=. python scripts/run_quality_batch.py --dry-run   # 미리보기 (work_schedules)
PYTHONPATH=. python scripts/run_quality_batch.py --commit    # 적재
```

## 2. Quality Distribution (실행 후 기록)

| 항목 | 값 |
|------|-----|
| source_rows (work_schedules LEGAL) | _PENDING_ |
| obligation_count (distinct rule_code) | _PENDING_ |
| READY | _PENDING_ |
| TRACE_REQUIRED | _PENDING_ |
| CORRECTION_REQUIRED | _PENDING_ |
| fully_classified | _PENDING_ |

## 3. TOP 10 원인 (quality_reason, 실행 후 기록)

| # | reason | count |
|---|--------|-------|
| 1 | _PENDING_ | |

## 4. Admin Queue 현황 (실행 후 기록)

`GET /admin/obligations/queue?status=OPEN` → OPEN 건수: _PENDING_

## 5. Schedule Gate 결과 (per-call 시연, 실행 후 기록)

`POST /legal-engine/generate-schedules/<FACTORY_ID>?enforce_quality=true`

| field | value |
|-------|-------|
| created | _PENDING_ |
| skipped_not_ready | _PENDING_ |
| skipped_unevaluated | _PENDING_ |

## 예상 (현 시점, Check 리포트 부재)

READY 0 / 대부분 TRACE_REQUIRED(EVIDENCE_INSUFFICIENT) / 일부 CORRECTION(LAW_LINK_ERROR·DUPLICATE). 실제 수치와 일치 여부를 실행으로 확인.
