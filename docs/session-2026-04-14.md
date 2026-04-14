# TAI Safe 작업 세션 — 2026-04-14

## 1. Railway → Fly.io 이전 (어제 세션 이월)
- 완료 확인: api.taieng.co.kr 정상, server_ip=137.66.9.95 고정 IP

---

## 2. UptimeRobot Fly.io 모니터 설정값 안내

| 모니터 | URL | 타입 |
|---|---|---|
| TAI API (Fly.io 도쿄) | https://api.taieng.co.kr/health | HTTPS + Keyword("healthy") |
| TAI Admin | https://admin.taieng.co.kr | HTTPS |
| TAI Safe | https://safe.taieng.co.kr | HTTPS |
| TAI 마케팅 | https://new.taieng.co.kr | HTTPS |

---

## 3. 가격체계 DB 수정 (price_saas_plan / price_diagnosis_report)

### 3-1. DDL — 컬럼 추가 (apply_migration)
```sql
ALTER TABLE price_saas_plan
  ADD COLUMN IF NOT EXISTS billing_unit TEXT DEFAULT 'FACILITY',
  ADD COLUMN IF NOT EXISTS sms_included INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS kakao_included INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS doc_included INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS include_tbm BOOLEAN DEFAULT false;
```

### 3-2. 확정 플랜 INSERT (10개 활성, 구버전 is_active=false)

| plan_code | sector | billing_unit | 월가격 | SMS | 카카오 | 서류 |
|---|---|---|---|---|---|---|
| BUILDING_BASIC | BUILDING | FACILITY | 59,000 | 50 | 50 | 5 |
| BUILDING_STANDARD | BUILDING | FACILITY | 99,000 | 150 | 150 | 15 |
| BUILDING_CUSTOM | BUILDING | FACILITY | 0 (협의) | 0 | 0 | 0 |
| INDUSTRY_STARTER_V2 | INDUSTRY | FACILITY | 79,000 | 100 | 100 | 10 |
| INDUSTRY_BUSINESS_V2 | INDUSTRY | FACILITY | 149,000 | 300 | 300 | 30 |
| INDUSTRY_PRO | INDUSTRY | FACILITY | 249,000 | 500 | 500 | 50 |
| INDUSTRY_CUSTOM_V2 | INDUSTRY | FACILITY | 350,000 | 0 | 0 | 0 |
| CONSTRUCTION_STANDARD_V2 | CONSTRUCTION | SITE | 199,000 | 300 | 300 | 30 |
| CONSTRUCTION_PREMIUM_V2 | CONSTRUCTION | SITE | 399,000 | 500 | 500 | 50 |
| CONSTRUCTION_CUSTOM_V2 | CONSTRUCTION | SITE | 500,000 | 0 | 0 | 0 |

### 3-3. 법령진단 V2 가격 업데이트 (구버전 is_active=false)

| code | process_fee | equipment_fee | total_report_fee |
|---|---|---|---|
| BUILDING_V2 | 299,000 | 0 | 0 |
| INDUSTRY_V2 | 99,000 | 199,000 | 249,000 |
| CONSTRUCTION_V2 | 299,000 | 0 | 0 |

---

## 4. 공개 가격 API 구현 (public_pricing v1.1.0)

### 신규 엔드포인트
- `GET /public/pricing/saas-plans` — SaaS 플랜 목록 (인증 불필요)
- `GET /public/pricing/diagnosis-reports` — 법령진단 가격 목록 (인증 불필요)

### 테스트 결과
```
curl https://api.taieng.co.kr/public/pricing/saas-plans
→ {"success":true,"data":[{"plan_code":"BUILDING_BASIC","monthly_base_fee":59000,...}]}

curl https://api.taieng.co.kr/public/pricing/diagnosis-reports
→ {"success":true,"data":[{"facility_type_code":"BUILDING_V2","process_fee":299000,...}]}
```
✅ 두 엔드포인트 모두 정상 응답 확인

---

## 5. 카카오 API 완전 제거 — juso.py v2.1.0

### 변경 내용
| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| API | 카카오 로컬 API (dapi.kakao.com) | 행안부 도로명주소 API (juso.go.kr) |
| 환경변수 | KAKAO_REST_API_KEY | JUSO_API_KEY (Fly.io에 이미 등록됨) |
| 엔드포인트 | /juso/coord, /juso/search | 동일 유지 |
| 추가 응답 | - | zip_code, sido, sigungu 추가 |

### 커밋 이력
- v2.0.0: 카카오 제거, 행안부 API 교체
- v2.1.0: 환경변수명 JUSO_API_KEY로 수정 (Fly.io 기존 secret 재사용)

### 환경변수 상태
- `KAKAO_REST_API_KEY`: 원래 없었음 (별도 삭제 불필요)
- `JUSO_API_KEY`: Fly.io에 이미 등록됨 ✅

---

## 6. dev 브랜치 생성

- tai-api 레포에 dev 브랜치 신규 생성 (main 기준)
- 이후 모든 개발 커밋은 dev → PR → main 원칙 적용
