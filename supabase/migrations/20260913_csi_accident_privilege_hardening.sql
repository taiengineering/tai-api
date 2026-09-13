-- OBJ-CSI privilege hardening (idempotent).
-- Reproduces production extra REVOKE after 20260913_csi_accident_catalog.sql.
-- Data mutation = 0. DROP = 0. No TRUNCATE/DELETE execution.

REVOKE ALL ON public.csi_accident_cases FROM PUBLIC;
REVOKE ALL ON public.csi_accident_cases FROM anon;
REVOKE ALL ON public.csi_accident_cases FROM authenticated;
REVOKE ALL ON public.csi_accident_snapshots FROM PUBLIC;
REVOKE ALL ON public.csi_accident_snapshots FROM anon;
REVOKE ALL ON public.csi_accident_snapshots FROM authenticated;
REVOKE ALL ON public.csi_accident_snapshot_items FROM PUBLIC;
REVOKE ALL ON public.csi_accident_snapshot_items FROM anon;
REVOKE ALL ON public.csi_accident_snapshot_items FROM authenticated;

GRANT SELECT, INSERT, UPDATE ON public.csi_accident_cases TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.csi_accident_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.csi_accident_snapshot_items TO service_role;

REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.csi_accident_cases FROM service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.csi_accident_snapshots FROM service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.csi_accident_snapshot_items FROM service_role;

REVOKE ALL ON public.csi_accident_current FROM PUBLIC;
REVOKE ALL ON public.csi_accident_current FROM anon;
REVOKE ALL ON public.csi_accident_current FROM authenticated;

GRANT SELECT ON public.csi_accident_current TO service_role;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.csi_accident_current FROM service_role;
