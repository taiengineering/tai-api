# 백엔드 작업지시서 v2 (2026-04-07 재지시)

## 현재 확인된 미완료 상태
- work_schedules LEGAL: 0건 (generate-schedules API 없음)
- notifications: 0건 (trigger-due-alerts 코드는 있으나 Railway 미배포 추정)
- legal_engine.py SHA: 4aef8151 (변화 없음)
- notifications.py SHA: bea2cf86 (trigger-due-alerts 코드 포함됨)

---

## 작업 1: POST /legal-engine/generate-schedules/{factory_id}

### 파일: routers/legal_engine.py 하단에 추가

### 로직
1. factories 테이블에서 factory_id 조회 → company_id 확보
2. factory_diagnosis_results에서 해당 factory_id의 최신(is_latest=True) 진단 결과 조회
3. result_data.inspection_required 배열 순회
4. 각 룰을 work_schedules에 INSERT
   - source_type = 'LEGAL'
   - status_code = 'PENDING'
   - active_yn = True
   - rule_code = rule.rule_id
   - law_name = rule.law_name
   - law_article = rule.law_article
   - description = rule.obligation_summary 또는 rule.description
   - planned_date = 오늘 날짜 (cycle 계산 없이 일단 오늘)
   - company_id, factory_id 세팅
5. 동일 factory_id + rule_code + source_type='LEGAL' + status_code='PENDING' 이 이미 존재하면 스킵 (중복 방지)
6. 생성 건수 반환

### work_schedules 컬럼 (information_schema로 확인 필수)
실제 컬럼: id, asset_id, assigned_user_id, repeat_type, repeat_interval,
repeat_weekday, repeat_day, week_of_month, start_date, end_date, active_yn,
inspection_set_id, company_id, factory_id, planned_date, status_code, description,
completed_at, inspector_name, summary, schedule_group_id, source_type,
obligation_type, event_type, event_date, cycle_base_guide, rule_code,
law_name, law_article, form_code, created_at, updated_at

### 반환 예시
```json
{"status": "success", "data": {"created": 5, "skipped": 2}}
```

---

## 작업 2: Railway 배포 확인 및 trigger-due-alerts 동작 검증

### notifications.py의 trigger-due-alerts는 이미 구현됨 (SHA: bea2cf86)
- Railway에 최신 배포가 됐는지 확인
- 배포가 안 됐다면 Railway 재배포 트리거
- 배포 후 POST https://api.taieng.co.kr/notifications/trigger-due-alerts 직접 호출하여 동작 검증

---

## 주의사항
- 작업 전 반드시 information_schema.columns로 컬럼 확인
- get_file_contents로 legal_engine.py 최신 SHA 조회 후 작업
- 완료 후 Railway 로그에서 에러 없는지 확인
- 완료됐다고 보고하기 전 DB에서 work_schedules LEGAL 건수 실제 확인 필수
