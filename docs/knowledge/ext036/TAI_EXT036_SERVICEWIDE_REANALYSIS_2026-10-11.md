# TAI / EXT-036 국가법령정보 공동활용 — 서비스 전반 재분석 v1

기준일: 2026-10-11 KST  |  작성: GPT 독립 분석  |  상태: **설계 제안 / 구현 승인 아님**

## 0. 결론

**이전 EXT-036 우선순위안(EXT-133 iaciac → EXT-134 moelCgmExpc → EXT-135 expc 즉시 구현)은 보류한다.** 건수와 '산안법 관련'만으로 선정해 기존 TAI의 Public Search, SEO, Paid Diagnosis, SaaS, Legal Search, Knowledge Graph, Search Dictionary와의 연결 가치를 보지 못했다.

**바뀐 목적**: LEG 안의 EXT-036 전용 원천 저장소에서 공식 연계정보를 보유하고, 기존 Shared Search 및 Knowledge Graph에 단일 승인형 읽기 경로를 제공한다. LEG 기존 법령 원천 및 법령엔진에는 자동 병합·자동 판정하지 않는다.

## 1. 확인된 사실과 한계

- 업로드된 `EXT036_ALL_API_GUIDES.json`: Guide **195개**, `guide_id` 고유 195, target 고유 **104**. List 표시 103 Guide, 본문 표시 80 Guide. 이는 API 목록 구조 검증이며 실데이터 수집 성공이 아님.
- `EXT036_LINKED_INFORMATION_MATRIX.csv`: P1 6 / P2 6 / P3 3 / P4 **89** Target. 업로드된 API total-count matrix에서 실제 수치가 채워진 고유 Target은 **33**. 이들은 **원천 검색 전체 건수**(시점은 첨부 조사 기준), TAI 관련·수집가능·중복제거 후 건수가 아니다.
- 모든 195 Guide의 `description` 앞부분이 동일한 웹사이트 내비게이션 문구다. 의미별 설명 추출/검증이 실질적으로 부족하다. `industrial_safety` HIGH/MEDIUM/LOW는 Claude의 분류이며 도메인별 제품가치의 독립 판정 아님.
- `tai-www` 기존 Shared Search 계약은 단일 검색 백엔드, canonical 상세 링크, 법령 판정 금지, `process/task/equipment/chemical/legal_obligation/risk_factor/sector` context vocabulary를 정의한다. `/safety-search` 결과 자체는 `noindex,follow`로 설정됐다. 별도의 검색엔진/검색 DB를 신규 구축할 이유가 없다.
- `tai-www` Knowledge Graph 계획: Knowledge → Context 근거 추적, source-current 확인, `Public / Paid / SaaS` consumer 분리, LEG 의무 적용 판정과 구분.
- `tai-api` Shared Search 마스터 계획에 SaaS Context Search와 Paid Diagnosis Knowledge의 연결 과제가 명시돼 있다. 이는 계획서의 이슈 기술이며 2026-10-11 실배포 미완료라고 단정하지 않는다.
- `prec` 전체 174,185건, `nlrc` 44,873, `decc` 35,217, `moelCgmExpc` 9,636, `expc` 8,881, `iaciac` 934 등은 **전역 규모**. 산업안전 자료 수는 미검증. `iaciac`은 산업재해보상 재심사 결정 사례로, 산업재해예방 기준과 혼동 불가.
- `ordin`이 '기존 EXT-036 수집 중'이라는 첨부 계획의 표현은 실 운영 DB/스케줄의 완료 증거가 없는 상태. 기존 수집 여부와 중복은 다음 소스 확인의 대상이다.

### 출처
- User attachments: EXT036_COLLECTION_PRIORITY_PLAN.md; EXT036_INDUSTRIAL_SAFETY_RELEVANCE.md; EXT036_ALL_API_GUIDES.json; EXT036_LINKED_INFORMATION_MATRIX.csv; EXT036_API_TOTAL_COUNT_MATRIX.csv.
- GitHub: https://github.com/taiengineering/tai-www/blob/main/docs/TAI_UNIFIED_SEARCH_HANDOFF_2026-09-22.md
- GitHub: https://github.com/taiengineering/tai-www/blob/main/docs/ops/tai-www/PLAN_safety-knowledge-graph_v1.md
- GitHub: https://github.com/taiengineering/tai-www/blob/main/docs/ops/tai-www/PLAN_safety-knowledge-hub-master_v0.1.md
- GitHub: https://github.com/taiengineering/tai-api/blob/main/docs/TAI_SHARED_SEARCH_MASTER_PLAN_v2.md
- Official `lsDelegated`: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsDelegated
- Official `lsRlt`: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsRltGuide
- Official `lstrmRltJo`: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lstrmRltJoGuide
- Official `lsJoHstInf`: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsDayJoRvsListGuide
- Official `lnkLsOrdJo`: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsOrdinConListGuide

## 2. 소비자별 목적과 필요한 API

| Consumer | 해결할 사용자 문제 | 가장 필요한 EXT-036 Target | 기능 방향 | 금지 경계 |
|---|---|---|---|---|
| Public 통합검색 | 일반 키워드로 관련 공식자료를 찾음 | `lstrmRlt`, `lstrmRltJo`, `moelCgmExpc`, `expc`, `prec`, `decc` | 검색사전 승인형 어휘 확장; 사례/해석 출처별 결과 및 canonical 상세 | 법령 적용 자동판정, 별도 검색 인덱스 증설 |
| SEO/안전정보 허브 | 방문자가 상세페이지에서 주제를 이해하고 다음 자료로 이동 | `prec`, `moelCgmExpc`, `expc`, `nlrc`, `decc` | 산업안전 확실한 사례만 상세/관련자료 연결, rights gate | 검색 결과 페이지 대량 색인, 무검토 복제 페이지 |
| Paid Diagnosis | 의무 결과를 이해하고 실행 참고자료 확인 | `lsDelegated`, `lsRlt`, `moelCgmExpc`, `expc` | 엔진이 **이미 판정한** 의무의 해설/공식사례 읽기 | 외부 사례가 의무 판정 바꾸기 |
| SaaS 설비·작업·공정 | 지게차/밀폐공간/화학작업에 필요한 참고지식 자동 발견 | `lstrmRltJo`, `lsRlt`, `lsDelegated`, `prec`, `moelCgmExpc` | context key → Knowledge relations, evidence 기반 추천 | 장비/사업장 법적 적합성 추정 |
| SaaS 변경관리 | 새 법령·조문 변경을 놓치지 않음 | `lsJoHstInf`, `lsHstInf`, `eflaw`, `oldAndNew`, `admrulOldAndNew` | 시행예정·개정 이벤트 → 검토후보 → 승인후 업무 연계 | 변경 정보만으로 법정의무 수정·점검주기 자동변경 |
| 법령검색 고도화 | 법령 간 연결과 배경 파악 | `lsRlt`, `lsDelegated`, `lnkLsOrdJo`, `lnkLs`, `lstrmRltJo` | 관계 그래프 / 왜 연결되는지 조문 경로 제시 | 기존 LEG 조문 SoT 덮어쓰기 |
| 업종별 SaaS | 제조·화학·건설·소방·시설 문맥에 맞춤 정보 | `meCgmExpc`, `molitCgmExpc`, `nfaCgmExpc`, `motieCgmExpc`, `moisCgmExpc` | 업종별 관할 해석/분쟁 참고 자료; scope-by-sector | 모든 부처 문서 일괄 노출 |

## 3. 우선순위 (Service Value first)

### P0: 연결·변경 데이터 계약 — **수집 전 범위 검증을 먼저**

1. **규정 간 링크**: `lsDelegated`, `lsRlt`. 133개 현재 LEG 범위에서 우선 조회하되, 연결 대상이 외부 법령이어도 **관계 메타데이터만 유지**하고 외부 법령 본문은 자동 취득하지 않는다.
2. **일상어 → 법령용어 → 관련 조문**: `lstrmRlt`, `lstrmRltJo`, 보조 `dlytrmRlt`. 검색사전 `APPROVED`를 우회해 새 동의어를 운영에 직접 노출하지 않는다. Shadow+검증 후 사용.
3. **조문 개정·시행예정**: `lsJoHstInf`, `lsHstInf`, `eflaw`, `eflawjosub`. 전체 169,345 'eflaw' 기록을 끌어오지 않는다. 현재 LEG 범위의 변경 이벤트만 탐지하여 사람/LEG reviewer에 전달.
4. **법령 ↔ 자치법규의 조문 수준 연결**: `lnkLs`, `lnkLsOrdJo`, `lnkDep`. 이용 사업장의 지자체 맥락에 따른 '참고' 정보; 전국 조례 161,682건 전수 다운로드 요구하지 않음.

### P1: 서비스용 공식 사례·해석 본문

- `moelCgmExpc` / `expc`: 안전관리 질의 Q&A·법령검색·의무 설명의 가장 명확한 공식 참고 원천. 전체 각각 9,636 / 8,881은 원천 전체; 산안 관련 분모 재산정 필요.
- `prec`: 현재 TAI 판례 849건과 고유키/본문 중복 비교부터. 174,185건 무분별 수집 금지.
- `decc`: 안전 관련 행정처분 불복, 시설기준·제재 이해의 참고. 전체 35,217건으로 선별 계약 필요.
- `nlrc`, `iaciac`: 근로·산재보상 분쟁 콘텐츠. 작업예방 의무 추출용 사용 금지.
- 부처 해석: `molitCgmExpc`(건설), `motieCgmExpc`(에너지/가스), `meCgmExpc`(환경/화학), `nfaCgmExpc`(소방), `moisCgmExpc`(재난). 기존 보고 LOW 분류 무효화, 검증 필요.

### P2: 연계 기능 확장·실험

`lstrm`, `dlytrm`, `lsStmd`, `lsAbrv`, `oldAndNew`, `admrulOldAndNew`, `thdCmp`, `lsHistory`, `oneview`, `drlaw`, `ordinbyl`, `mohwCgmExpc`, `eiac`, `trty` (ILO 산업안전 관련분), `baiPvcs` 등. 세부 사용처·계약 확인 전 전체 적재 금지.

### REUSE / EVALUATE / DEFER

- 기존 LEG로 해결: `law`, `admrul`, `lawjosub`, `licbyl`, `admbyl` — 신규 본문 중복 수집 금지.
- `ordin`: 기존 수집 실제 상태와 관계 메타데이터 분리 검토.
- `aiSearch`, `aiRltLs`, `lstrmAI`: 즉시 제외가 아닌 **검색품질 비교/평가용** (개인·사업장 데이터 외부 전송 금지).
- 나머지 기능은 서비스 KPI·업종 관련성이 확인될 때 재검토.

**104개 Target 전부에 대해 구/신 우선순위와 사용처·조사 게이트를 붙인 파일**: `EXT036_SERVICE_PRIORITY_104_2026-10-11.csv`.

## 4. 연결 아키텍처와 금지사항

```text
법제처 DRF Open API (출처별 1회 collection / metadata + raw)
                ↓
LEG PROD: ext036_* ONLY (기존 law_master/law_article/etc READ ONLY)
    - source_target + official_id + raw_payload + as_of + provenance
    - relation edges (law↔law, law↔article, term↔article, law↔ordinance)
    - cases (judgment / appeal / authoritative explanation)
    - revision events (promulgated / effective / pending)
                ↓ approved adapter (read-only)
TAI Shared Search / Canonical Knowledge Read (no competing Search SoT)
                ↓
Public Search / Canonical Details / Paid Diagnosis References / SaaS Context
```

**강제 경계**: 해당 법령군 대상 seed를 기존 LEG SCOPE_GATE_V2에서 읽고 manifest SHA로 동결. 외부 연계 대상은 relation pointer로 유지 가능하나 확대 법령 적용은 하지 않음. Source 레코드는 snapshot/current/rights/review/provenance/duplicate key로 관리. Knowledge Graph edge는 근거(Evidence)와 SOURCE_NATIVE/RULE 기반 승인상태를 가져야 한다. 데이터 공개·개인 사업장 검색 권한·법정 판단은 별도 승인/Consumer 계약.

**검색**: 기존 SearchDocument(`object_type/canonical_id/source_id/source_key/aliases/context/public_url/...`) 계약 재사용. 새 자료마다 새 검색 시스템 구축 금지. 현행 판례 849와 EXT-071 등 중복 검사 필수.

**SaaS**: 유료 고객의 회사·사업장·설비·공정·작업·화학물질 정보를 공개검색 인덱스에 합치지 않는다. private SaaS context request는 authorized consumer에서만 처리.

**개정 알림**: PENDING_REVIEW → HUMAN/LEG_VERIFY → APPROVED_EFFECTIVE_CHANGE → SaaS notice. 자동 점검의무 생성/처벌·주기 계산 금지.

**공개/권리**: 원문 제공 허용·저작권·가공 및 재배포 조건 API별 확인. 판례·결정례 개인정보/익명화 확인. 일반 검색결과는 noindex; 승인된 고유 상세페이지에만 canonical/SEO 판단.

## 5. 제품 활용 사례: 지게차

1. Public Search에서 '지게차'를 검색하면 승인된 검색사전과 용어↔조문 연결로 관련 조문·안전가이드·사고사례·행정해석·판례를 구분 표시한다.
2. 상세페이지에서는 '안전작업 위험', '관련 법령', '공식 해석', '관련 사고'를 출처·공표일 기준으로 보여준다. 해당 사업장에 의무가 적용된다고 주장하지 않는다.
3. Paid Diagnosis의 법령엔진이 지게차 작업 관련 의무를 **이미 판정했다면**, 사례·해석·위임 관계는 설명 자료로 표시한다.
4. SaaS의 설비/작업 컨텍스트에서 관련 지식을 제안하고 사용자가 점검·교육·작업지시 참조로 활용한다. 외부 판례 자체가 점검 주기/위험도를 결정하지 않는다.
5. 개정 이벤트는 LEG 담당자의 검토대상으로만 표시한다.

## 6. '전체 건수' 분모 설계

**데이터 수집 우선순위는 원천 전체 건수로 정하지 않는다.** Target별 아래 수치를 구분한다.

- `provider_total`: 조회 API가 제공한 전체 record 수 (첨부 현재 수치)
- `scope_match_preview`: 승인된 산업안전 법령·안전 관련 corpus 필터로 얻은 목록 수 (미확인)
- `unique_source_key_count`: 중복제거 가능한 원천 ID 수
- `detail_available_count`: 원문 상세 API 접근 성공 수
- `existing_tai_overlap_count`: 기존 849 판례/지식/경과 자료와 중복
- `net_new_publishable_count`: 권리·품질·현재성 검증 후 공개 가능한 순신규 자료 수
- `relation_edge_count`: 별도로 유의미한 법령/용어/조문 연결 건수 (문서 카운트와 다른 KPI)

`lsDelegated`, `lsRlt` 등 결과는 `provider_total` 없이도 서비스가치가 높다. 목록형이 아닌 API는 선택된 law ID로 fan-out 조회한다. 모든 명세에 `totalCnt`를 강제하지 않는다.

## 7. 실제 다음 WO (추천)

**WO-EXT036-SERVICE-CONTRACT-001 — 구현 전 검증/설계**

1. 업로드된 104 target matrix를 기준으로 P0 링크·변경과 P1 해석·판례·부처 자료에 대해 `목록 / 상세 / 관계 / 시계열`을 각각 계약검증한다.
2. 기존 LEG 18법령군/133개 법령 읽기전용 anchor와 scope manifest SHA 고정; 사업장 자동 적용 범위를 넓히지 않는다.
3. Current `tai-www`, `tai-api`, Knowledge Graph, Search Dictionary, Paid Diagnosis/SaaS consumer 구현현황을 **실제 main 코드**에서 조사하고 문서의 과거 갭과 혼동하지 않는다.
4. 5개 공개 사용자 질의와 5개 SaaS context 사례로 연결가능성을 QA 시나리오로 작성한다. 실패 케이스(오탐 조문, 과거 시행일, 유사단어, 기존 판례 중복)를 포함한다.
5. Source overlap·원천 PK·상세본문·인증·권리·수집량·쿼터 확인. 최소 Live Probe는 Owner 승인 전 미실행.
6. P0 우선 Collector + read adapter의 source-neutral 계약과 단계별 PR/DB/Deploy 승인 분리안을 제시. 기존 PRJ/45cm/LEG Freeze 변경 금지.

산출: `EXT036_P0_CONTRACT_EVIDENCE.md`, `EXT036_SERVICE_CONSUMER_GAP_MATRIX.csv`, `EXT036_NET_NEW_SCOPE_ESTIMATE.csv`, `EXT036_SOURCE_STORAGE_READ_MODEL_DESIGN.md`, `EXT036_PROBE_AUTHORIZATION_PROPOSAL.md`. 코드/DB write/probe 없음.

## 8. 새 우선순위 완료 기준

- P0의 성공: 133개 승인 법령 기준 `link/terms/change` **관계 수와 근거** 검증 + 3개 Consumer에서 실제로 유용한 read 계약 테스트.
- P1의 성공: 전체 건수 대비 산업안전 관련 정확도, 중복 제외 순신규, 상세/익명화/권리, 검색된 자료의 canonical detail과 문맥 노출.
- Public KPI: `결과 클릭률`, `관련자료 클릭률`, `상세→무료진단 진입률`, `미결과율` (GA4 테스트 트래픽 분리).
- SaaS KPI: `Context 추천 열람률`, `업무참고 전환율`, `잘못 연결된 자료 비율`, `검토 후 채택률`.
- LEG KPI: `연결 근거율`, `시행일 일치율`, `거짓 연결률`.

이번 문서는 데이터 **실수집/배포 승인 문서가 아니며**, 현행 Repo와 운영 DB에 대한 일괄 재검증 없이 '기능이 배포됨'을 확정하지 않는다.