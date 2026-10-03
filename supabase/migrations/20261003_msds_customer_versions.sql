-- WO-MSDS-03-IMPLEMENTATION-001: Customer Original MSDS Version
-- customer_msds_versions + 3 DB functions (register/promote/void)
-- RLS: anon=NO, authenticated=NO, service_role=YES
-- Evidence Lock: document_id UNIQUE + ON DELETE RESTRICT

-- ─── Table ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.customer_msds_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    factory_id uuid NOT NULL
        REFERENCES public.factories(id),

    chemical_product_id uuid NOT NULL,

    document_id uuid NOT NULL
        REFERENCES public.documents(id)
        ON DELETE RESTRICT,

    version_no integer NOT NULL,

    content_sha256 text NOT NULL,

    source_revision_date date,
    source_revision_no text,
    supplier_name text,

    is_current boolean NOT NULL DEFAULT false,
    superseded_at timestamptz,

    record_status text NOT NULL DEFAULT 'ACTIVE',

    voided_at timestamptz,
    void_reason text,

    created_source text NOT NULL,
    created_by uuid,

    created_at timestamptz NOT NULL DEFAULT now(),

    -- Composite FK: version must belong to same factory as product
    CONSTRAINT fk_cmv_product_factory
        FOREIGN KEY (chemical_product_id, factory_id)
        REFERENCES public.chemical_products(id, factory_id),

    CONSTRAINT chk_cmv_record_status
        CHECK (record_status IN ('ACTIVE', 'VOID')),

    CONSTRAINT chk_cmv_version_no_positive
        CHECK (version_no > 0),

    CONSTRAINT chk_cmv_sha256_format
        CHECK (
            length(content_sha256) = 64
            AND content_sha256 ~ '^[0-9a-f]{64}$'
        ),

    CONSTRAINT chk_cmv_created_source
        CHECK (created_source IN ('MANUAL', 'PDF', 'PHOTO', 'EXCEL', 'MIGRATION')),

    -- VOID must not be current
    CONSTRAINT chk_cmv_void_not_current
        CHECK (NOT (record_status = 'VOID' AND is_current = true)),

    -- VOID must have reason and timestamp
    CONSTRAINT chk_cmv_void_fields
        CHECK (
            record_status <> 'VOID'
            OR (
                voided_at IS NOT NULL
                AND void_reason IS NOT NULL
                AND btrim(void_reason) <> ''
            )
        ),

    -- Current must not have superseded_at
    CONSTRAINT chk_cmv_current_no_superseded
        CHECK (NOT (is_current = true AND superseded_at IS NOT NULL)),

    -- ACTIVE record must not have void fields populated
    CONSTRAINT chk_cmv_active_void_null
        CHECK (
            record_status <> 'ACTIVE'
            OR (voided_at IS NULL AND void_reason IS NULL)
        )
);

-- ─── Unique Constraints ───────────────────────────────────────────────────────

-- One document can only belong to one MSDS Version
ALTER TABLE public.customer_msds_versions
    ADD CONSTRAINT uq_cmv_document UNIQUE (document_id);

-- Stable internal version numbering per product
ALTER TABLE public.customer_msds_versions
    ADD CONSTRAINT uq_cmv_product_version UNIQUE (chemical_product_id, version_no);

-- Same byte file cannot create a second Version for same product
ALTER TABLE public.customer_msds_versions
    ADD CONSTRAINT uq_cmv_product_sha UNIQUE (chemical_product_id, content_sha256);

-- ─── Partial Unique Index: max 1 current per product ─────────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS uidx_cmv_one_current
    ON public.customer_msds_versions (chemical_product_id)
    WHERE is_current = true AND record_status = 'ACTIVE';

-- ─── Indexes ─────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_cmv_factory_product
    ON public.customer_msds_versions (factory_id, chemical_product_id);

CREATE INDEX IF NOT EXISTS idx_cmv_product_current
    ON public.customer_msds_versions (chemical_product_id, is_current);

CREATE INDEX IF NOT EXISTS idx_cmv_sha256
    ON public.customer_msds_versions (content_sha256);

-- ─── RLS ─────────────────────────────────────────────────────────────────────

ALTER TABLE public.customer_msds_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY cmv_no_anon ON public.customer_msds_versions
    AS RESTRICTIVE FOR ALL TO anon USING (false);

CREATE POLICY cmv_no_authenticated ON public.customer_msds_versions
    AS RESTRICTIVE FOR ALL TO authenticated USING (false);

REVOKE ALL ON public.customer_msds_versions FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.customer_msds_versions TO service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.customer_msds_versions FROM service_role;

-- ─── Function: register_customer_msds_version ────────────────────────────────

CREATE OR REPLACE FUNCTION public.register_customer_msds_version(
    p_factory_id uuid,
    p_chemical_product_id uuid,
    p_document_id uuid,
    p_content_sha256 text,
    p_source_revision_date date,
    p_source_revision_no text,
    p_supplier_name text,
    p_created_source text,
    p_created_by uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
    v_doc record;
    v_existing_version public.customer_msds_versions%ROWTYPE;
    v_existing_doc_count integer;
    v_max_version integer;
    v_new_version_no integer;
    v_is_first boolean;
    v_new_id uuid;
BEGIN
    -- Lock product row (serialize concurrent registrations for same product)
    PERFORM id
    FROM public.chemical_products
    WHERE id = p_chemical_product_id
      AND factory_id = p_factory_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'PRODUCT_NOT_FOUND');
    END IF;

    -- Validate document contract (defense in depth)
    SELECT category, factory_id, linked_table, linked_id::uuid, is_active
    INTO v_doc
    FROM public.documents
    WHERE id = p_document_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'DOCUMENT_NOT_FOUND');
    END IF;

    IF v_doc.is_active IS FALSE THEN
        RETURN jsonb_build_object('status', 'DOCUMENT_INACTIVE');
    END IF;

    IF v_doc.category <> 'msds' THEN
        RETURN jsonb_build_object('status', 'DOCUMENT_INVALID_CATEGORY');
    END IF;

    IF v_doc.factory_id <> p_factory_id THEN
        RETURN jsonb_build_object('status', 'DOCUMENT_FACTORY_MISMATCH');
    END IF;

    IF v_doc.linked_table <> 'chemical_products' THEN
        RETURN jsonb_build_object('status', 'DOCUMENT_LINKED_TABLE_MISMATCH');
    END IF;

    IF v_doc.linked_id <> p_chemical_product_id THEN
        RETURN jsonb_build_object('status', 'DOCUMENT_LINKED_ID_MISMATCH');
    END IF;

    -- Document must not already be referenced by another version
    SELECT COUNT(*) INTO v_existing_doc_count
    FROM public.customer_msds_versions
    WHERE document_id = p_document_id;

    IF v_existing_doc_count > 0 THEN
        RETURN jsonb_build_object('status', 'DOCUMENT_ALREADY_USED');
    END IF;

    -- Check duplicate SHA (same product + same byte file)
    SELECT * INTO v_existing_version
    FROM public.customer_msds_versions
    WHERE chemical_product_id = p_chemical_product_id
      AND content_sha256 = p_content_sha256
    LIMIT 1;

    IF FOUND THEN
        RETURN jsonb_build_object(
            'status', 'NO_CHANGE',
            'version_id', v_existing_version.id,
            'version_no', v_existing_version.version_no,
            'is_current', v_existing_version.is_current,
            'record_status', v_existing_version.record_status
        );
    END IF;

    -- Allocate version_no (safe inside product row lock)
    SELECT COALESCE(MAX(version_no), 0) INTO v_max_version
    FROM public.customer_msds_versions
    WHERE chemical_product_id = p_chemical_product_id;

    v_new_version_no := v_max_version + 1;

    -- Is this the first ACTIVE version?
    SELECT COUNT(*) = 0 INTO v_is_first
    FROM public.customer_msds_versions
    WHERE chemical_product_id = p_chemical_product_id
      AND record_status = 'ACTIVE';

    -- Insert
    INSERT INTO public.customer_msds_versions (
        factory_id,
        chemical_product_id,
        document_id,
        version_no,
        content_sha256,
        source_revision_date,
        source_revision_no,
        supplier_name,
        is_current,
        record_status,
        created_source,
        created_by,
        created_at
    ) VALUES (
        p_factory_id,
        p_chemical_product_id,
        p_document_id,
        v_new_version_no,
        p_content_sha256,
        p_source_revision_date,
        p_source_revision_no,
        p_supplier_name,
        v_is_first,
        'ACTIVE',
        p_created_source,
        p_created_by,
        now()
    )
    RETURNING id INTO v_new_id;

    RETURN jsonb_build_object(
        'status', 'NEW_VERSION',
        'version_id', v_new_id,
        'version_no', v_new_version_no,
        'is_current', v_is_first,
        'record_status', 'ACTIVE'
    );
END;
$$;

REVOKE ALL ON FUNCTION public.register_customer_msds_version(
    uuid, uuid, uuid, text, date, text, text, text, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.register_customer_msds_version(
    uuid, uuid, uuid, text, date, text, text, text, uuid
) TO service_role;

-- ─── Function: promote_customer_msds_version ─────────────────────────────────

CREATE OR REPLACE FUNCTION public.promote_customer_msds_version(
    p_factory_id uuid,
    p_chemical_product_id uuid,
    p_version_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
    v_target public.customer_msds_versions%ROWTYPE;
    v_current public.customer_msds_versions%ROWTYPE;
BEGIN
    -- Lock product row
    PERFORM id
    FROM public.chemical_products
    WHERE id = p_chemical_product_id
      AND factory_id = p_factory_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'PRODUCT_NOT_FOUND');
    END IF;

    -- Fetch and lock target version
    SELECT * INTO v_target
    FROM public.customer_msds_versions
    WHERE id = p_version_id
      AND chemical_product_id = p_chemical_product_id
      AND factory_id = p_factory_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'VERSION_NOT_FOUND');
    END IF;

    IF v_target.record_status = 'VOID' THEN
        RETURN jsonb_build_object('status', 'VERSION_VOID');
    END IF;

    -- Already current (idempotent)
    IF v_target.is_current = true THEN
        RETURN jsonb_build_object('status', 'ALREADY_CURRENT', 'version_id', v_target.id);
    END IF;

    -- Find and lock existing current
    SELECT * INTO v_current
    FROM public.customer_msds_versions
    WHERE chemical_product_id = p_chemical_product_id
      AND is_current = true
      AND record_status = 'ACTIVE'
    FOR UPDATE;

    -- Demote existing current
    IF FOUND THEN
        UPDATE public.customer_msds_versions
        SET is_current = false, superseded_at = now()
        WHERE id = v_current.id;
    END IF;

    -- Promote target
    UPDATE public.customer_msds_versions
    SET is_current = true, superseded_at = NULL
    WHERE id = v_target.id;

    RETURN jsonb_build_object('status', 'PROMOTED', 'version_id', v_target.id);
END;
$$;

REVOKE ALL ON FUNCTION public.promote_customer_msds_version(uuid, uuid, uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.promote_customer_msds_version(uuid, uuid, uuid)
    TO service_role;

-- ─── Function: void_customer_msds_version ────────────────────────────────────

CREATE OR REPLACE FUNCTION public.void_customer_msds_version(
    p_factory_id uuid,
    p_chemical_product_id uuid,
    p_version_id uuid,
    p_void_reason text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
    v_version public.customer_msds_versions%ROWTYPE;
BEGIN
    -- Lock product row
    PERFORM id
    FROM public.chemical_products
    WHERE id = p_chemical_product_id
      AND factory_id = p_factory_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'PRODUCT_NOT_FOUND');
    END IF;

    -- Fetch and lock version
    SELECT * INTO v_version
    FROM public.customer_msds_versions
    WHERE id = p_version_id
      AND chemical_product_id = p_chemical_product_id
      AND factory_id = p_factory_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'VERSION_NOT_FOUND');
    END IF;

    -- Already VOID (idempotent)
    IF v_version.record_status = 'VOID' THEN
        RETURN jsonb_build_object('status', 'ALREADY_VOID', 'version_id', v_version.id);
    END IF;

    -- Void
    UPDATE public.customer_msds_versions
    SET
        record_status = 'VOID',
        is_current = false,
        voided_at = now(),
        void_reason = p_void_reason
    WHERE id = v_version.id;

    RETURN jsonb_build_object('status', 'VOIDED', 'version_id', v_version.id);
END;
$$;

REVOKE ALL ON FUNCTION public.void_customer_msds_version(uuid, uuid, uuid, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.void_customer_msds_version(uuid, uuid, uuid, text)
    TO service_role;
