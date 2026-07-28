-- WO-2 AuditHook: 운영 감사 전용 테이블 (Goal G-ms4je4z3-33eada)
-- admin_audit_logs는 문서 리뷰 엔진 전용(action CHECK가 엔진 어휘로 제한)이라,
-- 결제/회원/환불/크레딧/삭제 등 운영 감사는 별도 테이블로 분리한다.
CREATE TABLE IF NOT EXISTS public.admin_ops_audit_logs (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id     uuid,
  action       text NOT NULL,
  entity_type  text NOT NULL,
  entity_id    uuid,
  before_data  jsonb,
  after_data   jsonb,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ops_audit_entity ON public.admin_ops_audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_ops_audit_action ON public.admin_ops_audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_ops_audit_created ON public.admin_ops_audit_logs(created_at DESC);
COMMENT ON TABLE public.admin_ops_audit_logs IS 'WO-2 운영 감사: 결제·환불·회원·크레딧·삭제 등 관리자 위험조작 불변 기록. action 자유 어휘(엔진 전용 admin_audit_logs와 분리).';