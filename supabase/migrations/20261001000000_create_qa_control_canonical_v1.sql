-- WO-QA-CONTROL-PHASE2A-001 + PATCH-2A-01: QA Canonical DB Contract v1
-- 5개 테이블: qa_items / qa_schedules / qa_run_targets / qa_runs / qa_run_results
-- RLS: ENABLED 전체 — anon / authenticated direct access = NONE
-- tai-api service_role 전용. Admin Front → tai-api → Supabase 경로만 허용.
-- text + CHECK constraints (ENUM 미사용 — 향후 value 확장 부담 최소화).
-- CREATE TABLE without IF NOT EXISTS (fail-loud: schema drift 노출 보장).
-- Legacy auto_qa_checks / auto_qa_log / auto_qa_pending: UNTOUCHED (별도 cleanup WO)

-- ─────────────────────────────────────────────────────────────────────────────
-- Table 1: qa_items
-- QA 항목 정본. scenario_id = tai-qa feature 시나리오 제목과 1:1.
-- assertion SoT = tai-qa 코드. expected_summary = display-only.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE public.qa_items (
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
    CONSTRAINT qa_items_priority_chk     CHECK (priority    IN ('P0','P1','P2','P3')),
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
-- Semantic CHECK: frequency_type + 연관 컨럼 조합 고정.
--   MANUAL    → enabled=false, frequency_value/anchor_time/day_of_week 모두 NULL
--   MINUTES   → frequency_value > 0, day_of_week NULL
--   HOURLY    → frequency_value > 0, day_of_week NULL
--   DAILY     → frequency_value NULL, anchor_time IS NOT NULL, day_of_week NULL
--   WEEKLY    → frequency_value NULL, anchor_time IS NOT NULL, day_of_week 0..6
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE public.qa_schedules (
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

    CONSTRAINT qa_schedules_qa_item_id_key  UNIQUE (qa_item_id),

    -- 시맨틱 CHECK: frequency_type별 연관 컨럼 조합 강제
    -- MINUTES/HOURLY의 anchor_time은 향후 offset 용도로 NULL/값 모두 허용
    CONSTRAINT qa_schedules_semantic_chk CHECK (
        (frequency_type = 'MANUAL'
            AND enabled         = false
            AND frequency_value IS NULL
            AND anchor_time     IS NULL
            AND day_of_week     IS NULL)
        OR
        (frequency_type = 'MINUTES'
            AND frequency_value IS NOT NULL
            AND frequency_value  > 0
            AND day_of_week     IS NULL)
        OR
        (frequency_type = 'HOURLY'
            AND frequency_value IS NOT NULL
            AND frequency_value  > 0
            AND day_of_week     IS NULL)
        OR
        (frequency_type = 'DAILY'
            AND frequency_value IS NULL
            AND anchor_time     IS NOT NULL
            AND day_of_week     IS NULL)
        OR
        (frequency_type = 'WEEKLY'
            AND frequency_value IS NULL
            AND anchor_time     IS NOT NULL
            AND day_of_week     IS NOT NULL
            AND day_of_week      >= 0
            AND day_of_week      <= 6)
    )
);

ALTER TABLE public.qa_schedules ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE  public.qa_schedules IS 'WO-QA-CONTROL-PHASE2A-001 Per-item QA schedule. Semantic check enforces frequency_type/column combination. Scheduler authority moves here Phase 2-E.';
COMMENT ON COLUMN public.qa_schedules.day_of_week IS '0=Sunday .. 6=Saturday. Meaningful only for WEEKLY frequency.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Table 3: qa_runs
-- 실행 요청 / GitHub Actions 실행 단위.
-- TAI 내부 id(uuid) != github_run_id(bigint). 별개 authority.
-- github_run_id: non-NULL 값 중복 금지, NULL 다중 허용 (partial unique index).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE public.qa_runs (
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
-- Table 4: qa_run_targets (PATCH-2A-01)
-- 실행 요청 대상 구체화. QUEUED/RUNNING 싴레에서도 대상 QA 항목 파악 가능.
-- qa_run_targets = 실행하기로 한 것 (request side)
-- qa_run_results = 실제 실행 결과 (evidence side)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE public.qa_run_targets (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      uuid        NOT NULL REFERENCES public.qa_runs(id),
    qa_item_id  uuid        NOT NULL REFERENCES public.qa_items(id),
    ordinal     integer,
    created_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT qa_run_targets_run_item_key UNIQUE (run_id, qa_item_id)
);

CREATE INDEX IF NOT EXISTS ix_qa_run_targets_run_id     ON public.qa_run_targets(run_id);
CREATE INDEX IF NOT EXISTS ix_qa_run_targets_qa_item_id ON public.qa_run_targets(qa_item_id);

ALTER TABLE public.qa_run_targets ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE  public.qa_run_targets IS 'WO-QA-CONTROL-PHASE2A-001 Run request targets. Enables QUEUED/RUNNING state inspection without waiting for results. request side != evidence side.';
COMMENT ON COLUMN public.qa_run_targets.ordinal IS 'Optional execution order hint. NULL = no ordering constraint.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Table 5: qa_run_results
-- 하나의 qa_run에 포함된 개별 시나리오 raw 결과.
-- result_status = raw evidence: PASS / FAIL / BLOCKED / SKIPPED
-- FLAKY = derived (API가 attempt1=FAIL + attempt2=PASS로 파생) — DB에 저장 안 함.
-- NEVER_RUN = derived (result 이력 부재) — DB에 저장 안 함.
-- UNIQUE(run_id, qa_item_id, attempt) — retry row 별도 보존.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE public.qa_run_results (
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

    -- raw evidence only: FLAKY는 API가 파생 — DB에 저장 금지
    CONSTRAINT qa_run_results_result_status_chk     CHECK (
        result_status IN ('PASS','FAIL','BLOCKED','SKIPPED')
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

COMMENT ON TABLE  public.qa_run_results IS 'WO-QA-CONTROL-PHASE2A-001 Raw attempt evidence per scenario per run. FLAKY/NEVER_RUN are derived by API, not stored here.';
COMMENT ON COLUMN public.qa_run_results.result_status IS 'Raw result: PASS/FAIL/BLOCKED/SKIPPED. FLAKY = derived when attempt1=FAIL + attempt2=PASS for same run+item.';
COMMENT ON COLUMN public.qa_run_results.artifact_ref  IS 'Internal reference only (GitHub artifact ID or storage key). Never store signed URLs or tokens.';
