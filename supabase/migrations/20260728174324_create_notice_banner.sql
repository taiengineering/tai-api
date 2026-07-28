-- WO-16: 통합 공지 배너 (Goal G-ms4je4z3-33eada)
-- marketing(taieng.co.kr)·safe(safe.taieng.co.kr) 두 채널 통합 관리. RLS off(service_role).
CREATE TABLE IF NOT EXISTS public.notice_banner (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title       text NOT NULL,
    body        text,
    channels    text[] NOT NULL DEFAULT ARRAY['MARKETING','SAFE'],  -- MARKETING | SAFE
    banner_type text NOT NULL DEFAULT 'INFO',   -- INFO | WARNING | MAINTENANCE | EVENT
    link_url    text,
    link_label  text,
    starts_at   timestamptz,
    ends_at     timestamptz,
    priority    integer NOT NULL DEFAULT 0,
    enabled     boolean NOT NULL DEFAULT true,
    created_by  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notice_banner_enabled ON public.notice_banner(enabled) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_notice_banner_channels ON public.notice_banner USING GIN (channels);
CREATE INDEX IF NOT EXISTS idx_notice_banner_window ON public.notice_banner(starts_at, ends_at);

ALTER TABLE public.notice_banner DISABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.notice_banner IS 'WO-16 통합 공지 배너. channels[]로 marketing·safe 타깃. 노출기간·priority.';