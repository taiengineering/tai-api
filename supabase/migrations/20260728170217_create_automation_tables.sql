-- WO-12: 운영 자동화 (Goal G-ms4je4z3-33eada)
-- 엔진 자산과 분리된 운영 전용 automation. RLS off(service_role 전용).
CREATE TABLE IF NOT EXISTS public.automation_rule (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_code     text UNIQUE NOT NULL,
    event_type    text NOT NULL,
    condition_json jsonb DEFAULT '{}'::jsonb,
    action_type   text NOT NULL,
    action_config_json jsonb DEFAULT '{}'::jsonb,
    require_approval boolean NOT NULL DEFAULT true,
    enabled       boolean NOT NULL DEFAULT true,
    memo          text,
    created_by    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.automation_run_log (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id       uuid REFERENCES public.automation_rule(id),
    event_type    text NOT NULL,
    trigger_ref   text,
    matched       boolean NOT NULL DEFAULT false,
    status        text NOT NULL,
    action_type   text,
    result_json   jsonb,
    error         text,
    approved_by   text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_automation_rule_event ON public.automation_rule(event_type) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_automation_run_rule ON public.automation_run_log(rule_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_automation_run_pending ON public.automation_run_log(status) WHERE status = 'APPROVAL_PENDING';

ALTER TABLE public.automation_rule DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.automation_run_log DISABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.automation_rule IS 'WO-12 운영 자동화 규칙(엔진 격리). event to condition to action.';
COMMENT ON TABLE public.automation_run_log IS 'WO-12 자동화 실행 이력. require_approval 게이트 포함.';