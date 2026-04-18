# BE-10: 업무 지연 에스켈레이션 작업지시서

**작성일:** 2026-04-17  
**파일:** `routers/overdue_checker.py` v1.0.0  
**PR:** https://github.com/taiengineering/tai-api/pull/1 (dev→main)

---

## 배경

`work_assignments`에 마감일이 지나도 완료되지 않으면 자동으로 단계적으로 알림하여 해소를 유도하는 에스켈레이션 시스템.

---

## 에스켈레이션 4단계

| 단계 | overdue_level | 조건 | 함수명 | 대상 | 채널 |
|---|---|---|---|---|---|
| D-1 리마인더 | 1 | 마감일 1일 전 | REMIND | 작업자 | SMS |
| D+1 작업자 경고 | 2 | 1일 초과 | WARN_WORKER | 작업자 | SMS + FCM |
| D+2 관리자 알림 | 3 | 2일 초과 | NOTIFY_MANAGER | 안전관리자 | SMS + FCM |
| D+7 OVERDUE | 4 | 7일 초과 | MARK_OVERDUE | 안전관리자 | SMS + FCM + 상태전환 |

---

## DB 변경 (Migration: `be10_overdue_escalation`)

### work_assignments 4코럼 추가

| 코럼 | 타입 | 설명 |
|---|---|---|
| `due_date` | date | 마감일 (NULL이면 scheduled_date 사용) |
| `overdue_level` | smallint | 0~4 (현재 에스켈 단계) |
| `last_reminded_at` | timestamptz | 마지막 알림 발송 시각 |
| `resolved_at` | timestamptz | 지연 해소 일시 |

### overdue_history 신규 테이블

```sql
CREATE TABLE overdue_history (
  id               uuid PRIMARY KEY,
  assignment_id    uuid REFERENCES work_assignments(id) ON DELETE CASCADE,
  factory_id       uuid,
  assigned_user_id uuid,
  overdue_level    smallint,
  action_type      text,  -- REMIND|WARN_WORKER|NOTIFY_MANAGER|MARK_OVERDUE|RESOLVE
  message_body     text,
  sms_sent         boolean,
  fcm_sent         boolean,
  notif_sent       boolean,
  resolved         boolean DEFAULT false,
  resolved_at      timestamptz,
  resolved_by      uuid,
  resolve_note     text,
  created_at       timestamptz DEFAULT now()
);
```

---

## API

| 메서드 | URL | 설명 |
|---|---|---|
| POST | `/overdue/check` | 에스켈레이션 실행 (cron/수동) |
| GET | `/overdue/summary` | 지연 현황 요약 |
| GET | `/overdue/history` | 이력 조회 |
| POST | `/overdue/resolve/{history_id}` | 지연 해소 |

**POST /overdue/check 쿼리파라미터:**
- `?factory_id=` — 특정 시설만 (미지정 = 전체)
- `?dry_run=true` — 시뮬레이션 (DB/알림 실제 발송 없음)
- `?limit=200` — 배치 최대 건수

---

## 알림 채널

| 채널 | 구현 | 기준 |
|---|---|---|
| SMS | `messaging.py._call_edge()` 동일 패턴 | `users.allow_sms=true` + `phone` |
| FCM 푸시 | FCM Edge Function 경유 | `users.allow_push=true` + `push_token` |
| notifications | `notifications` 테이블 INSERT | 전체 레벨 코드에서 작성 |

---

## 우선순위 로직

1. `due_date` 우선 → 없으면 `scheduled_date` 사용
2. 이미 해당 level 이상이면 재발송 안함
3. DONE / SKIP 작업 제외
4. MARK_OVERDUE 시 status_code='OVERDUE' 자동 전환

---

## cron 연동 예시 (cron-job.org)

```
URL: POST https://api.taieng.co.kr/overdue/check
스케줄: 매일 09:00 KST (00:00 UTC)
```

---

## FCM Edge Function

현재 `send-push` Edge Function 미배포 시 FCM 푸시 실패 활률 높음 (503).
가능하면 `send-push` Edge Function 배포 권장.
SMS와 notifications 테이블은 배포 없이 실행 가능.
