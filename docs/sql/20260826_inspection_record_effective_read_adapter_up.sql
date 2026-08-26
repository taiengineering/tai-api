-- WP-INSPECTION-OPS-01 / OBJ-01 INSPECTION RECORD / KNOT-2
-- EFFECTIVE READ ADAPTER — UP
--
-- ARTIFACT ONLY. NOT applied in the KNOT-2 implementation work order.
-- Adds a READ-ONLY list adapter that reuses the single-record resolver.
-- Base ledger and STEP-1A foundation objects are never mutated here.
--
-- Object created:
--   func  fn_list_effective_inspection_records_by_inspector(uuid, integer)
--         RETURNS jsonb  (STABLE, SECURITY DEFINER, service_role EXECUTE only)

BEGIN;

CREATE OR REPLACE FUNCTION public.fn_list_effective_inspection_records_by_inspector(
    p_inspector_id uuid,
    p_limit        integer
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $list$
DECLARE
    v_id    uuid;
    v_rec   jsonb;
    v_arr   jsonb := '[]'::jsonb;
    v_limit integer;
BEGIN
    v_limit := GREATEST(COALESCE(p_limit, 50), 0);

    -- candidate = base inspector UNION journal after_snapshot inspector.
    -- inspector_id itself can be changed by a correction voucher, so the base
    -- column alone is insufficient. Each candidate is resolved ONLY via the
    -- single-record resolver (folding is never reimplemented here).
    FOR v_id IN
        SELECT DISTINCT c.inspection_id FROM (
            SELECT si.id AS inspection_id
            FROM public.safety_inspections si
            WHERE si.inspector_id = p_inspector_id
            UNION
            SELECT j.inspection_id
            FROM public.safety_inspection_record_journal j
            WHERE j.after_snapshot->>'inspector_id' = p_inspector_id::text
        ) c
    LOOP
        v_rec := public.fn_resolve_inspection_record(v_id);
        -- fail-closed: an underlying resolver error is propagated, never silently dropped
        IF v_rec ? 'error' THEN
            RETURN v_rec;
        END IF;
        -- effective filter: current record is active AND current inspector is this inspector
        IF COALESCE((v_rec->>'is_active')::boolean, false) = true
           AND (v_rec->>'inspector_id') = p_inspector_id::text THEN
            v_arr := v_arr || jsonb_build_array(v_rec);
        END IF;
    END LOOP;

    -- deterministic sort (effective inspection_date DESC NULLS LAST, inspection_id DESC)
    -- + limit. inspection_date is compared as its stored JSON text (ISO 8601); there is
    -- no timestamptz cast, so a malformed snapshot cannot raise a SQL exception here.
    SELECT COALESCE(jsonb_agg(elem ORDER BY rn), '[]'::jsonb)
    INTO v_arr
    FROM (
        SELECT elem,
               row_number() OVER (
                   ORDER BY (elem->>'inspection_date') DESC NULLS LAST,
                            (elem->>'inspection_id') DESC
               ) AS rn
        FROM jsonb_array_elements(v_arr) elem
    ) s
    WHERE rn <= v_limit;

    RETURN v_arr;
END;
$list$;

-- backend (service_role) only; no anon/authenticated/PUBLIC execute
REVOKE ALL ON FUNCTION public.fn_list_effective_inspection_records_by_inspector(uuid, integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_list_effective_inspection_records_by_inspector(uuid, integer) TO service_role;

COMMIT;
