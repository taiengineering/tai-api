# TAI 백엔드 작업지시서 — 건설·특수시설 법령 추가 수집

> 우선순위: 🔴 긴급  
> 작성일: 2026-03-29  
> 레포: taiengineering/tai-api

---

## 현재 상태

| 항목 | 상태 |
|------|------|
| legal_engine.py v4.2.0 | ✅ 완성 (step1/2/3 API 모두 구현) |
| factory_diagnosis_results 테이블 | ✅ 생성 완료 |
| BUILDING 룰 398개 | ✅ 적재 완료 |
| MANUFACTURING 룰 13개 | ✅ 적재 완료 |
| CONSTRUCTION 룰 10개 | ✅ 적재 완료 |
| SPECIAL_FACILITY 룰 6개 | ✅ 적재 완료 |
| 건설·특수시설 핵심 법령 원문 | ❌ **미수집** |

---

## STEP 1. 서버 실행 + 추가 법령 수집

```bash
# 환경변수 설정
export SUPABASE_URL=https://xntdkrjhgcscmqctdzyo.supabase.co
export SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhudGRrcmpoZ2NzY21xY3RkenlvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMwNzM5NjksImV4cCI6MjA4ODY0OTk2OX0.VUe805Y1s4il1RgY1KV94xUw6F3YD7_to46yUIaQrBE
export LAW_API_OC=taieng

# 서버 실행
uvicorn main:app --reload --port 8000
```

별도 터미널에서 아래 순서대로 실행:

```bash
# 건설업 핵심 법령
curl -X POST "http://localhost:8000/law-collector/collect/건설산업기본법"
curl -X POST "http://localhost:8000/law-collector/collect/건설기술진흥법"

# 특수시설 핵심 법령
curl -X POST "http://localhost:8000/law-collector/collect/의료법"
curl -X POST "http://localhost:8000/law-collector/collect/학교안전사고 예방 및 보상에 관한 법률"
curl -X POST "http://localhost:8000/law-collector/collect/다중이용업소의 안전관리에 관한 특별법"
curl -X POST "http://localhost:8000/law-collector/collect/사회복지사업법"
curl -X POST "http://localhost:8000/law-collector/collect/노인복지법"
curl -X POST "http://localhost:8000/law-collector/collect/어린이놀이시설 안전관리법"

# 수집 확인
curl http://localhost:8000/law-collector/status
```

---

## STEP 2. step1 API 동작 테스트

수집 완료 후 각 섹터별로 테스트:

```bash
# BUILDING 테스트
curl -X POST http://localhost:8000/legal-engine/diagnose/step1 \
  -H 'Content-Type: application/json' \
  -d '{
    "factory_id": "<factories 테이블에서 실제 UUID 하나 사용>",
    "sector": "BUILDING",
    "input": {
      "building_use_category": "업무시설",
      "gross_floor_area": 5000,
      "above_ground_floors": 8,
      "worker_count": 50,
      "electric_capacity_kw": 200
    }
  }'

# MANUFACTURING 테스트
curl -X POST http://localhost:8000/legal-engine/diagnose/step1 \
  -H 'Content-Type: application/json' \
  -d '{
    "factory_id": "<실제 UUID>",
    "sector": "MANUFACTURING",
    "input": {
      "ksic_lv1_code": "C25",
      "worker_count": 80,
      "has_hazardous_material": true,
      "electric_capacity_kw": 200
    }
  }'

# CONSTRUCTION 테스트
curl -X POST http://localhost:8000/legal-engine/diagnose/step1 \
  -H 'Content-Type: application/json' \
  -d '{
    "factory_id": "<실제 UUID>",
    "sector": "CONSTRUCTION",
    "input": {
      "contract_amount": 20000000000,
      "worker_count": 50,
      "construction_type": "BUILDING"
    }
  }'
```

---

## 완료 체크리스트

```
□ 건설산업기본법 수집
□ 건설기술진흥법 수집
□ 의료법 수집
□ 다중이용업소법 수집
□ 사회복지사업법 수집
□ step1 BUILDING 200 응답
□ step1 MANUFACTURING 200 응답
□ step1 CONSTRUCTION 200 응답
□ factory_diagnosis_results 테이블에 결과 저장 확인
```
