-- Wave A2: add attributes JSONB column to equipment_assets for equipment source
-- numeric attribute capture (HOLD projection until C2 contract frozen).
-- Additive only — no existing column change.
-- PRODUCTION APPLY: Owner approval required before executing on production DB.

ALTER TABLE equipment_assets ADD COLUMN IF NOT EXISTS attributes JSONB;

COMMENT ON COLUMN equipment_assets.attributes IS
  'Wave A2 numeric source attributes (e.g. weight_ton, speed_rpm). '
  'Captured for replay only. Canonical numeric projection is HOLD pending C2 contract.';
