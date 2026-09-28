-- ─────────────────────────────────────────────────────────────────────────────
-- ARTIFACT ONLY — PRODUCTION APPLY = 0 — OWNER APPROVAL REQUIRED
-- ─────────────────────────────────────────────────────────────────────────────
-- Source : WO-PRICING-V2-BE-OBJ10-C Atomic Contract Persistence V2
-- Date   : 2026-09-28
-- Branch : docs/pricing-canonical-20260927
-- Status : GPT INDEPENDENT VERIFY REQUIRED before any application
-- ─────────────────────────────────────────────────────────────────────────────
-- 이 파일은 Production DDL을 적용하지 않는다.
-- Production 스키마 적용은 GPT 독립검증 + Owner 승인 후 별도 WO에서 진행한다.
-- Production apply = 0 / DDL = artifact only
-- ─────────────────────────────────────────────────────────────────────────────


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 1: Tables (promoted from OBJ04 DDL proposal verbatim)
-- ═══════════════════════════════════════════════════════════════════════════

-- TABLE 1: public.saas_contract_commercial_versions

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


-- TABLE 2: public.saas_contract_site_scopes

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


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 2: Service-role-only ACL (REVOKE ALL + minimal GRANT)
-- ═══════════════════════════════════════════════════════════════════════════

-- PUBLIC / anon / authenticated: 모든 권한 전면 박탈 (TRUNCATE 포함)
REVOKE ALL PRIVILEGES ON TABLE public.saas_contract_commercial_versions
    FROM PUBLIC, anon, authenticated;

REVOKE ALL PRIVILEGES ON TABLE public.saas_contract_site_scopes
    FROM PUBLIC, anon, authenticated;

-- service_role: 함수 실행에 필요한 최소 권한 (SELECT + INSERT)
-- 함수에서 UPDATE/DELETE 없음 — 최소권한 원칙 적용
GRANT SELECT, INSERT ON TABLE public.saas_contract_commercial_versions TO service_role;
GRANT SELECT, INSERT ON TABLE public.saas_contract_site_scopes TO service_role;


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 3: apply_saas_v2_contract_atomic Function
-- ═══════════════════════════════════════════════════════════════════════════
--
-- 역할: payment + contract + commercial_version + site_scopes를 1 트랜잭션으로 원자 저장.
-- 보안: SECURITY INVOKER (DEFINER 금지), search_path = '' (schema injection 방지).
-- 호출자: service_role 전용.
-- DB write: contracts 1, payments.contract_id UPDATE 1,
--           saas_contract_commercial_versions 1, saas_contract_site_scopes N.
-- 멱등성: ALREADY_APPLIED 반환 (raise X). site_scopes 포함 완전 상태 검증.
-- 부분 상태: V2_ATOMIC_PARTIAL_STATE 반환 (fail-closed, 3 경로).
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.apply_saas_v2_contract_atomic(
    p_payment_id          uuid,
    p_contract_row        jsonb,
    p_commercial_version  jsonb,
    p_site_scopes         jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_payment_status_code  text;
    v_payment_contract_id  uuid;
    v_contract_id          uuid;
    v_cv_id                uuid;
    v_cv_tier              text;
    v_scope_count          int;
    v_commercial_id        uuid;
    v_scope                jsonb;
BEGIN
    -- Step 1: Lock payment row — concurrent duplicate calls 차단
    SELECT status_code, contract_id
    INTO   v_payment_status_code, v_payment_contract_id
    FROM   public.payments
    WHERE  id = p_payment_id
    FOR UPDATE;

    -- Step 2: 결제 행 존재 확인
    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'status',     'V2_PAYMENT_NOT_FOUND',
            'payment_id', p_payment_id
        );
    END IF;

    -- Step 3: 결제 성공 상태 검증
    IF v_payment_status_code NOT IN ('PAID', 'SUCCESS') THEN
        RETURN jsonb_build_object(
            'status',      'V2_PAYMENT_NOT_PAID',
            'payment_id',  p_payment_id,
            'status_code', v_payment_status_code
        );
    END IF;

    -- Step 4: p_contract_row에서 contract_id 추출
    v_contract_id := (p_contract_row->>'id')::uuid;

    -- Step 5: 멱등성 — 이미 contract_id가 연결된 결제
    --         ALREADY_APPLIED = commercial v1 + STANDARD tiers의 site_scopes 완전 존재
    IF v_payment_contract_id IS NOT NULL THEN
        -- commercial version v1 조회
        SELECT id, product_tier
        INTO   v_cv_id, v_cv_tier
        FROM   public.saas_contract_commercial_versions
        WHERE  contract_id = v_payment_contract_id
          AND  version_no  = 1;

        IF NOT FOUND THEN
            -- contract_id 연결됐지만 commercial_version 없음 → 부분 상태 (fail-closed)
            RETURN jsonb_build_object(
                'status',      'V2_ATOMIC_PARTIAL_STATE',
                'payment_id',  p_payment_id,
                'contract_id', v_payment_contract_id
            );
        END IF;

        -- STANDARD tiers(MANAGER/FIELD): exact site_scope 일치 검증 (PATCH2 — B1)
        IF v_cv_tier IN ('MANAGER', 'FIELD') THEN
            -- Check 1: stored = 0 → partial
            SELECT COUNT(*)
            INTO   v_scope_count
            FROM   public.saas_contract_site_scopes
            WHERE  commercial_version_id = v_cv_id;

            IF v_scope_count = 0 THEN
                RETURN jsonb_build_object(
                    'status',      'V2_ATOMIC_PARTIAL_STATE',
                    'payment_id',  p_payment_id,
                    'contract_id', v_payment_contract_id
                );
            END IF;

            -- Check 2: duplicate (entity_type, entity_id) in input → partial
            IF EXISTS (
                SELECT 1 FROM (
                    SELECT e->>'entity_type' AS et, e->>'entity_id' AS ei
                    FROM   jsonb_array_elements(p_site_scopes) e
                ) t
                GROUP BY et, ei
                HAVING COUNT(*) > 1
            ) THEN
                RETURN jsonb_build_object(
                    'status',      'V2_ATOMIC_PARTIAL_STATE',
                    'payment_id',  p_payment_id,
                    'contract_id', v_payment_contract_id
                );
            END IF;

            -- Check 3: count mismatch → partial (extra or missing)
            IF v_scope_count != jsonb_array_length(p_site_scopes) THEN
                RETURN jsonb_build_object(
                    'status',      'V2_ATOMIC_PARTIAL_STATE',
                    'payment_id',  p_payment_id,
                    'contract_id', v_payment_contract_id
                );
            END IF;

            -- Check 4: every expected tuple exists (NULL-safe base_band_code)
            IF EXISTS (
                SELECT 1
                FROM   jsonb_array_elements(p_site_scopes) AS expected
                WHERE  NOT EXISTS (
                    SELECT 1
                    FROM   public.saas_contract_site_scopes AS stored
                    WHERE  stored.commercial_version_id = v_cv_id
                      AND  stored.entity_type           = expected->>'entity_type'
                      AND  stored.entity_id             = (expected->>'entity_id')::uuid
                      AND  stored.sector                = expected->>'sector'
                      AND  stored.base_band_code IS NOT DISTINCT FROM expected->>'base_band_code'
                )
            ) THEN
                RETURN jsonb_build_object(
                    'status',      'V2_ATOMIC_PARTIAL_STATE',
                    'payment_id',  p_payment_id,
                    'contract_id', v_payment_contract_id
                );
            END IF;
        END IF;

        -- 정상 완료 상태 (site_scopes 완전 일치 확인됨)
        RETURN jsonb_build_object(
            'status',      'ALREADY_APPLIED',
            'payment_id',  p_payment_id,
            'contract_id', v_payment_contract_id
        );
    END IF;

    -- Step 6: 반대 방향 부분 상태 탐지 — contract 행은 있지만 payment 미연결
    IF EXISTS (SELECT 1 FROM public.contracts WHERE id = v_contract_id) THEN
        RETURN jsonb_build_object(
            'status',      'V2_ATOMIC_PARTIAL_STATE',
            'payment_id',  p_payment_id,
            'contract_id', v_contract_id
        );
    END IF;

    -- Step 6.5: contract_id 정합성 검증 — p_contract_row.id == p_commercial_version.contract_id
    IF (p_commercial_version->>'contract_id')::uuid IS DISTINCT FROM v_contract_id THEN
        RETURN jsonb_build_object(
            'status',         'V2_CONTRACT_ID_MISMATCH',
            'payment_id',     p_payment_id,
            'contract_id',    v_contract_id,
            'cv_contract_id', p_commercial_version->>'contract_id'
        );
    END IF;

    -- Step 6.6: version_no = 1 강제 — 최초 적용은 반드시 v1
    IF (p_commercial_version->>'version_no')::integer IS DISTINCT FROM 1 THEN
        RETURN jsonb_build_object(
            'status',     'V2_VERSION_NO_INVALID',
            'payment_id', p_payment_id,
            'version_no', (p_commercial_version->>'version_no')::integer
        );
    END IF;

    -- Step 7: contracts 행 INSERT (명시적 컬럼 목록 — 누락 컬럼은 DB DEFAULT 적용)
    INSERT INTO public.contracts (
        id,
        contract_no,
        company_id,
        status_code,
        start_date,
        end_date,
        service_type,
        contract_amount,
        vat_amount,
        total_amount,
        paid_amount,
        paid_at,
        is_active,
        created_at,
        updated_at,
        memo,
        plan_code,
        quote_id
    )
    VALUES (
        (p_contract_row->>'id')::uuid,
        p_contract_row->>'contract_no',
        (p_contract_row->>'company_id')::uuid,
        p_contract_row->>'status_code',
        (p_contract_row->>'start_date')::date,
        (p_contract_row->>'end_date')::date,
        p_contract_row->>'service_type',
        (p_contract_row->>'contract_amount')::numeric,
        (p_contract_row->>'vat_amount')::numeric,
        (p_contract_row->>'total_amount')::numeric,
        (p_contract_row->>'paid_amount')::numeric,
        (p_contract_row->>'paid_at')::timestamptz,
        (p_contract_row->>'is_active')::boolean,
        (p_contract_row->>'created_at')::timestamptz,
        (p_contract_row->>'updated_at')::timestamptz,
        p_contract_row->>'memo',
        p_contract_row->>'plan_code',
        (p_contract_row->>'quote_id')::uuid
    );

    -- Step 8: payments.contract_id 연결
    UPDATE public.payments
    SET    contract_id = v_contract_id
    WHERE  id          = p_payment_id;

    -- Step 9: commercial version INSERT → generated id 캡처
    INSERT INTO public.saas_contract_commercial_versions (
        contract_id,
        version_no,
        commercial_schema_version,
        product_tier,
        pricing_mode,
        worker_capacity,
        term_months,
        pricing_result_status,
        pricing_policy_version,
        pricing_snapshot,
        effective_from,
        superseded_at,
        created_by
    )
    VALUES (
        (p_commercial_version->>'contract_id')::uuid,
        (p_commercial_version->>'version_no')::integer,
        p_commercial_version->>'commercial_schema_version',
        p_commercial_version->>'product_tier',
        p_commercial_version->>'pricing_mode',
        (p_commercial_version->>'worker_capacity')::integer,
        (p_commercial_version->>'term_months')::integer,
        p_commercial_version->>'pricing_result_status',
        p_commercial_version->>'pricing_policy_version',
        -- JSON null('null'::jsonb) → SQL NULL で格納
        NULLIF(p_commercial_version->'pricing_snapshot', 'null'::jsonb),
        (p_commercial_version->>'effective_from')::timestamptz,
        (p_commercial_version->>'superseded_at')::timestamptz,
        (p_commercial_version->>'created_by')::uuid
    )
    RETURNING id INTO v_commercial_id;

    -- Step 10: site scopes INSERT (JSONB array loop)
    FOR v_scope IN SELECT * FROM jsonb_array_elements(p_site_scopes)
    LOOP
        INSERT INTO public.saas_contract_site_scopes (
            commercial_version_id,
            entity_type,
            entity_id,
            sector,
            base_band_code
        )
        VALUES (
            v_commercial_id,
            v_scope->>'entity_type',
            (v_scope->>'entity_id')::uuid,
            v_scope->>'sector',
            v_scope->>'base_band_code'
        );
    END LOOP;

    -- Step 11: 성공 반환
    RETURN jsonb_build_object(
        'status',                'APPLIED',
        'payment_id',            p_payment_id,
        'contract_id',           v_contract_id,
        'commercial_version_id', v_commercial_id
    );
END;
$$;


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 4: Execute Permission — service_role 전용
-- ═══════════════════════════════════════════════════════════════════════════

REVOKE EXECUTE ON FUNCTION public.apply_saas_v2_contract_atomic(uuid, jsonb, jsonb, jsonb)
    FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.apply_saas_v2_contract_atomic(uuid, jsonb, jsonb, jsonb)
    FROM anon;

REVOKE EXECUTE ON FUNCTION public.apply_saas_v2_contract_atomic(uuid, jsonb, jsonb, jsonb)
    FROM authenticated;

GRANT EXECUTE ON FUNCTION public.apply_saas_v2_contract_atomic(uuid, jsonb, jsonb, jsonb)
    TO service_role;
