# TAI 공통 안전정보 연결 매트릭스 — 외부 심층조사 및 조건부 상세설계 v2.1

- 문서 ID: `TAI-COMMON-SAFETY-RELATION-MATRIX-RESEARCH-DESIGN-20261012`
- 기준일: 2026-10-12 (Asia/Seoul)
- 상태: **외부 조사 완료 / GPT 분석·조건부 설계 / MX00 내부 실사 전 구현 계약 미확정**
- 상위 문서: `TAI_SAFETY_SEARCH_REBUILD_MASTER_PLAN_2026-10-12(2).md` — 원문 불변
- 상위 문서 SHA-256: `15b8d13a3cee91cddc7a68b9e7d9fc5e923471937f4bc892b321f23ca6ea552f`
- 기존 참고 설계: `TAI_SAFETY_SEARCH_MATRIX_REPLAN_V2_2026-10-12.md`; 본 문서는 그 목적·우선순위를 **사용자 승인 방향**으로 정정하는 별도 보완서 (원본 파일 편집 아님)
- 업무 분장: GPT=외부조사·분석·설계·작업지시·독립검증 / Claude Code=내부 실사·실행·증거 수집 / Owner=설계·병합·DB·운영 승인
- 무변경 선언: `MASTER_CHANGE=0`, `SOURCE_CHANGE=0`, `PRODUCTION_DB_WRITE=0`, `INDEX_WRITE=0`, `PR=NONE`, `DEPLOY=NONE`

---

## 0. Owner 확정 의도와 과거 제안의 교정

**사용자의 확정 의도:** TAI는 이미 섹션별 검색을 제공한다. 별도의 검색 서비스 또는 별도 고객용 신규 서비스를 만들려는 것이 아니다. **기존 수집자료가 서로 어떻게 연결되는지**를 공통 관계 정보로 관리하고, 통합검색·상세페이지·안전관리 SaaS·화학물질관리 등 **기존 화면**에서 같은 연결을 재사용한다. 관계 연결의 우선순위는 기존 사용자에게 실질적으로 유용한가로 결정한다. 구매자는 의사결정권자, 주요 실제 사용자는 안전관리 관계자이므로 자료 탐색·정리 비용 감소와 관리 업무 보조 가치에 초점을 맞춘다.

**정정 사항:** 이전 설계의 '검색 매트릭스 = 컨텍스트 × 콘텐츠유형을 검색 시점에 집계하는 동적 행렬'은 검색 구현의 **하위 기능**일 수 있지만, **제품 수준의 매트릭스 정의는 아니다**. 매트릭스의 제품 정체성은 `표준개념 ↔ 콘텐츠 ↔ 검증 가능한 직접관계`를 재사용하게 하는 **공통 관계 계층**이다. 검색어 건수표·개별 키워드 관계표·새 제품 모듈은 본질이 아니다.

**신규 자료 범위:** 2026-10-12에 API 3건이 추가되어 사건·사고 및 MSDS 내부 데이터에 병합되었다는 사용자 보고를 반영한다. **세 API의 이름, 실제 소스 키, 수집 완료율, 병합 방식(물리통합/논리통합), 중복정책은 내부 미검증**이다. 별도 검색 섹션이나 새 콘텐츠 유형으로 잘못 추가하지 않는다.

**미래 자료:** 체크리스트와 다이어그램은 확장 슬롯만 정의한다. 구현·출시 일정/독립 서비스는 확정하지 않는다.

## 1. 외부 근거 — 관찰한 사실과 TAI에 대한 추론 분리

| 구분 | 외부에서 확인되는 사실 (공식 출처) | TAI 설계 적용 권고 (추론) | 즉시 도입? |
|---|---|---|---|
| W3C SKOS | `prefLabel/altLabel`, `broader/narrower`, `related`, `exactMatch/closeMatch`는 서로 다른 의미를 가진 용어·개념 관계 | 한글/영문 표기 및 설비·작업·위험 요인을 표준 개념 ID로 분리, 관련어를 동의어로 남용 금지 | **개념모델 채택** |
| W3C PROV-O | `Entity`, `Activity`, `Agent`, `wasDerivedFrom` 등으로 데이터 계보 표현 | 새 API 원본레코드→기존 사고/MSDS canonical→색인·관계 assignment까지 계보 기록 | **원칙 채택** |
| W3C SHACL | RDF 그래프가 선언된 shapes 제약을 충족하는지 검증 | 관계 종류별 validator·반례 시험 작성; RDF 저장 자체는 강제하지 않음 | **검증 원칙 채택** |
| W3C DCAT 3 | 여러 데이터셋·데이터 서비스의 메타와 버전정보를 상호운용성 있게 표현 | 원천 API inventory / 갱신 주기·이용조건 모델 설계에 참고 | 문서/필드만 참조 |
| BLS OIICS 3.03 | 사고 사건/노출, 사고 원천/2차원천, 작업자 활동, 장소 등을 분리하는 분류 체계 | 사고 유형, 사고객체, 작업을 한 키워드로 뭉치지 않기 위한 crosswalk 연구 | 참고 분류체계 |
| NIOSH FACE | 사고조사에서 위험요인과 예방 권고를 제시하되 규정 위반/책임 판단과 구분 | 사고→관련자료 연결의 실무적 근거 수준 설계 | 사례 참고 |
| 건설안전 Linked Data 연구(2022) | 건설 관련 사고 200건을 온톨로지·RDF·SPARQL로 모델링·검색하는 시범 시스템 | 관계 분류의 근거는 있으나 상용 운영·실제 업무성과는 별도 입증 | 연구 참조 |
| PubChemRDF | compound(CID), substance(SID)를 별도 식별해 상호 관계 표현 | MSDS/KECO와 제품/물질/성분을 동일 엔터티로 합쳐버리지 않도록 경계 설정 | 모델 참고 |
| EU-OSHA OiRA | 현장 위험요인 확인→예방 활동→점검·보고로 이어지는 실무 워크플로 | **새 OiRA 같은 서비스를 만들지 말 것**; 기존 TAI 화면에서 실제로 필요한 자료 연결 사용사례 선정 | 업무 참고 |
| Skosmos(MIT) | SKOS 통제어휘 탐색 REST API와 UI, SPARQL 엔드포인트 기반 | 기존 TAI 사전이 부족하고 관리량이 커질 때만 고려 | 설치 보류 |
| Open Semantic Entity Search API | 온톨로지/사전·정규화 명칭을 이용한 개체 식별·연결; Solr 등 별도 의존 | 문서별 candidate detection 구현 아이디어 참고 | 직접 도입 보류 |
| OpenSearch Relevance Workbench | 3.1부터 query set, human judgment, 실험 평가 지원 | TAI 운영 버전 확인 후 참조. 3.1 미만이면 독립 골든셋 테스트로 대체 | 조건부 |
| OpenSearch `_msearch` | 여러 독립 검색을 HTTP 1회로 요청 가능; 물리 검색은 각각 실행 | 기존 랭킹/섹션 검색을 바꾸지 않고 필요한 컨텍스트 조회를 보조로 붙이는 POC | 조건부 |

### 1.1 외부 연구로부터 하지 말아야 할 오해

1. **SKOS `related` ≠ `altLabel` ≠ `exactMatch`**. '지게차-운반장비'는 상하위 범주가 될 수 있어도 동의어는 아니다. `closeMatch`는 전이 관계가 아니고 `exactMatch`는 전이 가능하므로 외부 코드 매핑을 과감하게 단정하면 큰 오염을 만든다.
2. **SHACL은 RDF 그래프 검증 표준**이다. 기존 SQL/JSON validator를 만들면 'SHACL의 검증 원칙 참고'이지 SHACL 호환 구현이라고 표시할 수 없다.
3. **OIICS는 미국 사고 분류**이다. 한국 원천 코드·KOSHA·CSI 사고 분류를 무검증 교체하지 않는다. 사고유형/원인/객체/작업을 분리하는 참고 구조에만 사용한다.
4. **PubChem CID/SID·CAS가 곧 MSDS 제품 동일성을 증명하지 않는다.** 제품·혼합물·성분·순물질, 판본/제조사를 분리한다.
5. 외부 Knowledge Graph 논문은 연결·검색 가능성의 근거다. TAI에 Neo4j 등 새 Graph DB가 필요하다는 증거가 아니다.
6. OpenSearch 고도화·의미검색·LLM은 **관련 후보 탐색**을 개선할 수 있으나 법적 적용·원인·예방조치 적합성을 확정하지 못한다.

## 2. TAI 적합성 비교 — 사용효과와 변경 위험 기준

평가 척도: `상`/`중`/`하`는 **GPT의 정성적 설계 판단**이며 실측 성능·비용이 아니다.

| 접근 | 기존 인프라 재사용 | 자료 연결 신뢰성 | 신규 원천 확장성 | 운영부담 | 판단 |
|---|---|---|---|---|---|
| A. OpenSearch 검색만으로 연관 추정 | 상 | 하~중 | 상 | 낮음 | **단독으로 불충분**. 검색 결과=의미관계가 아님 |
| B. 키워드마다 문서×문서 수작업 매트릭스 | 중 | 중~상(수동 검증 시) | 하 | 매우 높음 | **기본안 제외**, 일부 검증 링크에만 수작업 |
| C. **기존 검색 + 표준 개념 + 문서별 근거 + 직접링크** | **상** | **상 가능(검증 준수 시)** | **상** | 중 | **우선 POC** |
| D. 별도 RDF/Neo4j 전체 KG 이전 | 중~하 | 구조만으로 정확도 확보 안 됨 | 중~상 | 높음 | **도입 보류**. 필요한 질의가 실제로 기존 SQL/OS로 안 되는지 먼저 입증 |
| E. 벡터·LLM 자동 연결 중심 | 중 | 가변/미검증 | 상 | 중~높음 | 후보 추천 연구용, 확정관계/법적 판단 불가 |

**권장 선택:** C를 목표 계약 후보로 한다. 기존 Knowledge Graph의 11,776개 테스트 관계는 **회귀 비교 기준선**이지 운영 SoT도 정답셋도 아니다. A와 C를 동일 사용 사례에서 비교하여 **추가 가치가 관측될 때만** C의 하위 기능을 확장한다.

## 3. 공통 관계 매트릭스의 대상과 재사용 소비자

```text
[기존 SoT: 사고 / MSDS·KECO / 가이드 / 안전자료 / 법령 / 지식 / 서식 / 판례]
                            │  기존 수집·통합 파이프라인 유지
              [원천 레코드와 canonical 식별자]
                            │
        [문서별 표준 개념 부여] + [직접관계 검증] + [원천 계보]
                            │
               [공통 안전정보 관계 조회 계층]
                            │
       ┌────────────────────┼────────────────────┐
   기존 통합검색         기존 상세페이지         기존 SaaS 화면
       └────────────────────┬────────────────────┘
                  기존 API/검색과 공존
```

*기존 OpenSearch는 문서 검색과 필터링을 계속 담당한다.* 관계 계층은 필요할 때 `context_ids` 또는 문서 canonical ID로 **관련 자료를 조회**할 수 있도록 지원한다. 별도 이용자 대상 상품, 신규 검색결과 섹션, 전체 검색 교체는 만들지 않는다. 새로운 내부 엔드포인트가 필요하더라도 기존 공용 백엔드 소비자 재사용 및 하위호환 검증 뒤 결정한다.

### 3.1 최소 의미 모델 (논리모델; 신규 DB 테이블 지시 아님)

| 엔터티 | 핵심 식별/속성 후보 | 주의 |
|---|---|---|
| `SourceRecord` | `source_id`, `source_record_id`, 원천 버전/해시/갱신일 | 병합된 신규 3 API 원본도 **원천별로 보존** |
| `CanonicalContent` | 기존 `object_type`, `canonical_id`, 공개상태, 판본, URL | 원천 레코드와 1:1이라 단정하지 않음 |
| `Concept` | 안정적인 `concept_id`, `scheme`, `pref_label`, `alt_labels`, `type`, `version` | 동음이의·동의어·관련어 별도 정의 |
| `Annotation` | `canonical_id`, `concept_id`, `role`, `evidence`, `rule_version`, `review_state` | 직접 주제/본문 언급 분리 |
| `VerifiedRelation` | `source_ref`, `target_ref`, `relation_type`, `evidence_ref`, `version`, `status` | 직접 ID/명시적 인용에만 확정 관계 |
| `SourceLineage` | 원천→정규화→canonical→관계/색인 파생, sync 실행ID | PROV 철학에 따른 출처·처리흐름 |

**관계 종류 및 레인(제안):**

- `MENTIONS`: 본문에 단어가 등장 — 일반 검색용, 관련자료 확정 아님.
- `ABOUT_CONTEXT`: 문서의 주요/보조 대상을 정형 필드·승인 규칙으로 확인 — 문맥상 관련자료.
- `REFERENCES_DOCUMENT`: 정확히 확인된 가이드·서식·문서 ID 인용 — 직접관계.
- `REFERENCES_LEGAL`: **governance RPC의 법령 canonical/version**과 조문번호까지 확인된 인용 — 참고조문 연결, 법적 적용 판정 아님.
- `VERSION_OF`/`DERIVED_FROM`: 공식 판본·원천에서 추적할 수 있는 관계.
- `SAME_SOURCE_OBJECT`: 원천 식별자·판본·동등성을 검증한 중복/원천 병합 관계. 같은 제목은 근거가 아님.
- `MATERIAL_IDENTIFICATION`: 제품·혼합물·물질·성분 중 **어떤 대상끼리** 연결되는지 명시한 관계. 'CAS 같음 = 모든 MSDS 동일'은 금지.
- `CANDIDATE_RELATED`: 용어/임베딩/LLM 기반 후보, 검토 전 공개에서 확정된 연결로 표시하지 않음.

`APPROVED` 관계만 공개 가능한 것은 아니다. 별도로 **참조 콘텐츠의 공개권한, 원천 라이선스, 현재 판본, stale 여부**를 함께 검사해야 한다.

### 3.2 역할이 다른 관계를 구분하는 예시

| 검색·대상 | 관계 판정 | 표시/재사용 가능성 |
|---|---|---|
| `지게차` ↔ `포크리프트` | 승인된 동의어/표기변형 | 같은 `equipment` 개념으로 검색 확장 가능 |
| 지게차 ↔ 운반장비 | 범주 관계 (`broader` 후보) | 사용자가 넓히는 탐색에만; 완전 동의어 아님 |
| 지게차 사고 ↔ 사고객체=지게차 | 원천 분류 근거 `ABOUT_CONTEXT` | 관련 사고사례 탐색 |
| 지게차 가이드 ↔ 지게차 | 원본 지침 대상 확인 시 `ABOUT_CONTEXT` | 상세페이지·SaaS 참고자료 |
| 지게차 ↔ 임의 연료/배터리 MSDS | **관계 미확인** | 자동 확정 연결 금지 |
| 사고 ↔ 예방조치 가이드 | 사고·가이드 모두 같은 컨텍스트라는 것만으로 인과/적합성 확정 불가 | '동일 주제 자료' 또는 인용 확인 시 '참조자료' |
| 특정 MSDS ↔ KECO | 식별된 **순물질/성분/제품**과 식별자 일치 수준을 검증 | 화학정보 연결, 규제대상 판정은 하지 않음 |
| 법령 조문 ↔ 가이드 | 정확한 조문/version 인용 근거 | `참고 조문`으로만 사용, 적용 의무 판단 금지 |

## 4. 활용 우선순위 — 새 서비스가 아니라 기존 화면의 연결 효과

순위 기준은 (1) 안전관리자에게 실제로 필요한 탐색, (2) 통합검색·상세페이지·SaaS의 다중 재사용, (3) 확보된 원천 근거·검증 가능성, (4) 유지보수/오연결 위험이다. 초기 판단으로만 사용하고 MX00 실제 필드를 확인해 재평가한다.

| 우선순위 | 연결을 우선 구현할 대상 | 쓰이는 기존 위치 | 즉시 검증할 사용자 과업 | 확인할 가치 지표 |
|---|---|---|---|---|
| **P1-A** | 설비·작업·위험 ↔ 사고사례·가이드·안전자료 | 통합검색, 사고/가이드 상세, 설비·작업 SaaS | 지게차 작업 전 동일 장비 사고·관련 예방자료 찾기 | 적합 자료 확보 시간, 오연결, 재탐색 감소 |
| **P1-B** | 등록 물질/제품 ↔ 기존 MSDS와 병합 API, KECO 정보 | MSDS 상세, 화학물질관리 화면, 통합검색 | 동일 제품의 MSDS·관련 물질 정보·규제 원문 찾아 비교하기 | 동일성 오류, 확인 시간, 출처 누락 |
| **P1-C** | 사고유형·사고객체·작업 ↔ 다른 사고·교육용 참고자료 | 기존 사고 상세, 통합검색, 안전관리 화면 | 유사사고 교육자료 모으기 | 적합 사고 비율, 유형혼동 감소 |
| **P2** | 정확한 법령 인용 ↔ 가이드·지식·서식 | 법령 상세, 관련자료 패널, 진단 결과의 참고정보 | 조문을 확인하고 인용된 가이드·자료 찾기 | 잘못된 조문/판본 링크 0 |
| **FUTURE** | 체크리스트·다이어그램 ↔ 동일 컨텍스트 | 기존 검색/상세/SaaS의 연관자료 | 해당 콘텐츠가 확보된 이후에만 정의 | 새 유형 추가 시 기존 관계 서비스 수정 범위 |

**구매자에게 설명 가능한 가치는 '자료 검색 건수'가 아니라 과업의 시간 절감과 정보 근거의 가시성이다.** 작업안전/법적 준수 향상 등 큰 결과는 임상적·법적 수준의 증거 없이 효과로 단정하지 않는다.

## 5. 오늘 추가된 3개 API 병합을 다루는 설계 제한

- 사용자 보고를 존중하여 **사건·사고와 MSDS 기존 유형에 통합된 입력**으로 다룬다. 새로운 원천이 추가되었다고 신규 섹션을 3개 만들지 않는다.
- 원천 레코드(`source_id + source_record_id + source_version`)와 canonical 콘텐츠를 분리해서 보존할 수 있는지 확인한다.
- 동일 사고로 판단한 근거가 `공식 사건번호`, `고유 원천 ID`, `검증된 cross-source ID`인지, 단순 제목·날짜 유사성인지 구분한다.
- MSDS는 회사의 제품별 문서/버전, 순물질/성분, 혼합물의 관계를 분리한다. CAS 또는 물질명만으로 문서를 병합하지 않는다.
- 사건·MSDS의 기존 canonical URL을 바꾸지 않고 기존 공개 권한을 승계해야 한다. `LINK_ONLY` 저작권, 비공개, 원문 충돌을 별도 검사한다.
- 삭제·공개상태 변경·원본 개정이 생기면 관계 `STALE/REJECTED`, 색인 제외/갱신 처리가 따라와야 한다. 속도 SLA와 현재 자동갱신 구현 여부는 MX00에서 확인한다.

## 6. 기존 시스템에 연결되는 최소 계약 (조건부, API/DB 미구현)

입력은 기존 canonical 콘텐츠/표준 개념 ID 중 하나이고, 반환값은 기존 검색 결과 타입을 바꾸지 않는 **부가 정보 계약**으로 설계한다. **경로·스키마 명칭은 후보**다.

```json
{
  "reference": {"object_type": "CSI_ACCIDENT", "canonical_id": "<existing-id>"},
  "groups": [
    {
      "group": "GUIDE",
      "items": [
        {
          "object_type": "GUIDE",
          "canonical_id": "<existing-id>",
          "public_url": "<existing-url>",
          "reason_type": "SHARED_APPROVED_CONTEXT",
          "reason_label": "동일 설비 주제의 안전가이드",
          "context_ids": ["equipment:forklift"],
          "relation_status": "CONTEXT_RELATED",
          "source_name": "<verified-source>",
          "source_version": "<verified-version>"
        }
      ]
    }
  ],
  "data_as_of": "<last-verified-at>",
  "limitations": ["REFERENCE_INFORMATION_ONLY"]
}
```

**필수 제약:**
1. OpenSearch 기존 `SearchResult`와 섹션별 검색·관련성 랭킹·공개/유료/SaaS 소비자 호환성 유지.
2. 내부 사용자·고객사 권한이 섞이지 않도록 관계 조회도 기존 공개정책과 tenant isolation 확인.
3. `SAME_CANONICAL`과 `SHARED_CONTEXT`와 `VERIFIED_CITATION`을 **분명히 분리**. 후보 관계는 확정 레일로 유입 금지.
4. 관계 근거가 없으면 **연결 없음/관련 주제 없음**으로 표시한다. 자료를 반드시 억지로 추천하지 않는다.
5. 집계가 필요하면 기존 OpenSearch의 조건부 집계 사용. 기존 검색결과를 다시 만드는 새 검색서비스는 범위 밖.
6. 검색 데이터 변경 시 파생 관계만 재계산하고 증거/규칙 버전을 추적할 수 있어야 한다. 실제 처리 위치는 현행 pipeline 조사 후 확정.

## 7. 작업 흐름과 성능/정확도 수용 게이트

### 7.1 공개용 관계로 승격할 수 있는 경로

```text
원천/원본 ID 확인
  → 정규화 필드로 개념 후보 탐지
  → 동의어·사고코드·화학ID·직접인용 검증
  → relation evidence + source/version 상태 확인
  → 공개정책/저작권/권한 검증
  → 기존 API에서 조회 가능한 관계로 노출
```

자동 규칙은 기계적으로 반복 가능한 경우에만 자동 승격한다. 텍스트만 기반으로 한 LLM 후보는 검토 전 `CANDIDATE`로 둔다. 검증 실패는 자료 자체를 삭제하라는 뜻이 아니라 잘못된 **연결**을 공개하지 말라는 뜻이다.

### 7.2 단계별 검증용 골든셋 (예시, 아직 데이터셋 미작성)

| 단계 | 최소 시나리오 | 평가 |
|---|---|---|
| 사고·설비 | 지게차 사고, 비계 추락, 굴착 붕괴, 용접 화재 | 사고객체/위험유형/작업 주제 정확 구분 |
| 화학 | 톨루엔 CAS, 이명·영문명, 다른 제조사 혼합제품, KECO 원천 불일치 | 제품·성분 동일성 오연결 0 |
| 법령 | 정확 인용이 있는 조문, 판본 변경, 단순 '법' 언급 | 직접 인용 오연결 0, 의무판정 금지 |
| 신규 API | 원천 3건의 대표 신규/중복/충돌/삭제/권리 변경 샘플 | 기존 canonical ID와 출처 일치, stale 처리 |
| 기존 경험 | 기존 top 결과, 검색 품질, 관련자료 클릭 | 기존 직접 검색 회귀 없음; 연관자료의 추가효용 입증 |

**필수 안전 게이트:** 법령 조문/제품-물질/판본의 위험한 확정 관계 오연결 **골든셋 0건**, 비공개·권리위반 노출 0건, 기존 법령엔진 판단 필드/결과 변경 0건, 기존 검색 중요 결과 유실 0건. 실제 표본 규모·통과 임계치·성능 p95는 MX00 baseline 후 Owner 승인.

**가치 평가:** 동일한 사용자 과업을 `현행 검색`과 `현행 검색+관계` 두 조건으로 수행한 뒤, 자료를 모으는 시간·정답 콘텐츠 비율·근거 누락률·실수 유형·내부 다음 클릭을 비교한다. 비교 집단/실제 시험 규모는 추후 합의한다. 실매출 증가나 안전사고 감소를 보장하지 않는다.

## 8. 확장 인터페이스 — 체크리스트·다이어그램 (일정 미정)

- 기존 콘텐츠 계약을 유지하되 미래 `content_type`을 등록할 때 필요한 최소 속성(`canonical_id`, `source_id`, `version`, `visibility`, `context_ids`, `related_reason`, `public_url` 또는 접근 경로)을 **설계 원칙으로만** 예약한다.
- 체크리스트가 법령 의무/필수 점검에 해당한다고 자동 표시하지 않는다.
- 다이어그램은 안전자료/저작물 이용권·원본 ID·버전·설명 텍스트와 함께 관계를 관리한다.
- 지금 신규 콘텐츠 제작, 추출 모델, 전용 뷰어, 신규 화면 구현은 착수하지 않는다.

## 9. 기술 도입 결정의 권한·가역성

| 항목 | 현재 권고 | 다음 승인 선행조건 |
|---|---|---|
| 기존 섹션별 검색 | **유지** | 신규 관계 기능이 품질/성능 회귀를 유발하지 않음 |
| 기존 Graph 11,776 | **읽기전용 기준선** | 현재 수치 재실측, 신구 ID 매핑, false-positive 샘플 |
| SKOS/PROV 개념 | **논리계약에 반영** | 기존 사전/원천 컬럼의 역할과 중복 여부 조사 |
| 기존 Supabase·OpenSearch | **재사용 우선** | 기존 dictionary/edges/read API/index materialization 동작 조사 |
| Skosmos / Graph DB | **보류** | 기존 스택으로 필요한 질의를 수행할 수 없다는 증거 |
| Search Relevance Workbench | **조건부** | OpenSearch 버전 3.1+와 설치 정책 검증; 미지원이면 독립 평가 fixture |
| 임베딩/LLM 자동 연결 | **후순위 실험** | 실무 가치/오연결 비용을 확인한 뒤 분리 승인 |
| 신규 DB/RPC/API write | **미승인** | MX00 증거 → GPT 설계 적합성 판정 → Owner 개별 승인 |

## 10. MX00 READONLY 내부 실사 후 GPT 최종 설계에서 확정할 것

1. 오늘의 3개 API의 **정확한 이름·source_id·원본 ID·최종 병합 위치·색인 상태** (현재 미확정).
2. 현재 기존 사전/Subject dictionary/객체 코드/관계 테이블의 재사용 가능성, 새 컨텍스트 사전이 정말 필요한지.
3. 관계 등록이 **원본 DB, 기존 Graph, 어댑터, 파생 OpenSearch** 중 어디에 이미 존재하는지; 중복 방지.
4. 현재 `knowledge_relation_edges` 및 `knowledge_relation_evidence`와 공개 Graph API의 실제 조회·업데이트·권한 계약.
5. 실제 관계 조회 대상 3곳 이상(검색 상세, 안전관리 SaaS, 화학물질관리)의 호출 구조·tenant/public 권한.
6. 3개 사용자 과업을 **기존 검색만으로 해결 가능한 부분**과 매트릭스가 실제 가치를 추가하는 부분으로 구분.
7. 현행 OpenSearch 버전/상태/성능 및 신규 기능 도입 필요성 (검색 전체 리빌드 제외).
8. 법령 SoT: **Supabase 45cm-prj-db `governance` RPC**만 권위; D1에서 법령 데이터 검색 금지. `GOVERNANCE_SOURCE_OF_TRUTH.md` 확인.

### 10.1 단계 판단

- `MX00` = 관찰·증거 확보; 새로운 스키마·구현 **0**.
- `GPT MX00 INDEPENDENT REVIEW` = 현재 자산만으로 지원 가능한 범위 / 갭 / 비용·리스크 분석.
- `MX01 DESIGN FREEZE` = 개념 사전·관계 타입·증거검증·소비 API·골든셋·확장 계약 최종화, **Owner 승인**.
- `MX03 ISOLATED POC` = 기존 검색과 관계 조회의 비교, 허가된 격리 환경에서만 실행.
- 구현/PR/운영변경 단계는 마스터플랜 WP00~09의 기존 승인 규칙을 그대로 따른다.

---

## 11. 외부 공식 근거 및 오픈소스 링크 (2026-10-12 확인)

1. W3C SKOS Reference: https://www.w3.org/TR/skos-reference/  (특히 §5, §8, §10)
2. W3C PROV-O / PROV overview: https://www.w3.org/TR/prov-o/ ; https://www.w3.org/TR/prov-overview/
3. W3C SHACL: https://www.w3.org/TR/shacl/
4. W3C DCAT 3: https://www.w3.org/TR/vocab-dcat-3/
5. BLS OIICS 3.03: https://www.bls.gov/iif/definitions/occupational-injuries-and-illnesses-classification-manual.htm
6. NIOSH FACE: https://www.cdc.gov/niosh/face/about/index.html
7. Data-Driven Construction Safety Information Sharing (2022): https://pmc.ncbi.nlm.nih.gov/articles/PMC8776242/
8. EU-OSHA OiRA: https://osha.europa.eu/en/tools-and-resources/oira
9. PubChemRDF: https://pubchem.ncbi.nlm.nih.gov/docs/rdf
10. Skosmos (MIT, SKOS vocabulary browser): https://github.com/NatLibFi/Skosmos
11. Open Semantic Entity Search: https://github.com/opensemanticsearch/open-semantic-entity-search-api
12. OpenSearch Relevance Workbench (3.1+): https://docs.opensearch.org/latest/search-plugins/search-relevance/using-search-relevance-workbench/
13. OpenSearch `_msearch`: https://docs.opensearch.org/latest/api-reference/search-apis/multi-search/
14. OpenSearch nested queries: https://docs.opensearch.org/latest/query-dsl/joining/nested/
15. 한국 건설안전 KG/RAG 선행 GitHub: https://github.com/juuuungwon/LMs_ConstructionSafety (코드·학습자료 권리 검토 전 상용 재사용 금지)

**근거의 한계:** 표준이 원칙·기술 가능성을 지지하는 것이지 TAI DB와의 적용 적합성을 직접 증명하지는 않는다. 외부 GitHub OSS 코드/학습데이터의 라이선스와 법적 재사용 가능성은 별도 검토 전 미확정. 국내 법령 적용 여부는 이 문서의 설계 대상이 아니다.

## 최종 상태

```text
DESIGN_INTENT                = OWNER_APPROVED (공통 연결·기존 재사용·실무 활용)
EXTERNAL_STANDARD_REVIEW     = COMPLETED
ARCHITECTURE                = CANDIDATE ONLY
MASTER_PLAN_SHA256          = 15b8d13a3cee91cddc7a68b9e7d9fc5e923471937f4bc892b321f23ca6ea552f
EXISTING_SECTION_SEARCH     = PRESERVE
THREE_API_IDENTITIES        = UNVERIFIED
EXISTING_ASSET_REUSE        = PENDING_MX00
NEW_SERVICE                 = NO
NEW_GRAPH_DB                = NO_APPROVAL
PRODUCTION_WRITE            = 0
NEXT_GATE                   = MX00 READONLY INVENTORY -> GPT INDEPENDENT REVIEW
```
