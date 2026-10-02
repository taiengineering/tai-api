---
title: QA Auto Operation v1
version: 1.1.0
work_order: WO-QA-CONTROL-PHASE2E-AUTO-OPS-001
status: IMPLEMENTED
---

# QA Auto Operation v1

## Architecture

```
cron_job_master (qa_scheduler_tick, * * * * *)
        │  direct://qa_scheduler_tick
        ▼
services/scheduler/handlers._run_qa_scheduler_tick()
        │  asyncio.run(scheduler_tick(sb))
        ▼
services/qa_scheduler_svc.scheduler_tick()
        │
        ├── qa_schedules WHERE enabled=true AND next_run_at <= now
        ├── 중복 방지: QUEUED/RUNNING run에 포함된 item 제외
        ├── qa_runs INSERT (trigger_type=SCHEDULE, run_status=QUEUED)
        ├── qa_run_targets INSERT
        ├── next_run_at 갱신 (기존 scheduled time 기준, drift 방지)
        ├── GitHub Actions dispatch
        └── dispatch 성공 → run_status=RUNNING / 실패 → run_status=ERROR
```

## Lifecycle

```
QUEUED
  ↓ (dispatch 성공)
RUNNING
  ↓ (callback)
COMPLETED / ERROR / CANCELED
```

## Scheduler Flow

1. `scheduler_worker.py` 가 5초 간격으로 `services/scheduler/dispatcher.tick()` 호출
2. dispatcher가 `cron_job_master`에서 due 상태인 job 조회
3. `qa_scheduler_tick` (cron `* * * * *`) → `direct://qa_scheduler_tick` 핸들러 실행
4. `scheduler_tick()` 이 `qa_schedules` 에서 `enabled=true AND next_run_at <= now` 조회
5. SCHEDULE trigger_type으로 `qa_runs` 생성 → GitHub dispatch → RUNNING 전환

## Production Activation

### Step 1: 마이그레이션 적용 (Owner)

```
supabase/migrations/20261002_qa_auto_ops_scheduler.sql
```

Production에 적용:
- `cron_job_master`: `qa_scheduler_tick` 등록 (is_active=false)
- `cron_schedule_config`: 동일 row 생성 (is_enabled=false)

### Step 2: P0-SAAS-001 Schedule 활성화 (1분 테스트)

DB constraint: `MINUTES` → `frequency_value > 0`, `anchor_time` 선택

```sql
UPDATE public.qa_schedules
SET
  enabled          = true,
  frequency_type   = 'MINUTES',
  frequency_value  = 1,
  next_run_at      = now() + interval '1 minute',
  updated_at       = now()
WHERE qa_item_id = (
  SELECT id FROM public.qa_items WHERE scenario_id = 'P0-SAAS-001'
);
```

### Step 3: Cron Job 활성화

Activation Authority = `cron_job_master.is_active`

```sql
UPDATE public.cron_job_master
SET is_active = true
WHERE job_code = 'qa_scheduler_tick';

UPDATE public.cron_schedule_config
SET is_enabled = true
WHERE job_code = 'qa_scheduler_tick';
```

### Step 4: 검증

1분 후 확인:
```sql
SELECT trigger_type, run_status, requested_at, started_at
FROM public.qa_runs
WHERE trigger_type = 'SCHEDULE'
ORDER BY requested_at DESC
LIMIT 5;
```

기대: `run_status = RUNNING` (dispatch 성공 시)

### Step 5: 운영 주기 전환 (1분 테스트 성공 후)

DB constraint: `DAILY` → `frequency_value IS NULL`, `anchor_time IS NOT NULL`

```sql
UPDATE public.qa_schedules
SET
  frequency_type  = 'DAILY',
  frequency_value = NULL,
  anchor_time     = '08:00:00',
  day_of_week     = NULL,
  next_run_at     = (current_date + interval '1 day')::date + time '08:00:00'
                    AT TIME ZONE 'Asia/Seoul',
  updated_at      = now()
WHERE qa_item_id = (
  SELECT id FROM public.qa_items WHERE scenario_id = 'P0-SAAS-001'
);
```

## Cron Configuration

| 항목 | 값 |
|------|-----|
| job_code | qa_scheduler_tick |
| cron_expression | `* * * * *` (매분) |
| endpoint_url | direct://qa_scheduler_tick |
| category | QA |
| timeout_seconds | 120 |
| Activation Authority | cron_job_master.is_active |

## Duplicate Guard

동일 `qa_item_id`에 QUEUED/RUNNING run이 이미 있으면 tick이 새 run을 생성하지 않는다.

```
08:00:00 tick → QUEUED → dispatch → RUNNING
08:00:05 tick → item already RUNNING → skip
08:01:00 tick → run COMPLETED → 새 run 생성 가능
```

## HTTP Tick Endpoint (보조)

```
POST /internal/scheduler/qa/tick
Header: X-Internal-Secret: <INTERNAL_API_SECRET>
```

Railway 외부 cron 또는 수동 호출에 사용. secret은 Railway env에만 저장하며 로그 출력 금지.

## Schedule Policy

| 단계 | 대상 | frequency_type | frequency_value | anchor_time |
|------|------|----------------|-----------------|-------------|
| 1. 테스트 | P0-SAAS-001 | MINUTES | 1 | NULL |
| 2. 운영 | P0-SAAS-001 | DAILY | NULL | 08:00:00 |
| 3. 확대 | P0 3개 | DAILY | NULL | 08:00:00 |
| 4. 전체 | P0 전체 | DAILY | NULL | 08:00:00 |

## Rollback

```sql
-- Schedule 비활성화
UPDATE public.qa_schedules
SET enabled = false, next_run_at = null, updated_at = now()
WHERE qa_item_id = (SELECT id FROM public.qa_items WHERE scenario_id = 'P0-SAAS-001');

-- Cron job 비활성화
UPDATE public.cron_job_master
SET is_active = false
WHERE job_code = 'qa_scheduler_tick';

UPDATE public.cron_schedule_config
SET is_enabled = false
WHERE job_code = 'qa_scheduler_tick';
```
