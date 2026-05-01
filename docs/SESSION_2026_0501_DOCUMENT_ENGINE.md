# 문서엔진 세션 기록 (2026-05-01)

## 1. 완료된 작업

### document_forms: 260건 완성
- 기존 179건 → 14개 법률 시행규칙 별지 전수 대조 → 83건 추가 → 중복 2건 삭제 = **260건**
- 중복 삭제: DOC-OSH-060(전기설비 점검기록부, DOC-BLD-009와 중복), DOC-CON-030(콘크리트 타설계획서, DOC-CON-016과 중복)

### 260건 데이터 완성도
| 항목 | 컬럼 | 채움 | 비율 |
|------|------|------|------|
| 기재항목 | required_fields | 260 | 100% |
| 법적근거 | law_ref | 260 | 100% |
| 작성자 | writer | 260 | 100% |
| 제출형태 | doc_format | 260 | 100% |
| 제출시기 | submit_timing | 251 | 97% |
| 과태료 | penalty | 87 | 해당건만 |
| 보존기간 | retention | 16 | 법령 미명시 다수 |
| 법정제출방법 | submit_method_legal | 82 | 자체보관 문서 제외 |

### doc_owner 분류
| 구분 | 건수 | 설명 |
|------|------|------|
| BUSINESS | 238 | 사업장 직접 작성 (TAI가 생성/관리) |
| EXTERNAL_RECEIVE | 19 | 외부기관 발행 → 사업장 수령 보관 |
| AGENCY_ONLY | 3 | 전문기관 자체용 (TAI 고객 대상 아님) |

### doc_format 분류
| 구분 | 건수 | 설명 |
|------|------|------|
| COPY_OK | 138 | 사본/팩스 제출 가능 |
| DIGITAL_OK | 105 | 전자문서 가능 |
| ORIGINAL_ONLY | 19 | 원본/직인 필수 |

**주의:** doc_format과 registered_mail_available 데이터는 GPT가 법령 기반으로 수집한 것이며, 임의 해석 아님.
기존에 Claude가 임의로 넣었던 값은 전부 초기화 후 GPT로 재수집 완료.

### DB 스키마 (Supabase vwlahtguyggrhvslabax)
추가된 컬럼:
- `doc_format` TEXT: ORIGINAL_ONLY / COPY_OK / DIGITAL_OK
- `registered_mail_available` BOOLEAN (현재 NULL — 데이터 미수집)
- `submit_method_legal` TEXT: 법령 원문의 제출방법 그대로
- `doc_owner` TEXT: BUSINESS / EXTERNAL_RECEIVE / AGENCY_ONLY
- `related_doc_id` TEXT (law_rule_drafts에 추가): 룰→문서 연결 (현재 전부 NULL, 매핑 미완)

---

## 2. 미완료 작업: 법령 룰 ↔ 문서 매핑

### 현황
- law_rule_drafts: 1,989건 (APPROVED/REGISTERED)
- document_forms: 260건
- related_doc_id: **전부 NULL (초기화됨)**

### 실패한 접근 (하지 말 것)
1. SQL LIKE 키워드 일괄 매핑 → 부정확, 신뢰 불가
2. 의무유형별 대표문서 지정 → 같은 유형이라도 문서가 다름
3. 나머지 일괄 배정 → 찍기에 불과

### 올바른 접근 (다음 세션에서 진행)
매핑 질문: **"이 법령 의무를 이행하면, 어떤 문서가 생성되거나 제출되는가?"**

매핑 기준:
1. 1차 매칭: 룰의 law_article 조항번호 = 문서의 law_ref 조항번호 (같은 법, 같은 조)
2. 2차 매칭: obligation_summary의 의미가 문서의 용도와 일치
3. 같은 조항에 문서가 여러 개면, obligation_summary로 구분
4. 물리적 조치(설치, 착용 등)라도 점검/확인 기록이 필요하면 해당 점검 문서에 연결
5. 해당 법률의 문서가 없으면 null (문서 미구축)

매핑 불가 법률 (문서 미구축, 330건):
- 액화석유가스법 (116건)
- 기계설비법 (69건)
- 도시가스사업법 (59건)
- 다중이용업소법 (43건)
- 토양환경보전법 (14건)
- 잔류성오염물질법 (14건)
- 기타 (15건)

---

## 3. 파이프라인 구조

```
법령엔진: 시설→법령진단→공정·설비→반복일정+담당지정→체크항목지정
    ↕ 접점: 체크항목 = 문서의 required_fields
문서엔진: 체크결과수집→문서자동생성→문서자동발송
```

### 핵심 파이프라인 끊김
- inspection_master(772개) ↔ inspection_set_items 연결 안 됨 (master_item_id 전부 NULL)
- law_rule_drafts ↔ document_forms 매핑 미완 (related_doc_id 전부 NULL)
- 이 두 개가 해결되면 법령엔진→문서엔진 전체 파이프라인 연결

---

## 4. 커버리지

### 14개 핵심 법률 (TAI 1차)
산안법, 중대재해처벌법, 건설기술진흥법, 건설산업기본법, 소방시설법, 전기안전관리법,
승강기안전관리법, 석면안전관리법, 시설물안전법, 고압가스안전관리법, 위험물안전관리법,
에너지이용합리화법, 화학물질관리법, 화학물질등록평가법

### 커버리지
- 14개 법률 시행규칙 별지 전수 대조 완료
- 현장 안전관리 문서의 약 90~95% 커버
- 나머지 5~10%: 건축법, 다중이용업소법, 환경법 등 (TAI 2차)
