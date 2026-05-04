# PHASE 3 PATCH — Vault 기반 secret 조회

**배경**: Supabase Cloud에서는 `ALTER DATABASE postgres SET app.internal_api_secret = ...` 권한이 제한됨(일반 이용자에게는 불가능). 대신 **Supabase Vault**에 secret을 저장하고 트리거에서 조회하는 방식으로 변경.

**적용 범위**: PHASE3_NOTIFY_ENDPOINT.md의 **Step 5의 SQL만 교체**. Step 1~4 (tai-api 코드 작업)와 Step 6 (테스트)는 그대로.

## 현재 상태

- [x] Vault에 secret 등록 완료 (2026-05-04)
  - name: `internal_api_secret`
  - id: `42ef59f1-c484-4419-9d3b-00282b6464dc`
- [x] Vault 내용은 Railway env `INTERNAL_API_SECRET`과 동일 값

## 등록 확인 쿼리

```sql
SELECT id, name, description, created_at
FROM vault.secrets
WHERE name = 'internal_api_secret';
```

## 교체: Step 5 SQL (Vault 조회 방식)

기존 PHASE3 지시서의 Step 5 SQL을 아래 내용으로 **전체 교체**:

```sql
-- 1. pg_net 확장 활성화 확인 (Supabase는 기본 설치)
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- 2. Vault 확장 활성화 확인 (Database → Extensions 에서도 확인 가능)
CREATE EXTENSION IF NOT EXISTS supabase_vault WITH SCHEMA vault;

-- 3. trigger 함수 정의 — Vault에서 secret 조회
CREATE OR REPLACE FUNCTION notify_inbox_trigger()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault, extensions
AS $$
DECLARE
  v_secret text;
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

  -- tai-api 호출 (실패해도 INSERT는 을고)
  PERFORM extensions.http_post(
    url     := 'https://api.taieng.co.kr/internal/inbox/notify',
    headers := jsonb_build_object(
      'Content-Type',     'application/json',
      'X-Internal-Secret', v_secret
    ),
    body    := jsonb_build_object('record', row_to_json(NEW))
  );
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
```

## 주요 변경점 (기존 대비)

| 이전 | 변경 후 |
|---|---|
| `current_setting('app.internal_api_secret', true)` 로 조회 | `vault.decrypted_secrets`에서 조회 |
| `ALTER DATABASE … SET …` 필요 | 동작 안 함 (권한 제한) |
| GUC 로드 시점 의존 | 매 트리거 호출 시 Vault 조회 |

**SECURITY DEFINER + search_path 명시**로 함수 소유자(supabase_admin) 권한으로 Vault 접근 가능. anon/authenticated도 트리거는 발동되지만 Vault 직접 조회는 불가 → 안전.

## 검증

### V1. Vault에 secret 있는지
```sql
SELECT name, created_at FROM vault.secrets WHERE name = 'internal_api_secret';
```
결과 1행 나와야 ✅

### V2. 트리거 함수가 secret 조회 가능한지 (디버그용, 하지 마세요 — secret 겪어 나올 수 있음)
Vault의 decrypted_secret을 SQL Editor에서 직접 SELECT하면 평문이 노출됩니다. **권장하지 않음.** 대신 아래 프록시 함수로 길이만 확인:

```sql
CREATE OR REPLACE FUNCTION _check_secret_length()
RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE v text;
BEGIN
  SELECT decrypted_secret INTO v FROM vault.decrypted_secrets WHERE name = 'internal_api_secret';
  RETURN length(coalesce(v, ''));
END $$;

SELECT _check_secret_length();
-- 결과: 64 (openssl rand -hex 32 기준) 또는 다른 길이. 0이면 조회 실패

DROP FUNCTION _check_secret_length;  -- 신속 제거
```

### V3. 실제 INSERT 테스트 (Step 6-B 동일)

Phase 3 코드 배포 완료 후:
```sql
INSERT INTO inquiries (source, inquiry_type, category, content, name, email)
VALUES (
  'marketing', 'FEEDBACK', 'fb_feature',
  'Vault 방식 테스트 — 슬랙에 이 메시지가 뜨면 성공',
  '테스트안', 'admin@taieng.co.kr'
);

-- pg_net 응답 로그 확인
SELECT id, status_code, content, error_msg, created
FROM net._http_response
ORDER BY created DESC LIMIT 5;

-- 정리
DELETE FROM inquiries WHERE content LIKE 'Vault 방식%';
```

`status_code = 200` + 슬랙 `#inbox-all` 채널에 메시지 도착 → 최종 성공.

## Cursor에게 알리기 한 둘

- Step 5는 이 PATCH 문서 따르기. 기존 PHASE3 지시서의 `ALTER DATABASE postgres SET ...` 라인은 **실행하지 말것**.
- tai-api 코드 쓬(Step 1~4)은 변화 없음. `INTERNAL_API_SECRET` 환경변수로 그대로 헤더 검증.
- 다른 secret을 추가로 관리하고 싶으면 같은 Vault에 따로 등록 후 동일 패턴으로 조회 (확장성 좋음).
