# 작업지시서: 유료 상세 PDF 템플릿

## 개요
- **목적**: 유료 결제 후 제공되는 상세 진단 리포트 PDF
- **페이지**: 9p + 부록 4~5p = 총 13~14p
- **위치**: taiengineering/tai-api → templates/diagnosis_report_paid.html
- **기술**: Jinja2 + xhtml2pdf (향후 Gotenberg)
- **브랜치**: dev

## 핵심 설계 — 이중 페르소나

### 결재권자 동선 (표지~결론, 9p)
- 표지 → 경영진요약 → (본문 건너뛰) → **결론(p9) = SaaS 안내**
- p9이 "마지막으로 보이는 페이지" = SaaS 전환 포인트

### 안전관리자 동선 (전체 + 부록)
- 본문 전체 읽음 + 부록 205건 표로 실무 관리
- 부록이 실제 "돈 받고 파는 값어치"

## 페이지별 상세

### P1: 표지
- report_v1.html 표지 레이아웃 재사용
- 제목: "산업안전 법적의무 상세 진단 리포트"
- 변수: company_name, report_date, receipt_no, sector_label
- 하이라이트: "법령 기반 정밀 분석" / "전문가 검토 포함" / "AI 엔진 분석"

### P2: 경영진 요약 (Executive Summary)
- 기안PDF p1과 동일 구조 (재사용 가능)
- 핵심 숫자 3개 + 위험도 카드 4칸 + TOP 5 리스크
- 여기에 "상세 내역은 본문 및 부록 참조" 안내

### P3: 목차 + 면책조항
- report_v1 목차 스타일 재사용
- 섹션 번호: SECTION 01~04 + 부록 A~D

### P4: 시설 개요 (SECTION 01)
- report_v1 p3 재사용
- input_data에서: 회사명, 사업자번호, 주소, 업종, 근로자수, 연면적, 세부설비
- 중대재해법 적용 여부 정보 박스

### P5~7: 법률별 의무 분석 (SECTION 02, 본문 핵심)
- full_result.rules_table을 law_name으로 그룹핑
- 상위 8~10개 법령만 본문에 수록 (건수 내림차순)
- 각 법령 블록:
  - 섹션 헤더: 법령명 + 총 건수
  - 요약 테이블:
    | 의무유형 | 조항 | 내용 | 주기 | 제출기관 |
    |---|---|---|---|---|
    | 선임 | 제17조 | 안전관리자 선임 | - | 지자체 |
    | 점검 | 제36조 | 위험성평가 | 연 1회 | 자체 |
- 나머지 법령은 "부록 A 참조" 안내
- 데이터 필드: law_name, law_article, obligation_type, description, inspection_cycle, submit_org_label

### P8: 처벌 조항 + 리스크 (SECTION 03)
- report_v1 p6 구조 재사용
- penalty_amount 있는 규칙 테이블
- 중대재해처벌법 경고 박스 (조건부)
- #06 과태료 변칙 구조 다이어그램 (가능 시)

### P9: 결론 = SaaS 안내 (SECTION 04) ★ 핵심
- **이 페이지가 전환 포인트**
- 제목: "이 의무를 어떻게 관리할 것인가"
- #11 업무분산 비포애프터 다이어그램
  - URL: https://xntdkrjhgcscmqctdzyo.supabase.co/storage/v1/object/public/diagrams/11-업무분산-비포애프터.svg
- TAI Safe 소개 (3줄 요약)
- 추천 플랜 + 가격
- 연락처: contact@taieng.co.kr / safe.taieng.co.kr
- **결재권자가 본문을 건너뛰어도 이 페이지는 반드시 도달** = "SaaS가 마지막으로 보이는 페이지"

### 부록 A: 전체 규칙 테이블 (2~5p)
- rules_table 205건 전체
- 테이블 컨:
  | No. | 법령 | 조항 | 의무유형 | 내용 | 주기 | 제출기관 |
- Jinja2 for loop + page-break-inside: avoid
- 이 테이블이 "돈 받고 파는 값어치" — 안전관리자의 실무 도구

### 부록 B: 점검 일정 요약 (1p)
- inspection_required 37건
- 테이블: 항목 | 주기 | 기준점 | 실행자 | 제출기관
- inspection_cycle: 정규화된 라벨 ("2년마다", "월 1회" 등)
- cycle_base_guide: 기준점 설명

### 부록 C: 선임 의무 상세 (1p)
- appointment_required 8건
- 테이블: 선임 대상 | 근거 법령 | 자격요건 | 선임기한 | 제출기관

### 부록 D: 용어 + 참고법령 (1p)
- 주요 용어 정의 (과태료, 중대재해, 위험성평가 등)
- 법령 원문 링크 (law.go.kr)
- TAI Engineering 연락처

## Jinja2 변수 목록

### 단순 변수
```
company_name, report_date, receipt_no, sector_label, report_type
business_no, ceo_name, address, industry_type, worker_count
area, floors, equip_summary, hazard_summary
total, appointment_count, inspection_count, action_count, report_notify_count
risk_level, law_count, max_penalty_text
csia_applicable (bool)
recommended_plan_name, recommended_plan_price
```

### 반복문
```
{% for group in law_groups %}          — 법령별 그룹 (8~10개)
  {% for rule in group.rules %}        — 그룹 내 개별 규칙
{% for rule in all_rules %}            — 부록 A 전체 테이블
{% for r in inspection_rules %}        — 부록 B 점검 일정
{% for r in appointment_rules %}       — 부록 C 선임 상세
{% for t in top5_risks %}              — TOP 5 리스크
```

## 디자인
- report_v1.html CSS 디자인 시스템 **전체 재사용**
- A4 (210mm × 297mm), Noto Sans KR, 인쇄 최적화
- 헤더: TAI 로고 + "산업안전 법적진단 리포트" + 접수번호
- 푸터: 면책 + 페이지 번호

## API 엔드포인트
```
GET /diagnosis/report-pdf/{public_token}
→ tier_code 확인 (PAID 티어만 허용)
→ full_result + input_data 조회
→ 법령별 그룹핑 전처리
→ Jinja2 렌더링 → PDF 생성
→ Content-Type: application/pdf 반환
```

## 참고 파일
- docs/ref/report_v1_reference.html — CSS 참조 (실제 파일은 대표님 로컬)
- docs/DIAGNOSIS_REPORT_STRUCTURE.md — 리포트 구조 설계서
- docs/WORK_ORDER_20260418_proposal_pdf.md — 기안PDF (재사용 가능 부분 표시)
- docs/PRICING_FINAL.md / docs/DIAGNOSIS_TIER_FINAL.md

## 금지 사항
- ❌ 카카오 API 사용 금지
- ❌ "기계적 대조" 표현 → "정밀 분석하여 도출" 사용
- ❌ "소개비" 등 소개 관련 용어
- ❌ SaaS 안내를 너무 광고성으로 → "결론" 섹션으로 자연스럽게
