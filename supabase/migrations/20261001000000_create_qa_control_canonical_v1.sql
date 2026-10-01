-- WO-QA-CONTROL-PHASE2A-001: QA Canonical DB Contract v1
-- 4 tables: qa_items / qa_schedules / qa_runs / qa_run_results
-- RLS: ENABLED on all 4 tables — anon / authenticated direct access = NONE
-- tai-api service_role 전용. Admin Front → tai-api → Supabase 경로만 허용.
-- text + CHECK constraints (ENUM 미사용 — 향후 value 확장 부담 최소화).
-- Legacy auto_qa_checks / auto_qa_log / auto_qa_pending: UNTOUCHED (별도 cleanup WO)

-- ─────────────────────────────────────────────────────────────────────────────
-- Table 1: qa_items
-- QA 항목 정본. scenario_id = tai-qa 코드의 Scenario 제목과 1:1 대응.
-- assertion SoT = tai-qa 코드. expected_summary = display-only.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.qa_items (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id      text        NOT NULL,
    site_code        text        NOT NULL,
    category         text        NOT NULL,
    name             text        NOT NULL,
    description      text,
    expected_summary text,
    priority         text        NOT NULL,
    runner_type      text        NOT NULL,
    enabled          boolean     NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT qa_items_scenario_id_key  UNIQUE (scenario_id),
    CONSTRAINT qa_items_priority_chk     CHECK (priority IN ('P0','P1','P2','P3')),
    CONSTRAINT qa_items_runner_type_chk  CHECK (runner_type IN ('PLAYWRIGHT','API','HEALTH')),
    CONSTRAINT qa_items_site_code_chk    CHECK (
        site_code IN ('WWW','SAFE','API','ADMIN','MKT','WORKER','EXTERNAL')
    )
);

CREATE INDEX IF NOT EXISTS ix_qa_items_site_code    ON public.qa_items(site_code);
CREATE INDEX IF NOT EXISTS ix_qa_items_priority     ON public.qa_items(priority);
CREATE INDEX IF NOT EXISTS ix_qa_items_enabled      ON public.qa_items(enabled);
CREATE INDEX IF NOT EXISTS ix_qa_items_site_enabled ON public.qa_items(site_code, enabled);

ALTER TABLE public.qa_items ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE  public.qa_items IS 'WO-QA-CONTROL-PHASE2A-001 QA canonical items. assertion SoT = tai-qa code.';
COMMENT ON COLUMN public.qa_items.expected_summary IS 'Display-only. NOT used for runtime assertion. SoT is tai-qa scenario code.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Table 2: qa_schedules
-- 항목별 자동 실행 설정. UNIQUE(qa_item_id) — 1항목 1스케줄.
-- Scheduler authority: Phase 2-E 이전에는 enabled=false, frequency_type=MANUAL 유지.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.qa_schedules (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    qa_item_id        uuid        NOT NULL REFERENCES public.qa_items(id),
    enabled           boolean     NOT NULL DEFAULT false,
    frequency_type    text        NOT NULL,
    frequency_value   integer,
    anchor_time       time,
    day_of_week       smallint,
    timezone          text        NOT NULL DEFAULT 'Asia/Seoul',
    next_run_at       timestamptz,
    last_scheduled_at timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT qa_schedules_qa_item_id_key      UNIQUE (qa_item_id),
    CONSTRAINT qa_schedules_frequency_type_chk  CHECK (
        frequency_type IN ('MINUTES','HOURLY','DAILY','WEEKLY','MANUAL')
    ),
    CONSTRAINT qa_schedules_frequency_value_chk CHECK (
        frequency_value IS NULL OR frequency_value > 0
    ),
    CONSTRAINT qa_schedules_day_of_week_chk     CHECK (
        day_of_week IS NULL OR (day_of_week >= 0 AND day_of_week <= 6)
    )
);

ALTER TABLE public.qa_schedules ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE  public.qa_schedules IS 'WO-QA-CONTROL-PHASE2A-001 Per-item QA schedule. Scheduler authority moves here Phase 2-E.';
COMMENT ON COLUMN public.qa_schedules.day_of_week IS '0=Sunday .. 6=Saturday. Meaningful only for WEEKLY frequency.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Table 3: qa_runs
-- 하나의 실행 요청 / GitHub Actions 실행 단위.
-- TAI 내부 id(uuid) != github_run_id(bigint). 별개 authority.
-- github_run_id: non-NULL 값 중복 금지, NULL 다중 허용 (partial unique index).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.qa_runs (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_type       text        NOT NULL,
    run_status         text        NOT NULL DEFAULT 'QUEUED',
    github_run_id      bigint,
    github_run_attempt integer,
    head_sha           text,
    branch_name        text,
    requested_by       text,
    requested_at       timestamptz NOT NULL DEFAULT now(),
    started_at         timestamptz,
    finished_at        timestamptz,
    error_code         text,
    error_summary      text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT qa_runs_trigger_type_chk CHECK (
        trigger_type IN ('SCHEDULE','MANUAL','PR','RETRY')
    ),
    CONSTRAINT qa_runs_run_status_chk   CHECK (
        run_status IN ('QUEUED','RUNNING','COMPLETED','ERROR','CANCELED')
    )
);

-- github_run_id: non-NULL 중복 금지, NULL 다중 허용
CREATE UNIQUE INDEX IF NOT EXISTS ux_qa_runs_github_run_id
    ON public.qa_runs(github_run_id)
    WHERE github_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_qa_runs_run_status   ON public.qa_runs(run_status);
CREATE INDEX IF NOT EXISTS ix_qa_runs_trigger_type ON public.qa_runs(trigger_type);
CREATE INDEX IF NOT EXISTS ix_qa_runs_requested_at ON public.qa_runs(requested_at DESC);

ALTER TABLE public.qa_runs ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE  public.qa_runs IS 'WO-QA-CONTROL-PHASE2A-001 One run = one GitHub Actions execution unit. TAI id != github_run_id.';
COMMENT ON COLUMN public.qa_runs.github_run_id IS 'GitHub Actions run_id reference. Partial unique index: non-NULL must be unique, NULL allowed multiple times.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Table 4: qa_run_results
-- 하나의 qa_run 에 포함된 개별 시나리오 결과.
-- UNIQUE(run_id, qa_item_id, attempt) — retry row 별도 보존 (FLAKY 탐지용).
-- NEVER_RUN 은 DB 에 저장하지 않는다 — API/UI 가 이력 부재로 파생 표현.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.qa_run_results (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        uuid        NOT NULL REFERENCES public.qa_runs(id),
    qa_item_id    uuid        NOT NULL REFERENCES public.qa_items(id),
    result_status text        NOT NULL,
    attempt       integer     NOT NULL DEFAULT 1,
    duration_ms   integer,
    http_status   integer,
    error_code    text,
    error_summary text,
    artifact_ref  text,
    started_at    timestamptz,
    finished_at   timestamptz,
    checked_at    timestamptz NOT NULL DEFAULT now(),
    created_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT qa_run_results_result_status_chk     CHECK (
        result_status IN ('PASS','FAIL','FLAKY','BLOCKED','SKIPPED')
    ),
    CONSTRAINT qa_run_results_attempt_chk           CHECK (attempt >= 1),
    CONSTRAINT qa_run_results_duration_ms_chk       CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CONSTRAINT qa_run_results_run_item_attempt_key  UNIQUE (run_id, qa_item_id, attempt)
);

CREATE INDEX IF NOT EXISTS ix_qa_run_results_run_id        ON public.qa_run_results(run_id);
CREATE INDEX IF NOT EXISTS ix_qa_run_results_qa_item_id    ON public.qa_run_results(qa_item_id);
CREATE INDEX IF NOT EXISTS ix_qa_run_results_result_status ON public.qa_run_results(result_status);
CREATE INDEX IF NOT EXISTS ix_qa_run_results_item_checked  ON public.qa_run_results(qa_item_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS ix_qa_run_results_run_item      ON public.qa_run_results(run_id, qa_item_id);

ALTER TABLE public.qa_run_results ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE  public.qa_run_results IS 'WO-QA-CONTROL-PHASE2A-001 Individual scenario result per run. attempt rows preserved for FLAKY detection.';
COMMENT ON COLUMN public.qa_run_results.result_status IS 'FLAKY = attempt1 FAIL + attempt2 PASS summary. Raw rows stored separately with attempt > 1.';
COMMENT ON COLUMN public.qa_run_results.artifact_ref  IS 'Internal reference only (GitHub artifact ID or storage key). Never store signed URLs or tokens.';
