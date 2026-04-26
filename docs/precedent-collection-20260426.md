# 판례 수집 작업 보고서 (2026-04-26)

**작업일**: 2026-04-26  
**작업자**: 심태왕 대표 + Claude 기획창  

---

## 1. 판례 테이블 설계

### 1.1 기존 테이블 변형
- `industrial_accident_precedents`: 기존 17컬럼 + 신규 16컬럼 = 33컬럼
- 추가 컬럼: case_type, prec_seq, accident_type, equipment_type, death_count, injury_count, defendant_type, sentence_type, sentence_detail, fine_amount, corporate_fine, industry_name, worker_count_range, violation_types, violation_summary, condition_codes, ai_tagged_at, ai_confidence, is_active, judicial_summary, violation_laws_raw

### 1.2 연결 테이블 신규
- `precedent_rule_links`: 판례 ↔ master rule M:N 연결
- UNIQUE(precedent_id, rule_id), relevance_score, link_type

---

## 2. 판례 수집 — 법제처 API

### 2.1 API 접근 이슈
- Railway IP → 법제처 차단
- Supabase Edge Function → 법제처 차단 (IP 미등록)
- Edge Function IP 비고정 (13.124.84.86 → 3.34.129.120 변동)
- **해결**: Mac에서 직접 호출 (대표님 IP가 법제처에 등록됨)

### 2.2 1차 수집 — 법령명 광범위 검색 (폐기)
- 방식: "산업안전보건법" 등 법령명으로 전체 검색
- 결과: 602건 수집
- **문제**: master rule과 매칭 안 되는 데이터 다수
- **대표님 지적**: "수집이 목적이 아니라 매칭이 목적. master rule 기준으로 검색해야"
- 602건 전량 삭제

### 2.3 2차 수집 — master 기반 참조조문 검색 (채택)
- 방식: master의 (법령명 + 제N조) → 법제처 참조조문 검색(search=3)
- 수집 = 매칭. 검색 시 rule_id 자동 연결
- 스크립트: `scripts/collect_precedents_matched.py`
- endpoint: `GET /precedents/master-keys` + `POST /precedents/save-matched`

**1차 실행 (모법만, 172키):**
- 결과: 543건 검색, 375건 저장, 726건 rule 연결

**2차 실행 (시행령/시행규칙 포함, 439키):**
- 결과: 1,276건 검색, 833건 저장, 1,165건 rule 연결

### 2.4 추가 수집 — 방향 2 + 방향 3

**방향 3: 기준규칙 조문별 직접 검색**
- 스크립트: `scripts/collect_prec_standard_rules.py`
- 대상: 산안기준규칙, 위험물법, 승강기법 등 8개 법령
- 결과: 81건 검색, 48건 저장, **0건 rule 연결**
- 원인: 48건은 이미 1차에서 수집+매칭됨 (중복)

**방향 2: 사건명 검색 (search=1)**
- 스크립트: `scripts/collect_prec_casename.py`
- 대상: 중대재해처벌법, 전기안전관리법 등 15개 키워드
- 결과: 34건 검색, 33건 저장, 170건 rule 연결
- 미검색: 전기사업법, 주택법, 재난안전법, 파견근로자법 (master-keys에 없음)

---

## 3. 최종 판례 현황

| 지표 | 값 |
|---|---|
| 총 판례 | **849건** |
| rule 연결 | **2,139건** |
| 매칭된 rule | **336 / 3,820 (8.8%)** |

### 매칭률 분석 (벌칙 유형별)

| 벌칙 유형 | rule 수 | 매칭 | 매칭률 |
|---|---|---|---|
| 형사 (금고/징역) | 327 | 56 | 17.1% |
| 벌금 | 170 | 30 | 17.6% |
| 과태료 | 1,834 | 152 | 8.3% |
| 벌칙 없음 | 556 | 3 | 0.5% |

---

## 4. 미완료 — KOSHA 재해사례 수집

### 4.1 배경
- 대표님 지적: "과태료 등 법원까지 안 가는 건에 대한 데이터가 필요"
- KOSHA 재해사례 = 실제 사고 사례 (재해유형, 기인물, 원인분석, 대책)
- 과태료 rule 1,834건과 매칭 가능

### 4.2 API 정보
- 공공데이터포털: https://www.data.go.kr/data/15121001/openapi.do
- Base URL: `apis.data.go.kr/B552468/disaster_api02`
- Endpoint: `GET /getdisaster_api02`
- 파라미터: ServiceKey, business(게시판 종류), keyword(제목), callApiId(고정값), pageNo, numOfRows

### 4.3 이슈 (미해결)
- data.go.kr ServiceKey 발급 + 활용신청 완료
- Railway 환경변수 `DATA_GO_KR_SERVICE_KEY` 등록 완료
- **API 테스트 실패**: HTTP 401 Unauthorized
- 이전 시도: 잘못된 URL(`B550064/domesticCaseBoardService`) → HTTP 500
- 올바른 URL(`B552468/disaster_api02`) 확인 후 → HTTP 401
- KOSHA 참고 홈페이지(`kosha.or.kr/kosha/data/machine.do`) → 404 (사이트 리뉴얼)
- **다음 행동**: 활용가이드(docx) 다운로드하여 정확한 호출 예시 확인 필요

---

## 5. 미완료 — 참조조문 파싱 (방향 1)

### 5.1 배경
- 849건 판례 중 627건에 `violation_laws_raw`(참조조문) 있음
- 참조조문에 시행령(233건), 시행규칙(101건), 기준(366건) 조문 포함
- 파싱하면 API 호출 0으로 rule 매칭 대폭 확대

### 5.2 상태
- 수집 완료 후 마지막에 진행 예정
- Railway endpoint 또는 DB 직접 처리

---

## 6. 보안 이슈

### INTERNAL_API_SECRET 노출
- 채팅 히스토리에 시크릿 키 2회 노출됨
- `3fc675597aa05f08685f63e2beb04cf7a08fc432248016b1c2520779f59bd0be`
- `env | grep` 실행 시 전체 환경변수 출력으로 노출
- **조치 필요**: Railway에서 INTERNAL_API_SECRET 재발급(rotate) **강력 권장**

---

## 7. 배포된 버전

| 파일 | 버전 | 커밋 | 내용 |
|---|---|---|---|
| `routers/precedent_api.py` | v1.7.2 | `cfddbfc` | master-keys + save-matched + 시행령 포함 |
| `services/safe_db_update.py` | v1.0.0 | `7a0d988` | 필드별 개별 UPDATE |
| `scripts/collect_precedents_matched.py` | - | `1eee07a` | master 기반 판례 수집 |
| `scripts/collect_prec_standard_rules.py` | - | `58eb41f` | 기준규칙 조문별 수집 |
| `scripts/collect_prec_casename.py` | - | `58eb41f` | 사건명 검색 수집 |

### DDL Migrations
- `precedent_table_upgrade_and_link`: 16컬럼 추가 + precedent_rule_links 생성
- `precedent_add_case_type_and_prec_seq`: case_type, prec_seq, judicial_summary, violation_laws_raw 추가

### Edge Functions
- `precedent-search` (v3): 법제처 판례 API 테스트 (IP 비고정 문제로 사용 불가)
- `check-ip` (v1): Supabase Edge Function outbound IP 확인
