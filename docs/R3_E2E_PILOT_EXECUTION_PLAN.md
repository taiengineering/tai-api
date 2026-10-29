---
title: R3 E2E 파일럿 실행 계획
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3-PRODUCTION-PREFLIGHT-001
status: PLAN_READY_EXECUTION_PENDING
date: 2026-10-30
---

# R3 E2E 파일럿 실행 계획 — G5

**선행 Gate**: G1(Migration) + G2(배포) + G3(Slack 설정) + G4(URL Verification) 완료  
**실행 주체**: Owner (수동)  
**범위**: 텍스트 메시지 1건, 파일럿 private 채널 → 테스트 대상 채널

---

## 파일럿 범위 재확인

| 항목 | 허용 | 금지 |
|------|------|------|
| 릴레이 채널 | 1개 (신규 private) | 본선 운영 채널 |
| 발신자 | 승인된 사용자만 | 비승인 사용자 |
| 메시지 타입 | text only | Blocks, 파일, 멘션 |
| 발신 봇 | tai_bot (SLACK_BOT_TOKEN1) | taimarketing 봇 |

---

## G5 실행 절차

### 사전 확인 (Owner)

1. `SLACK_RELAY_CHANNEL_MAP` 환경변수 설정 확인  
   (형식: `{"<relay_ch_id>":"<target_ch_id>"}`)
2. `SLACK_RELAY_ALLOWED_SENDER_IDS`에 자신의 Slack User ID 포함 확인
3. Railway 배포 상태 정상 확인

### 메시지 발송

1. Slack에서 파일럿 private relay 채널(`#tai-relay-pilot` 등)에 접속
2. 일반 텍스트 메시지 전송 (예: "R3 파일럿 테스트 메시지 1")
3. 대상 채널에 메시지가 `tai_bot`으로 전달되는지 확인 (약 3초 이내)

### 성공 기준

- [ ] 대상 채널에 메시지 도달
- [ ] 메시지 내용 일치
- [ ] DB 확인: `slack_relay_event_log`에 `status = 'SENT'` 행 존재

### DB 상태 확인 (선택)

```sql
SELECT event_id, status, sent_at, error_detail
FROM public.slack_relay_event_log
ORDER BY created_at DESC
LIMIT 5;
```

---

## 중단 조건

| 조건 | 처리 |
|------|------|
| 대상 채널에 메시지 미도달 (10초 이상) | DB status 확인 → 오류 조사 |
| DB status = FAILED_PERMANENT | error_detail 확인 → Slack API 오류 분류 |
| DB status = RETRY | `POST /internal/slack-relay/recover` 수동 실행 또는 CLI |
| 예상치 못한 채널에 메시지 발송 | SLACK_RELAY_CHANNEL_MAP 즉시 삭제 |

---

## 복구 방안

### 수동 복구 (PENDING/RETRY 행)

```bash
# 프로젝트 루트에서 실행 (운영 환경변수 필요)
python -m scripts.slack_relay_recover_cli --run
```

### 파일럿 중단

1. Railway 환경변수에서 `SLACK_RELAY_CHANNEL_MAP` 삭제 또는 `{}` 설정
2. 즉시 Fail Closed 상태로 전환 → 추가 발송 차단

---

## G6: ChatGPT 자동화 1건 파일럿 (별도 승인)

G5 PASS 후 7일 모니터링 (오류율 < 1%) 확인 후 Owner 별도 승인:

- 기존 ChatGPT 예약 자동화 1건에 릴레이 채널 연결
- 1주일 안정 운영 확인 후 G7(운영 채널 3곳 전체 전환)

---

## G7: 운영 채널 전환 (별도 승인)

G6 PASS 후:
- 본선 운영 채널 3곳 `SLACK_RELAY_CHANNEL_MAP` 추가
- `naver_monitor.py` / `slack_kin.py` 토큰 교체 검토 (TOKEN_ROTATION 별도 Gate)
- ChatGPT 자동화 4개 작업 업데이트

---

## 7일 모니터링 기준

| 지표 | 목표 |
|------|------|
| 오류율 | < 1% (FAILED_PERMANENT + UNKNOWN 비율) |
| 평균 발송 지연 | < 5초 (BackgroundTask 즉시 경로) |
| RETRY 미해소 건수 | 0건 (24시간 이내) |

**모니터링 쿼리**:
```sql
SELECT status, COUNT(*) AS cnt
FROM public.slack_relay_event_log
WHERE created_at > now() - INTERVAL '7 days'
GROUP BY status;
```
