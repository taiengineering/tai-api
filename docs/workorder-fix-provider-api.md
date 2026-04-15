# TAI Fix 업체등록 + 매칭 + 계약 API — 백엔드 작업지시서 (v2)

**작성일:** 2026-04-15  
**우선순위:** 즉시  
**방식:** 단계별 진행 — 각 단계 완료 확인 후 다음 단계로 이동  
**이전 버전:** workorder-fix-provider-api.md (v1) — 보증금/전자계약 흐름 반영 전

---

## TAI Fix 전체 플로우 (확정)

```
① 발주자: 증상/상황 입력 + 현장 정보
② 매칭엔진: 서비스 분류 → 적합 업체 선별
③ 업체에 알림: 상황 정보 전달 (연락처 없이)
④ 업체: 견적서 제출 (또는 "현장 확인 필요")
⑤ 발주자: 견적 비교 → 업체 선택
⑥ 전자계약: TAI 표준계약서 (이니시스 본인인증 서명)
⑦ 보증금 결제: 이니시스 결제 (금액확정 10% / 미확정 5만원)
   └─ 보증금 없으면 여기서 멈춤
⑧ 연락처 오픈: 양쪽 연락처 + 연락 가능
⑨ 작업 진행 → 완료
⑪ 정산: 보증금에서 TAI 수수료 차감 → 업체 정산
```

## 계약 상태 코드 (system_codes에 등록 완료)

```
DRAFT → SIGNED → DEPOSIT_PAID → IN_PROGRESS → COMPLETED → SETTLED
                                                              └─ CANCELLED
                                                              └─ DISPUTED
```

## 보증금 가상 설정값 (system_codes DEPOSIT_CONFIG)

| 설정 | 값 | 비고 |
|---|---|---|
| 기본 비율 | 10% | 견적 금액 확정 시 |
| 고정 보증금 | 5만원 | 금액 미확정(추후협의) 시 |
| 최소 보증금 | 3만원 | 10% 계산값이 이하일 때 |
| TAI 수수료 | 8% | 최종 계약금액 기준 |

---

## 단계 1: 기존 코드 확인

**프롬프트:**
```
아래 파일들을 읽고 현황만 정리해주세요. 수정하지 말고 파악만.

1. routers/connect_provider.py — 엔드포인트, 테이블 매핑
2. routers/matching.py — 엔드포인트, 흐름
3. main.py — 현재 등록된 라우터 목록

각 파일별로 "엔드포인트 목록", "사용하는 테이블" 정리.
```

**완료 조건:** 기존 코드 현황 파악 완료

---

## 단계 2: fix_providers_api.py 새로 작성 — 업체 CRUD

**프롬프트:**
```
routers/fix_providers_api.py 파일을 새로 만들어주세요.
prefix: /connect/providers

엔드포인트 3개:

1. POST /connect/providers — 업체 등록
   - fix_providers INSERT
   - fix_provider_qualifications 반복 INSERT
   - fix_provider_services 반복 INSERT
   - 트랜잭션으로 묶어서 하나라도 실패하면 전체 롤백
   - 인증 없이 호출 가능 (공개 API)
   - company_name, phone, email 필수 검증

2. GET /connect/providers — 업체 목록
   - fix_provider_overview 뷰 사용
   - status, 지역 필터 파라미터

3. GET /connect/providers/{id} — 업체 상세
   - fix_providers + qualifications + services JOIN

POST 요청 본문:
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
  "services": [{"subcategory_id": 1}, {"subcategory_id": 4}]
}

branch: dev에 push_files로 커밋.
이 단계에서는 이 파일만 만듭니다. main.py는 다음 단계에서.
```

**완료 조건:** fix_providers_api.py가 dev에 커밋됨

---

## 단계 3: main.py에 라우터 등록

**프롬프트:**
```
main.py를 읽고, fix_providers_api 라우터를 추가해주세요.

추가할 코드:
from routers import fix_providers_api
app.include_router(fix_providers_api.router)

기존 라우터는 유지. 새 라우터만 추가.
branch: dev에 create_or_update_file로 커밋.
이 단계에서는 main.py만 수정합니다.
```

**완료 조건:** main.py에 라우터 등록 완료

---

## 단계 4: DB 테스트

**프롬프트:**
```
Supabase MCP로 테스트 데이터를 넣고 확인합니다.

1. fix_providers에 테스트 업체 1건 INSERT
   id: '00000000-0000-0000-0000-000000000001'
   company_name: '(테스트) 대성전기'

2. fix_provider_qualifications에 3건 INSERT
   전기공사업(id=1, headcount=1), 전기기사(id=4, headcount=3), 전기기술사(id=5, headcount=1)

3. fix_provider_services에 2건 INSERT
   전기점검/진단(subcategory_id=1), 전기안전관리/대행(subcategory_id=4)

4. fix_provider_overview 뷰에서 조회 → 결과 확인
   license_count=1, cert_staff_count=4, service_count=2 맞는지

5. 테스트 데이터 삭제
   DELETE FROM fix_providers WHERE id = '00000000-0000-0000-0000-000000000001';
```

**완료 조건:** DB 저장/조회/삭제 정상

---

## 단계 5: fix_service_qualification_map 구조 확인

**프롬프트:**
```
fix_service_qualification_map 테이블의 컨럼 목록을 조회해주세요.
information_schema.columns에서.
수정하지 말고 구조만 파악.
```

**완료 조건:** 컨럼 목록 파악

---

## 단계 6: fix_service_qualification_map 데이터 INSERT

**프롬프트:**
```
fix_service_qualification_map에 A등급 중분류의 필수 자격 매핑을 INSERT.

매핑 기준: 중분류(fix_subcategory) → 필수 자격(fix_qualification_master)
OR 관계 — 하나만 있으면 됨.

A등급 중분류 매핑:
- ELEC-INS(1) → 전기공사업(1) OR 전기안전관리대행사업(2) OR 전기전문진단업(3)
- ELEC-MGT(4) → 전기안전관리대행사업(2) 필수
- FIRE-INS(6) → 소방시설관리업(9) 필수
- FIRE-CON(8) → 소방공사업(8) 필수
- FIRE-MGT(9) → 소방시설관리업(9) 필수
- MECH-ELV(13) → 승강기유지관리업(13) 필수
- ARCH-INS(16) → 건축물관리점검기관(22) OR 안전진단전문기관(23)
- ARCH-ASB(19) → 석면조사기관(24) OR 석면해체제거업(25)
- ARCH-DEM(20) → 해체공사업(27) 필수
- ENV-MEA(23) → 환경측정기관(40) OR 대기측정대행업(37) OR 실내공기질측정대행업(38)
- ENV-WST(24) → 폐기물수집운반업(39) 필수
- ENV-CST(27) → 환경전문공사업(36) 필수
- SAFE-MGT(28) → 안전관리전문기관(43) 필수
- SAFE-EDU(29) → 안전교육지정기관(44) 필수
- SAFE-WEM(30) → 지정측정기관(47) 필수
- SAFE-HLT(31) → 특수건강진단기관(48) 필수
- SAFE-CST(32) → 안전관리전문기관(43) OR 산업안전지도사(45)
- SAFE-PSM(33) → 공정안전전문인력(49) 필수
- SAFE-RSK(34) → 안전관리전문기관(43) OR 산업안전지도사(45)
- CLEAN-DIS(36) → 소독업(52) 필수
- CLEAN-TNK(37) → 저수조청소업(53) 필수

괄호 안 숫자는 DB id임. fix_qualification_master의 id를 반드시 확인 후 INSERT.
```

**완료 조건:** A등급 중분류 전체 매핑 완료

---

## 단계 7: dev → main PR

**프롬프트:**
```
tai-api에서 dev → main PR 생성.
PR 제목: "feat: TAI Fix 업체등록 API + juso.py 행안부 API 교체"
```

**완료 조건:** PR 생성

---

## 참고: DB 스키마

### fix_providers
```sql
id UUID PK, company_name TEXT NOT NULL, business_number VARCHAR(12),
representative TEXT, phone VARCHAR(20), email VARCHAR(100),
address TEXT, latitude DOUBLE, longitude DOUBLE,
service_regions JSONB, description TEXT, established_year INT,
employee_count INT, status VARCHAR(20) DEFAULT 'PENDING',
user_id UUID, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
```

### fix_provider_qualifications
```sql
id SERIAL PK, provider_id UUID FK(CASCADE),
qualification_id INT FK(fix_qualification_master),
headcount INT DEFAULT 1, license_number VARCHAR(50),
issued_date DATE, expiry_date DATE, verified BOOLEAN DEFAULT false,
UNIQUE(provider_id, qualification_id)
```

### fix_provider_services
```sql
id SERIAL PK, provider_id UUID FK(CASCADE),
subcategory_id INT FK(fix_subcategory),
price_min INT, price_max INT, price_unit VARCHAR(10),
price_note TEXT, is_active BOOLEAN DEFAULT true,
UNIQUE(provider_id, subcategory_id)
```

### matching_contracts 보증금 관련 컨럼 (신규 추가됨)
```sql
deposit_amount INT, deposit_rate NUMERIC(5,2) DEFAULT 10.00,
deposit_status VARCHAR(20) DEFAULT 'NONE',
deposit_payment_id TEXT, deposit_paid_at TIMESTAMPTZ,
deposit_refunded_at TIMESTAMPTZ,
contacts_released BOOLEAN DEFAULT false,
contacts_released_at TIMESTAMPTZ,
contract_status_code VARCHAR(20) DEFAULT 'DRAFT'
```
