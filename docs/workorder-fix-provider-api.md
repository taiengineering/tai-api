# TAI Fix 업체등록 API — 백엔드 작업지시서

**작성일:** 2026-04-15  
**우선순위:** 즉시  
**방식:** 단계별 진행 — 각 단계 완료 확인 후 다음 단계로 이동

---

## 배경

오늘 설계한 TAI Fix DB 스키마:
- `fix_providers` — 업체 프로필 (latitude, longitude 포함)
- `fix_provider_qualifications` — 인허가 + 인력 통합 (headcount 방식)
- `fix_provider_services` — 업체가 선택한 중분류
- `fix_provider_overview` — 매칭용 통합 뷰

기존 `connect_provider.py`는 이전 구조이므로 새로 작성합니다.

---

## 단계 1: 기존 connect_provider.py 확인

**프롬프트:**
```
routers/connect_provider.py 파일을 읽어주세요.
현재 어떤 엔드포인트가 있고, 어떤 테이블을 사용하는지 정리해주세요.
수정하지 말고 현황만 파악해주세요.
```

**완료 조건:** 기존 엔드포인트 목록과 테이블 매핑 파악

---

## 단계 2: fix_providers_api.py 새로 작성 — 업체 CRUD

**프롬프트:**
```
routers/fix_providers_api.py 파일을 새로 만들어주세요.
prefix: /connect/providers

엔드포인트:
1. POST /connect/providers — 업체 등록 (프론트 폼에서 호출)
2. GET /connect/providers — 업체 목록
3. GET /connect/providers/{id} — 업체 상세

대상 테이블:
- fix_providers (업체 프로필)
- fix_provider_qualifications (인허가 + 인력)
- fix_provider_services (제공 서비스)

POST 요청 본문 구조:
{
  "company_name": "대성전기종합안전",
  "business_number": "123-45-67890",
  "representative": "홍길동",
  "phone": "02-1234-5678",
  "email": "info@company.co.kr",
  "address": "서울시 강남구 ...",
  "latitude": 37.5013,
  "longitude": 127.0397,
  "established_year": 2010,
  "employee_count": 15,
  "service_regions": ["서울", "경기"],
  "qualifications": [
    {"qualification_id": 1, "headcount": 1},
    {"qualification_id": 4, "headcount": 3}
  ],
  "services": [
    {"subcategory_id": 1},
    {"subcategory_id": 4}
  ]
}

POST 로직:
1. fix_providers에 INSERT
2. qualifications 배열을 fix_provider_qualifications에 반복 INSERT
3. services 배열을 fix_provider_services에 반복 INSERT
4. 트랜잭션으로 묶어서 하나라도 실패하면 전체 롤백
5. 생성된 provider_id 반환

인증 없이 호출 가능 (공개 API — 업체가 직접 등록하는 것이므로).
단, company_name, phone, email 필수 검증.

branch: dev에 push_files로 커밋.
```

**완료 조건:** fix_providers_api.py가 dev에 커밋됨

---

## 단계 3: main.py에 라우터 등록

**프롬프트:**
```
main.py를 읽고, fix_providers_api 라우터를 추가해주세요.
기존 connect_provider 라우터는 유지하되, 새 라우터도 추가합니다.

추가할 코드:
from routers import fix_providers_api
app.include_router(fix_providers_api.router)

branch: dev에 create_or_update_file로 커밋.
```

**완료 조건:** main.py에 라우터 등록 완료

---

## 단계 4: Supabase에서 API 테스트

**프롬프트:**
```
Supabase MCP로 테스트 데이터를 넣고 확인합니다.

1단계: fix_providers에 테스트 업체 1건 INSERT
   - company_name: '(테스트) 대성전기'
   - id: '00000000-0000-0000-0000-000000000001'

2단계: fix_provider_qualifications에 3건 INSERT
   - 전기공사업 (id=1, headcount=1)
   - 전기기사 (id=4, headcount=3)
   - 전기기술사 (id=5, headcount=1)

3단계: fix_provider_services에 2건 INSERT
   - 전기점검/진단 (subcategory_id=1)
   - 전기안전관리/대행 (subcategory_id=4)

4단계: fix_provider_overview 뷰에서 조회하여 결과 확인
   - license_count, cert_staff_count, service_count 정상 여부

5단계: 테스트 데이터 삭제
   DELETE FROM fix_providers WHERE id = '00000000-0000-0000-0000-000000000001';
   (CASCADE로 하위 테이블 자동 삭제)
```

**완료 조건:** DB 저장/조회/삭제 정상 확인

---

## 단계 5: fix_service_qualification_map 데이터 채우기

**프롬프트:**
```
fix_service_qualification_map 테이블의 구조를 확인해주세요.
information_schema.columns에서 컨럼 목록을 조회하세요.
수정하지 말고 구조만 파악해주세요.
```

---

## 단계 6: fix_service_qualification_map 데이터 INSERT

**프롬프트:**
```
fix_service_qualification_map에 서비스별 필수 자격 매핑을 넣어주세요.

매핑 기준:
- 각 중분류(fix_subcategory)가 요구하는 필수 자격(fix_qualification_master)
- 한 중분류에 여러 자격이 매핑될 수 있음 (OR 관계 — 하나만 있으면 됨)

예시:
- ELEC-INS (전기점검/진단) → 전기공사업(1) OR 전기안전관리대행사업(2) OR 전기전문진단업(3)
- ELEC-MGT (전기안전관리/대행) → 전기안전관리대행사업(2) 필수
- FIRE-INS (소방점검) → 소방시설관리업(9) 필수
- MECH-ELV (승강기관리) → 승강기유지관리업(13) 필수
- ARCH-ASB (석면/유해물질) → 석면조사기관(24) OR 석면해체제거업(25)
- SAFE-MGT (안전관리자선임/대행) → 안전관리전문기관(43) 필수
- SAFE-EDU (안전교육/훈련) → 안전교육지정기관(44) 필수
- CLEAN-DIS (소독/방역) → 소독업(52) 필수
- CLEAN-TNK (저수조/수질관리) → 저수조청소업(53) 필수
- ENV-MEA (환경측정/분석) → 환경측정기관(40) OR 대기측정대행업(37) OR 실내공기질측정대행업(38)
- ENV-WST (폐기물처리) → 폐기물수집운반업(39) 필수

B등급 중분류는 자격 필수가 아닌 것이 많으므로,
자격이 명확한 A등급 중분류를 우선으로 매핑하세요.

qualification_id는 반드시 fix_qualification_master의 실제 id를 확인 후 사용.
Subabase execute_sql로 INSERT.
```

**완료 조건:** A등급 중분류 전체의 필수 자격 매핑 완료

---

## 단계 7: dev → main PR

**프롬프트:**
```
tai-api 리포에서 dev → main PR을 생성해주세요.
PR 제목: "feat: TAI Fix 업체등록 API + juso.py 행안부 API 교체"
포함 내용:
- fix_providers_api.py (신규)
- juso.py v2.0.1 (카카오→행안부)
- main.py 라우터 등록
```

**완료 조건:** PR 생성 완료, 배포 준비

---

## 참고: DB 스키마

```sql
-- fix_providers
CREATE TABLE fix_providers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_name TEXT NOT NULL,
  business_number VARCHAR(12),
  representative TEXT,
  phone VARCHAR(20),
  email VARCHAR(100),
  address TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  service_regions JSONB DEFAULT '[]',
  description TEXT,
  established_year INT,
  employee_count INT,
  status VARCHAR(20) DEFAULT 'PENDING',
  verified_at TIMESTAMPTZ,
  user_id UUID,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- fix_provider_qualifications
CREATE TABLE fix_provider_qualifications (
  id SERIAL PRIMARY KEY,
  provider_id UUID NOT NULL REFERENCES fix_providers(id) ON DELETE CASCADE,
  qualification_id INT NOT NULL REFERENCES fix_qualification_master(id),
  headcount INT NOT NULL DEFAULT 1,
  license_number VARCHAR(50),
  issued_date DATE,
  expiry_date DATE,
  verified BOOLEAN DEFAULT false,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(provider_id, qualification_id)
);

-- fix_provider_services
CREATE TABLE fix_provider_services (
  id SERIAL PRIMARY KEY,
  provider_id UUID NOT NULL REFERENCES fix_providers(id) ON DELETE CASCADE,
  subcategory_id INT NOT NULL REFERENCES fix_subcategory(id),
  price_min INT,
  price_max INT,
  price_unit VARCHAR(10),
  price_note TEXT,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(provider_id, subcategory_id)
);
```
