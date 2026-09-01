-- WO-SAFE-LEGAL-BLD-CANONICAL-IMPLEMENT-001 / STEP2 — BUILDING factories canonical extension (DOWN)
--
-- STEP2 UP 이 추가한 10 column + 1 check 만 제거한다. 기존 column/constraint 삭제 0. repeat-safe.

BEGIN;

ALTER TABLE public.factories DROP CONSTRAINT IF EXISTS ck_factories_water_tank_ton;

ALTER TABLE public.factories
    DROP COLUMN IF EXISTS has_sprinkler,
    DROP COLUMN IF EXISTS has_fire_hydrant,
    DROP COLUMN IF EXISTS has_emergency_broadcast,
    DROP COLUMN IF EXISTS has_emergency_gen,
    DROP COLUMN IF EXISTS has_gas,
    DROP COLUMN IF EXISTS has_hazmat_storage,
    DROP COLUMN IF EXISTS has_water_tank,
    DROP COLUMN IF EXISTS water_tank_ton,
    DROP COLUMN IF EXISTS multi_use_type,
    DROP COLUMN IF EXISTS has_smoke_control;

COMMIT;
