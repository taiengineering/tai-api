---
title: Owner 파일럿 구현 승인 요청서
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3
version: ADDENDUM-001
status: PENDING_OWNER_APPROVAL
date: 2026-10-29
---

# Owner 파일럿 구현 승인 요청서

## 목적

WO-TAI-SLACK-BOT-UNIFIED-001-R3 (Alternative C: Slack Events Relay)
파일럿 구현을 Claude Code가 시작하기 위한 Owner 사전 승인을 요청한다.

---

## GPT IV 최종 판정 요약

| 항목 | 판정 |
|------|------|
| 아키텍처 잠금 | ARCHITECTURE_LOCKED |
| 보안 계약 | PASS |
| 내구성 계약 | DURABILITY_CORRECTION_REQUIRED → Addendum으로 해소 |
| 토큰 교체 | TOKEN_ROTATION_DEFERRED (Owner 결정, SECURITY_RISK_OPEN 유지) |
| 최종 판정 | GPT_IV_CONDITIONAL_PASS (조건: Addendum 확정) |

---

## 산출물 완료 현황

| 산출물 | 상태 |
|--------|------|
| 보안 계약서 (원안) | COMPLETE |
| 내구성 계약서 (원안) | COMPLETE |
| 파일럿 테스트 매트릭스 T01~T18 (원안) | COMPLETE |
| 아키텍처 설계 (원안) | COMPLETE |
| DB 스키마 (원안) | COMPLETE |
| **R3_PILOT_GATE_ADDENDUM_FINAL.md** | COMPLETE (2026-10-29) |
| **RELAY_RECOVERY_STATE_MATRIX.md** | COMPLETE (2026-10-29) |
| **TOKEN_ROTATION_SAFE_PROCEDURE.md** | COMPLETE (2026-10-29) |
| **본 승인 요청서** | COMPLETE (2026-10-29) |

---

## Owner 선결 조건 (구현 시작 전 Owner 직접 실행)

아래 항목은 Claude Code가 대신 실행할 수 없습니다.
Owner가 완료 후 구두 또는 서면으로 확인해 주십시오.

| # | 항목 | 완료 여부 |
|---|------|-----------|
| P-01 | `SLACK_BOT_TOKEN1` 재발급 + Railway `tai-api-prod` 환경변수 업데이트 | **DEFERRED** — Owner 결정. 구현은 계속 진행하나 SECURITY_RISK_OPEN 유지. |
| P-02 | Slack App 관리 콘솔에서 `api_app_id` 확인 및 보안 기록 | □ |
| P-03 | `groups:history` 스코프 추가 (OAuth & Permissions) | □ |
| P-04 | 파일럿용 private 릴레이 채널 생성 + 채널 ID 확인 | □ |
| P-05 | 테스트 대상 채널 확인 + `tai_bot` 채널 초대 | □ |
| P-06 | Slack App Event Subscriptions URL 등록: `https://api.taieng.co.kr/slack/events` | □ |
| P-07 | Event Subscriptions: `message.groups` 이벤트 구독 추가 | □ |

**P-06 주의**: URL Verification은 `/slack/events` 엔드포인트가 배포된 후에만 성공.
구현 완료 → 배포 → P-06 순서.

---

## Claude Code 구현 범위 (Owner 승인 후)

| 파일 | 작업 | 규모 |
|------|------|------|
| `routers/slack_events.py` | 신규 생성 | ~90줄 |
| `services/slack_relay_svc.py` | 신규 생성 | ~80줄 |
| `services/permission_guard.py` | `_PUBLIC`에 1줄 추가 | 1줄 |
| `migrations/20261029XXXXXX_slack_relay_event_log.sql` | 신규 생성 | ~30줄 |
| `tests/test_slack_relay.py` | 신규 생성 (T01~T25) | ~200줄 |
| `main.py` or router_registry | 라우터 등록 | 1줄 |

**구현 불포함 항목** (파일럿 범위 외):
- 본선 채널 연결
- Blocks/파일/멘션 메시지 처리
- ChatGPT 자동화 4개 작업 업데이트
- `naver_monitor.py` / `slack_kin.py` 토큰 교체
- Token Rotation 활성화

---

## 파일럿 경계 재확인

| 항목 | 파일럿 중 허용 | 파일럿 중 금지 |
|------|--------------|--------------|
| 릴레이 채널 | 1개 (신규 private) | 본선 채널 |
| 수신 채널 | 1개 (테스트 전용) | 운영 채널 3개 |
| 메시지 타입 | text only | Blocks, 파일, 멘션 |
| 발신 봇 | tai_bot (SLACK_BOT_TOKEN1) | taimarketing 봇 |

---

## 구현 완료 후 Gate

| 단계 | 조건 |
|------|------|
| G1 (코드 완료) | T01~T25 PASS + mypy/flake8 PASS |
| G2 (배포) | Railway tai-api-prod 배포 성공 |
| G3 (E2E) | 파일럿 채널 수동 E2E 1회 PASS |
| G4 (모니터링) | 7일 오류율 < 1% |
| G5 (파일럿 성공) | Owner 확인 → 본선 채널 확장 승인 |

---

## 승인 방법

Owner가 아래 중 하나로 응답:

**승인**: "파일럿 구현 승인합니다." + P-01~P-07 완료 항목 명시

**조건부 승인**: 완료된 P 항목만 명시 후 나머지 완료 시 Claude Code 알림 요청

**거절**: 사유 명시

---

## 토큰 교체 결정 현황 (COR-06 보정)

**Owner 결정 (2026-10-30)**: TOKEN_ROTATION_DEFERRED

- P-01 토큰 교체는 파일럿 구현의 선결 조건에서 제외됨
- 구현(Draft PR)과 검증은 계속 진행
- SECURITY_RISK_OPEN 유지 — 토큰 노출 위험이 해소된 것으로 표기하지 않음
- 토큰 전체값은 어떠한 경우에도 로그·코드에 출력하지 않음
- 실제 토큰 교체는 별도 Owner 승인 후 진행

이 결정은 보안 위험을 허용하는 것이 아니라, 파일럿 코드 검증을 먼저 완료하여
교체 시점의 실수를 최소화하기 위한 절차적 결정입니다.
