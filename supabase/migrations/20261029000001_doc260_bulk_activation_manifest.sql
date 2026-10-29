-- 20261029000001_doc260_bulk_activation_manifest.sql
-- WO-DOC260-BULK-MAINLINE-001
-- doc260_bulk_activation_manifest: BULK 활성화 203종 schema_id 매니페스트 테이블
--
-- !! NOT EXECUTED — Owner 별도 실행 승인 후 운영 DB 적용 !!
-- 순서: 이 Migration 먼저 실행 → 이후 BULK_ACTIVATION_PROPOSAL.sql 실행
--
-- 소유권: Migration 소유 (DDL). 데이터 INSERT/복구는 각 SQL 담당.
-- 직접 수정 금지.

CREATE TABLE IF NOT EXISTS doc260_bulk_activation_manifest (
  schema_id   UUID        NOT NULL PRIMARY KEY REFERENCES runtime_form_schema(id),
  captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE doc260_bulk_activation_manifest IS
  'DOC260 BULK 활성화 203종 schema_id 매니페스트. '
  'BULK_ACTIVATION_PROPOSAL.sql에서 INSERT. '
  'BULK_ROLLBACK_PROPOSAL.sql에서 복구 대상 식별에 사용. '
  '직접 수정 금지.';

-- RLS: 고객 앱 직접 수정 불허 (서비스 롤만 허용)
ALTER TABLE doc260_bulk_activation_manifest ENABLE ROW LEVEL SECURITY;
-- anon/authenticated: policy 없음 = 기본 차단
