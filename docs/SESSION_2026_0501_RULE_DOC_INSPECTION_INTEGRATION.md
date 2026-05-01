# 5/1 세션 — 룰/문서/점검 통합 + 데이터 분리 정책 (최종)

**날짜**: 2026-05-01  
**프로젝트**: vwlahtguyggrhvslabax (서울 리전, taieng)  
**핵심 결정**: 데이터 분리 정책 적용 — 메인 테이블은 운영 데이터만

---

## 핵심 결정 사항

### 정책 변경
- **메인 테이블 컬럼 추가 금지** = 시스템 전체 변경 발생
- **사용 안 하는 데이터는 별도 테이블로 분리**
- 정제 ≠ 운영 (다른 차원)
  - 정제 = 룰 신뢰도 (drafts.APPROVED)
  - 운영 = 사업장 적용 (공장이면 산안+소방+화학+가스 등)
- **예외**: 외부 의뢰 워크플로우 통합을 위해 `document_forms.is_external_writer` 컬럼 추가 (5/1 결정)

---

## 데이터 분리 결과 (최종)

### 4개 테이블 구조

| 테이블 | 행수 | 의미 |
|---|---|---|
| `master_building_legal_rules` (운영) | **2,012** | 정제 1,601 + AGENCY_API 397 + pending 복귀 14 |
| `master_legal_rules_preserved` (보관) | **321** | TECHNICAL_STANDARD (NFTC 기술기준) |
| `master_legal_rules_pending_review` (검토) | **1,454** | UNKNOWN_SOURCE 738 + AI_GENERATED 714 + 기타 2 |
| `master_legal_rules_archive` (폐기) | **44** | 4월 정제 중복 33 + SPECIAL_FACILITY 잔재 11 |
| 합계 | 3,831 | |

### 사용자 기억 "1,900대"의 정체
- `law_rule_drafts.status='APPROVED'` = 1,988 (정제 결과)
- `master_building_legal_rules` 운영 = 2,012 (운영 룰)

---

## document_forms 작성자 구분 (외부 의뢰 워크플로우)

### 5/1 추가 정책
- `document_forms.is_external_writer` 컬럼 추가 (boolean, default false)
- 안전관리자 초과 등급(외부 검사기관/진단기관/지정기관) 작성 문서 표시
- **목적**: SaaS에서 외부 의뢰 목록 워크플로우로 활용

### 분류 결과
| 구분 | 건수 | 의미 |
|---|---|---|
| `is_external_writer = false` | **235** | 사용자 직접 작성 (사업주/관리감독자/관리주체/안전관리자/시공자/수급인 등) |
| `is_external_writer = true` | **25** | 외부 의뢰 (검사기관 8 / 건강진단기관 4 / 지정받으려는 자 3 / 한국가스안전공사·한국에너지공단 3 / 위험물·시도지사 검사 2 / 환경부·발주청 2 / 석면해체제거업자 3) |
| 합계 | 260 | |

### 혼합형 14건은 활성 유지 (사업장 작성 가능)
- 사업주/건설사업자/관리주체가 작성 가능한 경우 모두 `is_external_writer = false`로 유지
- 예: "사업주 또는 작업환경측정기관", "건설안전점검기관 또는 건설사업자", "관리주체 또는 정밀안전진단 실시기관"

---

## doc_rule_mapping 재구성 (최종)

### 변화
| 항목 | 이전 | 이후 |
|---|---|---|
| `doc_rule_mapping` (운영) | 616 | **227** (재구성) |
| `doc_rule_mapping_preserved` | 0 | 165 |
| `doc_rule_mapping_pending_review` | 0 | 183 |
| 고아 매핑 | 117 | 0 (정리됨) |

### 매핑 효과
- 매핑 총수: **227건**
- **문서 커버리지: 42.3%** (110/260)
- 룰 커버리지: 5.3% (107/2012)
- 매칭 방식: `LAW_REF_DIRECT_MATCH` — 100% 결정론적, 임의해석 0%

### 매핑 진화 (오늘 세션 전체)
```
67 → 114 → 169 → 198 → 227
정확  alias  1,998   혼합   pending복귀
```

---

## v_engine_integration view 업데이트 (5/1)

### 변경: is_external_writer 컬럼 노출
- 기존 view에 `df.is_external_writer` 컬럼 추가 (끝 위치)
- 외부 의뢰 vs 내부 작성 자동 추적 가능

### 분포 (매핑된 110 문서 기준)
| 구분 | row | 문서 | 점검 항목 |
|---|---|---|---|
| **내부 작성** (is_external_writer=false) | 963 | 101 | 510 |
| **외부 의뢰** (is_external_writer=true) | 138 | 9 | 43 |
| 합계 | 1,101 | 110 | 553 (중복 제외 416) |

### inspection_master 변경 불필요 (derived data)
- inspection_master는 document_forms.required_fields에서 derived
- document_forms.is_external_writer 변경 시 view에서 자동 따라감
- 점검 마스터 자체에 컬럼 추가 불필요 (동기화 부담 회피)

### 활용 (서비스 운영 시)
- **사용자 화면**: `WHERE is_external_writer = false` → 235개 문서 / 510개 점검
- **외부 의뢰 화면**: `WHERE is_external_writer = true` → 25개 문서 / 외부 의뢰 워크플로우
- 동일 view에서 두 워크플로우 자동 구분

---

## 정제 흐름 완전 복원

```
[4/7 5차 세션] 활성 룰 ~1,196건
  ↓ 4/22 KICKOFF — 새 법령엔진 시작
[4/23 ATOMIC SWITCH] 182 laws / 60,636 records
  ↓ Claude Sonnet auto_parse_parallel.py 의무 추출
law_rule_drafts 2,583
  ├ APPROVED 1,988 → master 등록 1,601
  ├ PENDING 542 / REJECTED 46 / NEEDS_REVIEW 6
  ↓
master_building_legal_rules 운영 2,012
  ├ 1,601: drafts 정제 거친 (산안법 위주)
  ├ 397: 부처 API 직접 수집 (소방/화학/가스/위험물/환경 등)
  └ 14: pending_review 복귀 (산안법 핵심 의무)
```

### pending_review에서 복귀한 14건
- 제124조 안전검사 (타워크레인/호이스트/곤돌라/리프트/공기압축기) 5건
- 제42조 유해위험방지계획서 (별지 16호서식) 2건 + 시행령 1건
- 제44조 심사결과서 (별지 19호서식) 1건
- 제54조 중대재해 발생 시 조치 2건
- 제64조 도급인 안전보건협의체 3건

---

## 점검 시스템 통합 검증

### 3중 매핑 정확한 상태
| 매핑 | 상태 | 커버리지 |
|---|---|---|
| **B. 문서 ↔ 점검항목** | ✅ **100% 매핑** | 260/260 문서 모두 점검 보유 (1,246건) |
| A. 의무 ↔ 문서 | ⚠️ 부분 | 110/260 (42.3%) |
| C. 의무 ↔ 점검 | ⚠️ 부분 | 416/1,246 (33.4%) |

---

## 매핑 한계 (남은 58% 미매핑) — 다음 세션 작업

| 원인 | 건수 | 다음 세션 작업 |
|---|---|---|
| master에 없는 법령 (석면안전관리법, 화학물질등록평가법 시행규칙) | 8 | 추가 정제 필요 |
| 모호 표기 ("법", "시행규칙" 단독) | 11 | 컨텍스트 보강 |
| 조문번호 없는 law_ref | 143 | 문서 데이터 보강 (GPT 작업) |

---

## 다음 세션 우선순위

### 즉시 진행 가능
1. **부분 일치 48건 검토** (3월 잔재 중 3개키 16 + 2개키 32)
2. **NFTC 321건 활용 검토** — preserved에서 점검 마스터에 직접 사용 가능한지

### 큰 작업 (별도 세션)
3. **master에 부족한 법령 추가 정제** (석면, 화학물질등록평가법 등)
4. **document_forms.required_fields의 law_ref 보강** — 조문번호 없는 143건 (GPT 작업)
5. **NULL 출처 738개 / AI_GENERATED 714개 추적** (pending_review)

### 운영 시작 전
6. inspection_set_items 사업장 인스턴스 시드
7. safety_inspection_results 운영 시작
8. 자동 문서 생성 파이프라인 가동 (외부 의뢰 워크플로우 포함)

---

## 데이터 품질 등급 재정의

```
master_building_legal_rules 운영 2,012
├─ A등급 (1,601): drafts.APPROVED 정제 거침 ✅
├─ A'등급 (397): 부처 API 직접 수집 (출처 신뢰)
└─ A''등급 (14): pending에서 복귀 (산안법 핵심 의무)

master_legal_rules_preserved 321
└─ B등급: TECHNICAL_STANDARD (NFTC, 너무 세분화)

master_legal_rules_pending_review 1,454
├─ C등급 (738): UNKNOWN_SOURCE
└─ D등급 (716): AI_GENERATED

master_legal_rules_archive 44
└─ E등급: 폐기/대체됨
```

---

## 사용자 작업 원칙 (절대 준수)

1. **임의해석 금지** — AI 의미 매칭 거부, 법령 텍스트 기반만
2. **결정론적 매칭만** (4개 키: law_name + law_article + obligation_type + condition_code)
3. **메인 테이블 깔끔 유지** — 컬럼 추가 금지, 별도 테이블 분리 (5/1 예외: is_external_writer)
4. **DELETE 대신 분리 보관** — 데이터 손실 방지
5. **한 번에 하나씩만 진행** — 비개발자 사용자 결정 단순화
6. **신뢰 추락 방지** — 잘못 매핑 시 모든 사용업체가 안 해도 될 의무 수행

---

## 핵심 SQL (재실행용)

### v_engine_integration view 정의 (5/1 최종)
```sql
CREATE OR REPLACE VIEW v_engine_integration AS
SELECT m.rule_id, m.law_name, m.law_article, m.obligation_type,
    "left"(m.obligation_summary, 60) AS "의무요약",
    drm.doc_id, df.doc_name, df.sector AS doc_sector,
    im.id AS inspection_item_id, im.inspection_item, im.is_mandatory,
    im.compliance_level, im.inspection_grade, im.source_field_key, im.field_group_key,
    df.is_external_writer
FROM master_building_legal_rules m
  JOIN doc_rule_mapping drm ON drm.rule_id = m.rule_id
  JOIN document_forms df ON df.doc_id = drm.doc_id
  JOIN inspection_master im ON im.source_doc_id = df.doc_id
WHERE m.is_active = true;
```

### document_forms.is_external_writer 분류 SQL
```sql
ALTER TABLE document_forms 
  ADD COLUMN is_external_writer boolean DEFAULT false NOT NULL;

UPDATE document_forms 
SET is_external_writer = true 
WHERE writer IN (
  '검사기관', '건강진단기관', '한국가스안전공사',
  '시도지사 또는 검사기관', '검사기관 또는 한국가스안전공사',
  '한국에너지공단 또는 검사기관',
  '보건관리전문기관으로 지정받으려는 자',
  '안전관리전문기관 지정을 받으려는 자',
  '재해예방 전문지도기관으로 지정받으려는 자',
  '환경부장관 또는 관계 행정기관',
  '발주청 또는 인허가기관의 장',
  '위험물 검사기관',
  '석면해체제거업자',
  '석면해체제거업자 또는 석면농도측정기관'
);
```

### 데이터 분리 테이블 구조
- `master_legal_rules_archive`: LIKE INCLUDING ALL + archived_at, archive_reason
- `master_legal_rules_preserved`: LIKE INCLUDING ALL + preserved_at, preservation_category
- `master_legal_rules_pending_review`: LIKE INCLUDING ALL + moved_at, review_category
- `doc_rule_mapping_preserved`: LIKE INCLUDING ALL + moved_at
- `doc_rule_mapping_pending_review`: LIKE INCLUDING ALL + moved_at

---

**작성일**: 2026-05-01  
**최종 매핑**: 227건 (42.3% 문서 커버리지) — 100% 결정론적  
**시스템 정합성**: ✅ v_engine_integration 정상 작동 (is_external_writer 자동 추적)  
**다음 세션**: 부분 일치 48건 검토 또는 추가 법령 정제
