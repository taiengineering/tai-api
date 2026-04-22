-- Phase 1-4 전략 B: 재수집 시 article_id FK 재연결용 스냅샷
-- Supabase에서 먼저 실행 후, force 재수집 + scripts/reconnect_fk.py 사용

CREATE TABLE IF NOT EXISTS law_article_key_map (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  old_article_id UUID NOT NULL,
  new_article_id UUID,
  article_internal_key TEXT NOT NULL,
  law_version_id UUID NOT NULL,
  migrated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_law_article_key_map_old
  ON law_article_key_map (old_article_id);

CREATE INDEX IF NOT EXISTS idx_law_article_key_map_key_ver
  ON law_article_key_map (article_internal_key, law_version_id);
