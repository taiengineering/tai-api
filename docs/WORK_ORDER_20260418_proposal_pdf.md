# 작업지시서: 기안용 PDF 템플릿 (무료)

## 개요
- **목적**: 안전관리자가 결재권자(대표/공장장)에게 전달하는 3페이지 리스크 보고서
- **무료 제공**: 안전관리자가 TAI 영업을 대행하는 구조
- **생성 방식**: Jinja2 템플릿 + xhtml2pdf (현재 스택), 향후 Gotenberg 전환
- **위치**: taiengineering/tai-api → templates/proposal_pdf.html
- **브랜치**: dev

## 핵심 설계
- **읽는 사람**: 결재권자 (3분 내 읽고 결정)
- **보내는 사람**: 안전관리자
- **심리 동선**: 위험 인식 → 비용 비교 → 해결책 → 견적 → 결재

## 3페이지 구조

### PAGE 1: 표지 + 경영진 요약

#### 상단: 표지 영역
- TAI 로고 (좌상단)
- 제목: "산업안전 법적의무 리스크 보고서"
- 진단 대상: {{ company_name }}
- 진단 일자: {{ report_date }}
- 섹터: {{ sector_label }} (건물/산업/건설)

#### 중단: 경영진 요약 (Executive Summary)
- 1줄 요약: "귀 사업장에 {{ total }}건의 법적 의무 사항이 확인되었습니다."
- 위험도 뱃지: {{ risk_level }} (HIGH=빨강, MEDIUM=노랑, LOW=초록)
- 핵심 숫자 3개:
  - 적용 법령: {{ law_count }}개
  - 법적 의무: {{ total }}건
  - 미이행 시 최대 과태료: {{ max_penalty_text }}

#### 하단: 요약 카드 (4칸 그리드)
| 선임 의무 | 점검·검사 | 조치 의무 | 보고·신고 |
|---|---|---|---|
| {{ appointment }}건 | {{ inspection }}건 | {{ action }}건 | {{ report_notify }}건 |

#### 최하단: 주요 리스크 TOP 5
- penalty_amount 기준 정렬, 상위 5건
- 각 항목: 위반 사항 + 근거 법령 + 처벌 내용
- 예: "안전관리자 미선임 | 산업안전보건법 제17조 | 500만원 이하 과태료"

### PAGE 2: 비용 비교 + 리스크

#### 상단: 방치 비용 vs 관리 비용 비교표
| 방법 | 월 비용 | 리스크 |
|---|---|---|
| 방치 | 0원 | 과태료 수천만원 + 징역 |
| 엑셀 관리 | 0원 | 누락 시 동일 |
| 안전관리 대행 | 150~300만원 | 낮음 |
| **TAI Safe** | **7.9~24.9만원** | **자동화로 최소화** |

#### 중단: 다이어그램
- #23 TAI ROI 비교 SVG 삽입
  - URL: https://xntdkrjhgcscmqctdzyo.supabase.co/storage/v1/object/public/diagrams/23-TAI-ROI-비교.svg
  - xhtml2pdf에서 SVG 렌더링 안 되면 PNG 변환 필요

#### 하단: 중대재해처벌법 경고 박스
- 조건: {{ csia_applicable }} (근로자 50인 이상)
- 적용 시:
  - "⚠️ 귀 사업장은 중대재해처벌법 적용 대상입니다"
  - 사망사고: 1년 이상 징역 또는 10억 이하 벌금
  - 부상·질병: 7년 이하 징역 또는 1억 이하 벌금
  - 양벌규정(법인): 50억 이하 벌금
  - **"경영책임자 개인이 처벌 대상입니다"** ← 핵심 문구
- 미적용 시:
  - "현재 50인 미만이나, 인원 증가 시 즉시 적용됩니다"

### PAGE 3: TAI 소개 + 견적

#### 상단: TAI Safe 도입 4단계
- #24 TAI 도입 4단계 SVG
  - URL: https://xntdkrjhgcscmqctdzyo.supabase.co/storage/v1/object/public/diagrams/24-TAI-도입-4단계.svg
- 또는 텍스트 버전:
  1. 법령 진단 (자동) → 2. 초기 세팅 (1일) → 3. 운영 시작 → 4. 자동 모니터링

#### 중단: 업무 분산 구조
- #25 안전관리 분산구조도 SVG
  - URL: https://xntdkrjhgcscmqctdzyo.supabase.co/storage/v1/object/public/diagrams/25-안전관리-분산구조도.svg
- 핵심 메시지: "안전관리자 1인 집중 → 전원 참여 체계로 전환"

#### 하단: 추천 플랜 + 견적
- 진단 데이터 기반 자동 추천:
  - {{ recommended_plan_name }}
  - {{ recommended_plan_price }}/월
  - 포함 인원: 10명 (초과 시 3,000원/명)
- 견적 근거: "{{ total }}건의 법적 의무를 자동 관리"
- 연락처:
  - TAI Engineering
  - contact@taieng.co.kr
  - www.taieng.co.kr
  - safe.taieng.co.kr

#### 최하단: 면책
- "본 보고서는 참고 자료이며 법적 효력이 없습니다."

## 데이터 소스 (Jinja2 변수)

### 진단 결과에서 추출
```python
# anonymous_diagnosis_results 테이블에서
partial = row['partial_result']
full = row['full_result']

# 기본 정보
company_name = input_data.get('company_name', '-')
report_date = datetime.now().strftime('%Y년 %m월 %d일')
sector_label = {'BUILDING':'건물','INDUSTRY':'산업','CONSTRUCTION':'건설'}[partial['sector']]

# 요약
total = partial['summary']['total']  # 205
appointment = partial['summary']['appointment']  # 8
inspection = partial['summary']['inspection']  # 37
action = partial['summary']['action']  # 129
report_notify = partial['summary']['report'] + partial['summary']['notify']  # 31
risk_level = partial['risk_level']  # HIGH
law_count = len(partial['law_badges'])  # 18

# TOP 5 리스크 (penalty_amount 기준)
rules_with_penalty = [r for r in full['rules_table'] if r.get('penalty_amount')]
top5 = sorted(rules_with_penalty, key=lambda r: float(r['penalty_amount'] or 0), reverse=True)[:5]

# 최대 과태료
max_penalty = max([float(r.get('penalty_amount',0) or 0) for r in full['rules_table']])
max_penalty_text = format_penalty(max_penalty)  # "5,000만원"

# 중대재해법
csia_applicable = input_data.get('worker_count', 0) >= 50

# 추천 플랜 (sector + tier 기반)
# price_saas_plan 테이블에서 조회
```

## 디자인 요구사항
- **A4 세로** (210mm × 297mm)
- **report_v1.html CSS 재사용**: 색상, 폰트, 테이블, 뱃지, 카드 스타일
- **TAI 브랜드 블루** (#1A5FD4) 기반
- **폰트**: Noto Sans KR (xhtml2pdf 호환)
- **헤더/푸터**: report_v1 스타일 (TAI 로고 + 페이지 번호 + 면책)
- **인쇄 최적화**: @media print, page-break 설정

## 다이어그램 처리
- SVG → xhtml2pdf 호환성 확인 필요
- 안 되면: SVG를 PNG로 사전 변환 후 base64 인라인 삽입
- 또는: 다이어그램 내용을 HTML 테이블/CSS로 재현

## 기술 스택
- **현재**: Jinja2 + xhtml2pdf (tai-api에서 생성)
- **향후**: Gotenberg (Docker, Chromium 기반)
- **저장**: Supabase Storage (reports 버킷)
- **제공**: 무료 웹 결과 페이지에서 다운로드 버튼

## API 엔드포인트 (신규)
```
GET /diagnosis/proposal-pdf/{public_token}
→ anonymous_diagnosis_results에서 조회
→ Jinja2 렌더링
→ PDF 생성
→ Content-Type: application/pdf 반환
```

## 참고 파일
- docs/ref/report_v1_reference.html — CSS 디자인 시스템
- docs/DIAGNOSIS_REPORT_STRUCTURE.md — 리포트 구조 설계서
- docs/PRICING_FINAL.md — 가격
- docs/DIAGNOSIS_TIER_FINAL.md — 진단 티어

## 금지 사항
- ❌ 카카오 API 사용 금지
- ❌ "기계적 대조" 표현 → "정밀 분석하여 도출"
- ❌ 콘텐츠 빈약하게 만들기 (유료 유도 목적으로 내용 축소 금지)
- ❌ "소개비" 등 소개 관련 용어
