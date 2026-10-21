-- Migration: 20261022000003_sec04_remaining6_privilege_function_revoke.sql
-- WO: WO-TAI-SEC04-REMAINING6-IMPLEMENT-001
-- SEC-04: 잔여 SECURITY DEFINER 함수 6개 공개 실행권한 제거.
--
-- 배경:
--   CSI4(20261022000001)·UDL7(20261022000002) 완료 후 잔여 7개 중
--   current_user_id()를 HOLD로 분리하고 6개를 처리한다.
--   Supabase는 함수를 생성할 때 anon/authenticated에 명시적 GRANT를 자동 부여.
--   결과: anon/authenticated EXECUTE 잔존 → 명시 회수 필요.
--
-- 대상 함수 분류:
--   CSI 조회 RPC 3개 (반환 타입: SETOF/json, 외부 호출 가능):
--     get_csi_blocklist_keyword_rows_json(integer)
--     get_unprocessed_csi_keyword_rows(integer)
--     get_unprocessed_csi_keyword_rows_json(integer)
--     → 기존 Python API(admin_csi_keyword_extract.py)는 service_role만 사용.
--
--   트리거 함수 3개 (반환 타입: trigger, Supabase Data API 호출 불가):
--     handle_new_user()
--       TRIGGER_LINK_ABSENT_VERIFIED: 운영 DB 직접 확인 결과 연결 트리거 0개.
--       함수 본문·공개 API·트리거 복구 변경 없음.
--     notify_inbox_trigger()
--       기존 inquiries AFTER INSERT 트리거 유지.
--       Vault 연동·net.http_post 변경 없음.
--     set_guest_user_null()
--       기존 payments BEFORE INSERT 트리거 유지.
--       Auth 조회·user_id 처리 로직 변경 없음.
--
-- 제외:
--   current_user_id() — explicit PUBLIC EXECUTE (=X/postgres) 존재.
--   RLS helper 의도 여부 미확인 → HOLD (별도 게이트).
--
-- 변경 범위:
--   PUBLIC, anon, authenticated → EXECUTE 회수 (6건).
--   service_role → 기존 명시적 GRANT 유지 (본 migration에서 변경 없음).
--   postgres → 기존 권한 유지 (본 migration에서 변경 없음).
--   함수 본문·SECURITY DEFINER 속성·트리거 정의 변경 없음.
--
-- 패턴: 20261022000001_sec04_csi_privilege_function_revoke.sql
--       20261022000002_sec04_udl7_privilege_function_revoke.sql
-- 기준: GPT_SEC04_REMAINING7_DESIGN_IV = PASS_WITH_CORRECTIONS

REVOKE EXECUTE ON FUNCTION
    public.get_csi_blocklist_keyword_rows_json(integer)
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.get_unprocessed_csi_keyword_rows(integer)
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.get_unprocessed_csi_keyword_rows_json(integer)
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.handle_new_user()
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.notify_inbox_trigger()
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.set_guest_user_null()
FROM PUBLIC, anon, authenticated;
