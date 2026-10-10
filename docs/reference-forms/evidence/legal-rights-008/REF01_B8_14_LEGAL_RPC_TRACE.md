---
wo: WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008
doc_type: LEGAL_RPC_TRACE
date: 2026-10-10
base_head: 9864b9ac2039086747b68d0ff31507ac40806a27
---

# REF01 B8 14종 — 법령 RPC 조회 추적

## 1. RPC 경로 탐색 결과

### 탐색 방법

1. `GOVERNANCE_SOURCE_OF_TRUTH.md` 파일 전체 저장소 검색 → **NOT FOUND** (node_modules 제외)
2. `clients/leg_runtime_client.py` 분석 — LEG 런타임 접근 방식 확인
3. `GOVERNANCE_SOURCE_OF_TRUTH.md` 대체 경로 탐색 (`docs/`, `supabase/`, repo root) → **NOT FOUND**

### 확인된 LEG 런타임 접근 방식

파일: `clients/leg_runtime_client.py`

```
POST {LEG_RUNTIME_URL}/evaluate
POST {LEG_RUNTIME_URL}/rtm/evaluate
```

- 접근 경로: HTTP REST API (Supabase 직접 RPC 아님)
- 환경변수 `LEG_RUNTIME_URL`: 이 조사 컨텍스트에서 미설정
- `45cm-prj-db` `governance` 스키마는 LEG 런타임 서비스 내부에서 참조되며, 외부에서 직접 SELECT 불가

### 판정

```
GOVERNANCE_SOURCE_OF_TRUTH_FILE = NOT_FOUND
LEG_RUNTIME_URL                 = NOT_SET (research context)
LEGAL_SOT_ACCESSIBLE            = NO
LEGAL_RPC_ROUTE                 = LEGAL_SOT_UNAVAILABLE
```

---

## 2. 기존 연구 문서 내 법령 근거 기록 (2차 증거)

이 섹션은 LEGAL_SOT_UNAVAILABLE 상황에서 이미 수집된 연구 문서의 법령 인용을 기록한다.  
이는 RPC 결과가 아닌 연구 문서 인용이며, 적용 조건·유효성·서식 법정 여부는 LEG가 최종 판정한다.

| 서식 | 연구 문서 출처 | 인용 조문 | URL (연구 문서 인용) | 한계 |
|------|-------------|---------|------------------|------|
| GOV-01 | OBJ-REF-01-GOVERNANCE-WORKFLOW-15.md S1 | 산업안전보건법 제24조 (회의록 작성·보존) | https://www.law.go.kr/lsLinkCommonInfo.do?ancYnChk=&chrClsCd=010202&lsJoLnkSeq=1019429287 | 시행 2026-08-01 표기, 현행 유효성 미독립검증. 적용 사업장(시행령 별표9) 조건부. |
| GOV-01 | OBJ-REF-01-GOVERNANCE-WORKFLOW-15.md S2 | 산업안전보건법 시행령 제34~35조 (위원회 구성 대상) | https://law.go.kr/lsLinkCommonInfo.do?lspttninfSeq=153989 | 시행 2026-08-01 표기, 현행 유효성 미독립검증. |
| C026-C029 | OBJ-REF-01-OFFICIAL-SOURCE-DISCOVERY-02.md S4 | 산업안전보건법 제36조 (위험성평가) — 방법 종류 언급 | https://edu.kosha.or.kr/headquater/support/pds/filedownload/20240618161529_4648504880514822912_pdf | indexed snippet only; PDF 원문 미검사. 법령 URL 아님. |
| C031 | OBJ-REF-01-KOSHA-24-FORMS-SOURCE-03.md 항목24 | KOSHA 공식 배포 '안전보건교육일지 서식' (붙임5 ZIP) | https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view | ZIP 내부 파일 미검사. 법령 조문 아님 (KOSHA 배포 서식). |
| C039-C044 | OBJ-REF-01-CHEM-FIRE-OFFICIAL-EVIDENCE-10.md | 화학물질관리법, 산업안전보건법 제110조 이하 — MSDS/경고표지/훈련 의무 언급 | https://msds.kosha.or.kr/ | 구체 조문·시행일·적용 조건 미확인. KOSHA MSDS 상업적 재사용 경고 명시(S2). |
| C033 | OBJ-REF-01-GOVERNANCE-WORKFLOW-15.md S5 | 산업안전보건법 도급 관련 법적 업무 체계 안내 | https://www.law.go.kr/LSW/cgmExpcInfoP.do?cgmExpcDatSeq=30596&mode=2&ofiClsCd=350101 | 구 해석(일자 불명), 최신 법령 검증 필요. |

---

## 3. 각 서식별 법령 의무 분류 (연구 문서 기반 잠정 분류)

**분류 기준** (WO-008 §7):
- `ACTIVITY_DUTY_CONFIRMED_CONDITIONAL`: 의무 존재, 조건 미확정
- `ACTIVITY_DUTY_NOT_FORM_MANDATE`: 활동 의무 존재, 이 서식이 법정 양식은 아님
- `REVIEW_REQUIRED`: 연구 문서 증거로 판단 불충분
- `LEGAL_SOT_UNAVAILABLE`: RPC 접근 불가

| 서식 | 잠정 분류 | 근거 | 비고 |
|------|---------|------|------|
| C026 | REVIEW_REQUIRED | 법 제36조 위험성평가 의무 — 3단계 판단법 법정 서식 여부 미확인 | RPC 미접근 |
| C027 | REVIEW_REQUIRED | 법 제36조 — 체크리스트형 법정 서식 여부 미확인 | RPC 미접근 |
| C028 | REVIEW_REQUIRED | 법 제36조 — OPS법 법정 인정 여부 미확인 | RPC 미접근 |
| C029 | REVIEW_REQUIRED | 법 제36조 + KOSHA 24종 REF-C006 유사명 — 원본 비교 필요 | C006 원본 HWP 미검사 |
| C031 | REVIEW_REQUIRED | 법 제29조 교육 의무 + KOSHA 24종 REF-C024 배포 서식 — 이 TAI 서식 관계 미확인 | KOSHA 붙임5 ZIP 미검사 |
| C033 | REVIEW_REQUIRED | 법 제63조 도급 의무 + KOSHA 24종 REF-C011 유사명 | C011 원본 HWP 미검사 |
| C037 | REVIEW_REQUIRED | 근로자 참여·위험개선 관련 조항 미확인 | RPC 미접근 |
| C039 | REVIEW_REQUIRED | 화학물질관리법 취급목록 관리 의무(조건부 추정) | 조건(물질·수량) 미확인 |
| C040 | REVIEW_REQUIRED | 법 제114조 MSDS 보관 의무 — 이력 대장 법정 여부 미확인 | RPC 미접근 |
| C041 | REVIEW_REQUIRED | 법 제115조 경고표지 의무 — 점검표 법정 여부 미확인 | RPC 미접근 |
| C042 | REVIEW_REQUIRED | 화학물질관리법 보관시설 기준 — 점검표 법정 여부 미확인 | RPC 미접근 |
| C043 | REVIEW_REQUIRED | 화학물질관리법 제41조 비상대응 — 훈련기록 법정 여부 미확인 | RPC 미접근 |
| C044 | REVIEW_REQUIRED | 법 제114조 교육·주지 의무 — 확인기록 법정 여부 미확인 | RPC 미접근 |
| GOV-01 | ACTIVITY_DUTY_CONFIRMED_CONDITIONAL | 법 제24조 회의록 의무 — 적용 사업장 조건부, TAI 서식은 법정 별지 아님 | 사업장 규모·업종 조건 미확정 |

---

## 4. 한계 및 다음 단계

1. **GOVERNANCE_SOURCE_OF_TRUTH.md 미존재**: WO-008 §3 요건인 "실제 허용 RPC 서명" 확인 불가. 법령 SoT 접근 = `LEGAL_SOT_UNAVAILABLE`.
2. **LEG 런타임 미접근**: 이 연구 컨텍스트에서 `LEG_RUNTIME_URL` 환경변수 미설정. GPT가 별도 법령 검증 필요.
3. **연구 문서 법령 인용 한계**: URL만 기록, 실제 조문 텍스트·조건·시행일 독립 검증 미실시.
4. **법 제24조 GOV-01만 CONFIRMED_CONDITIONAL**: 나머지 13종은 REVIEW_REQUIRED. 과잉 일반화 금지.

```
LEGAL_RPC_ROUTE       = LEGAL_SOT_UNAVAILABLE
EVIDENCED_COUNT       = 0 (RPC 결과 없음)
REVIEW_REQUIRED_COUNT = 13
CONDITIONAL_COUNT     = 1 (GOV-01, 연구 문서 2차 증거)
```
