---
title: R3 Slack App 설정 체크리스트
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3-PRODUCTION-PREFLIGHT-001
status: PENDING_OWNER_ACTION
date: 2026-10-30
---

# R3 Slack App 설정 체크리스트 — G3

**모든 항목은 Owner가 Slack App 관리 콘솔에서 직접 실행합니다.**  
Claude Code는 이 섹션을 실행할 수 없습니다.

---

## P-02: App ID + Workspace 확인

- [ ] Slack App 관리 콘솔 → App Settings → App Credentials
  - `App ID` 확인 → Railway `SLACK_RELAY_APP_ID` 환경변수에 설정
  - `Verification Token` 또는 `Signing Secret` 확인 → `SLACK_SIGNING_SECRET` 설정 확인
- [ ] Workspace 정보 확인
  - Team ID 확인 → `SLACK_RELAY_TEAM_ID` 환경변수에 설정

---

## P-03: groups:history 스코프 추가

- [ ] OAuth & Permissions → Scopes → Bot Token Scopes
  - `groups:history` 추가 (private channel 메시지 수신)
  - 추가 후 App 재설치(Reinstall App) 필요할 수 있음

**현재 스코프에 이미 있다면 생략 가능.**

---

## P-04: 파일럿용 Private Relay 채널 생성

- [ ] Slack Workspace에서 신규 private 채널 생성 (예: `#tai-relay-pilot`)
- [ ] 채널 ID 확인 (채널 상세 → 채널 ID, 형식: `G0XXXXXXXX`)
- [ ] `tai_bot`을 해당 채널에 초대 (`/invite @tai_bot`)
- [ ] 채널 ID → 아래 `SLACK_RELAY_CHANNEL_MAP` 설정에 사용

---

## P-05: 테스트 대상 채널 확인

- [ ] 릴레이 메시지를 수신할 채널 확인 (기존 채널 또는 신규 테스트 채널)
- [ ] 채널 ID 확인 (형식: `C0XXXXXXXX`)
- [ ] `tai_bot`이 해당 채널의 멤버인지 확인 (`/invite @tai_bot` 필요 시 추가)

---

## P-06: Event Subscriptions Request URL 등록 (G2 완료 후)

**Railway 배포 완료 후에만 진행 가능합니다.**

- [ ] Slack App → Event Subscriptions → Enable Events: ON
- [ ] Request URL: `https://api.taieng.co.kr/slack/events`
- [ ] URL Verification: Slack이 자동으로 `url_verification` challenge 전송 → 200 응답 확인
- [ ] URL Verification 성공 시 "Verified" 표시

---

## P-07: message.groups 이벤트 구독 추가

- [ ] Event Subscriptions → Subscribe to Bot Events
  - `message.groups` 추가 (private channel 메시지)
- [ ] Save Changes

---

## 환경변수 설정 (P-02~P-05 완료 후)

P-02~P-05 완료 후 Railway tai-api-prod 환경변수 업데이트:

```
SLACK_RELAY_APP_ID          = <P-02에서 확인한 App ID>
SLACK_RELAY_TEAM_ID         = <P-02에서 확인한 Team ID>
SLACK_RELAY_ALLOWED_SENDER_IDS = <테스트 발신자 User ID(쉼표 구분)>
SLACK_RELAY_CHANNEL_MAP     = {"<P-04 relay 채널 ID>":"<P-05 대상 채널 ID>"}
```

**주의**: `SLACK_RELAY_CHANNEL_MAP`을 설정하면 릴레이가 활성화됩니다.  
G5 E2E 파일럿 직전에 설정합니다. 그 전에는 빈 값 또는 미설정 유지.

---

## 설정 완료 확인

| 항목 | 완료 여부 |
|------|---------|
| P-02 App ID / Team ID 확인 및 환경변수 설정 | □ |
| P-03 groups:history 스코프 확인 | □ |
| P-04 파일럿 채널 생성 및 tai_bot 초대 | □ |
| P-05 대상 채널 확인 및 tai_bot 멤버십 | □ |
| P-06 Request URL Verified | □ |
| P-07 message.groups 이벤트 구독 | □ |
| 환경변수 CHANNEL_MAP 설정 | □ (E2E 직전) |
