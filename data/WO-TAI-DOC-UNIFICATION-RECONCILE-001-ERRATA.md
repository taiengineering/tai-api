# WO-TAI-DOC-UNIFICATION-RECONCILE-001 — ERRATA

**작성일**: 2026-10-21  
**기준 커밋**: `0d8fb6fe` (원본 비교표·증거 MD 파일)  
**목적**: GPT 독립검증(SEMANTIC_GATE FAIL) 이후 확인된 오류만 정정. 82쌍 전수 재조사 없음.

---

## E-01. 자동작성 엔진 현황 정정

### 원본 EVIDENCE.md 주장 (오류)
> "DOC-OSH-056 (TBM 기록): TbmFetcher 등록 — ACTIVE (유일)"  
> "나머지 53개 SaaS 문서 (tai_auto=True 포함): engine fetcher 없음"

### 정정 내용

원본은 `routers/document_engine.py`(구 DOC-ID 라우터)만 확인했고, 신규 범용 생성기를 누락했다.

**구 라우터** (`routers/document_engine.py`):
```python
_FETCHERS = {"DOC-OSH-056": TbmFetcher()}  # doc_id 기반, TBM만
```

**신규 범용 생성기** (`services/document_engine/generator.py`):
```python
FETCHER_MAP = {"inspection": InspectionFetcher, "tbm": TbmFetcher}
```
→ `document_type_registry` DB 테이블 조회 후 `fetcher_key`로 Fetcher 클래스 선택.

**운영 DB `document_type_registry` 실제 등록 현황** (2026-10-21 조회):

| doc_type | type_label | fetcher_key | fetcher_status |
|----------|------------|-------------|----------------|
| TBM | 작업 전 안전점검회의 | tbm | **EXISTING** |
| INSP | 안전점검일지 | inspection | **EXISTING** |
| CHK | 점검 체크리스트 | inspection | **EXISTING** |
| EQUIP | 설비점검기록부 | inspection | **EXISTING** |
| PPE | 보호구 착용 점검 | inspection | **EXISTING** |
| APPT | 선임 보고 | null | NO_SOURCE |
| CONLOG | 공사일지 | construction | NEW_NEEDED |
| EDU | 교육일지 | education | NEW_NEEDED |

**정정된 결론**:
- EXISTING fetcher: TBM + INSP + CHK + EQUIP + PPE — 5종, 신규 개발 불요
- `routers/document_engine_api.py`는 `source_type=INSPECTION|TBM`으로 INSP·CHK·EQUIP·PPE·TBM 전부 라우팅
- CONLOG(공사일지)·EDU(교육일지)만 신규 fetcher 필요 (`fetcher_status=NEW_NEEDED`)
- APPT(선임보고)는 입력폼 기반, 운영 데이터 소스 없음 (`fetcher_status=NO_SOURCE`)
- **신규 개발 금지 원칙 유지**: EXISTING 5종 재사용, NEW_NEEDED 2종 개발 미승인

---

## E-02. `recommended_relation=RELATED_WORKFLOW`이나 실질 무관한 16쌍

원본 CSV에서 `title_match`가 `DIFFERENT`로 기록된 쌍임에도 `recommended_relation=RELATED_WORKFLOW`로 분류된 16쌍.  
**이 16쌍은 `unified_document_link` PROPOSED 등록 대상에서 제외한다.**

| # | SaaS ID | SaaS 이름 | Ref ID | Ref 이름 | orig_relation | 제외 근거 |
|---|---------|-----------|--------|----------|---------------|----------|
| 15 | DOC-CON-029 | 철근 작업계획서 | ref-equip-01 | 지게차 작업계획서 | AMBIGUOUS | 철근조립 vs 지게차운용 — 다른 작업 |
| 16 | DOC-CON-029 | 철근 작업계획서 | ref-equip-05 | 굴착기 작업계획서 | AMBIGUOUS | 철근조립 vs 굴착기운용 — 다른 작업 |
| 25 | DOC-CON-029 | 철근 작업계획서 | ref-equip-03 | 고소작업대 작업계획서 | RELATED_WORKFLOW | 철근조립 vs 고소작업대 — 다른 작업 |
| 28 | DOC-CON-023 | 굴착공사 작업계획서 | ref-equip-01 | 지게차 작업계획서 | RELATED_WORKFLOW | 굴착공사계획 vs 지게차운용 — 다른 작업 |
| 31 | DOC-CON-033 | 양중작업계획서 | ref-equip-01 | 지게차 작업계획서 | RELATED_WORKFLOW | 양중(크레인/호이스트) vs 지게차 — 다른 장비 |
| 32 | DOC-CON-033 | 양중작업계획서 | ref-equip-05 | 굴착기 작업계획서 | RELATED_WORKFLOW | 양중 vs 굴착기 — 다른 장비 |
| 38 | DOC-CON-023 | 굴착공사 작업계획서 | ref-equip-03 | 고소작업대 작업계획서 | RELATED_WORKFLOW | 굴착공사 vs 고소작업대 — 다른 작업 |
| 39 | DOC-BLD-009 | 전기설비 점검기록부 | ref-h2-01 | 수소설비 운전·점검 기록부 | RELATED_WORKFLOW | 전기설비(전기안전관리법) vs 수소설비(수소경제육성법) — 법령·대상 상이 |
| 41 | DOC-OSH-059 | 기계설비 점검기록부 | ref-h2-01 | 수소설비 운전·점검 기록부 | RELATED_WORKFLOW | 기계설비 vs 수소설비 — 법령·안전기준 상이 |
| 42 | DOC-CON-033 | 양중작업계획서 | ref-equip-03 | 고소작업대 작업계획서 | RELATED_WORKFLOW | 양중 vs 고소작업대 — 다른 장비 |
| 43 | DOC-OSH-055 | 안전보건점검 체크리스트 | ref-p-21 | 산업안전보건관리비 지출증빙 체크리스트 | RELATED_WORKFLOW | 안전점검(위험요인) vs 지출증빙(비용관리) — 목적 완전 상이 |
| 55 | DOC-BLD-016 | 석면점검 기록부 | ref-h2-01 | 수소설비 운전·점검 기록부 | RELATED_WORKFLOW | 석면점검(석면안전관리법) vs 수소설비(수소경제육성법) — 법령·대상 완전 상이 |
| 57 | DOC-FAC-016 | 냉동기 설비 점검기록부 | ref-h2-01 | 수소설비 운전·점검 기록부 | RELATED_WORKFLOW | 냉동기(에너지이용합리화법) vs 수소설비 — 법령·대상 상이 |
| 59 | DOC-OSH-014 | 밀폐공간작업계획서 | ref-equip-01 | 지게차 작업계획서 | RELATED_WORKFLOW | 밀폐공간 vs 지게차 — 다른 작업 |
| 60 | DOC-OSH-014 | 밀폐공간작업계획서 | ref-equip-05 | 굴착기 작업계획서 | RELATED_WORKFLOW | 밀폐공간 vs 굴착기 — 다른 작업 |
| 78 | DOC-OSH-014 | 밀폐공간작업계획서 | ref-equip-03 | 고소작업대 작업계획서 | VARIANT | 밀폐공간 vs 고소작업대 — 다른 작업(DIFFERENT) |

**정정 방향**: `recommended_relation` 컬럼 값을 `NOT_APPLICABLE`로 변경하거나 CSV 별도 컬럼에 표기.  
단, 원본 CSV 파일(SHA 확정)은 수정하지 않음. 이 ERRATA가 적용 지침으로 기능한다.

---

## E-03. VARIANT 22쌍 원분류 보존 근거 및 세부 재분류

원본 CSV `orig_relation=VARIANT`인 22쌍을 일괄 RELATED_WORKFLOW로 재분류한 것에 대해 원분류 보존을 포함한 세부 재분류를 적용한다.

### E-03-A. TRUE_VARIANT 유지 권고 (4쌍)

같은 목적, 다른 방법론 또는 다른 대상 특화 — VARIANT 원분류가 적절하다.

| # | SaaS ID | SaaS 이름 | Ref ID | Ref 이름 | 근거 |
|---|---------|-----------|--------|----------|------|
| 76 | DOC-OSH-002 | 위험성평가서 | ref-c027 | 체크리스트형 위험성평가표 | 위험성평가 목적 동일, 체크리스트 방법론만 다름 |
| 77 | DOC-OSH-002 | 위험성평가서 | ref-c029 | 빈도·강도법 위험성평가표 | 위험성평가 목적 동일, 빈도·강도 방법론만 다름 |
| 81 | DOC-OSH-007 | 안전점검일지 | ref-equip-06 | 지게차 안전점검표 | 일반 안전점검(모든 유해위험요인) vs 지게차 특화 — 동일 업무 범위 특화 |
| 82 | DOC-OSH-007 | 안전점검일지 | ref-equip-07 | 크레인 안전점검표 | 일반 안전점검 vs 크레인 특화 — 동일 업무 범위 특화 |

### E-03-B. RELATED_WORKFLOW 재분류 적합 (12쌍)

순차 워크플로(계획→실시, 허가→관리대장, 보고→이력), 또는 동일 도메인 관련 서식 — RELATED_WORKFLOW 재분류 수용.

| # | SaaS ID | Ref ID | 관계 근거 |
|---|---------|--------|----------|
| 61 | DOC-SERA-008 | ref-c033 | 협력업체/도급업체 안전관리 동일 도메인 |
| 62 | DOC-OSH-021 | ref-c070 | 작업환경측정결과보고서 → 개선관리대장 (순차) |
| 63 | DOC-OSH-054 | ref-c033 | 협력업체 안전관리 동일 도메인 |
| 64 | DOC-OSH-037 | ref-c016 | 연간교육계획 → 교육 실시기록부 (순차) |
| 66 | DOC-CON-LAW-014 | ref-c067 | 건설법정 안전점검 vs 현장일일점검 (관련 도메인) |
| 67 | DOC-OSH-049 | ref-p-06 | 작업허가서 → 허가관리대장 (순차) |
| 68 | DOC-OSH-006 | ref-c016 | 연간교육계획 → 교육일지 (순차) |
| 74 | DOC-FAC-004 | ref-c013 | 가스사고 vs 사고조사보고서 (동일 도메인) |
| 75 | DOC-FAC-004 | ref-p-15 | 사고 최초 상황보고서 → 법정신고 (순차) |
| 79 | DOC-BLD-018 | ref-lab-02 | 시설물/연구실 정밀안전진단 (관련 도메인) |
| 80 | DOC-BLD-032 | ref-c056 | 승강기 중대고장 보고서 → 이력대장 (순차) |
| 73 | DOC-CON-015 | ref-equip-05 | 굴착작업 안전계획(공정) vs 굴착기 계획(장비) — 동일 굴착 도메인 |

### E-03-C. 실질 무관 — RELATED_WORKFLOW 분류 부적절 (4쌍)

| # | SaaS ID | Ref ID | 판단 근거 |
|---|---------|--------|----------|
| 65 | DOC-CON-011 (안전보건협의체 회의록-건설) | ref-gov-01 (산업안전보건위원회 회의록) | 협의체(산안법 제64조) vs 위원회(산안법 제24조) — 다른 법정 기구, 다른 조문 |
| 70 | DOC-OSH-015 (안전보건협의체회의록) | ref-gov-01 (산업안전보건위원회 회의록) | 협의체 vs 위원회 — 동일 문제(#65와 같음) |
| 69 | DOC-CON-031 (타워크레인 설치계획서) | ref-equip-04 (이동식크레인 작업계획서) | 타워크레인(고정식·설치단계) vs 이동식크레인(작업단계) — 유형·단계 모두 다름 |
| 71 | DOC-CON-008 (작업계획서-고위험작업) | ref-equip-01 (지게차 작업계획서) | 일반 고위험 계획서 vs 지게차 특화 — VARIANT 경계이나 출처 법령 상이(산안법 제42조 vs 미기재) |

> **비고 — #71·#72 경계 사례**: `작업계획서(고위험작업)` ↔ `지게차/굴착기 작업계획서`는  
> VARIANT(일반→특화) 해석도 가능하나 출처 법령 확인 미완료. Owner 판단 필요.

---

## E-04. 다중 매핑 — DB 제약과 의미 허용 가능성 구분

### DB 제약 사실
`unified_document_link` 테이블에는 `(saas_doc_id, ref_id)` 쌍 유일성 제약이 있다.  
→ **동일 참고서식에 여러 SaaS 문서가 각각 독립 연결(PROPOSED) 가능.**  
→ 같은 (saas_doc_id, ref_id) 쌍의 중복 APPROVED는 불가.

원본 EVIDENCE.md의 "이중 APPROVED 불가" 표현은 DB 제약과 불일치했음. 정정: 쌍별 중복 등록 방지이지, 1:N 연결 차단이 아님.

### 의미적 허용 가능성 (별도 Owner 판단 필요)

| Ref ID | 연결된 SaaS 문서들 | 의미적 허용 여부 |
|--------|-------------------|----------------|
| ref-c031 (교육 실시일지) | DOC-OSH-037 (실시기록부) + DOC-OSH-006 (교육일지) | 두 문서가 실질적으로 동일 서식인지 Owner 확인 필요 |
| ref-gov-06 (협의체 회의록-도급) | DOC-CON-011 (건설특화) + DOC-OSH-015 (일반) | 건설 특화 vs 일반 — 동일 서식의 컨텍스트 변형으로 볼 수 있음 |
| ref-conf-01 (밀폐공간 출입작업허가서) | DOC-OSH-047 (일반) + DOC-CON-037 (건설) | 건설 특화 vs 일반 — AMBIGUOUS 유지 중 |

---

## E-05. SAME_DOCUMENT_CANDIDATE 9쌍 상태 유지

GPT 검증 결과 9쌍은 후보 상태 유지. 변경 없음.

| # | SaaS ID | Ref ID | 현재 상태 | 비고 |
|---|---------|--------|----------|------|
| 1 | DOC-OSH-058 | ref-gov-01 | CANDIDATE_HOLD | ref 법령근거 미기재·서명 구조 미대조 |
| 2 | DOC-OSH-045 | ref-c023 | CANDIDATE_HOLD | SaaS evidence=2 항목 미확인 |
| 3 | DOC-OSH-047 | ref-conf-01 | CANDIDATE_HOLD | 가스측정·구조·승인 표현 차이 검토 필요 |
| 4 | DOC-CON-011 | ref-gov-06 | CANDIDATE_HOLD | 건설 특화 항목 여부 미확인 |
| 5 | DOC-OSH-037 | ref-c031 | CANDIDATE_HOLD | DOC-OSH-006 이중 매핑 정리 필요 |
| 8 | DOC-CON-041 | ref-p-14 | CANDIDATE_HOLD | 승인절차 포함 여부 미확인 |
| 12 | DOC-OSH-006 | ref-c031 | CANDIDATE_HOLD | DOC-OSH-037 이중 매핑 정리 필요 |
| 14 | DOC-OSH-049 | ref-c025 | CANDIDATE_HOLD | 위험확인·승인·종료 항목 차이 검토 필요 |
| 17 | DOC-OSH-015 | ref-gov-06 | CANDIDATE_HOLD | DOC-CON-011 이중 매핑 + E-03-C #70 연계 |

---

## 정정 요약 (적용 범위)

| 항목 | 정정 내용 | 소스 변경 여부 |
|------|----------|--------------|
| E-01 엔진 현황 | EXISTING fetcher=5종(TBM+INSP+CHK+EQUIP+PPE). 원본 "1종" 오류 정정 | EVIDENCE.md 메모. 코드·DB 변경 없음 |
| E-02 16쌍 제외 | DIFFERENT 16쌍 → PROPOSED 등록 대상 제외 | 원본 CSV 수정 없음. 이 ERRATA가 적용 지침 |
| E-03 VARIANT 22쌍 | TRUE_VARIANT=4, RELATED_WORKFLOW=12, 실질무관=4, 경계=2 | 원본 CSV 수정 없음. 이 ERRATA가 적용 지침 |
| E-04 다중 매핑 | DB 쌍별 제약 vs 의미 허용 가능성 구분 | 변경 없음 |
| E-05 9쌍 | CANDIDATE_HOLD 유지 | 변경 없음 |

**운영 DB 변경**: 0건  
**PR/배포**: 없음  
**Git 변경**: 이 ERRATA 파일만 신규 추가

---

**비교 소스 버전 식별자**:
- 원본 비교표: `data/document_link_comparison_table.csv` SHA256=53374607... (커밋 0d8fb6fe)
- 원본 증거 MD: `data/WO-TAI-DOC-UNIFICATION-RECONCILE-001-EVIDENCE.md` SHA256=36b393... (커밋 0d8fb6fe)
- document_type_registry: vwlahtguyggrhvslabax DB 2026-10-21 조회 (8행)
- 엔진 소스: `services/document_engine/generator.py` + `routers/document_engine_api.py` (커밋 0d8fb6fe)
