-- ─────────────────────────────────────────────────────────────────────────────
-- ARTIFACT ONLY — PRODUCTION APPLY = 0 — OWNER APPROVAL REQUIRED
-- ─────────────────────────────────────────────────────────────────────────────
-- Source : WO-PRICING-V2-BE-OBJ10-D-B2 Atomic Prepaid Renewal Persistence
--          PATCH2: payment uniqueness + scope snapshot SSOT + old-CV schema +
--                  user provenance + consumed-payment guard
-- Date   : 2026-09-28
-- Branch : docs/pricing-canonical-20260927
-- Status : GPT INDEPENDENT VERIFY REQUIRED before any application
-- ─────────────────────────────────────────────────────────────────────────────
-- 이 파일은 Production DDL을 적용하지 않는다.
-- Production 스키마 적용은 GPT 독립검증 + Owner 승인 후 별도 WO에서 진행한다.
-- Production apply = 0 / DDL = artifact only
-- ─────────────────────────────────────────────────────────────────────────────
--
-- 전제: OBJ10-C migration이 이미 적용된 상태 (saas_contract_commercial_versions,
--       saas_contract_site_scopes 테이블 존재).
-- 신규 변경:
--   renewal_payment_id uuid (nullable)  ADD COLUMN
--   FK: renewal_payment_id → payments(id)
--   UNIQUE INDEX: (renewal_payment_id) WHERE NOT NULL  → 1 payment = 1 renewal
--   apply_saas_v2_renewal_atomic 함수 (idempotent CREATE OR REPLACE)


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 1: Schema additions + ACL
-- ═══════════════════════════════════════════════════════════════════════════

-- renewal_payment_id: payment↔CV binding.
-- nullable: 신규 CV 전용 필드, 기존 legacy CV는 NULL 유지.
ALTER TABLE public.saas_contract_commercial_versions
    ADD COLUMN IF NOT EXISTS renewal_payment_id uuid;

-- FK: renewal_payment_id → payments(id). Idempotent via DO block.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.saas_contract_commercial_versions'::regclass
          AND conname  = 'fk_saas_ccv_renewal_payment_id'
    ) THEN
        ALTER TABLE public.saas_contract_commercial_versions
            ADD CONSTRAINT fk_saas_ccv_renewal_payment_id
            FOREIGN KEY (renewal_payment_id)
            REFERENCES public.payments(id);
    END IF;
END $$;

-- UNIQUE INDEX: 동일 payment_id는 전체 CV table에서 최대 1건.
-- WHERE renewal_payment_id IS NOT NULL: legacy NULL rows는 제외.
CREATE UNIQUE INDEX IF NOT EXISTS uix_saas_ccv_renewal_payment_id
    ON public.saas_contract_commercial_versions(renewal_payment_id)
    WHERE renewal_payment_id IS NOT NULL;

-- ACL: superseded_at UPDATE만 필요. renewal_payment_id는 INSERT 시 설정, UPDATE 불필요.
GRANT UPDATE (superseded_at)
    ON public.saas_contract_commercial_versions
    TO service_role;

-- contracts UPDATE: end_date/paid_amount/paid_at/updated_at
GRANT UPDATE (end_date, status_code, is_active, paid_amount, paid_at, updated_at)
    ON public.contracts
    TO service_role;


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 2: apply_saas_v2_renewal_atomic Function
-- ═══════════════════════════════════════════════════════════════════════════
--
-- 역할: Prepaid Renewal 결제 성공 후 단일 트랜잭션으로 CV 전환 + 계약 연장.
-- 보안: SECURITY INVOKER, search_path = ''
-- 호출자: service_role 전용
-- DB write:
--   saas_contract_commercial_versions.superseded_at UPDATE 1
--   saas_contract_commercial_versions INSERT 1 (renewal_payment_id = p_payment_id)
--   saas_contract_site_scopes INSERT N
--   contracts UPDATE 1
--   payments: READ only (FOR UPDATE)
-- Idempotency: renewal_payment_id = p_payment_id → same target → ALREADY_APPLIED
-- Cross-payment: renewal_payment_id exists for different payment → V2_RENEWAL_CROSS_PAYMENT_COLLISION
-- Global unique: renewal_payment_id UNIQUE INDEX → DB invariant
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.apply_saas_v2_renewal_atomic(
    p_payment_id             uuid,
    p_contract_id            uuid,
    p_quote_id               uuid,
    p_current_version_no     integer,
    p_new_commercial_version jsonb,
    p_site_scopes            jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    -- payment fields
    v_pay_status_code     text;
    v_pay_product_type    text;
    v_pay_payment_type    text;
    v_pay_plan_code       text;
    v_pay_contract_id     uuid;
    v_pay_quote_id        uuid;
    v_pay_period_months   integer;
    v_pay_supply_amount   numeric;
    v_pay_vat_amount      numeric;
    v_pay_total_amount    numeric;
    v_pay_company_id      uuid;
    v_pay_user_id         uuid;
    v_pay_paid_at         timestamptz;

    -- contract fields
    v_con_status_code     text;
    v_con_service_type    text;
    v_con_is_active       boolean;
    v_con_end_date        date;
    v_con_company_id      uuid;

    -- old CV fields
    v_old_cv_id           uuid;
    v_old_cv_schema_ver   text;
    v_old_cv_superseded   timestamptz;

    -- existing new CV (idempotency check)
    v_ex_new_cv_id              uuid;
    v_ex_new_eff_from           timestamptz;
    v_ex_new_sup                timestamptz;
    v_ex_new_schema_ver         text;
    v_ex_new_contract_id        uuid;
    v_ex_new_version_no         integer;
    v_ex_new_tier               text;
    v_ex_new_mode               text;
    v_ex_new_worker_cap         integer;
    v_ex_new_term_months        integer;
    v_ex_new_result_stat        text;
    v_ex_new_policy_ver         text;
    v_ex_new_snapshot           jsonb;
    v_ex_new_created_by         uuid;
    v_ex_new_renewal_payment_id uuid;

    -- payment consumed guard
    v_consumed_contract_id      uuid;
    v_consumed_version_no       integer;

    -- computed
    v_boundary            timestamptz;
    v_new_end_date        date;
    v_orig_boundary_date  date;
    v_expected_end_date   date;
    v_new_cv_id           uuid;
    v_scope               jsonb;
    v_scope_count         integer;
    v_snap_supply         numeric;
    v_snap_vat            numeric;
    v_snap_total          numeric;
    v_snap_term           integer;
    v_new_cv_input_sup    text;
    v_input_scope_count   integer;
    v_snap_sites          jsonb;
BEGIN

    -- ── Step 1: Lock payment row (deadlock 방지 lock 순서: pay→contract→old CV) ──
    SELECT status_code, product_type, payment_type, plan_code,
           contract_id, quote_id, period_months,
           supply_amount, vat_amount, total_amount,
           company_id, user_id, paid_at
    INTO   v_pay_status_code, v_pay_product_type, v_pay_payment_type, v_pay_plan_code,
           v_pay_contract_id, v_pay_quote_id, v_pay_period_months,
           v_pay_supply_amount, v_pay_vat_amount, v_pay_total_amount,
           v_pay_company_id, v_pay_user_id, v_pay_paid_at
    FROM   public.payments
    WHERE  id = p_payment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_PAYMENT_NOT_FOUND',
            'payment_id', p_payment_id);
    END IF;

    -- Payment guards
    IF v_pay_status_code NOT IN ('PAID', 'SUCCESS') THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_PAYMENT_NOT_PAID',
            'payment_id', p_payment_id, 'status_code', v_pay_status_code);
    END IF;

    IF v_pay_payment_type IS DISTINCT FROM 'RENEWAL' THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_PAYMENT_TYPE_INVALID',
            'payment_id', p_payment_id, 'payment_type', v_pay_payment_type);
    END IF;

    IF v_pay_product_type IS DISTINCT FROM 'SAAS' THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_PRODUCT_INVALID',
            'payment_id', p_payment_id, 'product_type', v_pay_product_type);
    END IF;

    IF v_pay_plan_code IS NOT NULL THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_LEGACY_PLAN_CODE_FORBIDDEN',
            'payment_id', p_payment_id);
    END IF;

    IF v_pay_contract_id IS DISTINCT FROM p_contract_id THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_CONTRACT_MISMATCH',
            'payment_id', p_payment_id,
            'pay_contract_id', v_pay_contract_id, 'p_contract_id', p_contract_id);
    END IF;

    IF v_pay_quote_id::text IS DISTINCT FROM p_quote_id::text THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_QUOTE_MISMATCH',
            'payment_id', p_payment_id,
            'pay_quote_id', v_pay_quote_id, 'p_quote_id', p_quote_id);
    END IF;

    -- User provenance: payment.user_id must be non-null for renewal
    IF v_pay_user_id IS NULL THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_USER_REQUIRED',
            'payment_id', p_payment_id);
    END IF;

    -- ── Step 2: Lock contract row ─────────────────────────────────────────────
    SELECT status_code, service_type, is_active, end_date, company_id
    INTO   v_con_status_code, v_con_service_type, v_con_is_active,
           v_con_end_date, v_con_company_id
    FROM   public.contracts
    WHERE  id = p_contract_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_CONTRACT_NOT_FOUND',
            'contract_id', p_contract_id);
    END IF;

    IF v_con_company_id IS DISTINCT FROM v_pay_company_id THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_COMPANY_MISMATCH',
            'contract_id', p_contract_id);
    END IF;

    IF v_con_service_type IS DISTINCT FROM 'SAAS' THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_CONTRACT_NOT_SAAS',
            'contract_id', p_contract_id, 'service_type', v_con_service_type);
    END IF;

    IF v_con_status_code IS DISTINCT FROM 'ACTIVE' OR NOT v_con_is_active THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_CONTRACT_NOT_ACTIVE',
            'contract_id', p_contract_id, 'status_code', v_con_status_code);
    END IF;

    IF v_con_end_date IS NULL THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_END_DATE_REQUIRED',
            'contract_id', p_contract_id);
    END IF;

    -- ── Step 3: Lock old CV row ───────────────────────────────────────────────
    SELECT id, commercial_schema_version, superseded_at
    INTO   v_old_cv_id, v_old_cv_schema_ver, v_old_cv_superseded
    FROM   public.saas_contract_commercial_versions
    WHERE  contract_id = p_contract_id
      AND  version_no  = p_current_version_no
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_CURRENT_CV_NOT_FOUND',
            'contract_id', p_contract_id, 'version_no', p_current_version_no);
    END IF;

    -- Old CV must be V2 schema (transition source guard)
    IF v_old_cv_schema_ver IS DISTINCT FROM 'SAAS_CONTRACT_COMMERCIAL_V2' THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_CURRENT_CV_SCHEMA_INVALID',
            'schema_version', v_old_cv_schema_ver);
    END IF;

    -- ── Global payment consumed guard ─────────────────────────────────────────
    -- Check if this payment_id was already used for ANY renewal across ALL versions.
    -- The UNIQUE INDEX enforces the DB invariant; this guard gives a deterministic result.
    SELECT contract_id, version_no
    INTO   v_consumed_contract_id, v_consumed_version_no
    FROM   public.saas_contract_commercial_versions
    WHERE  renewal_payment_id = p_payment_id;

    IF FOUND THEN
        IF v_consumed_contract_id IS DISTINCT FROM p_contract_id
           OR v_consumed_version_no IS DISTINCT FROM (p_current_version_no + 1)
        THEN
            -- Payment consumed for a different contract or version → hard fail
            RETURN jsonb_build_object('status', 'V2_RENEWAL_PAYMENT_ALREADY_CONSUMED',
                'consumed_contract_id', v_consumed_contract_id,
                'consumed_version_no',  v_consumed_version_no,
                'requested_contract_id', p_contract_id,
                'requested_version_no',  p_current_version_no + 1);
        END IF;
        -- ELSE: consumed for same target → fall through to idempotency branch (Step 4)
    END IF;

    -- ── New CV input guards ───────────────────────────────────────────────────
    IF (p_new_commercial_version->>'commercial_schema_version')
         IS DISTINCT FROM 'SAAS_CONTRACT_COMMERCIAL_V2' THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_CV_SCHEMA_INVALID');
    END IF;

    IF (p_new_commercial_version->>'contract_id')::uuid IS DISTINCT FROM p_contract_id THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_CV_CONTRACT_MISMATCH',
            'expected', p_contract_id,
            'got', p_new_commercial_version->>'contract_id');
    END IF;

    IF (p_new_commercial_version->>'version_no')::integer
         IS DISTINCT FROM (p_current_version_no + 1) THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_VERSION_MISMATCH',
            'expected', p_current_version_no + 1,
            'got', (p_new_commercial_version->>'version_no')::integer);
    END IF;

    v_new_cv_input_sup := p_new_commercial_version->>'superseded_at';
    IF v_new_cv_input_sup IS NOT NULL AND v_new_cv_input_sup != 'null' THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_CV_SUPERSEDED_AT_MUST_BE_NULL');
    END IF;

    -- Snapshot amount cross-validation vs payment
    v_snap_supply := (p_new_commercial_version->'pricing_snapshot'->>'prepaid_supply_amount')::numeric;
    v_snap_vat    := (p_new_commercial_version->'pricing_snapshot'->>'vat_amount')::numeric;
    v_snap_total  := (p_new_commercial_version->'pricing_snapshot'->>'total_amount')::numeric;
    v_snap_term   := (p_new_commercial_version->'pricing_snapshot'->>'term_months')::integer;

    IF v_snap_supply IS DISTINCT FROM v_pay_supply_amount THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_AMOUNT_MISMATCH',
            'field', 'prepaid_supply_amount');
    END IF;
    IF v_snap_vat IS DISTINCT FROM v_pay_vat_amount THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_AMOUNT_MISMATCH',
            'field', 'vat_amount');
    END IF;
    IF v_snap_total IS DISTINCT FROM v_pay_total_amount THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_AMOUNT_MISMATCH',
            'field', 'total_amount');
    END IF;
    IF v_snap_term IS DISTINCT FROM v_pay_period_months THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_AMOUNT_MISMATCH',
            'field', 'term_months');
    END IF;

    -- Top-level term_months must equal payment.period_months (3-way: snap + top-level + payment)
    IF (p_new_commercial_version->>'term_months')::integer IS DISTINCT FROM v_pay_period_months THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_TERM_MISMATCH',
            'field', 'new_cv_top_level_term_months',
            'expected', v_pay_period_months,
            'got', (p_new_commercial_version->>'term_months')::integer);
    END IF;

    -- created_by must equal payment.user_id (provenance binding, both non-null enforced above)
    IF (p_new_commercial_version->>'created_by')::uuid IS DISTINCT FROM v_pay_user_id THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_CV_CREATED_BY_MISMATCH',
            'expected', v_pay_user_id,
            'got', p_new_commercial_version->>'created_by');
    END IF;

    -- Scope completeness
    v_input_scope_count := jsonb_array_length(p_site_scopes);
    v_snap_sites        := p_new_commercial_version->'pricing_snapshot'->'sites';

    -- MANAGER/FIELD requires at least 1 scope
    IF (p_new_commercial_version->>'product_tier') IN ('MANAGER', 'FIELD')
       AND v_input_scope_count = 0
    THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_SCOPE_REQUIRED',
            'product_tier', p_new_commercial_version->>'product_tier');
    END IF;

    -- No duplicate (entity_type, entity_id) composite key in incoming scopes
    IF v_input_scope_count > 1 AND (
        SELECT COUNT(*) != COUNT(DISTINCT (elem->>'entity_type', elem->>'entity_id'))
        FROM   jsonb_array_elements(p_site_scopes) AS elem
    ) THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_SCOPE_DUPLICATE');
    END IF;

    -- MANAGER/FIELD: scope set must exactly match pricing_snapshot.sites
    -- Verifies (entity_type, entity_id, sector, base_band_code) exact-set both ways.
    IF (p_new_commercial_version->>'product_tier') IN ('MANAGER', 'FIELD') THEN
        -- Count must match
        IF jsonb_array_length(v_snap_sites) IS DISTINCT FROM v_input_scope_count THEN
            RETURN jsonb_build_object('status', 'V2_RENEWAL_SCOPE_SNAPSHOT_MISMATCH',
                'reason', 'count_mismatch',
                'snapshot_count', jsonb_array_length(v_snap_sites),
                'scope_count', v_input_scope_count);
        END IF;
        -- Every incoming scope tuple must appear in snapshot.sites
        IF EXISTS (
            SELECT 1
            FROM   jsonb_array_elements(p_site_scopes) AS sc
            WHERE  NOT EXISTS (
                SELECT 1
                FROM   jsonb_array_elements(v_snap_sites) AS ss
                WHERE  ss->>'entity_type' = sc->>'entity_type'
                  AND  ss->>'entity_id'   = sc->>'entity_id'
                  AND  ss->>'sector'      = sc->>'sector'
                  AND  ss->>'base_band_code' IS NOT DISTINCT FROM sc->>'base_band_code'
            )
        ) THEN
            RETURN jsonb_build_object('status', 'V2_RENEWAL_SCOPE_SNAPSHOT_MISMATCH',
                'reason', 'scope_not_in_snapshot');
        END IF;
        -- Every snapshot.sites tuple must appear in incoming scopes
        IF EXISTS (
            SELECT 1
            FROM   jsonb_array_elements(v_snap_sites) AS ss
            WHERE  NOT EXISTS (
                SELECT 1
                FROM   jsonb_array_elements(p_site_scopes) AS sc
                WHERE  sc->>'entity_type' = ss->>'entity_type'
                  AND  sc->>'entity_id'   = ss->>'entity_id'
                  AND  sc->>'sector'      = ss->>'sector'
                  AND  sc->>'base_band_code' IS NOT DISTINCT FROM ss->>'base_band_code'
            )
        ) THEN
            RETURN jsonb_build_object('status', 'V2_RENEWAL_SCOPE_SNAPSHOT_MISMATCH',
                'reason', 'snapshot_site_not_in_scope');
        END IF;
    END IF;

    -- ── Step 4: Check for existing target new version (idempotency) ───────────
    SELECT id,
           commercial_schema_version, contract_id, version_no,
           product_tier, pricing_mode, worker_capacity, term_months,
           pricing_result_status, pricing_policy_version, pricing_snapshot,
           effective_from, superseded_at, created_by, renewal_payment_id
    INTO   v_ex_new_cv_id,
           v_ex_new_schema_ver, v_ex_new_contract_id, v_ex_new_version_no,
           v_ex_new_tier, v_ex_new_mode, v_ex_new_worker_cap, v_ex_new_term_months,
           v_ex_new_result_stat, v_ex_new_policy_ver, v_ex_new_snapshot,
           v_ex_new_eff_from, v_ex_new_sup, v_ex_new_created_by,
           v_ex_new_renewal_payment_id
    FROM   public.saas_contract_commercial_versions
    WHERE  contract_id = p_contract_id
      AND  version_no  = p_current_version_no + 1;

    IF FOUND THEN
        -- ── IDEMPOTENCY BRANCH ────────────────────────────────────────────────

        -- BLOCKER 1: cross-payment collision (consumed guard above handles same-version reuse;
        -- this check handles different payment trying to claim same target version)
        IF v_ex_new_renewal_payment_id IS DISTINCT FROM p_payment_id THEN
            RETURN jsonb_build_object('status', 'V2_RENEWAL_CROSS_PAYMENT_COLLISION',
                'existing_payment_id', v_ex_new_renewal_payment_id,
                'requested_payment_id', p_payment_id,
                'contract_id', p_contract_id);
        END IF;

        -- A: old CV.superseded_at == existing new CV.effective_from
        IF v_old_cv_superseded IS DISTINCT FROM v_ex_new_eff_from THEN
            RETURN jsonb_build_object('status', 'V2_RENEWAL_PARTIAL_STATE',
                'reason', 'old_superseded_at_mismatch');
        END IF;

        -- D: exact new CV field comparison
        IF v_ex_new_schema_ver IS DISTINCT FROM 'SAAS_CONTRACT_COMMERCIAL_V2'
        OR v_ex_new_contract_id IS DISTINCT FROM p_contract_id
        OR v_ex_new_version_no  IS DISTINCT FROM (p_current_version_no + 1)
        OR v_ex_new_tier        IS DISTINCT FROM (p_new_commercial_version->>'product_tier')
        OR v_ex_new_mode        IS DISTINCT FROM (p_new_commercial_version->>'pricing_mode')
        OR v_ex_new_worker_cap  IS DISTINCT FROM (p_new_commercial_version->>'worker_capacity')::integer
        OR v_ex_new_term_months IS DISTINCT FROM (p_new_commercial_version->>'term_months')::integer
        OR v_ex_new_result_stat IS DISTINCT FROM (p_new_commercial_version->>'pricing_result_status')
        OR v_ex_new_policy_ver  IS DISTINCT FROM (p_new_commercial_version->>'pricing_policy_version')
        OR v_ex_new_snapshot    IS DISTINCT FROM
               NULLIF(p_new_commercial_version->'pricing_snapshot', 'null'::jsonb)
        OR v_ex_new_eff_from    IS DISTINCT FROM
               (p_new_commercial_version->>'effective_from')::timestamptz
        OR v_ex_new_sup IS NOT NULL
        OR v_ex_new_created_by  IS DISTINCT FROM
               (p_new_commercial_version->>'created_by')::uuid
        THEN
            RETURN jsonb_build_object('status', 'V2_RENEWAL_PARTIAL_STATE',
                'reason', 'new_cv_mismatch');
        END IF;

        -- E: stored scopes == incoming p_site_scopes (count + exact tuples)
        SELECT COUNT(*) INTO v_scope_count
        FROM   public.saas_contract_site_scopes
        WHERE  commercial_version_id = v_ex_new_cv_id;

        IF v_scope_count != v_input_scope_count THEN
            RETURN jsonb_build_object('status', 'V2_RENEWAL_PARTIAL_STATE',
                'reason', 'scope_count_mismatch');
        END IF;

        IF v_scope_count > 0 AND EXISTS (
            SELECT 1
            FROM   jsonb_array_elements(p_site_scopes) AS expected
            WHERE  NOT EXISTS (
                SELECT 1
                FROM   public.saas_contract_site_scopes AS stored
                WHERE  stored.commercial_version_id = v_ex_new_cv_id
                  AND  stored.entity_type           = expected->>'entity_type'
                  AND  stored.entity_id             = (expected->>'entity_id')::uuid
                  AND  stored.sector                = expected->>'sector'
                  AND  stored.base_band_code IS NOT DISTINCT FROM expected->>'base_band_code'
            )
        ) THEN
            RETURN jsonb_build_object('status', 'V2_RENEWAL_PARTIAL_STATE',
                'reason', 'scope_tuple_mismatch');
        END IF;

        -- F: contract.end_date == original_boundary_date + term_months
        v_orig_boundary_date := (v_ex_new_eff_from AT TIME ZONE 'Asia/Seoul')::date;
        v_expected_end_date  := (v_orig_boundary_date
            + ((v_ex_new_term_months || ' months')::interval))::date;

        IF v_con_end_date IS DISTINCT FROM v_expected_end_date THEN
            RETURN jsonb_build_object('status', 'V2_RENEWAL_PARTIAL_STATE',
                'reason', 'end_date_mismatch');
        END IF;

        RETURN jsonb_build_object(
            'status',      'ALREADY_APPLIED',
            'payment_id',  p_payment_id,
            'contract_id', p_contract_id,
            'new_commercial_version_id', v_ex_new_cv_id,
            'new_end_date', v_expected_end_date
        );
    END IF;

    -- ── P8: version > N+1 이미 존재하면 부분 상태 ──────────────────────────────
    IF EXISTS (
        SELECT 1
        FROM   public.saas_contract_commercial_versions
        WHERE  contract_id = p_contract_id
          AND  version_no  > p_current_version_no + 1
    ) THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_PARTIAL_STATE',
            'reason', 'unexpected_higher_version_exists');
    END IF;

    -- ── FIRST APPLY PATH ──────────────────────────────────────────────────────

    -- P1: old CV must have superseded_at = NULL
    IF v_old_cv_superseded IS NOT NULL THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_PARTIAL_STATE',
            'reason', 'old_already_superseded_no_new_cv');
    END IF;

    -- DB-derived boundary: contracts.end_date → Asia/Seoul midnight
    v_boundary := (v_con_end_date::timestamp AT TIME ZONE 'Asia/Seoul');

    -- Boundary check: new CV.effective_from must == v_boundary
    IF (p_new_commercial_version->>'effective_from')::timestamptz IS DISTINCT FROM v_boundary THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_BOUNDARY_MISMATCH',
            'expected', v_boundary,
            'got', p_new_commercial_version->>'effective_from');
    END IF;

    -- ── Writes ───────────────────────────────────────────────────────────────

    -- Write 1: supersede old CV (AND guard: concurrent-safe)
    UPDATE public.saas_contract_commercial_versions
    SET    superseded_at = v_boundary
    WHERE  id            = v_old_cv_id
      AND  superseded_at IS NULL;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'V2_RENEWAL_PARTIAL_STATE',
            'reason', 'old_update_concurrent_conflict');
    END IF;

    -- Write 2: INSERT new CV (renewal_payment_id = p_payment_id — unique key)
    INSERT INTO public.saas_contract_commercial_versions (
        contract_id, version_no, commercial_schema_version,
        product_tier, pricing_mode, worker_capacity, term_months,
        pricing_result_status, pricing_policy_version, pricing_snapshot,
        effective_from, superseded_at, created_by, renewal_payment_id
    ) VALUES (
        (p_new_commercial_version->>'contract_id')::uuid,
        (p_new_commercial_version->>'version_no')::integer,
        p_new_commercial_version->>'commercial_schema_version',
        p_new_commercial_version->>'product_tier',
        p_new_commercial_version->>'pricing_mode',
        (p_new_commercial_version->>'worker_capacity')::integer,
        (p_new_commercial_version->>'term_months')::integer,
        p_new_commercial_version->>'pricing_result_status',
        p_new_commercial_version->>'pricing_policy_version',
        NULLIF(p_new_commercial_version->'pricing_snapshot', 'null'::jsonb),
        (p_new_commercial_version->>'effective_from')::timestamptz,
        NULL,
        (p_new_commercial_version->>'created_by')::uuid,
        p_payment_id
    )
    RETURNING id INTO v_new_cv_id;

    -- Write 3: INSERT site_scopes
    FOR v_scope IN SELECT * FROM jsonb_array_elements(p_site_scopes)
    LOOP
        INSERT INTO public.saas_contract_site_scopes (
            commercial_version_id, entity_type, entity_id, sector, base_band_code
        ) VALUES (
            v_new_cv_id,
            v_scope->>'entity_type',
            (v_scope->>'entity_id')::uuid,
            v_scope->>'sector',
            v_scope->>'base_band_code'
        );
    END LOOP;

    -- Write 4: extend contract
    v_new_end_date := (v_con_end_date
        + (((p_new_commercial_version->>'term_months')::integer) || ' months')::interval
    )::date;

    UPDATE public.contracts
    SET    end_date    = v_new_end_date,
           status_code = 'ACTIVE',
           is_active   = TRUE,
           paid_amount = v_pay_total_amount,
           paid_at     = v_pay_paid_at,
           updated_at  = now()
    WHERE  id = p_contract_id;

    RETURN jsonb_build_object(
        'status',                    'APPLIED',
        'payment_id',                p_payment_id,
        'contract_id',               p_contract_id,
        'new_commercial_version_id', v_new_cv_id,
        'new_end_date',              v_new_end_date
    );
END;
$$;


-- ═══════════════════════════════════════════════════════════════════════════
-- SECTION 3: Execute Permission — service_role 전용
-- ═══════════════════════════════════════════════════════════════════════════

REVOKE EXECUTE ON FUNCTION public.apply_saas_v2_renewal_atomic(
    uuid, uuid, uuid, integer, jsonb, jsonb)
    FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.apply_saas_v2_renewal_atomic(
    uuid, uuid, uuid, integer, jsonb, jsonb)
    FROM anon;

REVOKE EXECUTE ON FUNCTION public.apply_saas_v2_renewal_atomic(
    uuid, uuid, uuid, integer, jsonb, jsonb)
    FROM authenticated;

GRANT EXECUTE ON FUNCTION public.apply_saas_v2_renewal_atomic(
    uuid, uuid, uuid, integer, jsonb, jsonb)
    TO service_role;
