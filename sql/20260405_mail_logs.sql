-- ============================================================
-- mail_logs: Resend 메일 관리 테이블 (수신/발신)
-- 생성일: 2026-04-05
-- ============================================================

CREATE TABLE IF NOT EXISTS public.mail_logs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  direction       text NOT NULL DEFAULT 'outbound',     -- inbound / outbound
  from_email      text NOT NULL DEFAULT 'tai@taieng.co.kr',
  to_emails       jsonb NOT NULL DEFAULT '[]'::jsonb,
  cc_emails       jsonb NOT NULL DEFAULT '[]'::jsonb,
  subject         text NOT NULL DEFAULT '',
  html_body       text NOT NULL DEFAULT '',
  status          text NOT NULL DEFAULT 'pending',      -- sent / failed / pending
  resend_id       text,
  error_message   text,
  sent_by         text,
  read            boolean NOT NULL DEFAULT false,
  deleted         boolean NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_mail_logs_created_at ON public.mail_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mail_logs_status     ON public.mail_logs (status);
CREATE INDEX IF NOT EXISTS idx_mail_logs_read       ON public.mail_logs (read) WHERE read = false;
CREATE INDEX IF NOT EXISTS idx_mail_logs_direction  ON public.mail_logs (direction);
CREATE INDEX IF NOT EXISTS idx_mail_logs_deleted    ON public.mail_logs (deleted) WHERE deleted = false;

-- RLS (서버 사이드 전용)
ALTER TABLE public.mail_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON public.mail_logs
  FOR ALL
  USING (true)
  WITH CHECK (true);

COMMENT ON TABLE public.mail_logs IS 'Resend 메일 관리 (수신/발신 로그)';
