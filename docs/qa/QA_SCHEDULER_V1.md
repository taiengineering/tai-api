---
title: QA Scheduler v1
version: 1.0.0
work_order: WO-QA-CONTROL-PHASE2E-001
status: IMPLEMENTED
---

# QA Scheduler v1

## Architecture

```
tai-api
 ├ services/qa_scheduler_svc.py     Scheduler tick logic
 ├ services/github_dispatch_svc.py  GitHub Actions dispatch
 ├ routers/internal_scheduler.py    POST /internal/scheduler/qa/tick
 └ routers/admin_qa.py              POST /admin/qa/runs (Manual + dispatch)
```

## Schedule Contract

| frequency_type | 필수 필드 | 반복 기준 |
|----------------|----------|-----------|
| MINUTE | frequency_value (양수) | +N 분 |
| HOUR | frequency_value (양수) | +N 시간 |
| DAY | frequency_value (양수) | +N 일 |

- MANUAL: 자동실행 불가 (enabled=false 강제)
- WEEKLY/DAILY: Admin Console에서 수정 가능, Scheduler는 MINUTE/HOUR/DAY만 처리

## Execution Flow

```
/internal/scheduler/qa/tick  (X-Internal-Secret 인증)
        │
        ▼
qa_schedules WHERE enabled=true AND next_run_at <= now
        │
        ▼
중복 방지: QUEUED/RUNNING run에 포함된 item 제외
        │
        ▼
qa_runs INSERT (trigger_type=SCHEDULE, requested_by=scheduler)
        │
        ▼
qa_run_targets INSERT
        │
        ▼
next_run_at 갱신 (dispatch 성공 여부 무관)
        │
        ▼
GitHub Actions workflow_dispatch
(QA_GITHUB_TOKEN / QA_GITHUB_OWNER / QA_GITHUB_REPO / QA_GITHUB_WORKFLOW)
        │
        ▼
tai-qa Playwright 실행
        │
        ▼
POST /internal/qa/runs/{id}/results  (기존 Phase 2-B callback)
        │
        ▼
결과 저장 + Slack 이상 알림 (기존 Phase 2-C)
```

## Duplicate Guard

같은 qa_item_id가 QUEUED 또는 RUNNING 상태 run에 포함되어 있으면 새 run 생성 금지.
tick 재실행 시 중복 run 발생하지 않는다.

## Manual Run

```
POST /admin/qa/runs
Body: { "qa_item_ids": ["uuid1", "uuid2"] }

→ qa_runs (trigger_type=MANUAL, requested_by=current_user.id)
→ qa_run_targets
→ GitHub dispatch
→ { "dispatch": "OK" | "ERROR" | "SKIPPED" }
```

- enabled=false item 포함 시 422
- dispatch 실패 시 run_status=ERROR 업데이트, dispatch=ERROR 반환

## GitHub Dispatch

```
POST https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches

Payload:
{
  "ref": "main",
  "inputs": {
    "run_id": "uuid",
    "scenario_ids": "P0-001,P0-002,..."
  }
}
```

### Secret Contract

| 환경변수 | 설명 | 기본값 |
|---------|------|--------|
| QA_GITHUB_TOKEN | PAT (workflow scope) — log 출력 금지 | 필수 |
| QA_GITHUB_OWNER | repo 소유자 | taiengineering |
| QA_GITHUB_REPO | tai-qa repo | tai-qa |
| QA_GITHUB_WORKFLOW | workflow file id | run-qa.yml |
| QA_GITHUB_REF | dispatch branch | main |

## Callback Flow

기존 Phase 2-B 재사용:
```
POST /internal/qa/runs/{run_id}/results
X-Internal-Secret: {INTERNAL_API_SECRET}
```

변경 없음.

## Known Limitations

- MONTH/YEAR/CRON 주기 미지원 (후속 WO)
- 휴일 제외, 공휴일 처리 미지원
- 복수 schedule batch를 단일 run으로 묶음 (per-item run 분리 불가)
- E2E 실증은 Phase 2-E Production 배포 이후 P0 1개 시나리오로 수행
