# 작업지시서: 무료 진단 결과 페이지 (free-diagnosis-result.html)

## 개요
- **목적**: 법령진단 무료 결과를 웹에서 표시하는 페이지
- **위치**: taiengineering/taieng 리포 (taieng.co.kr)
- **파일명**: nexas/free-diagnosis-result.html
- **연결**: free-diagnosis.html → /diagnosis/run API → 이 페이지
- **브랜치**: dev

## 핵심 설계 원칙
1. **콘텐츠 100% 공개** — 빈약하게 보이면 유도행위로 비춰짐
2. **형식 차별** — 웹은 확인용, PDF는 전달용/공식문서
3. **이중 페르소나** — 안전관리자(웹 확인) + 결재권자(PDF 전달)
4. **기안PDF 무료** — 안전관리자가 TAI 영업 대행하는 구조
5. **토스 원칙** — 지금 보지 않아도 되는 것은 보여주지 않는다

## 데이터 소스

### API 흐름
```
free-diagnosis.html에서 /diagnosis/run POST
→ 응답: { public_token, result_url, ... }
→ 리다이렉트: free-diagnosis-result.html?token={public_token}
→ 페이지 로드 시: GET /diagnosis/result/{public_token}
→ anonymous_diagnosis_results 테이블에서 partial_result + full_result 반환
```

### partial_result 구조 (무료 요약)
```json
{
  "sector": "BUILDING",
  "summary": {
    "total": 205,
    "appointment": 8,
    "inspection": 37,
    "action": 129,
    "report": 16,
    "notify": 15,
    "form_linked": 116
  },
  "law_badges": ["산업안전보건법", "건축법", "건축물관리법", ...],  // 18개
  "risk_level": "HIGH",
  "key_obligations": [
    "조치 의무 (산업안전보건기준에 관한 규칙 제669조)",
    "조치 의무 (산업안전보건기준에 관한 규칙 제13조)",
    ...
  ],
  "applicable_count": 205
}
```

### full_result.rules_table 개별 규칙 구조
```json
{
  "rule_id": "BLDACT-001",
  "sector": "BUILDING",
  "law_name": "건축법",
  "law_article": "제35조",
  "category": "점검",
  "obligation_type": "INSPECT",  // APPOINT, INSPECT, ACTION, REPORT, NOTIFY
  "obligation_summary": "점검 의무 (건축법 제35조)",
  "description": "점검 의무 (건축법 제35조)",
  "appointment_target": "",
  "inspection_cycle": "2년마다",  // 정규화된 한글 라벨
  "inspection_cycle_int": 2,
  "inspection_cycle_unit": "year",
  "cycle_base_type": "APPROVAL_DATE",
  "cycle_base_guide": "건물 사용승인일 기준 정기 점검",
  "schedule_type": "PERIODIC",
  "penalty_amount": "",
  "penalty_summary": "",
  "qualification_required": "national",
  "submit_org_label": "국토교통부(지자체)",
  "executor_type_label": "사업주 누구나",
  "report_method_label": "자체보관(미제출)",
  "condition_code": "building_area",
  "condition_value": 1000,
  "due_info": { "urgency": "URGENT", "due_date": "2026-05-02", "due_days": 14 },
  "form_code": "",
  "form_url": ""
}
```

## 페이지 구조 (8 섹션)

### SECTION 1: 위험도 헤더
- risk_level에 따른 색상 (HIGH=빨강, MEDIUM=노랑, LOW=초록)
- "귀 사업장에 {applicable_count}건의 법적 의무가 확인되었습니다"
- 섹터 표시 (건물/산업/건설)

### SECTION 2: 요약 카드 (4열 그리드)
| 선임 의무 | 점검·검사 | 조치 의무 | 보고·신고 |
|---|---|---|---|
| {appointment}건 | {inspection}건 | {action}건 | {report+notify}건 |

### SECTION 3: 적용 법령 뱃지
- law_badges[] 를 pill 형태로 나열
- 클릭 시 해당 법령 그룹으로 스크롤

### SECTION 4: 법률별 의무 카드 (핵심 콘텐츠)
- full_result.rules_table을 law_name으로 그룹핑
- 각 법률 = 아코디언 카드
  - 헤더: 법령명 + 건수 + 카테고리별 소계
  - 본문: 개별 규칙 목록 (의무유형 뱃지 + 설명 + 주기 + 제출기관)
- 기본: 첫 3개 법령만 펼침, 나머지 접힘
- obligation_type별 아이콘/색상:
  - APPOINT: 파랑 (👤)
  - INSPECT: 초록 (🔍) + inspection_cycle 표시
  - ACTION: 빨강 (⚡)
  - REPORT: 노랑 (📋)
  - NOTIFY: 회색 (📢)

### SECTION 5: 기안용 PDF 다운로드 (무료)
- "경영진 보고용 3페이지 PDF를 무료로 받으세요"
- "사업장의 법적 리스크를 경영진에게 보고해야 할 때"
- 다운로드 버튼 (기안PDF는 아직 미구현이므로 "준비 중" 표시 또는 더미)

### SECTION 6: 유료 상세 보고서 CTA
- "이 {total}건을 체계적으로 관리하고 싶다면?"
- 필요성 설명 먼저 → 버튼 클릭 시 가격 노출
- 가격: DIAGNOSIS_TIER_FINAL.md 참조
- 유료 결과는 즉시 표시 (마이페이지 리다이렉트 금지)

### SECTION 7: SaaS 전환 유도
- "엑셀 대신 자동화" 메시지
- Supabase diagrams 버킷의 #11 업무분산 비포애프터 이미지 활용 가능
  - URL: https://xntdkrjhgcscmqctdzyo.supabase.co/storage/v1/object/public/diagrams/11-업무분산-비포애프터.svg
- SaaS 플랜 요약 + safe.taieng.co.kr 링크

### SECTION 8: 면책 + 푸터
- "본 진단 결과는 법적 효력이 없으며, 참고 자료로만 활용하시기 바랍니다."
- TAI Engineering | contact@taieng.co.kr | www.taieng.co.kr

## 디자인 요구사항
- **헤더·푸터 없음** (free-diagnosis.html과 동일하게 독립 페이지)
- **모바일 우선** 반응형 (안전관리자가 현장에서 모바일로 확인)
- **색상 시스템**: TAI 브랜드 블루 (#1A5FD4) 기반, report_v1.html CSS 참조 가능
- **폰트**: Pretendard 또는 Noto Sans KR
- **아코디언**: 순수 CSS/JS (라이브러리 없이)
- **인쇄 최적화**: @media print 포함

## 금지 사항
- ❌ 카카오 API 사용 금지
- ❌ 콘텐츠 잠금/블러 처리 금지 (무료도 100% 공개)
- ❌ "기계적 대조" 표현 → "정밀 분석하여 도출" 사용
- ❌ "더 많이 입력하면 더 정확" → "해당 법령이 추가 적용됩니다"
- ❌ 마이페이지 리다이렉트 금지 (유료 결과도 이 페이지에서 즉시 표시)

## Mock 데이터
- 현재 anonymous_diagnosis_results에 E2E 테스트 데이터 존재
- public_token으로 조회하는 API 엔드포인트가 아직 없으면 mock JSON으로 개발
- BUILDING 섹터 기준 (total=205, laws=18개)

## 참고 파일
- docs/DIAGNOSIS_REPORT_STRUCTURE.md — 리포트 구조 설계서
- docs/ref/report_v1_reference.html — 초창기 리포트 CSS 참조
- docs/PRICING_FINAL.md — 가격 정책
- docs/DIAGNOSIS_TIER_FINAL.md — 진단 티어 정책
- 프로젝트 파일: tai_forklift_check_ui_html.html — UI 디자인 참조 (점검 카드 스타일)
