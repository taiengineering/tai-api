---
title: R3 DB Migration Gate
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3-PRODUCTION-PREFLIGHT-001
status: READY_FOR_OWNER_APPROVAL
date: 2026-10-30
---

# R3 DB Migration Gate — G1

**대상**: `migrations/2026-10-30_slack_relay_event_log.sql`  
**대상 DB**: taieng (vwlahtguyggrhvslabax), ap-northeast-2  
**현재 상태**: **MIGRATION_APPLIED — G1V GPT_IV_PASS / CLOSED FINAL**  
**Migration 이력**: `20261030060217_slack_relay_event_log_r3`

---

## 1. 사전 점검 결과

| 항목 | 결과 |
|------|------|
| `slack_relay_event_log` 존재 여부 | **NOT EXISTS** → 신규 생성 필요 |
| 동명 충돌 테이블 | 없음 |
| Migration SQL 멱등성 | `CREATE TABLE IF NOT EXISTS` — 멱등 ✅ |
| DB 상태 | ACTIVE_HEALTHY ✅ |
| 최신 Migration 버전 | `20261029173518` |

---

## 2. Migration SQL 내용 요약

```sql
-- 테이블: slack_relay_event_log
-- 컬럼 19개:
--   id, event_id, relay_channel, target_channel, message_text(≤4000),
--   sender_id, source_message_ts, status, retry_count, next_attempt_at,
--   claimed_at, dispatch_started_at, sent_at, slack_ts, claim_token,
--   claim_expires, error_detail, created_at, updated_at
-- (status: PENDING/CLAIMED/SENDING/SENT/RETRY/UNKNOWN/FAILED_PERMANENT)

-- 명시적 CREATE INDEX 3개 (event_id UNIQUE 자동 인덱스 별도):
--   idx_srel_status_next   (status, next_attempt_at, created_at)
--   idx_srel_event_id      (event_id)
--   idx_srel_updated_at    (updated_at)

-- RLS:
--   anon:          DENY (RESTRICTIVE)
--   authenticated: DENY (RESTRICTIVE)
--   service_role:  ALLOW
```

---

## 3. 적용 방법

`apply_migration` 도구를 통한 **1회 단일 적용** 방식을 사용합니다.  
Dashboard SQL Editor에서 동일 SQL을 중복 실행하지 않습니다.

**Claude Code 실행 절차 (Owner 승인 후)**:
1. `apply_migration` 도구 호출
   - 대상 프로젝트: `taieng` (`vwlahtguyggrhvslabax`)
   - Migration 이름: `slack_relay_event_log_r3`
   - SQL: `migrations/2026-10-30_slack_relay_event_log.sql` 전체 내용
2. 적용 이력 자동 기록 (중복 실행 방지)
3. 성공 확인: `SELECT COUNT(*) FROM public.slack_relay_event_log;` → `0`
4. RLS 확인: `SELECT rowsecurity FROM pg_tables WHERE tablename = 'slack_relay_event_log';` → `true`

**실패 시**: 부분 적용 여부를 먼저 조사하고, 재실행 전 GPT 독립검증 선행.

---

## 4. 롤백 방안

적용 후 문제 발생 시:
```sql
-- 롤백 (운영 데이터 없을 경우만 실행)
DROP TABLE IF EXISTS public.slack_relay_event_log;
```

파일럿 시작(첫 메시지 발송) 이후에는 `DROP` 금지. 상태 조사 후 Owner 승인 필요.

---

## 5. 90일 보관 cron 설정 (별도 Gate)

```sql
-- 파일럿 안정화 후 Owner 승인 시 실행
SELECT cron.schedule('slack-relay-cleanup', '0 3 * * *',
  $$DELETE FROM public.slack_relay_event_log
    WHERE status IN ('SENT','FAILED_PERMANENT')
    AND created_at < now() - INTERVAL '90 days'$$);
```

이 cron은 G1과 별도로 Owner가 승인할 때 적용합니다.

---

## 6. Gate 통과 기준

- [x] `slack_relay_event_log` 테이블 존재 확인
- [x] 컬럼 19개 존재 확인
- [x] `rowsecurity = true` 확인
- [x] 명시적 CREATE INDEX 3개 생성 확인 (event_id UNIQUE 자동 인덱스와 구분)
- [x] anon 역할 접근 거부 확인 (GPT 독립검증)

**G1V: PASS — 2026-10-30 (GPT 독립검증 완료)**

---

## 7. GPT IV 발견 사항 (비차단)

| 항목 | 내용 | 처리 |
|------|------|------|
| anon/authenticated SQL 권한 | 테이블에 GRANT 잔존. RLS RESTRICTIVE가 데이터 접근 차단 중 | G5 전 별도 Gate에서 REVOKE 권고 |
| idx_srel_event_id 중복 | UNIQUE 자동 인덱스와 구조 중복 | 성능 정리 후보 — 현재 차단 사유 아님 |

두 항목 모두 G1 차단 사유 아님. 별도 Owner 승인하에 보안 보강.

**Owner 승인 후 Claude Code가 GPT 독립검증 제출.**
