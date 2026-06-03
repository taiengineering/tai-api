# Phase 10 — Quality Coverage Report

> 상태: **PENDING** — 아래 숫자는 `scripts/run_quality_batch.py` 실제 실행 후 채운다. 추측 금지.

## 1. 실행 명령
```bash
PYTHONPATH=. python scripts/run_quality_batch.py --dry-run   # 미리보기
PYTHONPATH=. python scripts/run_quality_batch.py --commit    # 적재
```

## 2. Quality Distribution (실행 후 기록)

| status | count |
|--------|-------|
| 전체 의무 | _PENDING_ |
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

READY 0 / 대부분 TRACE_REQUIRED(EVIDENCE_INSUFFICIENT) / 일부 CORRECTION(LAW_LINK_ERROR·DUPLICATE). 이 예상과 실제 수치가 일치하는지 실행으로 확인.
