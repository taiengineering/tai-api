---
title: R3 Slack Events Relay 운영 사전점검 보고서
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3-PRODUCTION-PREFLIGHT-001
status: PREFLIGHT_COMPLETE
date: 2026-10-30
scope: READ_ONLY
---

# R3 Slack Events Relay — 운영 사전점검 보고서

**기준 main SHA**: `24b88847274d21e803082b11050f20eae9576818`  
**점검 일시**: 2026-10-30 (UTC)  
**점검 범위**: READ_ONLY — DB/Railway/Slack 변경 없음

---

## G0-01. GitHub 기준선

| 항목 | 결과 |
|------|------|
| main SHA | `24b88847` ✅ |
| PR #722 | MERGED ✅ (2026-10-29 20:30:04 UTC) |
| Migration 파일 존재 | `migrations/2026-10-30_slack_relay_event_log.sql` ✅ |
| CLI 스크립트 존재 | `scripts/slack_relay_recover_cli.py` ✅ |
| P0 Automation 변경 없음 | ✅ (git diff 확인) |
| 테스트 | 58/58 PASS ✅ |

---

## G0-02. Supabase 사전점검

| 항목 | 결과 |
|------|------|
| 프로젝트 | `taieng` (vwlahtguyggrhvslabax) |
| 리전 | ap-northeast-2 |
| DB 상태 | ACTIVE_HEALTHY |
| PostgreSQL | 17.6.1 |
| `slack_relay_event_log` 존재 | **NOT EXISTS** → Migration 미적용 |
| 충돌 테이블 | 없음 (auth.saml_relay_states만 존재, 무관) |
| Migration 이력 최신 버전 | `20261029173518` (R3 미포함) |
| Migration 명명 규칙 | 로컬: `YYYY-MM-DD_name.sql` / 추적: `YYYYMMDDHHMMSS` — 직접 SQL 적용 방식 |

**결론**: Migration 적용 준비 완료. 충돌 없음.

상세 내용: [R3_DB_MIGRATION_GATE.md](R3_DB_MIGRATION_GATE.md)

---

## G0-03. Railway 사전점검

| 항목 | 결과 |
|------|------|
| 현재 배포 SHA | `b3cd3a5b` ✅ (R3 미포함 — Fail Closed) |
| 배포 시각 | 2026-10-29 19:57:35 UTC (PR #722 머지 32분 전) |
| Auto-deploy 트리거 여부 | 미발생 ✅ |
| SLACK_RELAY_APP_ID | NOT SET ✅ Fail Closed |
| SLACK_RELAY_TEAM_ID | NOT SET ✅ Fail Closed |
| SLACK_RELAY_ALLOWED_SENDER_IDS | NOT SET ✅ Fail Closed |
| SLACK_RELAY_CHANNEL_MAP | NOT SET ✅ Fail Closed |
| SLACK_SIGNING_SECRET | SET ✅ |
| SLACK_BOT_TOKEN1 | SET ✅ |
| SUPABASE_URL | `vwlahtguyggrhvslabax.supabase.co` ✅ |

**결론**: R3 코드 미배포, Relay 환경변수 4개 미설정 → Fail Closed 보증. 추가 발송 차단 확인.

상세 내용: [R3_RAILWAY_DEPLOY_GATE.md](R3_RAILWAY_DEPLOY_GATE.md)

---

## G0-04. Slack App 사전점검

| 항목 | 결과 |
|------|------|
| SLACK_SIGNING_SECRET 설정 | 기존 환경변수 (이미 설정 가정) |
| api_app_id | PENDING — Owner 콘솔 확인 필요 (P-02) |
| team_id | PENDING — Owner 콘솔 확인 필요 (P-02) |
| groups:history 스코프 | PENDING — OAuth & Permissions (P-03) |
| message.groups 이벤트 구독 | PENDING — Event Subscriptions (P-07) |
| 파일럿 private relay 채널 | PENDING — 신규 생성 필요 (P-04) |
| 테스트 대상 채널 | PENDING — 확인 및 tai_bot 초대 필요 (P-05) |
| Request URL 등록 | **배포 완료 후** 진행 (P-06) |

**결론**: Owner 직접 실행 항목 P-02~P-07 전체 PENDING.

상세 내용: [R3_SLACK_APP_SETUP_CHECKLIST.md](R3_SLACK_APP_SETUP_CHECKLIST.md)

---

## G0-05. 운영 Gate 실행 순서

| Gate | 작업 | 선행 조건 | 승인 |
|------|------|----------|------|
| G1 | Supabase Migration 적용 | main 병합 완료 ✅ | Owner 별도 승인 |
| G1V | DB 독립검증 | G1 완료 | GPT IV |
| G2 | Railway tai-api-prod 배포 | G1V PASS | Owner 별도 승인 |
| G2V | 배포 검증 (health/ready) | G2 완료 | 자동 확인 |
| G3 | Slack App P-02~P-07 설정 | G2 완료 | Owner 직접 실행 |
| G4 | Request URL Verification | G2 + G3 완료 | Owner P-06 실행 |
| G5 | 단일 Relay E2E (메시지 1건) | G3 + G4 완료 | Owner 별도 승인 |
| G6 | ChatGPT 자동화 1건 파일럿 | G5 PASS | Owner 별도 승인 |
| G7 | 운영 채널 3곳 전환 | G6 PASS | Owner 별도 승인 |

**각 Gate는 독립 Owner 승인 경계.** G1~G7 연속 자동 실행 금지.

---

## 제한 사항 유지

- TOKEN_ROTATION_DEFERRED / SECURITY_RISK_OPEN 유지
- 90일 보관 pg_cron: 별도 Owner 승인 후 설정
- `routers/slack_relay_recover.py` 파일 유지 (R15 테스트 의존), external.py 미등록
