-- =====================================================================
-- WP-PERSISTENCE-02A STEP-4E — DOWN 실패 Audit (별도 자율 TX)
-- =====================================================================
-- !!! NOT EXECUTED — 별도 명시 Owner 승인 없이 실행 금지 !!!
-- 목적: STEP4E_DOWN DO 블록 실패 시 ROLLBACK_ABORTED 기록
-- 전제: STEP4E_DOWN DO 블록이 RAISE EXCEPTION으로 종료된 것을 확인 후 실행
-- 경고: DO 블록 성공 후 이 파일을 실행하면 오감지 기록이 남습니다.
--       DO 블록 psql 오류 메시지를 확인한 뒤에만 실행하십시오.
-- ─────────────────────────────────────────────────────────────────────
-- 실행 전 교체 필수 (3개 플레이스홀더 — 미교체 시 DO 블록이 ABORT):
--   'ABORT_GATE_HERE'   → 실패한 게이트 (예: D1, D2, B1, DOWN[1], DOWN[2])
--   'ERROR_REASON_HERE' → RAISE EXCEPTION 메시지 (psql 오류 출력)
--   'ACTOR_UUID_HERE'   → 실행한 운영자 auth.users.id (또는 NULL)
-- =====================================================================

-- ─── 플레이스홀더 교체 검증 (미교체 시 실행 차단) ──────────────────────
DO $$
BEGIN
  IF 'ABORT_GATE_HERE' = 'ABORT_GATE_HERE' THEN
    RAISE EXCEPTION
      'ABORT: 플레이스홀더가 교체되지 않았습니다. '
      'ABORT_GATE_HERE / ERROR_REASON_HERE / ACTOR_UUID_HERE를 실제 값으로 교체한 후 재실행하십시오.';
  END IF;
END $$;

-- ─── 실패 Audit INSERT (플레이스홀더 교체 확인 후 실행) ─────────────────

INSERT INTO runtime_form_audit_log
  (source_table, source_id, action, schema_version,
   before_state, after_state, reviewer_id, review_comment,
   rollback_snapshot, rollback_available)
VALUES
  ('runtime_form_schema', '4e07df2e-904a-4fe6-ad18-cecc0f5e57f3',
   'ROLLBACK_ABORTED', 1,
   NULL,
   jsonb_build_object(
     'target_schema_id', '4e07df2e-904a-4fe6-ad18-cecc0f5e57f3',
     'abort_gate',       'ABORT_GATE_HERE',
     'reason',           'ERROR_REASON_HERE',
     'actor',            'ACTOR_UUID_HERE',
     'attempted_at',     now()
   ),
   NULL, NULL, NULL, false);

-- =====================================================================
-- END STEP4E_DOWN_FAIL_AUDIT SQL — NOT EXECUTED.
