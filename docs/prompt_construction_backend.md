# 건설 섹터 백엔드 작업 프롬프트

> 이 파일을 **백엔드 Claude 창**에 그대로 붙여넣으세요.

---

```
당신은 TAI Safe 백엔드 개발자입니다.

## 프로젝트 스택
- FastAPI / Python (tai-api)
- Railway 배포: api.taieng.co.kr
- Supabase / PostgreSQL (project: xntdkrjhgcscmqctdzyo)
- GitHub: taiengineering/tai-api

## 오늘 작업: 건설 섹터 백엔드 구현

작업 파일: routers/construction.py (기존 파일 확인 후 미구현 엔드포인트 추가)

---

### ★ 최우선 스펙 (v2.1.0) — 반드시 준수

#### 1. 법령진단 POST /construction/sites/{site_id}/diagnose
응답 구조:
```json
{
  "status": "success",
  "data": {
    "site_id": "uuid",
    "total_rules": 173,
    "applicable_rules": 47,
    "inspection_sets_created": 47,
    "by_obligation_type": {
      "BEFORE_WORK": 22, "ACTION": 18, "INSPECT": 5, "APPOINT": 2
    }
  }
}
```
- 중복 실행 시 기존 inspection_sets SKIP (NOT EXISTS 패턴)
- 완료 후 construction_sites.diagnosis_applicable_count, last_diagnosis_at 업데이트 필수
- 에러: HTTP 422 + {"detail": "공사금액을 먼저 입력해주세요."}

#### 2. 작업일정 자동 생성 POST /construction/sites/{site_id}/generate-schedules
응답 구조:
```json
{"status":"success","data":{"created":34,"skipped":13,"total_rules":47}}
```
- diagnosis_applicable_count == 0 이면 HTTP 400 + {"detail": "법령진단을 먼저 실행하세요."}
- BEFORE_WORK 의무: cycle_unit=day, cycle_value=1 자동 설정
- 이미 생성된 스케줄 중복 생성 금지 (NOT EXISTS)

#### 3. 점검 저장 POST /construction/inspections
요청 Body:
```json
{
  "site_id": "uuid",
  "process_id": "uuid",
  "inspector_phone": "01012345678",
  "checklist_items": [
    {"item_name": "타이어 상태", "result": "ok",  "note": ""},
    {"item_name": "경적 작동",  "result": "bad", "note": "경적 불량"}
  ]
}
```
- overall_result 생략 가능 → API 자동 계산:
  - overall_result = "ISSUE" if any result=="bad" else "PASS"
  - defect_count = bad 항목 수
- 이상 발생 시 site.manager_id → users.push_token → FCM 자동 발송
- FIREBASE_CREDENTIALS = Railway Variables에 서비스 계정 JSON 전체 저장

---

### 구현 순서

1단계: construction sites CRUD
- GET  /construction/sites?company_id={cid}&page=1&size=20
- POST /construction/sites (필수: site_name, company_id, contract_amount, construction_type, start_date, end_date, total_workers)
- GET  /construction/sites/{id}
- PATCH /construction/sites/{id}
- DELETE /construction/sites/{id} → is_active=False

선임 자동 계산 (저장 시):
```python
def calc_safety_manager_required(construction_type, contract_amount):
    thresholds = {"건축": 15_000_000_000, "토목": 12_000_000_000, "복합": 12_000_000_000}
    return contract_amount >= thresholds.get(construction_type, 15_000_000_000)
```

2단계: 법령진단 API → ★ v2.1.0 스펙 준수
- master_building_legal_rules WHERE sector='CONSTRUCTION' 전체 조회
- condition_code 기반 해당 현장 조건 매칭 → inspection_sets 생성
- applicable_rules, by_obligation_type 응답 필수

3단계: 공정 CRUD
- GET/POST/PATCH/DELETE /construction/sites/{id}/processes
- is_high_risk 자동 계산:
```python
HIGH_RISK_TYPES = {'DEMOLITION','EXCAVATION','HIGH_PLACE','CRANE','TUNNEL','COFFERDAM','CONCRETE_FORM','STEEL_FRAME'}
is_high_risk = work_type_code in HIGH_RISK_TYPES
```

4단계: 점검 저장 + FCM → ★ v2.1.0 스펙 준수
- POST /construction/inspections
- GET  /construction/inspections?site_id={id}&page=1&size=20
- PATCH /construction/inspections/{id}  # 시정조치

5단계: 작업자 관리
- GET/POST/DELETE /construction/sites/{id}/workers

6단계: 작업일정 자동 생성 → ★ v2.1.0 스펙 준수
- POST /construction/sites/{id}/generate-schedules

---

### 주의사항
- construction_sites.factory_id는 선택사항 (없어도 됨)
- total_workers = direct_workers + subcon_workers
- construction_inspections.process_id로 공정별 이력 추적
- main.py에 라우터 등록 후 버전 업 (v5.x.x → v5.x.x+1)
- 완료 후 Railway 자동 배포 확인
```
