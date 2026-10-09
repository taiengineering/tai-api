-- ─────────────────────────────────────────────────────────────────────────────
-- TAM-008C-004-C1 — factories UNIQUE(company_id, id) — Option A Prerequisite
--
-- Purpose:
--   tam_permission_grants에 복합 FK
--     FOREIGN KEY (company_id, factory_id) REFERENCES factories(company_id, id)
--   를 추가하기 위한 선행 UNIQUE 제약 조건.
--
-- Safety analysis:
--   factories.id = UUID PK → (company_id, id) 쌍은 이미 유일함이 보장됨.
--   company_id nullable 행 5061건 존재하나, PostgreSQL UNIQUE는 NULL을
--   개별 고유값으로 처리 → 기존 데이터 충돌 없음.
--
-- Apply order: FIRST — must precede 20261009010002 (permission ledger)
-- Apply method: supabase db push --linked  (NOT apply_migration MCP)
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE factories
    ADD CONSTRAINT uq_factories_company_id UNIQUE (company_id, id);
