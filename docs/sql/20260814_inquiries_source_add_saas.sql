-- 20260814_inquiries_source_add_saas.sql
-- inquiries.source CHECK 제약 정합: SaaS 회원 문의(source='saas') 저장 허용.
--
-- 배경(운영 E2E 원인확정):
--   POST /me/support/ask 의 HANDOFF 저장에서 inquiries INSERT 시 source='saas' 가
--   기존 inquiries_source_chk(허용: direct/marketing/safe)에 걸려 PostgreSQL 23514 위반 →
--   status=ERROR(handoff save failed) → 프론트 generic ERROR.
--   backend 의 source='saas'(SaaS/마케팅 문의 구분용 의도값)는 유지하고, DB 제약을 계약에 맞춘다.
--
-- 실측(2026-08-14, prod vwlahtguyggrhvslabax):
--   기존 제약: CHECK (source = ANY (ARRAY['direct','marketing','safe']))
--   기존 데이터 source 분포: marketing=3 (그 외 값 없음)
--
-- 변경: 기존 허용값(direct/marketing/safe) 전체 유지 + 'saas' 추가.
--   (saas 는 기존 허용집합의 상위집합이므로 기존 행이 위반되지 않는다.)
--
-- idempotent: DROP CONSTRAINT IF EXISTS 후 재생성. 재적용 안전.

ALTER TABLE public.inquiries DROP CONSTRAINT IF EXISTS inquiries_source_chk;

ALTER TABLE public.inquiries ADD CONSTRAINT inquiries_source_chk
  CHECK (source = ANY (ARRAY['direct'::text, 'marketing'::text, 'safe'::text, 'saas'::text]));

-- 검증(적용 후 수동 확인용):
-- SELECT conname, pg_get_constraintdef(oid)
-- FROM pg_constraint
-- WHERE conrelid = 'public.inquiries'::regclass AND conname = 'inquiries_source_chk';
-- 기대: CHECK ((source = ANY (ARRAY['direct'::text, 'marketing'::text, 'safe'::text, 'saas'::text])))
