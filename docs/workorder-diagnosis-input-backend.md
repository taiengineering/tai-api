# 법령진단 입력항목 API — 백엔드 작업지시서

**작성일:** 2026-04-15  
**방식:** 단계별 진행  

---

## 배경

`diagnosis_input_fields` 테이블이 생성되었고, 전 섹터 입력항목 111건이 등록됨.
프론트에서 이 테이블을 읽어 동적 폼을 생성하는 구조.

## 가격 체계 (확정)

| 섹터 | FREE | 유료1 | 유료2 | 유료3 |
|---|---|---|---|---|
| 소형건물 (<5,000㎡) | 0원 | 99,000원 | — | — |
| 대형건물 (≥5,000㎡) | 0원 | 249,000원 | — | — |
| 제조·산업 | 0원 | 79,000원 | 149,000원 | 249,000원 |
| 건설현장 | 0원 | 199,000원 | — | — |

건물은 연면적 5,000㎡ 기준으로 자동 판단. 입력항목은 동일.

## 입력항목 테이블 구조

```sql
diagnosis_input_fields:
  id SERIAL PK
  sector VARCHAR(20)      -- BUILDING, INDUSTRY, CONSTRUCTION
  tier VARCHAR(20)         -- FREE, PAID, PAID1, PAID2, PAID3
  field_group VARCHAR(30)  -- 그룹명 (기본정보, 전기, 소방, 위험물 등)
  field_code VARCHAR(50)   -- 코드 (worker_count, electric_capacity 등)
  field_name TEXT          -- 한글명
  field_type VARCHAR(20)   -- number, boolean, select, text, multi_select
  input_options JSONB      -- select 옵션
  placeholder TEXT
  unit VARCHAR(10)         -- 명, kW, ㎡, 톤, 대 등
  is_required BOOLEAN
  help_text TEXT
  auto_source VARCHAR(30)  -- building_register 등
  sort_order INT
  UNIQUE(sector, tier, field_code)
```

---

## 단계 1: 입력항목 조회 API

**프롬프트:**
```
routers/diagnosis_fields.py 파일을 새로 만들어주세요.
prefix: /diagnosis/fields

엔드포인트 1개:

GET /diagnosis/fields?sector=BUILDING&tier=PAID

응답:
{
  "success": true,
  "data": {
    "sector": "BUILDING",
    "tier": "PAID",
    "field_count": 36,
    "groups": [
      {
        "group": "건축물대장",
        "fields": [
          {
            "field_code": "address",
            "field_name": "건물 주소",
            "field_type": "text",
            "unit": null,
            "is_required": true,
            "placeholder": "주소를 검색하세요",
            "help_text": null,
            "auto_source": null,
            "input_options": null
          },
          ...
        ]
      },
      {
        "group": "전기",
        "fields": [...]
      }
    ]
  }
}

로직:
1. diagnosis_input_fields에서 sector, tier로 필터
2. field_group별로 그룹핑
3. sort_order로 정렬
4. is_active = true만

산업의 경우 누적 구조:
  tier=PAID2 요청 시 → PAID1 + PAID2 필드 합쏐서 반환
  tier=PAID3 요청 시 → PAID1 + PAID2 + PAID3 필드 합쏐서 반환

인증 없이 호출 가능 (공개 API).
branch: dev에 push_files.
이 단계에서는 이 파일만 만듭니다.
```

**완료 조건:** diagnosis_fields.py dev 커밋

---

## 단계 2: main.py에 라우터 등록

**프롬프트:**
```
main.py에 diagnosis_fields 라우터 추가.

from routers import diagnosis_fields
app.include_router(diagnosis_fields.router)

이 단계에서는 main.py만 수정.
```

**완료 조건:** main.py 커밋

---

## 단계 3: 가격 자동 판단 API

**프롬프트:**
```
routers/diagnosis_fields.py에 엔드포인트 1개 추가.

GET /diagnosis/pricing?sector=BUILDING&total_floor_area=8000

응답:
{
  "success": true,
  "data": {
    "sector": "BUILDING",
    "determined_type": "BUILDING_LARGE_V2",
    "label": "대형건물 (5,000㎡ 이상)",
    "free_fee": 0,
    "paid_fee": 249000,
    "area_threshold": 5000,
    "input_area": 8000
  }
}

로직:
1. sector=BUILDING이고 total_floor_area >= 5000 → BUILDING_LARGE_V2 (249K)
2. sector=BUILDING이고 total_floor_area < 5000 → BUILDING_V2 (99K)
3. sector=INDUSTRY → tier 파라미터로 가격 반환 (PAID1=79K, PAID2=149K, PAID3=249K)
4. sector=CONSTRUCTION → 199K 고정
5. price_diagnosis_report 테이블에서 조회

이 단계에서는 이 엔드포인트만 추가.
```

**완료 조건:** 가격 판단 API 동작

---

## 단계 4: Supabase에서 검증

**프롬프트:**
```
Supabase MCP로 테스트.

1. 입력항목 조회
   SELECT sector, tier, count(*) FROM diagnosis_input_fields
   WHERE is_active = true GROUP BY sector, tier ORDER BY sector, tier;
   → 총 111건 확인

2. 건물 PAID 필드 그룹별 확인
   SELECT field_group, count(*) FROM diagnosis_input_fields
   WHERE sector = 'BUILDING' AND tier = 'PAID' GROUP BY field_group;
   → 10개 그룹, 36건

3. 산업 누적 테스트
   SELECT tier, count(*) FROM diagnosis_input_fields
   WHERE sector = 'INDUSTRY' GROUP BY tier;
   → FREE 3, PAID1 15, PAID2 9, PAID3 12
```

**완료 조건:** 데이터 정합성 확인

---

## 단계 5: dev → main PR

**프롬프트:**
```
tai-api에서 dev → main PR 생성.
PR 제목: "feat: 법령진단 입력항목 API + 가격판단 API"
포함: diagnosis_fields.py, main.py
```

---

## 참고: 섹터별 tier 매핑

```
BUILDING:
  FREE → 8필드 (건축물대장 자동조회)
  PAID → 36필드 (전체 설비/위험물)
  → 연면적으로 가격 자동 판단 (99K or 249K)

INDUSTRY:
  FREE  → 3필드
  PAID1 → 15필드 (79K)
  PAID2 → PAID1 + 9필드 = 24필드 (149K)
  PAID3 → PAID2 + 12필드 = 36필드 (249K)

CONSTRUCTION:
  FREE → 4필드
  PAID → 24필드 (199K)
```
