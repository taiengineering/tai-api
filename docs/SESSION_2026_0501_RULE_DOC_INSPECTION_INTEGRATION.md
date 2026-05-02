# 5/1 세션 — 룰/문서/점검 통합 + 데이터 분리 정책 (최종)

**날짜**: 2026-05-01  
**프로젝트**: vwlahtguyggrhvslabax (서울 리전, taieng)  
**핵심 결정**: 데이터 분리 정책 적용 — 메인 테이블은 운영 데이터만

> ⚠️ **컨텍스트 압축 안내**: 이 세션 중간에 컨텍스트 압축 발생. 전체 흐름은 transcript 파일에 보존됨 (`/mnt/transcripts/2026-05-01-13-14-44-tai-rule-doc-mapping-2026-0501.txt`). 다음 세션에서 필요 시 참조.

---

## 🎯 오늘 작업의 본질 (반드시 읽기)

### 오늘 세션은 "백엔드 청소"였다 — 소비자 직접 가치는 X
- 사용자 화면에 새 기능 추가된 것 **0개**
- 모든 작업이 **데이터 정제/분리/매핑 정리**
- **간접 가치**:
  - 사고 위험 감소 (옛 룰/잘못된 룰 분리 → 운영 시 잘못 발동 안 함)
  - 공장 사업장 커버리지 확장 (산안법 외 소방/화학/가스/위험물 397개 룰 운영 진입)
  - 데이터 신뢰성 (매핑 임의해석 0%)

### 진짜 소비자 가치 = 다음 세션부터
- `inspection_set_items` 행수 = **0** (사업장 인스턴스 미생성)
- `safety_inspection_results` 행수 = **0** (점검 결과 미수집)
- → 이 두 테이블 채워져야 소비자가 "TAI Safe로 점검했다", "자동 문서 발급됐다" 체감

---

## 🔄 5/1 세션 의사결정 흐름 (시행착오 포함)

> **목적**: 다음 세션이 같은 길 안 가도록 의사결정 배경 + 사용자 통찰 진화 기록

### 1단계 — 초기 분리 정책 (정제 신뢰도 기반)
- **결정**: drafts.APPROVED 거친 1,601건만 master 운영
- **나머지 분리**:
  - TECHNICAL_STANDARD (NFTC) 321 → preserved
  - **AGENCY_API 397 → preserved**  ← (시행착오)
  - UNKNOWN_SOURCE 738 + AI_GENERATED 714 → pending_review
  - 4월 정제 중복 33 + SPECIAL_FACILITY 잔재 11 → archive

### 2단계 — 사용자 통찰 (공장 사업장은 다중 법령 적용)
- 사용자 발언: "공장이 있으면, 소방법. 산안법. 화확물질관리법 등이 다 적용받습니다."
- **깨달음**: 정제 ≠ 운영 (다른 차원)
  - 정제 = 룰 신뢰도 (drafts.APPROVED)
  - 운영 = 사업장 적용 (공장이면 산안+소방+화학+가스+위험물+환경+전기 모두)
- AGENCY_API 397건은 부처 API 직접 수집 → **출처 신뢰 + 사업장 적용 명확**
- **수정 결정**: AGENCY_API 397 → master 운영 복귀 (1,601 → 1,998)

### 3단계 — 매핑 재구성 + pending 산안법 14건 복귀
- 매핑 진화: 67 → 114 (alias) → 169 (1,998 기준) → 198 (혼합 표기)
- 발견: 매핑 안 된 산안법 조문 일부가 pending_review에 있음
- pending 16건 검토 → 14건 의무 구체적, 2건 모호
- **결정**: A 그룹 14건만 master 복귀 (1,998 → 2,012), 매핑 198 → 227

### 4단계 — 외부 의뢰 워크플로우 (시행착오)
- 사용자 정책: "안전관리자 초과 등급은 SaaS에서 사용 안 함, 비활성"
- **초기 시도**: `document_forms_external_writer` 별도 테이블 분리 (25건)  ← (시행착오)
- 사용자 정책 수정: "테이블에 컬럼 하나 추가, 외부 작성 구분값 + 서비스중 외부 의뢰 목록"
- **수정 결정**:
  - `document_forms_external_writer` 테이블 삭제
  - `document_forms.is_external_writer` 컬럼 추가 (boolean)
  - 25건 메인 테이블 복귀 + 컬럼=true 표시
  - **이유**: 외부 의뢰 워크플로우는 SaaS의 핵심 기능 (문서 자동 의뢰 목록)

### 5단계 — view 통합
- `v_engine_integration` view 끝에 `is_external_writer` 컬럼 노출
- inspection_master는 derived data → 변경 불필요 (자동 따라감)

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

### 혼합형 14건은 활성 유지 (사업장 작성 가능, is_external_writer=false)
| 작성자 패턴 | 건수 | 사업장 측 작성자 |
|---|---|---|
| 사업주 또는 작업환경측정기관 | 3 | 사업주 |
| 건설안전점검기관 또는 건설사업자 | 2 | 건설사업자 |
| 안전점검을 실시한 건설안전점검기관 또는 건설사업자 | 1 | 건설사업자 |
| 건설사업자, 주택건설등록업자 또는 건설안전점검기관 | 1 | 건설사업자/주택건설업자 |
| 건설사업자, 주택건설등록업자 또는 품질검사 대행기관 | 1 | 건설사업자/주택건설업자 |
| 품질시험을 실시한 건설사업자 또는 품질검사기관 | 1 | 건설사업자 |
| 관리주체 또는 정밀안전진단 실시기관 | 1 | 관리주체 |
| 관리주체 또는 안전점검 수행기관 | 1 | 관리주체 |
| 관리주체 또는 성능평가 실시기관 | 1 | 관리주체 |
| 관리업자 또는 점검기관 | 1 | 관리업자 |
| 석면조사기관 또는 석면건축물 소유자 | 1 | 석면건축물 소유자 |
| 건설사업관리기술인 또는 감리자 | 1 | 건설사업관리기술인 |

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

### law_alias 등록 (15건)
- 기존 11: 산안법, 고압가스안전관리법, 승강기안전관리법 등
- 신규 4: 산안법 시행규칙, 산안법 시행령, 안전보건규칙, 시설물안전법

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

### pending_review에서 복귀한 14건 (산안법 핵심 의무)
- 제124조 안전검사 (타워크레인/호이스트/곤돌라/리프트/공기압축기) 5건
- 제42조 유해위험방지계획서 (별지 16호서식) 2건 + 시행령 1건
- 제44조 심사결과서 (별지 19호서식) 1건
- 제54조 중대재해 발생 시 조치 2건
- 제64조 도급인 안전보건협의체 3건

### 복귀 안 된 pending 산안법 (B 그룹 2건, 모호)
- 제36조 위험성평가 — "점검 의무 (산업안전보건법 제36조)" 단순 문구만, 별지 서식 매핑 어려움 → pending 유지

---

## 점검 시스템 통합 검증

### 3중 매핑 정확한 상태
| 매핑 | 상태 | 커버리지 |
|---|---|---|
| **B. 문서 ↔ 점검항목** | ✅ **100% 매핑** | 260/260 문서 모두 점검 보유 (1,246건) |
| A. 의무 ↔ 문서 | ⚠️ 부분 | 110/260 (42.3%) |
| C. 의무 ↔ 점검 | ⚠️ 부분 | 416/1,246 (33.4%) |

### 운영 시 의미
| 시나리오 | 동작 |
|---|---|
| 사업장이 점검 항목 직접 사용 | ✅ 모든 1,246개 점검 작동 (B가 100%) |
| 의무 발생 → 자동 문서 발급 | ⚠️ 110개 문서만 자동 (A 매핑된 것) |
| 의무 발생 → 점검 추적 | ⚠️ 416개 점검만 추적 (C 매핑된 것) |

### 매핑 안 된 830개 점검의 의미
- 점검 항목 자체는 정상 (서식 기반)
- 단지 **어떤 운영 룰이 발동시키는지 추적 안 됨** (매핑 안 된 150개 문서의 점검들)
- 매핑이 늘어나면 자동 통합

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

### 운영 시작 전 (진짜 소비자 가치 시작점) 🎯
6. **inspection_set_items 사업장 인스턴스 시드** — 첫 사업장 등록 + 점검 항목 자동 생성
7. **safety_inspection_results 운영 시작** — 점검 데이터 기록
8. **자동 문서 생성 파이프라인 가동** — 의무 발생 시 별지 서식 자동 발급 (외부 의뢰 워크플로우 포함)

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

### 사용자 통찰 핵심 (반복 금지)
- 공장 사업장은 다중 법령 적용 (산안+소방+화학+가스+위험물+전기 등 동시)
- 정제 = 신뢰도, 운영 = 사업장 적용 (다른 차원)
- 부처 API 397건은 정제 안 거쳤어도 출처 명확 → 운영
- 외부 작성 문서는 SaaS 내 외부 의뢰 워크플로우로 활용

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
**다음 세션 우선순위**: 부분 일치 48건 검토 → 운영 시작 단계 (inspection_set_items 시드)
