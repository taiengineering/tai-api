-- 무료진단(익명) 목업 데이터 — 관리자 목록/상세 API 테스트용
-- Supabase SQL Editor에서 실행. 테이블: 20260402_anonymous_diagnosis_results.sql 선행 적용 필요.
-- 재실행 시 토큰 충돌을 피하려면 아래 DELETE 후 INSERT 하거나, ON CONFLICT 사용.

-- 기존 목업만 제거(선택)
DELETE FROM public.anonymous_diagnosis_results
WHERE public_token IN (
  'a1111111-1111-4111-8111-111111111101',
  'a2222222-2222-4222-8222-222222222202',
  'a3333333-3333-4333-8333-333333333303',
  'a4444444-4444-4444-8444-444444444404',
  'a5555555-5555-4555-8555-555555555505'
);

INSERT INTO public.anonymous_diagnosis_results (
  id,
  public_token,
  input_data,
  partial_result,
  full_result,
  created_at,
  expires_at,
  claimed_user_id,
  status,
  source_type,
  engine_version,
  rule_version
) VALUES
(
  'b1111111-1111-4111-8111-111111111101'::uuid,
  'a1111111-1111-4111-8111-111111111101',
  '{"site_kind":"construction","scale":"medium","workers":45,"region":"경기","sector":"CONSTRUCTION"}'::jsonb,
  '{"risk_level":"MEDIUM","summary":{"ko":"적용 의무 다수 확인"},"applicable_count":12,"sector":"CONSTRUCTION","evaluated_at":"2026-04-01T09:00:00Z","message":"일부 결과만 표시"}'::jsonb,
  '{"risk_level":"MEDIUM","applicable_count":12,"rules":[{"id":"R1","title":"산안법 샘플"}],"evaluated_at":"2026-04-01T09:00:00Z"}'::jsonb,
  now() - interval '2 days',
  now() + interval '5 days',
  NULL,
  'ACTIVE',
  'site_free',
  'legal_engine:mock',
  'master_building_legal_rules:v1'
),
(
  'b2222222-2222-4222-8222-222222222202'::uuid,
  'a2222222-2222-4222-8222-222222222202',
  '{"site_kind":"manufacturing","scale":"large","workers":120,"region":"인천","sector":"MANUFACTURING"}'::jsonb,
  '{"risk_level":"HIGH","summary":{"ko":"고위험"},"applicable_count":28,"sector":"MANUFACTURING","evaluated_at":"2026-04-02T10:00:00Z"}'::jsonb,
  '{"risk_level":"HIGH","rules":[],"evaluated_at":"2026-04-02T10:00:00Z"}'::jsonb,
  now() - interval '1 day',
  now() + interval '6 days',
  NULL,
  'CLAIMED',
  'site_free',
  'legal_engine:mock',
  'master_building_legal_rules:v1'
),
(
  'b3333333-3333-4333-8333-333333333303'::uuid,
  'a3333333-3333-4333-8333-333333333303',
  '{"site_kind":"building","scale":"small","workers":8,"region":"서울","sector":"BUILDING"}'::jsonb,
  '{"risk_level":"LOW","applicable_count":4,"sector":"BUILDING","evaluated_at":"2026-03-15T08:00:00Z"}'::jsonb,
  '{"risk_level":"LOW","rules":[],"evaluated_at":"2026-03-15T08:00:00Z"}'::jsonb,
  now() - interval '20 days',
  now() - interval '1 day',
  NULL,
  'EXPIRED',
  'site_free',
  'legal_engine:mock',
  'master_building_legal_rules:v1'
),
(
  'b4444444-4444-4444-8444-444444444404'::uuid,
  'a4444444-4444-4444-8444-444444444404',
  '{"site_kind":"other","scale":"medium","workers":30,"region":"부산","sector":"SPECIAL_FACILITY"}'::jsonb,
  '{"risk_level":"MEDIUM","applicable_count":9,"sector":"SPECIAL_FACILITY","evaluated_at":"2026-04-03T11:30:00Z"}'::jsonb,
  '{"risk_level":"MEDIUM","rules":[],"evaluated_at":"2026-04-03T11:30:00Z"}'::jsonb,
  now() - interval '3 hours',
  now() + interval '7 days',
  NULL,
  'ACTIVE',
  'site_free',
  'legal_engine:mock',
  'master_building_legal_rules:v1'
),
(
  'b5555555-5555-4555-8555-555555555505'::uuid,
  'a5555555-5555-4555-8555-555555555505',
  '{"site_kind":"construction","scale":"small","workers":5,"region":"강원","sector":"CONSTRUCTION"}'::jsonb,
  '{"risk_level":"LOW","applicable_count":3,"sector":"CONSTRUCTION","evaluated_at":"2026-04-04T14:00:00Z"}'::jsonb,
  '{"risk_level":"LOW","rules":[],"evaluated_at":"2026-04-04T14:00:00Z"}'::jsonb,
  now() - interval '30 minutes',
  now() + interval '7 days',
  NULL,
  'ACTIVE',
  'site_free',
  'legal_engine:mock',
  'master_building_legal_rules:v1'
);

COMMENT ON TABLE public.anonymous_diagnosis_results IS '비로그인 무료진단 결과 — 목업 시드: sql/20260420_anonymous_diagnosis_mock_seed.sql';
