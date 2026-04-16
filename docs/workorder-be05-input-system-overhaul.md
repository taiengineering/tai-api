# BE-05: diagnosis 입력 시스템 정형화 + 자동조회

**우선순위**: P0  | **의존**: 없음  | **병렬 가능**: BE-06

## 배경
diagnosis_input_fields 111개 중 boolean만·자유텍스트·자동채움 미구현 다수.
사용자 "모름" 처리 불가, process_list 쉼표 파싱 의존, 건축물대장 자동채움 미작동.

## 완료 작업

### Migration 1: `diagnosis_input_fields_add_tri_state`
- `unknown_handler` 컬럼 추가 (VARCHAR 30, DEFAULT 'ALLOW_AND_ASK_AFTER')
- `boolean` 58건 → `tri_state` 일괄 전환
- 핵심 안전 필드 6종 → `unknown_handler = 'BLOCK_PAY'`

### Migration 2: `diagnosis_input_fields_restructure_unstructured`
- `main_structure` text → `select` (RC/S/SRC/MASONRY/WOOD/OTHER 6종)
- `process_list` text → `table` (공정명 + 위험요인 multi_select)
- `process_worker_data` text → `table` (공정명/직접/하도급/교대)
- `subcontractor` 신규 `table` 필드 추가 (CONSTRUCTION PAID)

### Migration 3: `diagnosis_input_fields_add_operation_shift`
- `operation_shift` 신규 `select` 필드 추가
  - INDUSTRY PAID1 + CONSTRUCTION PAID 양쪽
  - enum: SHIFT_1/SHIFT_2/SHIFT_3/SHIFT_24H/SHIFT_FLEX/SHIFT_UNKNOWN

### routers/diagnosis_autofill.py v1.0.0
- `GET /diagnosis/autofill/address?query=` — juso.go.kr 도로명주소 검색
- `GET /diagnosis/autofill/building-register?address=` — 건축물대장 자동채움
- `GET /diagnosis/autofill/business?biz_no=` — 국세청 사업자상태조회
- API 키 미설정 시 mock 응답 반환 (개발 환경 안전)
- 카카오 API 미사용 ✅ / 개인정보 수집 없음 ✅

## 완료 조건 확인

```sql
SELECT field_type, COUNT(*) AS cnt
FROM diagnosis_input_fields
GROUP BY field_type ORDER BY cnt DESC;
```

| field_type  | cnt |
|---|---|
| tri_state   | 58  |
| number      | 36  |
| select      | 12  |
| table       | 4   |
| text        | **3** ← ≤ 5 ✅ |
| multi_select| 1   |

- `field_type='text'` 3건 (address×2, project_address×1) — 주소·회사명만 ✅
- `boolean` → `tri_state` 전환 완료 (boolean 0건) ✅
- `/diagnosis/autofill/*` 엔드포인트 3종 등록 ✅

## 환경변수 필요 (Fly.io secrets)

| 변수명 | 용도 | 필수 |
|---|---|---|
| `BUILDING_REGISTER_API_KEY` | 공공데이터포털 건축물대장 | 권장 |
| `JUSO_CONFIRM_KEY` | 도로명주소 juso.go.kr | 권장 |
| `NTS_API_KEY` | 국세청 사업자상태조회 | 선택 |

미설정 시 mock 응답 반환 — 개발/테스트 환경에서 안전하게 작동.

## 금기 준수
- 카카오 API 사용 없음 ✅
- 개인정보(주민번호·여권번호) 수집 없음 ✅
- main 직접 커밋 없음 ✅ (dev 브랜치만)
