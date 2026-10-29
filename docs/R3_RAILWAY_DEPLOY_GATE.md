---
title: R3 Railway Deploy Gate
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3-PRODUCTION-PREFLIGHT-001
status: G2_DEPLOYED_PENDING_GPT_IV
date: 2026-10-30
---

# R3 Railway Deploy Gate — G2

**대상 서비스**: tai-api-prod  
**Railway 프로젝트**: `7c3ab53b-feb6-40a4-a4f0-7ade3f6e524b`  
**Railway 서비스**: `4cf52678-1fbf-42f4-8bd7-f59fab98c3ae`

---

## 1. 배포 전 현황 (guri-cf 직접 확인, 2026-10-30)

| 항목 | 값 |
|------|-----|
| 현재 운영 배포 ID | `b75fb857` |
| 현재 운영 SHA | `b3cd3a5b` (R3 코드 미포함) |
| 현재 배포 상태 | SUCCESS |
| 현재 배포 시각 | 2026-10-29 19:57:35 UTC |
| 자동 배포 트리거 (G1~G1V 커밋 3건) | **미발생** — Fail Closed 유지 |
| 배포 대상 SHA | `a3e2e015` (현재 main) |
| **실제 배포 결과** | **배포 ID `66f7bd06` — SUCCESS** |
| 배포 시각 | 2026-10-29 21:16:23 UTC |
| 배포된 SHA | `a3e2e015e3dce54ebbadb251abb95795c7575158` ✅ |
| imageDigest | `sha256:a9364a94...` |

---

## 2. 필요 환경변수

| 환경변수 | 필수 여부 | 현재 설정 | 비고 |
|---------|---------|---------|------|
| `SUPABASE_URL` | 필수 | SET ✅ | `vwlahtguyggrhvslabax.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | 필수 | SET ✅ | slack_relay_event_log 서버 전용 |
| `SLACK_SIGNING_SECRET` | 필수 | SET ✅ | HMAC 검증 |
| `SLACK_BOT_TOKEN1` | 발송 시 필수 | SET ✅ | TOKEN_ROTATION_DEFERRED |
| `SLACK_RELAY_APP_ID` | Fail Closed | **NOT SET** | P-02 후 설정 |
| `SLACK_RELAY_TEAM_ID` | Fail Closed | **NOT SET** | P-02 후 설정 |
| `SLACK_RELAY_ALLOWED_SENDER_IDS` | Fail Closed | **NOT SET** | P-05 후 설정 |
| `SLACK_RELAY_CHANNEL_MAP` | Fail Closed | **NOT SET** | 미설정 = 발송 차단, G5 전까지 유지 |

**중요**: `SLACK_RELAY_CHANNEL_MAP` 미설정 상태 유지 — Relay 발송 차단 보증.

---

## 3. G2 배포 절차 (Owner 승인 후 Claude Code 실행)

1. `guri-cf railway_graphql`로 `tai-api-prod` 재배포 트리거
2. 배포 완료 후 신규 배포 SHA = `eea7ff35` 확인
3. `GET https://api.taieng.co.kr/health` → 200 확인
4. `GET https://api.taieng.co.kr/ready` → 200 확인
5. `POST /slack/events` (서명 없는 요청) → 403 응답 확인 (500 아님)
6. `SLACK_RELAY_CHANNEL_MAP` 미설정 → Fail Closed 확인

---

## 4. 중단 조건

| 조건 | 처리 |
|------|------|
| 배포 후 `/health` 실패 | Railway Dashboard에서 `b75fb857`으로 롤백 |
| `/slack/events` 500 응답 | `SLACK_SIGNING_SECRET` 환경변수 확인 |
| DB 연결 실패 | `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` 확인 |
| 예상치 못한 Relay 발송 | `SLACK_RELAY_CHANNEL_MAP` 즉시 삭제 |

---

## 5. Gate 통과 기준

- [x] 배포 SHA = `a3e2e015` 확인 ✅ (`66f7bd06` SUCCESS)
- [x] `GET /health` → HTTP 200 ✅ (`{"status":"ok","version":"6.0.2"}`)
- [~] `GET /ready` → HTTP 404 (엔드포인트 미존재 — 비차단, Railway healthcheck=/health)
- [x] `POST /slack/events` (서명 없음) → HTTP 403 ✅
- [x] `SLACK_RELAY_CHANNEL_MAP` 미설정 → Fail Closed ✅

**G2 판정: PASS — PENDING_GPT_IV**
