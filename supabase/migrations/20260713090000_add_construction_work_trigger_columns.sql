-- DEV-IN-006: restore construction-work trigger contract (INPUT_DEAD fix)
--
-- The emitter services/trigger_generator.WORK_FIELD_MAP already maps:
--   has_excavation_work  -> WORK:EXCAVATION
--   has_welding_work     -> WORK:WELDING
--   has_demolition_work  -> WORK:DEMOLITION
-- and the detector (TRIGGER_SPECS) + binder (_TRIGGER_TO_SCOPE_SLOTS) already
-- carry those codes. But these columns were missing from public.factories, so the
-- codes were never emitted (INPUT_DEAD). This migration adds only the 3 columns.
--
-- Nullable boolean, DEFAULT NULL — matches existing has_* convention and preserves
-- UNKNOWN semantics (null -> UNKNOWN in FacilityProfile._tri; false/true -> PRESENT).
-- Apply via approved migration path in dev/verification env only. NOT production console.

ALTER TABLE public.factories ADD COLUMN IF NOT EXISTS has_excavation_work boolean;
ALTER TABLE public.factories ADD COLUMN IF NOT EXISTS has_welding_work    boolean;
ALTER TABLE public.factories ADD COLUMN IF NOT EXISTS has_demolition_work boolean;

COMMENT ON COLUMN public.factories.has_excavation_work IS 'DEV-IN-006 굴착작업 유무 -> WORK:EXCAVATION (null=UNKNOWN)';
COMMENT ON COLUMN public.factories.has_welding_work    IS 'DEV-IN-006 용접작업 유무 -> WORK:WELDING (null=UNKNOWN)';
COMMENT ON COLUMN public.factories.has_demolition_work IS 'DEV-IN-006 해체/철거작업 유무 -> WORK:DEMOLITION (null=UNKNOWN)';
