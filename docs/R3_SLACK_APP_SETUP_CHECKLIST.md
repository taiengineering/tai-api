---
title: R3 Slack App 설정 체크리스트
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3-PRODUCTION-PREFLIGHT-001
status: G3_EXISTING_CONFIG_REUSE_PENDING_OWNER_ACTION
date: 2026-10-30
decision: WO-TAI-SLACK-BOT-R3-G3-EXISTING-CONFIG-REUSE-001
---

# R3 Slack App 설정 체크리스트 — G3

**Owner 결정 (WO-TAI-SLACK-BOT-R3-G3-EXISTING-CONFIG-REUSE-001)**:  
신규 채널 생성 취소. 기존 Slack App, 기존 채널 ID, 기존 설정값 전체 재사용.  
신규 생성 항목: 없음. 기존 값을 R3 전용 환경변수에 연결하는 것만 실행.

**모든 항목은 Owner가 Slack App 관리 콘솔 및 Railway에서 직접 실행합니다.**  
Claude Code는 이 섹션을 실행하지 않습니다. 비밀값을 채팅에 공개하지 않습니다.

---

## P-02: 기존 App ID + Team ID 재사용 확인

- [ ] Slack App 관리 콘솔 → App Settings → App Credentials
  - 기존 `App ID` 확인 → Railway `SLACK_RELAY_APP_ID` 환경변수에 설정
  - `SLACK_SIGNING_SECRET`은 이미 Railway에 설정됨 — 재확인만
- [ ] Workspace Team ID 확인
  - Team ID (형식: `T0XXXXXXXX`) 확인 → Railway `SLACK_RELAY_TEAM_ID` 환경변수에 설정

---

## P-03: groups:history 스코프 확인

- [ ] OAuth & Permissions → Scopes → Bot Token Scopes
  - `groups:history` 존재 여부 확인
  - **이미 있으면 생략** — 불필요한 App 재설치 금지
  - 없을 경우에만 추가 + 재설치 (기존 Bot 연동 영향 사전 확인 후)

---

## P-04: Relay 발신 채널 및 Bot 멤버십 확인

- [ ] 파일럿 Relay 발신 채널로 사용할 기존 비공개 채널 확인
  - 채널 ID 확인 (형식: `G0XXXXXXXX`)
  - `tai_bot`이 해당 채널 멤버인지 확인 (미초대 시 `/invite @tai_bot`)
  - **신규 채널 생성 금지**

---

## P-05: 릴레이 대상 채널 및 승인 발신자 확인

- [ ] 릴레이 메시지를 수신할 기존 채널 확인
  - 채널 ID 확인 (형식: `C0XXXXXXXX`)
  - `tai_bot`이 해당 채널 멤버인지 확인
- [ ] 파일럿 발신자 Slack User ID 확인 (형식: `U0XXXXXXXX`)
  - `SLACK_RELAY_ALLOWED_SENDER_IDS`에 설정할 값 (쉼표 구분 가능)

---

## P-06: Event Subscriptions Request URL 등록 (G4 — G3 완료 후 별도 실행)

**G4 진입 시에만 실행. G3 범위 아님.**

- [ ] Slack App → Event Subscriptions → Enable Events: ON
- [ ] Request URL: `https://api.taieng.co.kr/slack/events`
- [ ] URL Verification → Slack `url_verification` challenge 전송 → "Verified" 확인

---

## P-07: message.groups 이벤트 구독 (G4 — P-06 완료 후)

**G4 진입 시에만 실행. G3 범위 아님.**

- [ ] Event Subscriptions → Subscribe to Bot Events
  - `message.groups` 추가
- [ ] Save Changes

---

## G3 환경변수 설정 (P-02~P-05 완료 후, Railway)

P-02~P-05 확인 후 Railway `tai-api-prod` 환경변수 3개 설정:

```
SLACK_RELAY_APP_ID             = <P-02 기존 App ID>
SLACK_RELAY_TEAM_ID            = <P-02 기존 Team ID>
SLACK_RELAY_ALLOWED_SENDER_IDS = <P-05 승인 발신자 User ID>
```

**`SLACK_RELAY_CHANNEL_MAP` → G5 E2E 직전까지 미설정 유지. G3에서 절대 설정 금지.**

환경변수 변경 후 Railway 재배포가 트리거될 수 있음 → `/health` 200 및 배포 상태 확인.

---

## G3 실행 제한

| 금지 항목 | 근거 |
|----------|------|
| 신규 Slack 채널 생성 | REUSE-001 결정 |
| 기존 Bot Token 교체 | TOKEN_ROTATION_DEFERRED |
| `SLACK_RELAY_CHANNEL_MAP` 설정 | G5 직전까지 금지 |
| 실제 Relay 메시지 발송 | G5 별도 승인 |
| P-06/P-07 실행 | G4 범위 |

---

## G3 완료 증거 (비밀값 불필요)

| 항목 | 완료 여부 |
|------|---------|
| P-02 App ID / Team ID 확인 및 환경변수 설정 | □ |
| P-03 `groups:history` 권한 확인 | □ |
| P-04 Relay 발신 채널 및 `tai_bot` 멤버십 확인 | □ |
| P-05 대상 채널·승인 발신자 확인 | □ |
| Railway 환경변수 3개 설정 + `/health` 200 확인 | □ |
| `SLACK_RELAY_CHANNEL_MAP` 미설정 유지 | □ |
