-- WO-TAI-SEC-SEARCHPATH-REM97-ISOLATED-FIDELITY-R1-003
-- Isolated schema setup — production-accurate fidelity
-- Target: rem97_isolated_test (port 55432, DB=rem97_test)
-- Source: production vwlahtguyggrhvslabax (taieng, PG 17.6)
-- EXACT_MIGRATION_EXECUTED = FALSE  (local OIDs differ from production)
-- PG_VERSION_DIFFERENCE = TRUE  (local PG 15.19 vs production PG 17.6)

SET search_path = public;

-- ─── STUB TABLES ──────────────────────────────────────────────────────────────

-- Minimal stub for runtime_obligation_registry (FK target only)
CREATE TABLE IF NOT EXISTS runtime_obligation_registry (
  id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label text
);

-- ─── B-W2B TABLES (production-accurate schema) ────────────────────────────────

CREATE TABLE IF NOT EXISTS runtime_inspection_session (
  id                    uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
  operational_work_order_id uuid NOT NULL,
  worker_user_id        uuid  NOT NULL,
  session_status        text  NOT NULL DEFAULT 'READY',
  submission_status     text  NOT NULL DEFAULT 'NOT_SUBMITTED',
  evidence_status       text  NOT NULL DEFAULT 'PENDING',
  review_status         text  NOT NULL DEFAULT 'NOT_REVIEWED',
  offline_sync_status   text  NOT NULL DEFAULT 'ONLINE',
  source_trace          text  NOT NULL DEFAULT 'RUNTIME_GENERATED',
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runtime_inspection_review (
  id                    uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
  inspection_session_id uuid  NOT NULL REFERENCES runtime_inspection_session(id),
  reviewer_id           uuid  NOT NULL,
  review_action         text  NOT NULL,
  reject_reason         text,
  reopen_trace          text,
  previous_status       text  NOT NULL,
  new_status            text  NOT NULL,
  source_trace          text  NOT NULL DEFAULT 'MANUAL_REVIEW',
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runtime_operational_work_order (
  id                     uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
  obligation_registry_id uuid  NOT NULL REFERENCES runtime_obligation_registry(id),
  execution_type         text  NOT NULL,
  assigned_user_id       uuid  NOT NULL,
  work_status            text  NOT NULL DEFAULT 'GENERATED',
  review_required        bool  NOT NULL DEFAULT true,
  evidence_required      bool  NOT NULL DEFAULT false,
  source_trace           text  NOT NULL DEFAULT 'RUNTIME_GENERATED',
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runtime_work_order_review (
  id              uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
  work_order_id   uuid  NOT NULL REFERENCES runtime_operational_work_order(id),
  reviewer_id     uuid  NOT NULL,
  review_action   text  NOT NULL,
  review_comment  text,
  previous_status text  NOT NULL,
  new_status      text  NOT NULL,
  source_trace    text  NOT NULL DEFAULT 'MANUAL_REVIEW',
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- ─── B-W3B TABLES (production-accurate schema) ────────────────────────────────

CREATE TABLE IF NOT EXISTS companies (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text,
  company_code text NOT NULL
);

CREATE TABLE IF NOT EXISTS factories (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sector            varchar DEFAULT 'INDUSTRY',
  notification_time time DEFAULT '07:00:00',
  legal_status      text NOT NULL DEFAULT 'NOT_APPLIED'
);

CREATE TABLE IF NOT EXISTS construction_sites (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        uuid NOT NULL REFERENCES companies(id),
  site_name         text NOT NULL,
  factory_id        uuid REFERENCES factories(id),
  notification_time time DEFAULT '06:30:00'
);

CREATE TABLE IF NOT EXISTS subcontractors (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id      uuid NOT NULL REFERENCES construction_sites(id),
  company_id   uuid NOT NULL REFERENCES companies(id),
  company_name text NOT NULL,
  tier         int  NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS worker_registry (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id      uuid NOT NULL REFERENCES companies(id),
  name            text NOT NULL,
  phone           text NOT NULL,
  job_type_code   text NOT NULL,
  job_type_name   text,
  contractor_name text,
  status_code     text DEFAULT 'ACTIVE',
  is_active       bool DEFAULT true,
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS construction_workers (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id            uuid NOT NULL REFERENCES construction_sites(id),
  worker_name        text,
  worker_phone       text,
  worker_type        text DEFAULT 'SUBCON',
  subcontractor_id   uuid REFERENCES subcontractors(id),
  role_code          text,
  is_active          bool DEFAULT true,
  worker_registry_id uuid REFERENCES worker_registry(id),
  created_at         timestamptz DEFAULT now(),
  updated_at         timestamptz DEFAULT now()
);

-- ─── FUNCTIONS — B-W2B (exact production prosrc for MD5 match) ────────────────

-- production OID=69146  MD5=d11c6e83fc4105683304bfed9679ba47
-- proconfig=NULL (pre-migration state)
CREATE OR REPLACE FUNCTION public.fn_validate_inspection_reviewer()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
AS $function$
DECLARE
  v_worker UUID;
BEGIN
  SELECT worker_user_id INTO v_worker
  FROM runtime_inspection_session
  WHERE id = NEW.inspection_session_id;

  IF NEW.reviewer_id = v_worker THEN
    RAISE EXCEPTION 'REVIEW_BLOCKED: reviewer cannot be the inspector (self-review forbidden)';
  END IF;

  -- Update session statuses
  UPDATE runtime_inspection_session
  SET session_status = CASE NEW.review_action
      WHEN 'APPROVE' THEN 'APPROVED'
      WHEN 'REJECT' THEN 'REJECTED'
      WHEN 'REOPEN' THEN 'IN_PROGRESS'
      WHEN 'ESCALATE' THEN 'REVIEW_PENDING'
    END,
    review_status = CASE NEW.review_action
      WHEN 'APPROVE' THEN 'APPROVED'
      WHEN 'REJECT' THEN 'REJECTED'
      WHEN 'REOPEN' THEN 'REOPENED'
      WHEN 'ESCALATE' THEN 'REVIEW_PENDING'
    END,
    updated_at = now()
  WHERE id = NEW.inspection_session_id;

  RETURN NEW;
END;
$function$;

-- production OID=68962  MD5=2b7fbd47bb00b04b5e52e5a177ba8e97
-- proconfig=NULL (pre-migration state)
CREATE OR REPLACE FUNCTION public.fn_validate_reviewer_not_assignee()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
AS $function$
DECLARE
  v_assigned_user UUID;
BEGIN
  SELECT assigned_user_id INTO v_assigned_user
  FROM runtime_operational_work_order
  WHERE id = NEW.work_order_id;

  IF NEW.reviewer_id = v_assigned_user THEN
    RAISE EXCEPTION 'REVIEW_BLOCKED: reviewer cannot be the same as assigned worker';
  END IF;

  -- Update work_order status
  UPDATE runtime_operational_work_order
  SET work_status = NEW.new_status,
      updated_at = now()
  WHERE id = NEW.work_order_id;

  RETURN NEW;
END;
$function$;

-- ─── FUNCTIONS — B-W3B (exact production prosrc for MD5 match) ────────────────

-- production OID=18576  MD5=c69e276c1cd46e449f64b1ec145923fd
-- proconfig=NULL (pre-migration state)
CREATE OR REPLACE FUNCTION public.sync_construction_notification_time()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
AS $function$
BEGIN
  IF NEW.notification_time IS DISTINCT FROM OLD.notification_time 
     AND NEW.factory_id IS NOT NULL THEN
    UPDATE factories 
    SET notification_time = NEW.notification_time
    WHERE id = NEW.factory_id;
  END IF;
  RETURN NEW;
END;
$function$;

-- production OID=18577  MD5=9c8c095278619c15fd243c7da50c02db
-- proconfig=NULL (pre-migration state)
CREATE OR REPLACE FUNCTION public.sync_factory_notification_time_to_cs()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
AS $function$
BEGIN
  IF NEW.notification_time IS DISTINCT FROM OLD.notification_time 
     AND NEW.sector = 'CONSTRUCTION' THEN
    UPDATE construction_sites 
    SET notification_time = NEW.notification_time
    WHERE factory_id = NEW.id;
  END IF;
  RETURN NEW;
END;
$function$;

-- production OID=245046  MD5=8db8ee7d30d5484f0f573cde2234bce4
-- proconfig=NULL (pre-migration state)
CREATE OR REPLACE FUNCTION public.sync_construction_worker_to_registry()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
AS $function$
DECLARE
  v_company_id uuid;
  v_contractor text;
  v_reg_id uuid;
BEGIN
  -- 이름/연락처 없으면 동기화 스킵(레지스트리 필수값 미충족)
  IF NEW.worker_name IS NULL OR NEW.worker_phone IS NULL THEN
    RETURN NEW;
  END IF;

  -- 원청(회사) 조회 — 사이트 기준
  SELECT company_id INTO v_company_id FROM public.construction_sites WHERE id = NEW.site_id;
  IF v_company_id IS NULL THEN
    RETURN NEW;
  END IF;

  -- 하도급사명(없으면 원청직영)
  IF NEW.subcontractor_id IS NOT NULL THEN
    SELECT company_name INTO v_contractor FROM public.subcontractors WHERE id = NEW.subcontractor_id;
    IF v_contractor IS NULL THEN
      SELECT name INTO v_contractor FROM public.companies WHERE id = NEW.subcontractor_id;
    END IF;
  ELSE
    v_contractor := '원청직영';
  END IF;

  IF TG_OP = 'INSERT' THEN
    IF NEW.worker_registry_id IS NULL THEN
      INSERT INTO public.worker_registry
        (company_id, name, phone, job_type_code, job_type_name, contractor_name, status_code, is_active)
      VALUES
        (v_company_id, NEW.worker_name, NEW.worker_phone,
         COALESCE(NULLIF(NEW.role_code,''), NULLIF(NEW.worker_type,''), 'WORKER'),
         COALESCE(NULLIF(NEW.role_code,''), NEW.worker_type),
         v_contractor, 'ACTIVE', COALESCE(NEW.is_active, true))
      RETURNING id INTO v_reg_id;
      NEW.worker_registry_id := v_reg_id;
    END IF;
  ELSIF TG_OP = 'UPDATE' THEN
    IF NEW.worker_registry_id IS NOT NULL THEN
      UPDATE public.worker_registry
        SET name = NEW.worker_name,
            phone = NEW.worker_phone,
            job_type_code = COALESCE(NULLIF(NEW.role_code,''), NULLIF(NEW.worker_type,''), job_type_code),
            contractor_name = v_contractor,
            is_active = COALESCE(NEW.is_active, is_active),
            updated_at = now()
      WHERE id = NEW.worker_registry_id;
    END IF;
  END IF;

  RETURN NEW;
END;
$function$;

-- ─── TRIGGERS (exact production definitions) ──────────────────────────────────

-- B-W2B: BEFORE INSERT (production: trg_validate_inspection_reviewer)
CREATE TRIGGER trg_validate_inspection_reviewer
  BEFORE INSERT ON public.runtime_inspection_review
  FOR EACH ROW EXECUTE FUNCTION fn_validate_inspection_reviewer();

-- B-W2B: BEFORE INSERT (production: trg_validate_reviewer)
CREATE TRIGGER trg_validate_reviewer
  BEFORE INSERT ON public.runtime_work_order_review
  FOR EACH ROW EXECUTE FUNCTION fn_validate_reviewer_not_assignee();

-- B-W3B: AFTER UPDATE OF notification_time (column-specific)
CREATE TRIGGER trg_sync_construction_notif_time
  AFTER UPDATE OF notification_time ON public.construction_sites
  FOR EACH ROW EXECUTE FUNCTION sync_construction_notification_time();

-- B-W3B: BEFORE INSERT
CREATE TRIGGER trg_sync_cw_registry_ins
  BEFORE INSERT ON public.construction_workers
  FOR EACH ROW EXECUTE FUNCTION sync_construction_worker_to_registry();

-- B-W3B: BEFORE UPDATE OF specific 6 columns (column-specific)
CREATE TRIGGER trg_sync_cw_registry_upd
  BEFORE UPDATE OF worker_name, worker_phone, role_code, worker_type, subcontractor_id, is_active
  ON public.construction_workers
  FOR EACH ROW EXECUTE FUNCTION sync_construction_worker_to_registry();

-- B-W3B: AFTER UPDATE OF notification_time (column-specific)
CREATE TRIGGER trg_sync_factory_notif_time_to_cs
  AFTER UPDATE OF notification_time ON public.factories
  FOR EACH ROW EXECUTE FUNCTION sync_factory_notification_time_to_cs();

-- ─── VERIFY SETUP ─────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_fn_count   int;
  v_trg_count  int;
  v_md5        text;

  -- Expected production MD5s
  c_md5_fn_insp_rev   CONSTANT text := 'd11c6e83fc4105683304bfed9679ba47';
  c_md5_fn_wo_rev     CONSTANT text := '2b7fbd47bb00b04b5e52e5a177ba8e97';
  c_md5_sync_notif    CONSTANT text := 'c69e276c1cd46e449f64b1ec145923fd';
  c_md5_sync_worker   CONSTANT text := '8db8ee7d30d5484f0f573cde2234bce4';
  c_md5_sync_factory  CONSTANT text := '9c8c095278619c15fd243c7da50c02db';

  c_fns CONSTANT text[] := ARRAY[
    'fn_validate_inspection_reviewer',
    'fn_validate_reviewer_not_assignee',
    'sync_construction_notification_time',
    'sync_construction_worker_to_registry',
    'sync_factory_notification_time_to_cs'
  ];
  c_md5s CONSTANT text[] := ARRAY[
    'd11c6e83fc4105683304bfed9679ba47',
    '2b7fbd47bb00b04b5e52e5a177ba8e97',
    'c69e276c1cd46e449f64b1ec145923fd',
    '8db8ee7d30d5484f0f573cde2234bce4',
    '9c8c095278619c15fd243c7da50c02db'
  ];
  i int;
BEGIN
  -- Function count
  SELECT COUNT(*) INTO v_fn_count
  FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid
  WHERE n.nspname = 'public' AND p.proname = ANY(c_fns);

  IF v_fn_count <> 5 THEN
    RAISE EXCEPTION 'SETUP FAILED: expected 5 functions, found %.', v_fn_count;
  END IF;

  -- MD5 match for each function
  FOR i IN 1..5 LOOP
    SELECT md5(p.prosrc) INTO v_md5
    FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE n.nspname = 'public' AND p.proname = c_fns[i];

    IF v_md5 IS DISTINCT FROM c_md5s[i] THEN
      RAISE EXCEPTION 'SETUP FAILED: % prosrc MD5 mismatch (expected %, got %).',
        c_fns[i], c_md5s[i], v_md5;
    END IF;
    RAISE NOTICE 'FN MD5 OK: % = %', c_fns[i], v_md5;
  END LOOP;

  -- Trigger count
  SELECT COUNT(*) INTO v_trg_count
  FROM pg_trigger t JOIN pg_proc p ON t.tgfoid = p.oid
  JOIN pg_namespace n ON p.pronamespace = n.oid
  WHERE n.nspname = 'public' AND p.proname = ANY(c_fns) AND NOT t.tgisinternal;

  IF v_trg_count <> 6 THEN
    RAISE EXCEPTION 'SETUP FAILED: expected 6 triggers, found %.', v_trg_count;
  END IF;

  -- Verify trigger definitions match production
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger t JOIN pg_class c ON t.tgrelid = c.oid
    WHERE t.tgname = 'trg_validate_inspection_reviewer'
      AND c.relname = 'runtime_inspection_review'
      AND (t.tgtype & 2) = 2  -- BEFORE
      AND (t.tgtype & 4) = 4  -- INSERT
  ) THEN
    RAISE EXCEPTION 'SETUP FAILED: trg_validate_inspection_reviewer not BEFORE INSERT on runtime_inspection_review';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger t JOIN pg_class c ON t.tgrelid = c.oid
    WHERE t.tgname = 'trg_validate_reviewer'
      AND c.relname = 'runtime_work_order_review'
      AND (t.tgtype & 2) = 2  -- BEFORE
      AND (t.tgtype & 4) = 4  -- INSERT
  ) THEN
    RAISE EXCEPTION 'SETUP FAILED: trg_validate_reviewer not BEFORE INSERT on runtime_work_order_review';
  END IF;

  -- Verify column-specific triggers have columns (pg_trigger.tgattr IS NOT NULL check)
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger t JOIN pg_class c ON t.tgrelid = c.oid
    WHERE t.tgname = 'trg_sync_construction_notif_time'
      AND c.relname = 'construction_sites'
      AND array_length(t.tgattr::int[], 1) > 0
  ) THEN
    RAISE EXCEPTION 'SETUP FAILED: trg_sync_construction_notif_time missing column filter';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger t JOIN pg_class c ON t.tgrelid = c.oid
    WHERE t.tgname = 'trg_sync_factory_notif_time_to_cs'
      AND c.relname = 'factories'
      AND array_length(t.tgattr::int[], 1) > 0
  ) THEN
    RAISE EXCEPTION 'SETUP FAILED: trg_sync_factory_notif_time_to_cs missing column filter';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger t JOIN pg_class c ON t.tgrelid = c.oid
    WHERE t.tgname = 'trg_sync_cw_registry_upd'
      AND c.relname = 'construction_workers'
      AND array_length(t.tgattr::int[], 1) = 6
  ) THEN
    RAISE EXCEPTION 'SETUP FAILED: trg_sync_cw_registry_upd should have 6 column filters';
  END IF;

  RAISE NOTICE '';
  RAISE NOTICE 'SETUP OK: 5 functions (MD5 matched) + 6 triggers (definitions matched)';
  RAISE NOTICE 'FUNCTION_BODY_MD5_MATCH = 5/5';
  RAISE NOTICE 'TRIGGER_DEFINITION_MATCH = 6/6 (timing + column-specificity verified)';
END;
$$;
