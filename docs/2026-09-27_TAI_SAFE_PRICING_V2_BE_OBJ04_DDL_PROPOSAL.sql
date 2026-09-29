-- PROPOSAL ONLY
-- NOT APPLIED
-- ─────────────────────────────────────────────────────────────────────────────
-- Source : WO-PRICING-V2-BE-OBJ04 Commercial Contract Storage V2
-- Date   : 2026-09-27
-- Branch : docs/pricing-canonical-20260927
-- Status : GPT INDEPENDENT VERIFY REQUIRED before any application
-- ─────────────────────────────────────────────────────────────────────────────
-- 이 파일은 Production DDL을 적용하지 않는다.
-- 실제 Supabase migration 파일이 아니다.
-- Production 스키마 적용은 GPT 독립검증 + Owner 승인 후 별도 WO에서 진행한다.
-- ─────────────────────────────────────────────────────────────────────────────


-- ═══════════════════════════════════════════════════════════════════════════
-- TABLE 1: public.saas_contract_commercial_versions
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE public.saas_contract_commercial_versions (
    id                          uuid            NOT NULL DEFAULT gen_random_uuid(),
    contract_id                 uuid            NOT NULL,
    version_no                  integer         NOT NULL,

    commercial_schema_version   text            NOT NULL,

    product_tier                text            NOT NULL,
    pricing_mode                text            NOT NULL,

    worker_capacity             integer         NOT NULL,
    term_months                 integer         NOT NULL,

    pricing_result_status       text            NOT NULL,
    pricing_policy_version      text            NULL,
    pricing_snapshot            jsonb           NULL,

    effective_from              timestamptz     NOT NULL,
    superseded_at               timestamptz     NULL,

    created_at                  timestamptz     NOT NULL DEFAULT now(),
    created_by                  uuid            NULL,

    -- ── CHECK constraints ────────────────────────────────────────────────
    CONSTRAINT chk_saas_ccv_schema_version
        CHECK (commercial_schema_version = 'SAAS_CONTRACT_COMMERCIAL_V2'),

    CONSTRAINT chk_saas_ccv_product_tier
        CHECK (product_tier IN ('MANAGER', 'FIELD', 'CUSTOM')),

    CONSTRAINT chk_saas_ccv_pricing_mode
        CHECK (pricing_mode IN ('STANDARD', 'CUSTOM')),

    CONSTRAINT chk_saas_ccv_worker_capacity
        CHECK (worker_capacity >= 0),

    CONSTRAINT chk_saas_ccv_term_months
        CHECK (term_months IN (1, 3, 6, 9, 12)),

    CONSTRAINT chk_saas_ccv_pricing_result_status
        CHECK (pricing_result_status IN ('READY', 'CUSTOM_REQUIRED')),

    CONSTRAINT chk_saas_ccv_version_no
        CHECK (version_no >= 1),

    -- Tier/Mode canonical combination
    CONSTRAINT chk_saas_ccv_tier_mode_combo
        CHECK (
            (product_tier = 'MANAGER' AND pricing_mode = 'STANDARD')
            OR (product_tier = 'FIELD'   AND pricing_mode = 'STANDARD')
            OR (product_tier = 'CUSTOM'  AND pricing_mode = 'CUSTOM')
        ),

    -- MANAGER는 worker_capacity = 0
    CONSTRAINT chk_saas_ccv_manager_no_workers
        CHECK (
            product_tier != 'MANAGER' OR worker_capacity = 0
        ),

    -- STANDARD(MANAGER/FIELD): READY + policy_version + snapshot 필수
    CONSTRAINT chk_saas_ccv_standard_ready
        CHECK (
            product_tier NOT IN ('MANAGER', 'FIELD')
            OR (
                pricing_result_status = 'READY'
                AND pricing_policy_version IS NOT NULL
                AND pricing_snapshot IS NOT NULL
            )
        ),

    -- CUSTOM: CUSTOM_REQUIRED + policy_version=NULL + snapshot=NULL
    CONSTRAINT chk_saas_ccv_custom_no_snapshot
        CHECK (
            product_tier != 'CUSTOM'
            OR (
                pricing_result_status = 'CUSTOM_REQUIRED'
                AND pricing_policy_version IS NULL
                AND pricing_snapshot IS NULL
            )
        ),

    -- effective period ordering
    CONSTRAINT chk_saas_ccv_effective_period
        CHECK (
            superseded_at IS NULL
            OR superseded_at >= effective_from
        ),

    -- ── Primary Key ──────────────────────────────────────────────────────
    CONSTRAINT pk_saas_contract_commercial_versions
        PRIMARY KEY (id),

    -- ── Foreign Key ──────────────────────────────────────────────────────
    CONSTRAINT fk_saas_ccv_contracts
        FOREIGN KEY (contract_id)
        REFERENCES public.contracts (id)
        ON DELETE RESTRICT
);

-- ── Indexes ──────────────────────────────────────────────────────────────────

CREATE INDEX idx_saas_ccv_contract_id
    ON public.saas_contract_commercial_versions (contract_id);

-- version_no uniqueness per contract
CREATE UNIQUE INDEX uq_saas_ccv_contract_version_no
    ON public.saas_contract_commercial_versions (contract_id, version_no);

-- 한 Contract에 current version 최대 1개 (superseded_at IS NULL)
CREATE UNIQUE INDEX uq_saas_ccv_current_version
    ON public.saas_contract_commercial_versions (contract_id)
    WHERE superseded_at IS NULL;

-- ── Row Level Security ────────────────────────────────────────────────────────

ALTER TABLE public.saas_contract_commercial_versions ENABLE ROW LEVEL SECURITY;

-- NO POLICIES CREATED
-- anon policy   = 0
-- authenticated policy = 0
-- Backend runtime 접근 방식 확정 후 별도 Object에서 정의한다.


-- ═══════════════════════════════════════════════════════════════════════════
-- TABLE 2: public.saas_contract_site_scopes
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE public.saas_contract_site_scopes (
    id                      uuid            NOT NULL DEFAULT gen_random_uuid(),
    commercial_version_id   uuid            NOT NULL,

    entity_type             text            NOT NULL,
    entity_id               uuid            NOT NULL,
    sector                  text            NOT NULL,
    base_band_code          text            NULL,

    created_at              timestamptz     NOT NULL DEFAULT now(),

    -- ── CHECK constraints ────────────────────────────────────────────────
    CONSTRAINT chk_saas_css_entity_type
        CHECK (entity_type IN ('factory', 'site')),

    CONSTRAINT chk_saas_css_sector
        CHECK (sector IN ('INDUSTRY', 'BUILDING', 'CONSTRUCTION')),

    -- Sector/EntityType canonical mapping
    CONSTRAINT chk_saas_css_sector_entity_type
        CHECK (
            (sector = 'INDUSTRY'     AND entity_type = 'factory')
            OR (sector = 'BUILDING'  AND entity_type = 'factory')
            OR (sector = 'CONSTRUCTION' AND entity_type = 'site')
        ),

    -- ── Primary Key ──────────────────────────────────────────────────────
    CONSTRAINT pk_saas_contract_site_scopes
        PRIMARY KEY (id),

    -- ── Foreign Key ──────────────────────────────────────────────────────
    CONSTRAINT fk_saas_css_commercial_version
        FOREIGN KEY (commercial_version_id)
        REFERENCES public.saas_contract_commercial_versions (id)
        ON DELETE RESTRICT
);

-- ── Indexes ──────────────────────────────────────────────────────────────────

CREATE INDEX idx_saas_css_commercial_version_id
    ON public.saas_contract_site_scopes (commercial_version_id);

-- 한 Commercial Version 내에서 동일 사업장 중복 금지
CREATE UNIQUE INDEX uq_saas_css_site_per_version
    ON public.saas_contract_site_scopes (commercial_version_id, entity_type, entity_id);

-- entity 역방향 조회용
CREATE INDEX idx_saas_css_entity
    ON public.saas_contract_site_scopes (entity_type, entity_id);

-- ── Row Level Security ────────────────────────────────────────────────────────

ALTER TABLE public.saas_contract_site_scopes ENABLE ROW LEVEL SECURITY;

-- NO POLICIES CREATED
-- anon policy   = 0
-- authenticated policy = 0
-- Backend runtime 접근 방식 확정 후 별도 Object에서 정의한다.
