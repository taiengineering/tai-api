# 판례 수집 + 과태료 보강 작업 보고서 (2026-04-26)

**작업일**: 2026-04-26 (전일)  
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
- **수집 = 매칭.** 검색 시 rule_id 자동 연결
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
- 결과: 81건 검색, 48건 저장, **0건 rule 연결** (이미 매칭됨)

**방향 2: 사건명 검색 (search=1)**
- 스크립트: `scripts/collect_prec_casename.py`
- 대상: 중대재해처벌법, 전기안전관리법 등 15개 키워드
- 결과: 34건 검색, 33건 저장, 170건 rule 연결

### 2.5 참조조문 파싱 — 매칭 확대 (방향 1, 완료)

기존 849건 판례의 `violation_laws_raw`(참조조문 텍스트)에서 시행령/시행규칙 조문을 추출하여 master rule과 추가 매칭.

- **API 호출 0**, DB SQL 작업만으로 처리
- 634건 판례에 참조조문 있음 → 5,820개 "법령명 제N조" 패턴 추출
- master rule과 JOIN → **358건 신규 연결** (link_type='ref_article', relevance_score=85)
- 매칭 rule: 336 → **448** (+112, +33%)

---

## 3. 판례 최종 현황

| 지표 | 값 |
|---|---|
| 총 판례 | **849건** |
| rule 연결 | **2,497건** |
| 매칭된 rule | **448 / 3,820 (11.7%)** |

### link_type 분포
- `violation`: 2,139건 (직접 검색 매칭, relevance=90)
- `ref_article`: 358건 (참조조문 파싱 매칭, relevance=85)

### 매칭률 분석 (벌칙 유형별)

| 벌칙 유형 | rule 수 | 매칭 | 매칭률 |
|---|---|---|---|
| 형사 (금고/징역) | 327 | 56 | 17.1% |
| 벌금 | 170 | 30 | 17.6% |
| 과태료 | 1,834 | 152 | 8.3% |
| 벌칙 없음 | 556 | 3 | 0.5% |

**구조적 한계**: 과태료(1,834건)는 법원까지 안 가므로 판례 자체가 적음. NFTC(665건)는 판례에서 직접 인용 안 됨.

---

## 4. penalty 데이터 보강

### 4.1 penalty_summary 100% 달성

| 단계 | 작업 | 건수 |
|---|---|---|
| 기존 | Sonnet reparse | 3,264건 (85%) |
| SQL 추가 | "해당없음" → penalty_value=0 | +276건 |
| SQL 추가 | NFTC/NFPC → "소방시설법에 따른 과태료 부과 가능" | +259건 |
| SQL 추가 | 고시/기준 → "기준 위반 시 관련 법령에 따른 행정처분 대상" | +67건 |
| SQL 추가 | 시행규칙 → 모법별 벌칙 참조 텍스트 | +219건 |
| **최종** | | **3,820/3,820 (100%)** |

### 4.2 penalty_value 텍스트 추출

penalty_summary 텍스트에서 금액을 추출하여 penalty_value 채움:
- "300만원 이하 과태료" → 3,000,000
- "3천만원 이하 벌금" → 30,000,000
- "1억원 이하 벌금" → 100,000,000

SQL regex 추출 + Sonnet reparse(500건) 병행.

### 4.3 penalty_value 원 단위 통일

**발견된 문제**: Sonnet이 채운 건은 원 단위(3000000), SQL 추출 건은 만원 단위(300) — 혼재.

**수정 내역**:

| 단계 | 작업 | 건수 |
|---|---|---|
| Step 1 | 만원 단위(1~10000) 중 summary에 "만원" 있는 건 → ×10000 | ~68건 |
| Step 2 | 징역 년수 오입력(1~20, "만원" 없음) → NULL | ~5건 |
| Step 3 | 극단값("10억원"인데 100억 입력) → 재추출 | ~3건 |
| Step 4 | summary "해당없음"인데 value>0 → 0으로 | 13건 |

### 4.4 penalty 최종 현황

| 상태 | 건수 | 비율 |
|---|---|---|
| **penalty_summary 있음** | **3,820** | **100%** |
| penalty_value > 0 (원 단위 금액) | 2,488 | 65.1% |
| penalty_value = 0 (벌칙 없음 확인) | 371 | 9.7% |
| penalty_value NULL (금액 미정) | 957 | 25.1% |

**penalty_value NULL 957건**: 법령 원문에 구체적 금액이 없는 건. penalty_summary 텍스트("과태료 부과 가능" 등)로 대체 표시.

---

## 5. 무결성 검증 (완료)

### 5.1 판례 데이터
| 검증 | 결과 |
|---|---|
| prec_seq 중복 | 0건 ✅ |
| 필수필드 NULL (case_number, prec_seq, source_url, decision_date, case_name) | 0건 ✅ |

### 5.2 판례-rule 연결
| 검증 | 결과 |
|---|---|
| 중복 연결 (precedent_id+rule_id) | 0건 ✅ |
| 고아 링크 (판례 없음) | 0건 ✅ |
| 고아 링크 (rule 비활성) | 0건 ✅ |
| 연결 없는 판례 | 0건 ✅ |

### 5.3 penalty 데이터
| 검증 | 결과 |
|---|---|
| penalty_summary 채움률 | 100% ✅ |
| 비정상 값 (1~9999) | 0건 ✅ |
| 불일치 (value>0 + summary="해당없음") | 0건 ✅ |
| 단위 혼재 | 해소 ✅ (원 단위 통일) |

---

## 6. 고용노동부 과태료 데이터 조사

### 6.1 data.go.kr 파일 3종 분석

| # | 데이터셋 | 핵심 필드 | master 매칭 |
|---|---|---|---|
| 1 | 조항별 과태료 부과 건수 (CSV) | 위반법령, 위반법조항, 건수 (2019~2023) | ✅ 직접 매칭 |
| 2 | 과태료 부과내역 (CSV) | 과태료결정금액, 합계금액 | ❌ 법조항 없음 |
| 3 | 근로자 과태료 기준코드 (CSV) | 위반내용, 과태료금액 | △ 근로자 과태료 (사업주 아님) |

### 6.2 결론 — 대표님 지적
"나한테 과태료 얼마"의 답은 외부 데이터 수집이 아니라 **master의 penalty_value를 채우는 것**.
- 파일 1(건수): 보조 정보 (실제 부과 건수)
- 파일 2(금액): 법조항 없어서 매칭 불가
- 파일 3(기준코드): 근로자 과태료 (EUC-KR 인코딩)
- **행동**: penalty_value 채움률 향상에 집중 → 65% → 원 단위 통일 완료

---

## 7. KOSHA 재해사례 조사

### 7.1 KOSHA 웹사이트 현황
- 기존 URL (`kosha.or.kr/kosha/data/machine.do`) → 404
- 새 URL: `portal.kosha.or.kr/archive/disaster-case/accident-case`
- 게시판: 제조업(1,427건), 건설업, 조선업, 서비스업, 지역별, 공공기관, 중대산업사고

### 7.2 게시글 데이터 구조
- 제목: "지게차 작업 중 뒷바퀴에 깔림" (재해유형+기인물 추출 가능)
- 본문: 1줄 요약
- 첨부: PDF (상세 분석 — 재해개요, 원인분석, 대책)

### 7.3 핵심 발견
- **KOSHA 재해사례에는 과태료/벌금 정보 없음** (사고 사례 데이터)
- master의 penalty_value(과태료 금액)와 결합하면 가치 생김
- "산안기준규칙 제171조 위반 → 과태료 300만원 + 실제 사고: 지게차 깔림 사망"

### 7.4 API 이슈 (미해결)
- data.go.kr ServiceKey 발급 + 활용신청 완료
- Railway 환경변수 `DATA_GO_KR_SERVICE_KEY` 등록 완료
- API 테스트 실패: HTTP 401 Unauthorized
- 원인 추정: 활용가이드 미확인 (정확한 호출 형식 불명)
- **다음 행동**: data.go.kr 활용가이드.docx 다운로드 또는 Swagger "Try it out" 실행

---

## 8. 보안 이슈

### INTERNAL_API_SECRET 노출 (3회)
- 채팅 히스토리에 시크릿 키 노출
- `env | grep` 실행 시 전체 환경변수 출력으로 추가 노출
- **조치 필요**: Railway에서 INTERNAL_API_SECRET 재발급(rotate) **강력 권장**

---

## 9. 배포된 버전

| 파일 | 버전 | 커밋 | 내용 |
|---|---|---|---|
| `routers/precedent_api.py` | v1.7.2 | `cfddbfc` | master-keys + save-matched + 시행령 포함 |
| `routers/law_viewer.py` | v1.0.0 | `9f16b0e` | 조문+판례 조회 endpoint |
| `services/legal_format.py` | - | `9f16b0e` | 9필드 반영 |
| `services/safe_db_update.py` | v1.0.0 | `7a0d988` | 필드별 개별 UPDATE |
| `scripts/collect_precedents_matched.py` | - | `1eee07a` | master 기반 판례 수집 |
| `scripts/collect_prec_standard_rules.py` | - | `58eb41f` | 기준규칙 조문별 수집 |
| `scripts/collect_prec_casename.py` | - | `58eb41f` | 사건명 검색 수집 |
| `scripts/collect_precedents.py` | - | `d8ee230` | 법령명 검색 (폐기됨) |

### DDL Migrations
- `precedent_table_upgrade_and_link`: 16컬럼 추가 + precedent_rule_links 생성
- `precedent_add_case_type_and_prec_seq`: case_type, prec_seq, judicial_summary, violation_laws_raw 추가
- `penalty_enforcement_stats`: 과태료 통계 테이블 (생성 시도, 미완료)

### Edge Functions
- `precedent-search` (v3): 법제처 판례 API 테스트 (IP 비고정 문제로 사용 불가)
- `check-ip` (v1): Supabase Edge Function outbound IP 확인

---

## 10. 남은 작업

### 법령엔진 관련
1. 법엔진 출력에 penalty_value 원 단위 표시 로직 확인 (프론트)
2. 진단 결과에 판례 표시 연동 (law_viewer.py 활용)
3. KOSHA 재해사례 API 인증 해결 + 수집
4. 과태료 부과 건수 통계 연결 (CSV 파일)
5. PENDING draft 542건 검토
6. 법령 개정 자동 감지 파이프라인 (향후)

### 서비스 출시 관련
7. INTERNAL_API_SECRET 재발급 (보안)
8. KG이니시스 PG 승인
9. 도메인 전환 (`new.taieng.co.kr` → `taieng.co.kr`)
10. 본인인증 연동 (KG이니시스 CI)
11. 면책동의 체크박스
12. 유료진단 입력 폼 + PDF
