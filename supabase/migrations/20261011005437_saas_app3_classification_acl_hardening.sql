-- WO-013R: fix explicit Supabase default grants on already-created objects.
-- This migration intentionally changes ONLY three existing object ACLs.
revoke all privileges on table public.factory_legal_classifications from service_role;
grant select, insert, update on table public.factory_legal_classifications to service_role;

revoke all privileges on table public.factory_legal_classification_events from service_role;
grant select, insert on table public.factory_legal_classification_events to service_role;

revoke execute on function public.fn_factory_legal_classification_audit()
  from public, anon, authenticated;
grant execute on function public.fn_factory_legal_classification_audit()
  to service_role;
