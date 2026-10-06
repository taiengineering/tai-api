-- WO-LFR-OBJ-B03-P4A-S1-PRIVILEGE-PATCH-01
-- Explicit backend-only privileges for hazardous material event records.

REVOKE ALL
ON TABLE public.factory_hazardous_material_events
FROM anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.factory_hazardous_material_events
TO service_role;
