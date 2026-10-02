-- WO-MSDS-02: Canonical Chemical Product
-- chemical_products + chemical_product_identifiers
-- RLS: anon=NO, authenticated direct=NO, service_role=YES

-- ─── chemical_products ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.chemical_products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    company_id uuid NOT NULL
        REFERENCES public.companies(id),

    product_name text NOT NULL,
    product_name_normalized text NOT NULL,

    manufacturer_name text,
    manufacturer_normalized text,

    identity_status text NOT NULL DEFAULT 'DRAFT',
    status_code text NOT NULL DEFAULT 'ACTIVE',
    created_source text NOT NULL DEFAULT 'MANUAL',

    created_by uuid,
    updated_by uuid,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_cp_identity_status
        CHECK (identity_status IN ('DRAFT', 'CONFIRMED', 'REVIEW_REQUIRED')),
    CONSTRAINT chk_cp_status_code
        CHECK (status_code IN ('ACTIVE', 'INACTIVE')),
    CONSTRAINT chk_cp_created_source
        CHECK (created_source IN ('MANUAL', 'PDF', 'PHOTO', 'EXCEL', 'MIGRATION')),
    CONSTRAINT chk_cp_product_name_nonempty
        CHECK (btrim(product_name) <> '')
);

CREATE INDEX IF NOT EXISTS idx_cp_company_status
    ON public.chemical_products (company_id, status_code);

CREATE INDEX IF NOT EXISTS idx_cp_company_name_norm
    ON public.chemical_products (company_id, product_name_normalized);

CREATE INDEX IF NOT EXISTS idx_cp_company_mfr_norm
    ON public.chemical_products (company_id, manufacturer_normalized);

ALTER TABLE public.chemical_products ENABLE ROW LEVEL SECURITY;

CREATE POLICY cp_no_anon ON public.chemical_products
    AS RESTRICTIVE FOR ALL TO anon USING (false);

-- ─── chemical_product_identifiers ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.chemical_product_identifiers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    company_id uuid NOT NULL
        REFERENCES public.companies(id),

    chemical_product_id uuid NOT NULL
        REFERENCES public.chemical_products(id)
        ON DELETE RESTRICT,

    identifier_type text NOT NULL,
    identifier_value text NOT NULL,
    identifier_normalized text NOT NULL,

    issuer_name text,

    is_primary boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,

    created_source text NOT NULL DEFAULT 'MANUAL',

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_cpi_type
        CHECK (identifier_type IN (
            'GTIN', 'EAN', 'UPC', 'BARCODE',
            'MANUFACTURER_CODE', 'SUPPLIER_CODE', 'INTERNAL_CODE',
            'QR_ALIAS', 'OTHER'
        )),
    CONSTRAINT chk_cpi_created_source
        CHECK (created_source IN ('MANUAL', 'PDF', 'PHOTO', 'EXCEL', 'MIGRATION')),
    CONSTRAINT chk_cpi_value_nonempty
        CHECK (btrim(identifier_value) <> '')
);

-- 활성 identifier 내에서 동일 product + type + normalized 중복 방지
CREATE UNIQUE INDEX IF NOT EXISTS uidx_cpi_active_unique
    ON public.chemical_product_identifiers (chemical_product_id, identifier_type, identifier_normalized)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_cpi_product
    ON public.chemical_product_identifiers (chemical_product_id);

CREATE INDEX IF NOT EXISTS idx_cpi_company_type_norm
    ON public.chemical_product_identifiers (company_id, identifier_type, identifier_normalized);

ALTER TABLE public.chemical_product_identifiers ENABLE ROW LEVEL SECURITY;

CREATE POLICY cpi_no_anon ON public.chemical_product_identifiers
    AS RESTRICTIVE FOR ALL TO anon USING (false);
