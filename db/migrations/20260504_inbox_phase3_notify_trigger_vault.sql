-- Phase 3: inquiries INSERT → tai-api /internal/inbox/notify (Vault secret)
-- Apply in Supabase SQL Editor. See docs/inbox-system/PHASE3_PATCH_VAULT.md
-- Do NOT use ALTER DATABASE ... SET app.internal_api_secret (use Vault instead).
--
-- IMPORTANT: pg_net 함수는 net 스키마에 설치됨 (extensions 아님).
-- Supabase Cloud 기준: net.http_post(url, body, params, headers, timeout_milliseconds)

-- 1. pg_net 확장 활성화 (Supabase는 기본 설치 — net 스키마에 함수 위치)
CREATE EXTENSION IF NOT EXISTS pg_net;

-- 2. Vault 확장 활성화 확인
CREATE EXTENSION IF NOT EXISTS supabase_vault WITH SCHEMA vault;

-- 3. trigger 함수 정의 — Vault에서 secret 조회
CREATE OR REPLACE FUNCTION notify_inbox_trigger()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault, net, extensions
AS $$
DECLARE
  v_secret text;
  v_request_id bigint;
BEGIN
  -- Vault에서 복호화된 secret 조회 (service_role 컨텍스트)
  SELECT decrypted_secret INTO v_secret
    FROM vault.decrypted_secrets
   WHERE name = 'internal_api_secret'
   LIMIT 1;

  IF v_secret IS NULL OR length(v_secret) < 16 THEN
    RAISE WARNING 'notify_inbox_trigger: vault secret missing or too short';
    RETURN NEW;
  END IF;

  -- tai-api 호출 (실패해도 INSERT는 유지)
  -- net.http_post 는 비동기적으로 요청을 큐에 넣고 request_id만 즉시 반환
  SELECT net.http_post(
    url     := 'https://api.taieng.co.kr/internal/inbox/notify',
    body    := jsonb_build_object('record', row_to_json(NEW)::jsonb),
    headers := jsonb_build_object(
      'Content-Type',     'application/json',
      'X-Internal-Secret', v_secret
    ),
    timeout_milliseconds := 5000
  ) INTO v_request_id;

  RETURN NEW;
EXCEPTION
  WHEN OTHERS THEN
    -- 알림 실패가 INSERT 자체를 막으면 안 됨
    RAISE WARNING 'notify_inbox_trigger failed: %', SQLERRM;
    RETURN NEW;
END;
$$;

-- 4. trigger 등록 (기존 있으면 교체)
DROP TRIGGER IF EXISTS trg_inquiries_notify ON inquiries;
CREATE TRIGGER trg_inquiries_notify
AFTER INSERT ON inquiries
FOR EACH ROW
EXECUTE FUNCTION notify_inbox_trigger();
