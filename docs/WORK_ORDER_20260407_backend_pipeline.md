# 백엔드 작업지시서 — 진단→일정 자동생성 + 알림 파이프
**날짜: 2026-04-07 | 담당: 백엔드 창 | 저장소: tai-api**

---

## 배경

법령엔진이 `factory_diagnosis_results`에 진단 결과를 쌓고 있으나,
그 결과가 `work_schedules`로 자동 변환되는 파이프가 없음.
현재 work_schedules 156건 전부 MANUAL, 법령 연동 0건.
알림도 notification_settings 42건이 있으나 발송 기록 0건.

---

## 작업 1: 진단 결과 → work_schedules 자동생성 API

### 엔드포인트
```
POST /legal-engine/generate-schedules/{factory_id}
```

### 로직
1. `factory_diagnosis_results`에서 해당 factory_id의 최신 진단 결과 조회 (is_latest=True)
2. `result_data.inspection_required` 배열 순회
3. 각 룰을 `work_schedules`에 INSERT
   - `source_type` = `'LEGAL'`
   - `legal_rule_id` = rule.rule_id
   - `title` = rule.obligation_summary
   - `schedule_type` = rule.schedule_type (PERIODIC / BEFORE_WORK / ON_DEMAND)
   - `cycle_unit` = rule.inspection_cycle_unit
   - `cycle_value` = rule.inspection_cycle_int
   - `due_date` = 오늘 기준 cycle 계산
   - `status` = 'PENDING'
   - `factory_id` = factory_id
4. 이미 동일 `legal_rule_id`로 PENDING인 일정이 있으면 스킵 (중복 방지)
5. 생성된 건수 반환

### 반환 예시
```json
{
  "status": "success",
  "data": {
    "created": 18,
    "skipped": 5,
    "total_rules": 23
  }
}
```

### 파일 위치
`routers/legal_engine.py` 하단에 추가 (기존 create-inspection-sets 참고)

---

## 작업 2: D-7 / D-3 / 당일 알림 발송 API

### 엔드포인트
```
POST /notifications/trigger-due-alerts
```

### 로직
1. 오늘 기준 work_schedules에서 due_date 조회
   - D-7: due_date = 오늘 + 7일
   - D-3: due_date = 오늘 + 3일  
   - D-0: due_date = 오늘
2. 각 일정의 담당자(assigned_user_id) 조회
3. `notifications` 테이블에 INSERT
   ```
   {
     factory_id, user_id, schedule_id,
     type: 'DUE_ALERT',
     message: f"{title} 마감 {days}일 전입니다",
     due_days: 7 or 3 or 0,
     is_sent: false
   }
   ```
4. 같은 schedule_id + due_days 조합이 이미 있으면 스킵
5. 생성 건수 반환

### 파일 위치
`routers/notifications.py` 신규 생성 또는 기존 파일 확인 후 추가

---

## 작업 3: 크론 연동

`routers/cron.py`에 아래 두 작업 등록:

```python
# 매일 오전 8시 — 당일/D-3/D-7 알림 생성
POST /notifications/trigger-due-alerts

# 진단 완료 후 호출 — 일정 자동생성 (diagnose/step1 완료 시 자동 호출 고려)
POST /legal-engine/generate-schedules/{factory_id}
```

---

## 검증 방법

```bash
# 1. 특정 factory_id로 일정 자동생성 호출
POST https://api.taieng.co.kr/legal-engine/generate-schedules/{factory_id}

# 2. work_schedules 확인
SELECT source_type, count(*) FROM work_schedules GROUP BY source_type;
# LEGAL 건수가 0보다 커야 함

# 3. 알림 트리거
POST https://api.taieng.co.kr/notifications/trigger-due-alerts

# 4. notifications 확인
SELECT count(*) FROM notifications;
# 0보다 커야 함
```

---

## 주의사항
- work_schedules 테이블 컬럼명 `information_schema.columns`로 먼저 확인 후 작업
- SHA는 항상 get_file_contents로 최신값 조회 후 업데이트
- diagnose/step1 완료 시 자동으로 generate-schedules를 호출할지는 별도 결정 필요
