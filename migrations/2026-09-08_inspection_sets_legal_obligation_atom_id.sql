-- WO-SAAS-OBLIGATION-IDENTITY-BRIDGE-001 / STEP 4B-1
-- inspection_sets 에 공식 obligation exact identity carrier 추가 (additive).
--
-- 의미: legal_obligation_atom_id = full_result.obligations_raw[].atom_id EXACT.
--   legal_rule_id(rule-code 공간, 예 CON3-SCF-002)와는 서로 다른 identity space 다.
--   기존 필드(legal_rule_id/legal_rule_code/law_name/law_article/obligation_* 등) 변경 0.
--   기존 326 ACTIVE LEGACY row 는 NULL 유지(이번 WP backfill 금지).
--
-- ARTIFACT ONLY — DB APPLY = 0 (운영자/GPT 승인 후 별도 실행).
-- idempotent: IF NOT EXISTS 로 재실행 안전.

ALTER TABLE public.inspection_sets
    ADD COLUMN IF NOT EXISTS legal_obligation_atom_id text;

-- exact-linked 신규 LEGAL_ENGINE row 중복방지 (partial unique).
--   NULL(legacy/unlinked) 및 MANUAL 은 제약 대상 아님.
CREATE UNIQUE INDEX IF NOT EXISTS uq_inspection_sets_factory_atom_le
    ON public.inspection_sets (factory_id, legal_obligation_atom_id)
    WHERE legal_obligation_atom_id IS NOT NULL
      AND source = 'LEGAL_ENGINE';

COMMENT ON COLUMN public.inspection_sets.legal_obligation_atom_id IS
    'Official LEG obligation atom_id (full_result.obligations_raw[].atom_id) EXACT. legal_rule_id와 별개 identity space. NULL=legacy/unlinked.';
