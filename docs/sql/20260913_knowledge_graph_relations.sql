-- OBJ-GRAPH relation store (additive). Knowledge source tables unchanged.
-- Semantic edge is unique. method/rule live on evidence, not edge identity.
-- No DROP/TRUNCATE. No anon public grants.

CREATE TABLE IF NOT EXISTS public.knowledge_relation_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_type text NOT NULL,
  scope_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  rule_set_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
  dry_run boolean NOT NULL DEFAULT true,
  started_at timestamptz NOT NULL,
  completed_at timestamptz,
  knowledge_items_scanned integer NOT NULL DEFAULT 0,
  candidates_generated integer NOT NULL DEFAULT 0,
  accepted integer NOT NULL DEFAULT 0,
  rejected integer NOT NULL DEFAULT 0,
  duplicate_prevented integer NOT NULL DEFAULT 0,
  no_relation_items integer NOT NULL DEFAULT 0,
  metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_code text,
  error_message text
);

CREATE INDEX IF NOT EXISTS knowledge_relation_runs_status_idx
  ON public.knowledge_relation_runs (status, started_at DESC);

COMMENT ON TABLE public.knowledge_relation_runs IS
  'OBJ-GRAPH refresh ledger. Stale mutation only after COMPLETED apply.';

CREATE TABLE IF NOT EXISTS public.knowledge_relation_edges (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  edge_key text NOT NULL UNIQUE,
  edge_kind text NOT NULL CHECK (edge_kind IN ('CONTEXT', 'DIRECT')),
  source_content_type text NOT NULL,
  source_content_id text NOT NULL,
  relation_type text NOT NULL
    CHECK (relation_type IN (
      'topic','sector','industry','process','equipment','task',
      'chemical','legal_obligation','legal_article','RELATED_TO',
      'EXPLAINS','ACCIDENT_CASE_FOR','GUIDE_FOR'
    )),
  relation_key text,
  relation_label text,
  target_content_type text,
  target_content_id text,
  status text NOT NULL CHECK (status IN ('CANDIDATE', 'ACCEPTED', 'REJECTED')),
  is_active boolean NOT NULL DEFAULT true,
  first_seen_run_id uuid REFERENCES public.knowledge_relation_runs(id),
  last_seen_run_id uuid REFERENCES public.knowledge_relation_runs(id),
  stale_at timestamptz,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT knowledge_relation_edges_shape_chk CHECK (
    (edge_kind = 'CONTEXT' AND relation_key IS NOT NULL)
    OR (
      edge_kind = 'DIRECT'
      AND target_content_type IS NOT NULL
      AND target_content_id IS NOT NULL
    )
  )
);

CREATE INDEX IF NOT EXISTS knowledge_relation_edges_context_idx
  ON public.knowledge_relation_edges (relation_type, relation_key, status, is_active);

CREATE INDEX IF NOT EXISTS knowledge_relation_edges_source_idx
  ON public.knowledge_relation_edges (source_content_type, source_content_id, status, is_active);

COMMENT ON TABLE public.knowledge_relation_edges IS
  'OBJ-GRAPH semantic edges. One row per relation identity. No source body copy.';

CREATE TABLE IF NOT EXISTS public.knowledge_relation_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  edge_id uuid NOT NULL REFERENCES public.knowledge_relation_edges(id),
  evidence_key text NOT NULL,
  method text NOT NULL,
  evidence_type text,
  source_field text,
  evidence_value text,
  rule_id text,
  rule_version text,
  source_version text,
  source_content_hash text,
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  last_seen_run_id uuid REFERENCES public.knowledge_relation_runs(id),
  UNIQUE (edge_id, evidence_key)
);

CREATE INDEX IF NOT EXISTS knowledge_relation_evidence_edge_idx
  ON public.knowledge_relation_evidence (edge_id);

COMMENT ON TABLE public.knowledge_relation_evidence IS
  'Provenance for a semantic edge. Multiple evidence rows per edge allowed.';

ALTER TABLE public.knowledge_relation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_relation_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_relation_evidence ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.knowledge_relation_runs FROM anon, authenticated;
REVOKE ALL ON public.knowledge_relation_edges FROM anon, authenticated;
REVOKE ALL ON public.knowledge_relation_evidence FROM anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.knowledge_relation_runs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.knowledge_relation_edges TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.knowledge_relation_evidence TO service_role;
