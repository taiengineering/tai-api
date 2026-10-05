-- WO-QA-H3B-PROVENANCE-GATE-001 — tested deployment identity per QA run
ALTER TABLE qa_runs
ADD COLUMN tested_product_heads jsonb NULL;

ALTER TABLE qa_runs
ADD CONSTRAINT chk_qa_runs_tested_product_heads CHECK (
    tested_product_heads IS NULL
    OR (
        jsonb_typeof(tested_product_heads) = 'object'
        AND tested_product_heads ? 'tai-api'
        AND tested_product_heads ? 'tai-admin'
        AND tested_product_heads ? 'tai-www'
        AND (SELECT COUNT(*) FROM jsonb_object_keys(tested_product_heads)) = 3
        AND (tested_product_heads->>'tai-api') ~ '^[0-9a-f]{40}$'
        AND (tested_product_heads->>'tai-admin') ~ '^[0-9a-f]{40}$'
        AND (tested_product_heads->>'tai-www') ~ '^[0-9a-f]{40}$'
    )
);
