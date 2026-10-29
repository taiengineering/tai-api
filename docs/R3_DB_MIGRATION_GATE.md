---
title: R3 DB Migration Gate
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3-PRODUCTION-PREFLIGHT-001
status: READY_FOR_OWNER_APPROVAL
date: 2026-10-30
---

# R3 DB Migration Gate — G1

**대상**: `migrations/2026-10-30_slack_relay_event_log.sql`  
**대상 DB**: taieng (vwlahtguyggrhvslabax), ap-northeast-2  
**현재 상태**: **MIGRATION_NOT_APPLIED**

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
-- 컬럼: id(uuid PK), event_id(UNIQUE), relay_channel, target_channel,
--        message_text(≤4000), sender_id, source_message_ts,
--        status(PENDING/CLAIMED/SENDING/SENT/RETRY/UNKNOWN/FAILED_PERMANENT),
--        retry_count, next_attempt_at, claimed_at, dispatch_started_at,
--        sent_at, slack_ts, claim_token, claim_expires, error_detail,
--        created_at, updated_at

-- 인덱스 3개:
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

Migration은 직접 SQL 실행 방식을 사용합니다 (Supabase CLI migrate 방식 아님).

**Owner 실행 절차**:
1. Supabase Dashboard → SQL Editor (또는 psql)
2. `migrations/2026-10-30_slack_relay_event_log.sql` 내용 전체 실행
3. 성공 확인: `SELECT COUNT(*) FROM public.slack_relay_event_log;` → `0`
4. RLS 확인: `SELECT schemaname, tablename, rowsecurity FROM pg_tables WHERE tablename = 'slack_relay_event_log';` → `rowsecurity=true`

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

- [ ] `slack_relay_event_log` 테이블 존재 확인
- [ ] `rowsecurity = true` 확인
- [ ] 인덱스 3개 생성 확인
- [ ] anon 역할 접근 거부 확인 (GPT 독립검증)

**Owner 승인 후 Claude Code가 GPT 독립검증 제출.**
