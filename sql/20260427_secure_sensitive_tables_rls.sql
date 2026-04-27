-- RLS migration: 민감 테이블 8개 — service_role only
-- Issue #43 Phase S-1
-- 실행: Supabase MCP (기획창)

-- 1. expert_applications
ALTER TABLE expert_applications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full" ON expert_applications
  FOR ALL USING (auth.role() = 'service_role');

-- 2. fix_provider_qualifications
ALTER TABLE fix_provider_qualifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full" ON fix_provider_qualifications
  FOR ALL USING (auth.role() = 'service_role');

-- 3. expert_profiles
ALTER TABLE expert_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full" ON expert_profiles
  FOR ALL USING (auth.role() = 'service_role');

-- 4. settlements
ALTER TABLE settlements ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full" ON settlements
  FOR ALL USING (auth.role() = 'service_role');

-- 5. price_commission
ALTER TABLE price_commission ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full" ON price_commission
  FOR ALL USING (auth.role() = 'service_role');

-- 6. connection_commission
ALTER TABLE connection_commission ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full" ON connection_commission
  FOR ALL USING (auth.role() = 'service_role');

-- 7. diagnosis_auth_log
ALTER TABLE diagnosis_auth_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full" ON diagnosis_auth_log
  FOR ALL USING (auth.role() = 'service_role');

-- 8. identity_logs
ALTER TABLE identity_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full" ON identity_logs
  FOR ALL USING (auth.role() = 'service_role');
