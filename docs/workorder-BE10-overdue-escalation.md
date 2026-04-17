# BE-10: 점검 미이행 에스컬레이션 시스템

> **작성일**: 2026-04-17
> **대상 레포**: taiengineering/tai-api (백엔드)
> **법적 근거**: 산안법 §36, §93, §164 / 중대재해처벌법 §6, §7
> **🔴 절대 금지**: legal_engine.py 수정 금지

---

## 배경

점검이 할당(work_assignments)되었으나 기한 내 미이행 시:
- 현재: 아무 조치 없음 (PENDING 상태 유지)
- 목표: 자동 감지 → 알림 → 에스컬레이션 → 이력 기록

### 법적 리스크
- 점검 미실시 자체: 과태료 300~1,000만원
- 미실시 상태에서 사고: 7년 이하 징역 / 1억원 이하 벌금
- 사망사고(50인+): 1년 이상 징역 / 법인 50억원 이하 벌금

---

## 작업 1: DB 스키마 추가

```sql
-- work_assignments에 미이행 추적 컬럼
ALTER TABLE work_assignments
  ADD COLUMN IF NOT EXISTS due_date DATE,
  ADD COLUMN IF NOT EXISTS overdue_notified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS escalation_level INT DEFAULT 0;

COMMENT ON COLUMN work_assignments.due_date IS '이행 기한 (scheduled_date 기반 자동 설정)';
COMMENT ON COLUMN work_assignments.overdue_notified_at IS '미이행 알림 발송 시각';
COMMENT ON COLUMN work_assignments.escalated_at IS '안전관리자 에스컬레이션 시각';
COMMENT ON COLUMN work_assignments.escalation_level IS '에스컬레이션 단계 (0=없음, 1=작업자알림, 2=관리자알림, 3=OVERDUE전환)';

-- 미이행 이력 테이블
CREATE TABLE IF NOT EXISTS overdue_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id UUID REFERENCES work_assignments(id),
  factory_id UUID REFERENCES factories(id),
  user_id UUID,
  user_name TEXT,
  schedule_description TEXT,
  scheduled_date DATE,
  escalation_level INT DEFAULT 0,
  resolved_at TIMESTAMPTZ,
  resolved_by UUID,
  created_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE overdue_history IS '점검 미이행 이력 (누적 추적)';
```

---

## 작업 2: `routers/overdue_checker.py` 신규

### 에스컬레이션 타임라인

```
D-1  → 작업자 "내일 점검 예정" 알림
D-Day → 할당 활성화 (작업자 홈 표시)
D+1  → Level 1: 작업자 "점검 누락" 경고 알림
D+2  → Level 2: 안전관리자 "OOO 미이행" 에스컬레이션
D+7  → Level 3: 상태 PENDING → OVERDUE, 대시보드 빨간 경고
```

### API 엔드포인트

```
POST /overdue/check          수동 트리거 (cron 대체)
GET  /overdue/summary         미이행 현황 요약
GET  /overdue/history          미이행 이력 조회
POST /overdue/resolve/{id}    미이행 해소 처리
```

### 핵심 로직 (의사코드)

```python
async def check_overdue():
    supabase = get_supabase()
    today = date.today()
    
    # 1. D-1 리마인더 (내일 예정 + 미완료)
    tomorrow = today + timedelta(days=1)
    d1 = supabase.table("work_assignments").select("*")
        .eq("status_code", "PENDING")
        .eq("scheduled_date", tomorrow.isoformat())
        .is_("overdue_notified_at", "null")
        .execute()
    for a in d1.data:
        send_notification(a["assigned_user_id"], 
            f"내일 점검 예정: {a.get('description', '점검')}",
            type="REMINDER")
    
    # 2. D+1 Level 1: 작업자 경고
    yesterday = today - timedelta(days=1)
    d_plus_1 = supabase.table("work_assignments").select("*")
        .eq("status_code", "PENDING")
        .lte("scheduled_date", yesterday.isoformat())
        .lt("escalation_level", 1)
        .execute()
    for a in d_plus_1.data:
        send_notification(a["assigned_user_id"],
            f"⚠️ 점검 미이행: {a.get('description', '')}. 즉시 완료해주세요.",
            type="OVERDUE_WORKER")
        update_escalation(a["id"], level=1)
    
    # 3. D+2 Level 2: 안전관리자 에스컬레이션
    two_days_ago = today - timedelta(days=2)
    d_plus_2 = supabase.table("work_assignments").select("*")
        .eq("status_code", "PENDING")
        .lte("scheduled_date", two_days_ago.isoformat())
        .lt("escalation_level", 2)
        .execute()
    for a in d_plus_2.data:
        manager_id = find_safety_manager(a["factory_id"])
        send_notification(manager_id,
            f"🔴 점검 미이행 에스컬레이션: {user_name} - {description}",
            type="OVERDUE_MANAGER")
        update_escalation(a["id"], level=2)
    
    # 4. D+7 Level 3: OVERDUE 전환
    week_ago = today - timedelta(days=7)
    d_plus_7 = supabase.table("work_assignments").select("*")
        .eq("status_code", "PENDING")
        .lte("scheduled_date", week_ago.isoformat())
        .lt("escalation_level", 3)
        .execute()
    for a in d_plus_7.data:
        supabase.table("work_assignments").update({
            "status_code": "OVERDUE"
        }).eq("id", a["id"]).execute()
        
        # overdue_history 기록
        supabase.table("overdue_history").insert({...}).execute()
        update_escalation(a["id"], level=3)
    
    return {"d1_reminders": len(d1), "level1": len(d_plus_1), 
            "level2": len(d_plus_2), "level3": len(d_plus_7)}
```

### 알림 발송 (MessageMi 연동)

```python
def send_notification(user_id, message, type):
    # 1. notifications 테이블 INSERT
    # 2. MessageMi SMS API 호출 (user의 phone 조회)
    # 3. FCM 푸시 (fcm_token 있으면)
```

---

## 작업 3: main.py 라우터 등록

```python
from routers.overdue_checker import router as overdue_router
app.include_router(overdue_router)
```

---

## 작업 4: 스케줄러 연동

`scheduler.py`에 cron 등록:
```python
# 매일 오전 8시 KST (23:00 UTC 전일)
scheduler.add_job(check_overdue_job, 'cron', hour=23, minute=0)
```

또는 외부 cron (cron-job.org)에서 `POST /overdue/check` 호출

---

## 작업 5: GET /overdue/summary 응답

```json
{
  "status": "success",
  "data": {
    "total_overdue": 5,
    "by_level": {
      "level1_worker_warned": 2,
      "level2_manager_escalated": 2,
      "level3_overdue_status": 1
    },
    "by_factory": [
      {"factory_id": "...", "factory_name": "대성정밀", "count": 3},
      {"factory_id": "...", "factory_name": "1공장", "count": 2}
    ],
    "by_user": [
      {"user_id": "...", "user_name": "김작업", "overdue_count": 2, "reliability": "LOW"}
    ],
    "legal_risk": {
      "message": "5건 미이행 — 과태료 최대 5,000만원 노출",
      "penalty_estimate_krw": 50000000
    }
  }
}
```

---

## 체크리스트

- [ ] DB: work_assignments 4컬럼 추가
- [ ] DB: overdue_history 테이블 생성
- [ ] routers/overdue_checker.py 생성
- [ ] POST /overdue/check (미이행 체크 + 에스컬레이션)
- [ ] GET /overdue/summary (현황 요약)
- [ ] GET /overdue/history (이력 조회)
- [ ] POST /overdue/resolve/{id} (해소 처리)
- [ ] main.py 라우터 등록
- [ ] scheduler.py cron 등록 (매일 08:00 KST)
- [ ] notifications 연동 (MessageMi SMS)
- [ ] legal_engine.py 미수정 확인

---

## 🔴 금지사항

1. legal_engine.py 수정 금지
2. work_schedules 테이블 구조 변경 금지
3. 기존 PENDING→DONE 상태 전환 로직 변경 금지
