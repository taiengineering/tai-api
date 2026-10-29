---
title: R3 Railway Deploy Gate
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3-PRODUCTION-PREFLIGHT-001
status: OWNER_CONFIRMATION_PENDING
date: 2026-10-30
---

# R3 Railway Deploy Gate — G2

**대상 서비스**: tai-api-prod (Railway)  
**Railway API 접근**: NOT_AUTHORIZED (MCP 미인증) — Owner 직접 확인 필요

---

## 1. 배포 전 확인 사항 (Owner 직접)

| 항목 | 확인 방법 | 상태 |
|------|----------|------|
| 현재 배포 SHA | Railway Dashboard → tai-api-prod → 최신 배포 | PENDING |
| 자동 배포 설정 | Railway Dashboard → Service → Deploy → Auto Deploy | PENDING |
| 배포 전 main SHA | `24b88847274d21e803082b11050f20eae9576818` | 기준값 |

현재 배포 SHA = `24b88847`이면 이미 최신 코드 반영됨 (자동 배포 활성화된 경우).  
현재 배포 SHA ≠ `24b88847`이면 수동 배포 또는 자동 배포 대기 필요.

---

## 2. 필요 환경변수

| 환경변수 | 필수 여부 | 현재 설정 | 비고 |
|---------|---------|---------|------|
| `SUPABASE_URL` | 필수 | 기설정 가정 | 기존 서비스 운영 중 |
| `SUPABASE_SERVICE_ROLE_KEY` | 필수 | 기설정 가정 | slack_relay_event_log 서버 전용 |
| `SLACK_SIGNING_SECRET` | 필수 | 기설정 가정 (P-02 확인 후) | HMAC 검증 |
| `SLACK_BOT_TOKEN1` | 발송 시 필수 | 기설정 (SECURITY_RISK_OPEN) | TOKEN_ROTATION_DEFERRED |
| `SLACK_RELAY_APP_ID` | 필수 (Fail Closed) | **PENDING** | P-02 후 설정 |
| `SLACK_RELAY_TEAM_ID` | 필수 (Fail Closed) | **PENDING** | P-02 후 설정 |
| `SLACK_RELAY_ALLOWED_SENDER_IDS` | 필수 (Fail Closed) | **PENDING** | P-05 후 설정 |
| `SLACK_RELAY_CHANNEL_MAP` | Fail Closed 기본값 | **미설정 권장** | 미설정 = 발송 차단 |

**중요**: `SLACK_RELAY_CHANNEL_MAP` 미설정 상태로 배포하면 Fail Closed로 동작하여  
실제 릴레이 발송이 차단됩니다. 파일럿 준비 완료 후 G5 직전 설정합니다.

---

## 3. 배포 절차 (Owner)

1. G1 Migration 적용 완료 확인 후 진행
2. Railway Dashboard → tai-api-prod → Deploy Now (또는 자동 배포 대기)
3. 배포 완료 후:
   - `GET https://api.taieng.co.kr/health` → 200 확인
   - 배포 SHA = `24b88847` 확인
4. `/slack/events` 엔드포인트가 500/404 없이 서명 오류(403)를 반환하는지 확인  
   (올바른 서명 없이 POST → 403 예상)

---

## 4. 중단 조건

| 조건 | 처리 |
|------|------|
| 배포 후 health 실패 | Railway Dashboard에서 이전 배포 롤백 |
| `/slack/events` 500 응답 | SLACK_SIGNING_SECRET 환경변수 확인 |
| DB 연결 실패 | SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 확인 |

---

## 5. Gate 통과 기준

- [ ] 배포 SHA = `24b88847` 확인
- [ ] `GET /health` 200 응답
- [ ] `POST /slack/events` (서명 없음) → 403 응답 (500 아님)
- [ ] SLACK_RELAY_CHANNEL_MAP 미설정 → Fail Closed 상태 유지
