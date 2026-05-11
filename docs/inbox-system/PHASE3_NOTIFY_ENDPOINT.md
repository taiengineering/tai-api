# Phase 3: tai-api 알림 엔드포인트 + DB Trigger

**목적**: inquiries 테이블에 INSERT 발생 시 슬랙 `#inbox-all` 채널(`C0B1HKW5Y7N`)로 자동 알림 발송.

## 아키텍처 재확인

```
[폼 제출 또는 어드민 입력]
   → Supabase INSERT inquiries
   → DB Trigger AFTER INSERT (pg_net.http_post)
   → tai-api: POST /internal/inbox/notify
   → 기존 Slack Bot 재활용 → SLACK_CHANNEL_ID_INBOX
```

## 사전 조건

- [x] Phase 1 SQL 적용 완료 (inquiries 테이블 + 컬럼 + RLS)
- [ ] Phase 2 완료 (Railway 환경변수 + 봇 초대)
  - `SLACK_CHANNEL_ID_INBOX=C0B1HKW5Y7N`
  - `INTERNAL_API_SECRET` 재발급 권장 (메모리 노트 따름)
  - 슬랙 새 채널에 `/invite @slackbot` 실행

## 구성 파일 (Cursor 작업)

```
tai-api/
  routers/
    internal_inbox.py         ← 신규 (이 단계의 주작업)
  services/
    inbox_notify_svc.py       ← 신규 (슬랙 메시지 빌더)
  main.py                     ← 라우터 등록 추가 (1줄)
```

서비스 계층 분리 규칙 (메모리에 명시된 룰):
- Router = HTTP만 (SQL 금지)
- Service = 비즈니스 로직 (FastAPI import 금지)
- 한 파일 최대 400줄 / 15KB

## Step 1 — 기존 슬랙 클라이언트 위치 확인

Cursor 워크스페이스에서 grep:

```bash
grep -rn "SLACK_BOT_TOKEN" --include="*.py"
grep -rn "chat.postMessage" --include="*.py"
grep -rn "slack_sdk\|WebClient" --include="*.py"
```

**3가지 경우**:

### Case A: 기존 슬랙 클라이언트 존재 (권장)
그 파일의 자래 함수(예: `send_slack_message(channel, blocks)`)를 `inbox_notify_svc.py`에서 import 해 재사용.

### Case B: 기존 클라이언트는 있으나 hardcoded 함수
refactor하지 말고, 이번 작업에서는 자체 fetch 구현 (아래 Step 3 코드).

### Case C: 슬랙 클라이언트 없음 (환경변수만 있음)
아래 Step 3처럼 httpx로 직접 호출.

## Step 2 — services/inbox_notify_svc.py 작성

```python
"""
Inbox Slack 알림 빌더 + 발송

Doc: docs/inbox-system/PHASE3_NOTIFY_ENDPOINT.md
"""
import os
import httpx
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api/chat.postMessage"
ADMIN_BASE_URL = "https://admin.taieng.co.kr/html/horizontal-menu-template/inquiry-list.html"

# 소스 라벨
SOURCE_LABEL = {
    "direct":    "어드민 직접 입력",
    "marketing": "마케팅 사이트",
    "safe":      "SaaS (safe.taieng.co.kr)",
}

# 카테고리 라벨
CATEGORY_LABEL = {
    # INQUIRY
    "consult":   "법적진단 컨설팅",
    "safety":    "안전관리자 선임대행",
    "electric":  "전기설비 점검",
    "risk":      "위험성평가",
    "csia":      "중대재해처벌법",
    "saas":      "SaaS 서비스",
    "repair":    "수선중개",
    "edu":       "안전보건교육",
    "partner":   "파트너/협력 제안",
    "other":     "기타",
    # FEEDBACK
    "fb_feature": "기능 제안",
    "fb_bug":     "버그/오류",
    "fb_ux":      "사용성 불편",
    "fb_idea":    "아이디어",
    "fb_praise":  "응원·칭찬",
}


def build_blocks(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """inquiries row → Slack Block Kit"""
    is_feedback  = record.get("inquiry_type") == "FEEDBACK"
    emoji        = "💬" if is_feedback else "📨"
    type_label   = "TAI에 바란다" if is_feedback else "도입 문의"

    source_lbl   = SOURCE_LABEL.get(record.get("source", ""), record.get("source", "-"))
    category_lbl = CATEGORY_LABEL.get(record.get("category", ""), record.get("category", "-"))

    body = (record.get("content") or "").strip()
    if len(body) > 600:
        body = body[:600] + "…"
    body_quoted = "\n".join(">" + line for line in body.split("\n"))

    name  = record.get("name")  or "익명"
    email = record.get("email") or "-"
    phone = record.get("phone") or "-"
    contact_line = f"보낸이: *{name}* · {email} · {phone}"

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {type_label}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*인입경로*\n{source_lbl}"},
                {"type": "mrkdwn", "text": f"*분류*\n{category_lbl}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": body_quoted or "_(내용 없음)_"},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": contact_line}],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "어드민에서 보기"},
                    "url": ADMIN_BASE_URL,
                }
            ],
        },
    ]


async def send_inbox_notification(record: Dict[str, Any]) -> bool:
    """슬랙 알림 발송. 실패 시 로그만 남기고 False 반환."""
    token   = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID_INBOX")

    if not token or not channel:
        logger.warning(
            "[inbox_notify] missing slack env vars (token=%s, channel=%s)",
            bool(token), bool(channel),
        )
        return False

    blocks = build_blocks(record)
    payload = {
        "channel": channel,
        "blocks":  blocks,
        "text":    "새 인박스 메시지",  # fallback
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                SLACK_API,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type":  "application/json; charset=utf-8",
                },
                json=payload,
            )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("[inbox_notify] slack error: %s", data.get("error"))
            return False
        return True
    except Exception as e:
        logger.warning("[inbox_notify] exception: %s", e)
        return False
```

**주의**:
- httpx async 사용 (FastAPI 환경)
- timeout 5초 — 슬랙 장애가 시스템 전체를 느리게 하면 안 됨
- 실패 시 로그만 남기고 제복 시도 불평 (POST 자체는 200)

## Step 3 — routers/internal_inbox.py 작성

```python
"""
Internal: Inbox 알림 엔드포인트

Doc: docs/inbox-system/PHASE3_NOTIFY_ENDPOINT.md
"""
import os
import logging
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from typing import Any, Dict, Optional

from services.inbox_notify_svc import send_inbox_notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/inbox", tags=["internal-inbox"])


class NotifyPayload(BaseModel):
    record: Dict[str, Any]   # 전체 inquiries row jsonb


@router.post("/notify")
async def notify_inbox(
    payload: NotifyPayload,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    expected = os.environ.get("INTERNAL_API_SECRET")
    if not expected or x_internal_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid internal secret",
        )

    record = payload.record or {}
    sent   = await send_inbox_notification(record)

    return {
        "ok":     True,
        "sent":   sent,
        "row_id": record.get("id"),
    }
```

**주의**:
- 403 외에는 에러를 던지지 않음 (슬랙 실패 시에도 200·sent=false)
- DB Trigger가 다시 호출해서 부하가 높아지는 것 방지

## Step 4 — main.py에 라우터 등록

```python
from routers import internal_inbox
# ...
app.include_router(internal_inbox.router)
```

## Step 5 — Supabase DB Trigger 설치

Supabase Studio → SQL Editor:

```sql
-- 1. pg_net 확장 활성화 확인 (최신 Supabase는 기본 설치)
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- 2. 내부 secret을 PostgreSQL setting으로 저장
--    ⚠️ INTERNAL_API_SECRET은 메모리 노트에 따라 재발급 권장
ALTER DATABASE postgres SET app.internal_api_secret = '신규_시크릿_값_입력';

-- 3. trigger 함수 정의
CREATE OR REPLACE FUNCTION notify_inbox_trigger()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  PERFORM extensions.http_post(
    url     := 'https://api.taieng.co.kr/internal/inbox/notify',
    headers := jsonb_build_object(
      'Content-Type',     'application/json',
      'X-Internal-Secret', current_setting('app.internal_api_secret', true)
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

**핵심 안전장치**:
- `EXCEPTION WHEN OTHERS`: 알림 실패가 INSERT 자체를 막지 않도록. RAISE WARNING만 임.
- `SECURITY DEFINER`: 함수 소유자(supabase_admin) 권한으로 실행되어 anon도 트리거 사용 가능
- `current_setting('app.internal_api_secret', true)`: 2번째 인자 true → 설정 없을 때 에러 대신 NULL

## Step 6 — 테스트

### 6-A. tai-api 직접 호출 (Railway 배포 후)

```bash
# secret 맞는 경우 → 200 + 슬랙 메시지 도착해야 정상
curl -X POST https://api.taieng.co.kr/internal/inbox/notify \
  -H "Content-Type: application/json" \
  -H "X-Internal-Secret: $INTERNAL_API_SECRET" \
  -d '{
    "record": {
      "id": "00000000-0000-0000-0000-000000000001",
      "source": "marketing",
      "inquiry_type": "FEEDBACK",
      "category": "fb_feature",
      "content": "Phase 3 일조도 테스트 — 이 메시지가 슬랙에 보이면 성공",
      "name": "테스트",
      "email": "test@taieng.co.kr"
    }
  }'
# 예상: {"ok":true,"sent":true,"row_id":"00000000-..."}

# secret 틀린 경우 → 403
curl -X POST https://api.taieng.co.kr/internal/inbox/notify \
  -H "Content-Type: application/json" \
  -H "X-Internal-Secret: wrong" \
  -d '{"record":{}}'
# 예상: 403 invalid internal secret
```

### 6-B. Supabase 트리거 경유 테스트

Supabase SQL Editor:

```sql
-- service_role로 INSERT → 트리거 발동 → 슬랙 알림
INSERT INTO inquiries (source, inquiry_type, category, content, name, email)
VALUES (
  'marketing',
  'FEEDBACK',
  'fb_feature',
  'Supabase 트리거 테스트 — 슬랙에 이 메시지가 뜨면 성공',
  '테스트안',
  'admin@taieng.co.kr'
);

-- 정리
DELETE FROM inquiries WHERE content LIKE 'Supabase 트리거 테스트%';
```

슬랙 `#inbox-all` 채널에 다음 메시지가 뜨면 성공:

```
💬 TAI에 바란다
────────────────────
인입경로: 마케팅 사이트     분류: 기능 제안
────────────────────
> Supabase 트리거 테스트 — 슬랙에 이 메시지가 뜨면 성공
────────────────────
보낸이: 테스트안 · admin@taieng.co.kr
[ 어드민에서 보기 ]
```

## 자주 실시되는 이슈

### `not_in_channel`
→ 슬랙 채널에 `/invite @slackbot` 안 했음

### `channel_not_found`
→ SLACK_CHANNEL_ID_INBOX 오타. `C0B1HKW5Y7N` 확인

### `invalid_auth`
→ SLACK_BOT_TOKEN 만료 또는 오타. 기존 마케팅 채널에서도 동일 증상 시 토큰 재발급 필요

### Trigger는 돌아가는데 슬랙 메시지가 안 오면
```sql
-- pg_net 호출 결과 조회 (최근 100건)
SELECT id, status_code, content, error_msg
FROM net._http_response
ORDER BY created DESC
LIMIT 20;
```

### `app.internal_api_secret` 설정 확인
```sql
SHOW app.internal_api_secret;
```

## 롤백

```sql
DROP TRIGGER IF EXISTS trg_inquiries_notify ON inquiries;
DROP FUNCTION IF EXISTS notify_inbox_trigger();
```

tai-api 쪽은 internal_inbox 라우터를 main.py에서 제거하고 재배포.

## 완료 기준

- [ ] tai-api `/internal/inbox/notify` 배포 완료
- [ ] curl 직접 테스트 성공 (`sent: true`)
- [ ] Supabase 트리거 등록 완료
- [ ] INSERT 경유 테스트 성공 (슬랙에 메시지 도착)
- [ ] `_http_response` 테이블에서 status_code=200 확인

## 다음 단계

Phase 4: 어드민 inquiry-list 포함 확장 (입술경로·유형 컴럼, FEEDBACK 카테고리 추가)
Phase 5: 마케팅 + SaaS 의견 폼 구현
