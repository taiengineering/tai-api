---
title: R3 Slack App 설정 체크리스트
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3-PRODUCTION-PREFLIGHT-001
status: G3_PASS_COMPLETE
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

- [x] Slack App 관리 콘솔 → App Settings → App Credentials
  - 기존 `App ID` 확인 → Railway `SLACK_RELAY_APP_ID` 환경변수에 설정
  - `SLACK_SIGNING_SECRET`은 이미 Railway에 설정됨 — 재확인만
- [x] Workspace Team ID 확인
  - Team ID (형식: `T0XXXXXXXX`) 확인 → Railway `SLACK_RELAY_TEAM_ID` 환경변수에 설정

**G3V 확인**: Railway `SLACK_RELAY_APP_ID` SET ✅ / `SLACK_RELAY_TEAM_ID` SET ✅ (guri-cf 직접 확인)

---

## [ERRATA] COR-02 정정 (GPT IV WO-TAI-SLACK-BOT-R3-G4-SECRET-ISOLATION-IV-CORRECTION-001)

| 항목 | 기존 기재 | 정정 후 | 근거 |
|------|---------|---------|------|
| Event Subscriptions 이벤트명 | `message.groups` | `message.channels` | 공개 채널 대상 — `message.groups`는 비공개 채널 전용 |
| OAuth Scope | `groups:history` | `channels:history` | 공개 채널 대상 |
| R3 Signing Secret 환경변수 | `SLACK_SIGNING_SECRET` | `SLACK_RELAY_SIGNING_SECRET` | G4 격리 설계 반영 |
| 기존 Slack Kin Secret | (언급 없음) | `SLACK_SIGNING_SECRET` 유지 — Kin 전용 | 기존 연동 불변 |

기존 P-03/P-07 본문은 원문 보존. 위 정정이 본문에 우선합니다.

---

## P-03: channels:history 스코프 확인 *(정정: 구명칭 groups:history)*

- [x] OAuth & Permissions → Scopes → Bot Token Scopes
  - `channels:history` 추가 완료 *(ERRATA: 기재된 `groups:history`는 `channels:history`로 정정)*
  - App 재설치 완료 (기존 Bot 연동 영향 확인 후 진행)

**G3V 확인**: `channels:history` 추가 + App 재설치 Owner 직접 완료 ✅

---

## P-04: Relay 발신 채널 및 Bot 멤버십 확인

- [x] 파일럿 Relay 발신 채널로 사용할 기존 공개 채널 확인 *(ERRATA: 비공개 채널 → 공개 채널로 정정)*
  - 채널 ID 확인 (형식: `C0XXXXXXXX`)
  - `tai_bot`이 해당 채널 멤버인지 확인 (미초대 시 `/invite @tai_bot`)
  - **신규 채널 생성 금지**

**G3V 확인**: Owner 직접 확인 완료 ("기존 채널에 tai_bot 멤버 등록이 모두 완료됐다") ✅

---

## P-05: 릴레이 대상 채널 및 승인 발신자 확인

- [x] 릴레이 메시지를 수신할 기존 채널 확인
  - 채널 ID 확인 (형식: `C0XXXXXXXX`)
  - `tai_bot`이 해당 채널 멤버인지 확인
- [x] 파일럿 발신자 Slack User ID 확인 (형식: `U0XXXXXXXX`)
  - `SLACK_RELAY_ALLOWED_SENDER_IDS`에 설정할 값 (쉼표 구분 가능)

**G3V 확인**: Railway `SLACK_RELAY_ALLOWED_SENDER_IDS` SET ✅ / Bot 멤버십 Owner 직접 확인 ✅

---

## P-06: Event Subscriptions Request URL 등록 (G4 — G3 완료 후 별도 실행)

**G4 진입 시에만 실행. G3 범위 아님.**

- [ ] Slack App → Event Subscriptions → Enable Events: ON
- [ ] Request URL: `https://api.taieng.co.kr/slack/events`
- [ ] URL Verification → Slack `url_verification` challenge 전송 → "Verified" 확인

---

## P-07: message.channels 이벤트 구독 (G4 — P-06 완료 후) *(정정: 구명칭 message.groups)*

**G4 진입 시에만 실행. G3 범위 아님.**

- [ ] Event Subscriptions → Subscribe to Bot Events
  - `message.channels` 추가 *(ERRATA: 기재된 `message.groups`는 `message.channels`로 정정)*
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
| P-02 App ID / Team ID 확인 및 환경변수 설정 | ✅ (Railway guri-cf 직접 확인) |
| P-03 `channels:history` 권한 확인 + App 재설치 | ✅ (Owner 직접 완료) |
| P-04 Relay 발신 채널 및 `tai_bot` 멤버십 확인 | ✅ (Owner 직접 확인) |
| P-05 대상 채널·승인 발신자 확인 | ✅ (Railway guri-cf 직접 확인) |
| Railway 환경변수 3개 설정 + `/health` 200 확인 | ✅ (7f54d4e9 SUCCESS, /health 200) |
| `SLACK_RELAY_CHANNEL_MAP` 미설정 유지 | ✅ (Railway 환경변수 미존재 확인) |

---

## G3 소스계약 검증 (WO-TAI-SLACK-BOT-R3-G3-CLOSE-G4-READINESS-001)

**검증 SHA**: `be58799e` (배포 기준) / 소스 `routers/slack_events.py`

| 항목 | 검증 결과 | 소스 위치 |
|------|---------|---------|
| url_verification 핸들러 | ✅ PASS | lines 103–106 |
| 서명 검증 실패 → 403 | ✅ PASS | lines 92–94 |
| Fail Closed (CHANNEL_MAP 미설정) | ✅ PASS | lines 117–119 |
| api_app_id 하드 매칭 | ✅ PASS | lines 122–124 |
| team_id 하드 매칭 | ✅ PASS | lines 127–129 |
| 채널 유형 필터 없음 (비공개 채널 처리 가능) | ✅ PASS | line 148 |
| bot_id 존재 시 차단 | ✅ PASS | lines 137–139 |
| 승인 발신자 only 처리 | ✅ PASS | lines 142–145 |

**G4 선행 조건** (`url_verification` 소스 확인됨):
- P-06 Request URL `https://api.taieng.co.kr/slack/events` 등록 시 `/slack/events` 엔드포인트가 challenge에 즉시 응답 ✅

---

## G3 판정

**G3V 종합**: PASS — P-02~P-05 전 항목 완료 ✅

- P-03 `channels:history` 추가 + App 재설치 Owner 직접 완료
- 기존 공개 채널 재사용 (`message.channels` 적용)
- `SLACK_SIGNING_SECRET` 기존 유지 (Kin 전용)
- `SLACK_RELAY_SIGNING_SECRET` 설정 대기 (G4 Merge + 배포 후)
- G4 URL Verification: Signing Secret 불일치 해결(PR #725 Merge) 후 실행
- G5 이후: 별도 Owner 승인
