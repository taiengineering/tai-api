-- WO-8B: Gmail 수신 폴링 중복 방지 (Goal G-ms4je4z3-33eada)
-- inbound 메일의 외부 메일ID(resend_id 컬럼 재사용 = Gmail message id)를 유일화.
-- 기존 inbound 201건 중복 0 확인 후 안전 적용. outbound는 대상 아님(부분 인덱스).
CREATE UNIQUE INDEX IF NOT EXISTS uq_mail_logs_inbound_extid
  ON public.mail_logs(resend_id)
  WHERE direction = 'inbound' AND resend_id IS NOT NULL;
COMMENT ON INDEX public.uq_mail_logs_inbound_extid IS 'WO-8B 수신 메일 중복방지: inbound resend_id(=외부 메일ID/Gmail message id) 유일.';