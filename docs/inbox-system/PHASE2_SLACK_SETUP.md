# Phase 2: 슬랙 봇 새 채널 연결

**목적**: 기존 슬랙 봇이 신규 인박스 채널(`C0B1HKW5Y7N`)에 메시지 발송 가능하도록 설정.

## 작업 순서

### 1. 슬랙 새 채널에 봇 초대

슬랙에서 채널 `C0B1HKW5Y7N` 입장 → 입력창에:

```
/invite @봇이름
```

봇 이름은 기존 마케팅 채널에서 확인 가능. (앱 설정 → Bot Users에도 표시)

초대 안 하면 발송 시 `not_in_channel` 에러납니다.

### 2. Railway 환경변수 추가

Railway 대시보드 → tai-api 서비스 → Variables 탭:

```
SLACK_CHANNEL_ID_INBOX=C0B1HKW5Y7N
```

기존 변수는 절대 건드리지 않음:
```
SLACK_BOT_TOKEN          ← 그대로 (공용)
SLACK_CHANNEL_ID         ← 그대로 (마케팅 채널 — 네이버 지식인 승인용)
SLACK_SIGNING_SECRET     ← 그대로
SLACK_CHANNEL_ID_INBOX   ← 신규 추가
```

저장 시 Railway가 자동 재배포. 약 1-2분 소요.

### 3. INTERNAL_API_SECRET 재발급 (권장)

메모리 노트에 따르면 세션 중 노출 발생. Phase 3에서 DB Trigger가 이 값으로 tai-api를 호출하므로, 신규 secret으로 교체하는 게 안전:

1. 새 secret 생성 (32바이트 hex 권장):
   ```bash
   openssl rand -hex 32
   ```
2. Railway env에서 `INTERNAL_API_SECRET` 값 교체
3. Supabase에서도 같은 값을 PostgreSQL setting으로 저장 (Phase 3에서 사용):
   ```sql
   ALTER DATABASE postgres SET app.internal_api_secret = '신규_시크릿_값';
   ```

## 검증

Phase 3 endpoint 배포 전에는 직접 봇 테스트 어려움. 대신 Slack API에서 dry-run 가능:

```bash
curl -X POST https://slack.com/api/auth.test \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"
# {"ok": true, "team": "..."} 나오면 토큰 유효

curl -X POST https://slack.com/api/conversations.info \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "channel=C0B1HKW5Y7N"
# {"ok": true, "channel": {...}} 나오면 채널 접근 가능
```

## 진행 후 다음 단계

Phase 3으로 이동: `PHASE3_NOTIFY_ENDPOINT.md` (작성 예정)
