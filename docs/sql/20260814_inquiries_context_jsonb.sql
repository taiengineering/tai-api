-- TAI: inquiries.context jsonb 추가 (고객응대 MVP 1단계 — Question Context Contract)
-- 설계: docs(tai-www) 2026-08-14_TAI-고객응대-자동화_MVP-설계서.md §8-D, §15(1단계)
-- 적용: 2026-08-14 운영 DB(vwlahtguyggrhvslabax)에 이미 반영됨. 본 파일은 재현 가능한 이력 보존용.
-- Supabase: SQL Editor 또는 migration 으로 적용. IF NOT EXISTS 로 idempotent.
--
-- 목적: SaaS 회원 문의(POST /me/inquiries)의 화면 Context 를 하나의 부속 jsonb 로 보존한다.
--   정규 컬럼(user_id/company_id/page_url/source/content)에 있는 값은 context 에 중복 저장하지 않는다.
--   context 에는 화면 Context 만 담는다 — factory_id, object_type, object_id.
--   (안 A: 별도 테이블 대신 단일 jsonb 컬럼. 실제 문의 로그가 쌓이면 자주 쓰는 키만 정규 컬럼으로 승격 가능.)

ALTER TABLE public.inquiries
  ADD COLUMN IF NOT EXISTS context jsonb;

COMMENT ON COLUMN public.inquiries.context IS
  'Question Context Contract 부속 데이터(jsonb). 정규 컬럼(user_id/company_id/page_url/source/content)에 없는 화면 Context만 보존: factory_id, object_type, object_id. 참고정보이며 법적 판단 SoT 아님. 없으면 NULL.';
