# WO-TAI-DOC-UNIFICATION-RECONCILE-001 — 비교 증거 제출 (GPT 독립검증용)

**작성일**: 2026-10-21  
**작업 범위**: 82개 SaaS 문서 ↔ 참고서식 후보 쌍 전수 비교  
**소스 파일**: `data/document_link_comparison_table.csv` (82행 전체 포함)

---

## 1. 데이터 소스 식별자

| 소스 | 버전/상태 | 비고 |
|------|-----------|------|
| `document_forms` | DB 조회 2026-10-21 | 54개 SaaS 문서. doc_id, doc_name, category, law_ref, tai_auto |
| `runtime_form_schema` | DB 조회 2026-10-21 | 260개 CANDIDATE 상태. catalog_document_id로 document_forms 연결 |
| `reference_form_content` + `reference_form_slug_registry` | DB 조회 2026-10-21 | 42개 ref form title + body_html |
| `document_form_master` | 이전 세션 조회 | STD-MTG-001 등 주요 법령 서식 메타데이터 |
| `data/document_link_candidates.csv` | 2026-10-21 기준 HEAD | 82쌍, 8컬럼 |
| `routers/document_engine.py` | API main 98a3c383 | `_FETCHERS = {"DOC-OSH-056": TbmFetcher()}` — 유일 활성 엔진 |

---

## 2. 자동작성 엔진 현황 (REUSE/NO CHANGE 검증)

- **DOC-OSH-056 (TBM 기록)**: `TbmFetcher` 등록 — **ACTIVE** (유일)
- 나머지 53개 SaaS 문서 (`tai_auto=True` 포함): engine fetcher **없음**. TAI는 문서 관리·보관·FAX·포털 링크 역할. 자동작성 엔진은 미구현.
- `runtime_form_schema` 260개 레코드 전부 `status=CANDIDATE` — 운영 중인 런타임 스키마 없음.

**결론**: 기존 자동작성 엔진은 DOC-OSH-056만 해당. 신규 개발 없이 재사용 가능한 엔진은 1개.

---

## 3. 비교 결과 요약

| 권고 관계유형 | 쌍 수 | 원본 대비 변화 |
|---|---|---|
| SAME_DOCUMENT_CANDIDATE | **9** | 원본 3 → 6 추가 승격 |
| AMBIGUOUS | **8** | 원본 14 → 4 유지 + 4 신규 |
| RELATED_WORKFLOW | **65** | 원본 43 + 22 VARIANT 통합 |
| VARIANT | 0 | RELATED_WORKFLOW로 재분류 |

---

## 4. SAME_DOCUMENT_CANDIDATE 9쌍 (GPT 검증 대상)

| # | SaaS ID | SaaS 이름 | Ref ID | Ref 이름 | sim | 원본 | 제목일치 | 법령 | 주요 일치항목 | 미확인사항 |
|---|---------|-----------|--------|----------|-----|------|---------|------|--------------|-----------|
| 1 | DOC-OSH-058 | 산업안전보건위원회 회의록 | ref-gov-01 | 산업안전보건위원회 회의록 | 1.000 | SDC | EXACT | SaaS=산안법 제24조 / Ref=미기재 | 제목 완전일치·회의일시·장소·사회자·참석자·안건·의결·이행담당자·기한·서명 | Ref 법령근거 미기재·SaaS 5필드명 미확인·서명란 구조 세부 대조 미완료 |
| 2 | DOC-OSH-045 | 보호구 지급대장 | ref-c023 | 안전보호구 지급대장 | 0.875 | SDC | NEAR_EXACT | SaaS=산안법 제41조 / Ref=미기재 | 품목명규격·지급일·지급수량·수령자명·소속·반납일·비고 | SaaS 6필드명·evidence=2 항목·Ref 법령근거 |
| 3 | DOC-OSH-047 | 밀폐공간 작업허가서 | ref-conf-01 | 밀폐공간 출입·작업허가서 | 0.857 | SDC | NEAR_EXACT | SaaS=산안법 제38조 / Ref=미기재 | 작업일시·위치·내용·신청자·공기측정·환기감시인·출입자명단·비상연락·결재 3단 | SaaS evidence=3 항목·SaaS 5필드명 상세 |
| 4 | DOC-CON-011 | 안전보건협의체 회의록(건설) | ref-gov-06 | 안전보건협의체 회의록(도급사업) | 0.786 | AMBIGUOUS | NEAR_EXACT | SaaS=산안법 제64조 / Ref=미기재 | 회의일시·장소·주관자·참석자·안건·결정조치·담당·기한·이행여부·결재 | 건설 특화 필드 여부·SaaS 5필드명 |
| 5 | DOC-OSH-037 | 안전보건교육 실시기록부 | ref-c031 | 안전보건교육 실시일지 | 0.762 | AMBIGUOUS | NEAR_EXACT | SaaS=산안법 제29조 / Ref=미기재 | 교육일시·장소·교육자·내용요약·참석자·소속·서명 | SaaS 4필드명·DOC-OSH-006 이중매핑 |
| 8 | DOC-CON-041 | 작업중지 및 재개 기록 | ref-p-14 | 작업중지·재개 승인기록 | 0.727 | AMBIGUOUS | NEAR_EXACT | SaaS=산안법 제52조 / Ref=미기재 | 중지일시·작업명/위치·중지명령자·중지사유·조치내용·재개조건·결재 | SaaS evidence=2 항목·승인절차 포함 여부 |
| 12 | DOC-OSH-006 | 안전보건교육일지 | ref-c031 | 안전보건교육 실시일지 | 0.706 | AMBIGUOUS | NEAR_EXACT | SaaS=산안법 제29조 / Ref=미기재 | 교육일시·장소·교육자·참석자명단·서명 | DOC-OSH-037 이중매핑·SaaS 6필드명 |
| 14 | DOC-OSH-049 | 작업허가서(위험작업) | ref-c025 | 위험작업 허가서 | 0.667 | AMBIGUOUS | NEAR_EXACT | SaaS=산안법 제38조 / Ref=미기재 | 작업번호·작업명·신청자·장소·일시·위험확인·주요위험·추가조치·격리방호·결재·종료확인 | SaaS 6필드명·evidence=1 항목 |
| 17 | DOC-OSH-015 | 안전보건협의체회의록 | ref-gov-06 | 안전보건협의체 회의록(도급사업) | 0.667 | AMBIGUOUS | NEAR_EXACT | SaaS=산안법 제64조 / Ref=미기재 | 회의일시·장소·주관자·참석자·안건·결정조치·담당·기한·이행여부 | DOC-CON-011 이중매핑 정리 필요 |

---

## 5. AMBIGUOUS 8쌍 (추가 검토 필요)

| # | SaaS ID | SaaS 이름 | Ref ID | Ref 이름 | sim | 미확인/불일치 사항 |
|---|---------|-----------|--------|----------|-----|-----------------|
| 6 | DOC-BLD-009 | 전기설비 점검기록부 | ref-c052 | 전기설비 일상 점검기록표 | 0.762 | 정기(법정 주기) vs 일상(일과) 빈도 차이·전기안전관리법 특수성 |
| 7 | DOC-CON-037 | 밀폐공간 작업허가서(건설) | ref-conf-01 | 밀폐공간 출입·작업허가서 | 0.750 | DOC-OSH-047도 동일 ref 매핑(이중)·건설 특화 fields=7 vs 일반 fields=5 |
| 9 | DOC-CON-036 | 용접작업 허가서 | ref-c012 | 안전작업 허가서 | 0.714 | 용접 특화 안전조치(차폐·환기·열원·불꽃) Ref에 없음 |
| 10 | DOC-CON-036 | 용접작업 허가서 | ref-c025 | 위험작업 허가서 | 0.714 | 용접은 위험작업의 일종이나 특화 항목 누락 가능·ref-c012 vs ref-c025 중 근접 ref 미결정 |
| 23 | DOC-OSH-043 | 화학물질 관리대장 | ref-c039 | 사업장 화학물질 취급목록 관리대장 | 0.640 | SaaS 제목에 '취급목록' 없음→범위 차이·fields=5 vs Ref 반복 9항목 |
| 24 | DOC-CON-038 | 고소작업 계획서 | ref-equip-03 | 고소작업대 작업계획서 | 0.625 | SaaS '고소작업' 일반 vs Ref '고소작업대(장비)' 특화 범위 차이 |
| 30 | DOC-OSH-048 | 밀폐공간 산소농도 측정기록 | ref-conf-02 | 밀폐공간 산소·유해가스 측정 기록부 | 0.581 | SaaS '산소농도'만 vs Ref '산소+유해가스' 포괄·SaaS evidence=5 항목 미확인 |
| 52 | DOC-OSH-052 | 비상훈련 실시기록 | ref-c047 | 비상대피훈련 실시 및 개선기록 | 0.522 | SaaS '비상훈련'(전반) vs Ref '비상대피훈련'(특화) 범위 차이 |

---

## 6. 다중 매핑 충돌 목록

| Ref ID | 매핑된 SaaS 문서들 | 비고 |
|--------|-------------------|------|
| ref-c031 (교육 실시일지) | DOC-OSH-037(SDC), DOC-OSH-006(SDC), DOC-SERA-006(RELATED) | 3방향. SDC 2개 동시 — 실제 동일 Ref 가능하나 이중 APPROVED 불가 |
| ref-gov-06 (협의체 회의록-도급) | DOC-CON-011(SDC-건설), DOC-OSH-015(SDC-일반) | 건설 특화 vs 일반 — 동일 서식의 컨텍스트 변형 여부 확인 필요 |
| ref-conf-01 (밀폐공간 출입작업허가서) | DOC-OSH-047(SDC-일반), DOC-CON-037(AMBIGUOUS-건설) | 일반 vs 건설 — CON-037은 AMBIGUOUS 보류 |

---

## 7. RELATED_WORKFLOW 65쌍 분류

65쌍은 아래 패턴으로 분류됩니다 (세부는 CSV 참조):

| 패턴 | 대표 예시 | 쌍 수 |
|------|----------|-------|
| 다른 장비/작업 유형 (작업계획서 계열) | 철근↔지게차, 양중↔굴착기, 밀폐공간↔고소작업대 | 약 20 |
| 법정신고 vs 자체기록 (사고 보고서 계열) | 가스사고↔아차사고, 보일러사고↔아차사고 | 약 8 |
| 순차 워크플로 (측정→개선, 허가→이력) | 작업환경측정↔개선관리대장, 허가서↔허가관리대장 | 약 10 |
| 법령 도메인 상이 (소방/시설물/석면/연구실) | 소방시설↔안전보건내부점검, 석면↔수소설비 | 약 12 |
| 범위/특화 차이 (일반 vs 특화) | 안전점검일지↔지게차점검표, 위험성평가서↔체크리스트형 | 약 15 |

---

## 8. 확정 사실

1. **DOC-OSH-056만 engine fetcher 활성** — 나머지는 tai_auto=True여도 fetcher 없음 (재개발 없이 현상 유지)
2. **runtime_form_schema 260개 전부 CANDIDATE** — 운영(ACTIVE) 스키마 없음
3. **SAME_DOCUMENT_CANDIDATE 9쌍**: 제목 near-exact 또는 exact + 목적 동일 + 법령 동일 도메인 확인
4. **ref form 법령근거 전부 미기재** — Ref 측 법령근거는 SaaS 측 법령으로 추정만 가능
5. **SaaS runtime 필드명 미조회** — fields/checklists/evidence 수량만 확인. 상세 field_name 미조회.

---

## 9. GPT 독립검증 요청 사항

1. **SAME_DOCUMENT_CANDIDATE 9쌍 각각**:
   - 제목 유사도 판단이 관계 승격에 충분한지 (필드 수준 상세 조회 없이)
   - ref-c031 이중매핑(DOC-OSH-037·006) — 두 쌍 모두 SDC 유지 가능한지
   - ref-gov-06 이중매핑(DOC-CON-011·015) — 두 쌍 모두 SDC 유지 가능한지

2. **AMBIGUOUS 8쌍 각각**:
   - 현재 근거로 SDC 또는 RELATED_WORKFLOW로 확정 가능한지
   - DOC-CON-036: ref-c012 vs ref-c025 중 더 가까운 것이 어느 쪽인지

3. **RELATED_WORKFLOW vs VARIANT 통합**:
   - 원본 VARIANT 22쌍을 RELATED_WORKFLOW로 일괄 재분류한 것이 적절한지 (VARIANT 유지 사유 있는 쌍 있는지)

4. **전체 82쌍 관계유형 분포**:
   - SAME_DOCUMENT_CANDIDATE 9쌍이 unified_document_link PROPOSED 등록 대상으로 적절한 우선순위인지

---

**비교 소스 버전 식별자**:
- document_forms: vwlahtguyggrhvslabax DB 2026-10-21 조회
- runtime_form_schema: vwlahtguyggrhvslabax DB 2026-10-21 조회 (260 rows, all CANDIDATE)
- reference_form_content: vwlahtguyggrhvslabax DB 2026-10-21 조회 (42 ref forms)
- document_engine.py: API main 98a3c383 (2026-10-21)
- document_link_candidates.csv: HEAD 2026-10-21 (82 pairs)
