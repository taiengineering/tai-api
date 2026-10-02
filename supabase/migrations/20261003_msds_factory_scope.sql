-- WO-MSDS-02-PATCH-003: Canonical Scope Correction (company_id → factory_id)
-- chemical_products / chemical_product_identifiers 의 관리 기준을 company → factory 로 교정.
-- rows=0 임을 pre-guard 로 강제 확인. 데이터 migration/backfill 없음.

DO $$
BEGIN
  IF (SELECT COUNT(*) FROM public.chemical_products) > 0 THEN
    RAISE EXCEPTION 'ABORT: chemical_products has rows — Owner approval required before ALTER';
  END IF;
  IF (SELECT COUNT(*) FROM public.chemical_product_identifiers) > 0 THEN
    RAISE EXCEPTION 'ABORT: chemical_product_identifiers has rows — Owner approval required before ALTER';
  END IF;
END $$;

-- ─── chemical_product_identifiers: company scope 제거 ─────────────────────────
-- (identifiers FK가 products FK에 의존하므로 identifiers 먼저 처리)

DROP INDEX IF EXISTS public.idx_cpi_company_type_norm;

ALTER TABLE public.chemical_product_identifiers
    DROP CONSTRAINT IF EXISTS chemical_product_identifiers_company_id_fkey;

-- simple FK 제거 (composite FK 로 교체)
ALTER TABLE public.chemical_product_identifiers
    DROP CONSTRAINT IF EXISTS chemical_product_identifiers_chemical_product_id_fkey;

ALTER TABLE public.chemical_product_identifiers
    DROP COLUMN IF EXISTS company_id;

-- ─── chemical_products: company scope 제거 ────────────────────────────────────

DROP INDEX IF EXISTS public.idx_cp_company_status;
DROP INDEX IF EXISTS public.idx_cp_company_name_norm;
DROP INDEX IF EXISTS public.idx_cp_company_mfr_norm;

ALTER TABLE public.chemical_products
    DROP CONSTRAINT IF EXISTS chemical_products_company_id_fkey;

ALTER TABLE public.chemical_products
    DROP COLUMN IF EXISTS company_id;

-- ─── chemical_products: factory scope 추가 ───────────────────────────────────

ALTER TABLE public.chemical_products
    ADD COLUMN factory_id uuid NOT NULL
    REFERENCES public.factories(id);

-- Identifier composite FK를 위한 UNIQUE (id, factory_id)
ALTER TABLE public.chemical_products
    ADD CONSTRAINT uq_cp_id_factory UNIQUE (id, factory_id);

CREATE INDEX idx_cp_factory_status
    ON public.chemical_products (factory_id, status_code);

CREATE INDEX idx_cp_factory_name_norm
    ON public.chemical_products (factory_id, product_name_normalized);

CREATE INDEX idx_cp_factory_mfr_norm
    ON public.chemical_products (factory_id, manufacturer_normalized);

-- ─── chemical_product_identifiers: factory scope 추가 ─────────────────────────

ALTER TABLE public.chemical_product_identifiers
    ADD COLUMN factory_id uuid NOT NULL
    REFERENCES public.factories(id);

-- Composite FK: identifier(product_id, factory_id) → product(id, factory_id)
-- Product와 Identifier가 반드시 같은 Site에 속하도록 DB 레벨에서 강제
ALTER TABLE public.chemical_product_identifiers
    ADD CONSTRAINT fk_cpi_product_factory
    FOREIGN KEY (chemical_product_id, factory_id)
    REFERENCES public.chemical_products(id, factory_id);

CREATE INDEX idx_cpi_factory_product
    ON public.chemical_product_identifiers (factory_id, chemical_product_id);

CREATE INDEX idx_cpi_factory_type_norm
    ON public.chemical_product_identifiers (factory_id, identifier_type, identifier_normalized);
