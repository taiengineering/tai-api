-- =====================================================================
-- WP-PERSISTENCE-02A STEP-4E — DOWN 실패 Audit (별도 자율 TX)
-- =====================================================================
-- !!! NOT EXECUTED — 별도 명시 Owner 승인 없이 실행 금지 !!!
-- 목적: STEP4E_DOWN DO 블록 실패 시 ROLLBACK_ABORTED 기록
-- 전제: STEP4E_DOWN DO 블록이 RAISE EXCEPTION으로 종료된 것을 확인 후 실행
-- 경고: DO 블록 성공 후 이 파일을 실행하면 오감지 기록이 남습니다.
--       STEP4E_DOWN psql 오류 메시지를 확인한 뒤에만 실행하십시오.
-- ─────────────────────────────────────────────────────────────────────
-- 실행 전 교체 필수 (3개 변수 — 미교체 시 DO 블록이 RAISE EXCEPTION으로 종료):
--   v_abort_gate   : 실패한 게이트 (예: 'D1', 'D2', 'B1', 'DOWN[1]', 'DOWN[2]')
--   v_error_reason : STEP4E_DOWN psql 오류 메시지
--   v_actor        : 실행한 운영자 auth.users.id (UUID 문자열), 모를 경우 NULL
-- =====================================================================

DO $$
DECLARE
  -- ★ 실행 전 아래 세 변수를 실제 값으로 교체하십시오 ★
  v_abort_gate   text := 'ABORT_GATE_HERE';    -- ★ 교체 필수
  v_error_reason text := 'ERROR_REASON_HERE';  -- ★ 교체 필수
  v_actor        text := 'ACTOR_UUID_HERE';    -- ★ 교체 필수 (모를 경우 NULL로 변경)
BEGIN
  -- ─── 플레이스홀더 교체 검증 ────────────────────────────────────────
  -- 각 변수가 초기값(플레이스홀더)인 경우 INSERT 없이 RAISE EXCEPTION 종료.
  -- 조건이 참 = 교체 안 됨 = 실행 차단.

  IF v_abort_gate = 'ABORT_GATE_HERE' THEN
    RAISE EXCEPTION
      'ABORT: v_abort_gate를 실제 실패 게이트로 교체하십시오. '
      '(예: D1, D2, B1, DOWN[1], DOWN[2])';
  END IF;

  IF v_error_reason = 'ERROR_REASON_HERE' THEN
    RAISE EXCEPTION
      'ABORT: v_error_reason을 STEP4E_DOWN psql 오류 메시지로 교체하십시오.';
  END IF;

  IF v_actor = 'ACTOR_UUID_HERE' THEN
    RAISE EXCEPTION
      'ABORT: v_actor를 운영자 UUID 또는 NULL로 교체하십시오.';
  END IF;

  -- ─── 실패 Audit INSERT ───────────────────────────────────────────
  -- 위 가드를 모두 통과한 경우에만 실행됨.

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
       'abort_gate',       v_abort_gate,
       'reason',           v_error_reason,
       'actor',            v_actor,
       'attempted_at',     now()
     ),
     NULL, NULL, NULL, false);

  RAISE NOTICE 'STEP4E_DOWN_FAIL_AUDIT OK: gate=% actor=%', v_abort_gate, v_actor;
END $$;

-- =====================================================================
-- END STEP4E_DOWN_FAIL_AUDIT SQL — NOT EXECUTED.
