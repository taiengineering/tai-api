# 법령 프론트엔드 작업 지시서 — 2026-03-30
## 담당: Cursor
## 레포: tai-admin

---

## TASK 1. engine-legal.html 신규 페이지 구현

파일: `admin/full-version/html/horizontal-menu-template/engine-legal.html`

### 구성

**상단 통계 카드 (4개)**
| 카드 | API | 필드 |
|------|-----|------|
| 전체 법령 수 | GET /law-collector/status | collected_law_count |
| 전체 조문 수 | GET /byulpyo/stats (신규) 또는 DB | - |
| 판정룰 수 | GET /legal-engine/stats | total_rules |
| 별표 데이터 수 | GET /byulpyo/stats | 합계 |

**탭 구성 (3개)**

탭1: 법령 목록
- 필터: 법령유형(LAW/ENFORCEMENT_DECREE/ENFORCEMENT_RULE) / 키워드 검색
- 컬럼: No. / 법령명 / 유형 / 조문수 / 항수 / 수집일
- 항수 = 0이면 빨간 배지로 표시 (재수집 필요 표시)

탭2: 판정룰 목록
- 필터: 섹터(BUILDING/MANUFACTURING/CONSTRUCTION/SPECIAL_FACILITY) / obligation_type
- 컬럼: No. / 룰코드 / 법령명 / 조문 / 의무유형 / 조건요약
- obligation_type 배지 색상:
  - APPOINT → 보라
  - INSPECT → 파랑
  - REPORT → 주황 (신고)
  - NOTIFY → 하늘 (보고)
  - ACTION → 초록
  - OTHER → 회색

탭3: 별표 현황
- 소카드 5개: 안전인증(CERT) / 자율안전확인(SELF) / 위험물품명 / 선임기준 / 법정검사대상
- 각 카드 클릭 → 해당 데이터 테이블 토글 표시
- API: GET /byulpyo/safety-cert / /byulpyo/dangerous-goods / /byulpyo/safety-manager / /byulpyo/legal-inspection

### 전역 규칙 준수
- 첫 번째 컬럼: 전체선택 체크박스 (toggleAll)
- 두 번째 컬럼: No. (순번)

---

## TASK 2. 법령 진단 결과 화면 신고·보고 구분 표시

대상 파일: 법령 진단 결과를 표시하는 모든 HTML
(report-v1.html / diagnosis-step1.html 등 진단 결과 관련)

### 변경 내용

obligaton_type 기반 배지 색상 적용:
```javascript
function getObligationBadge(type) {
  const map = {
    'APPOINT': { color: 'bg-label-primary',   icon: 'tabler-user-check',  label: '선임' },
    'INSPECT': { color: 'bg-label-info',       icon: 'tabler-clipboard',   label: '점검' },
    'REPORT':  { color: 'bg-label-warning',    icon: 'tabler-file-upload', label: '신고' },
    'NOTIFY':  { color: 'bg-label-secondary',  icon: 'tabler-bell',        label: '보고' },
    'ACTION':  { color: 'bg-label-success',    icon: 'tabler-check',       label: '조치' },
    'OTHER':   { color: 'bg-label-secondary',  icon: 'tabler-dots',        label: '기타' },
  };
  const m = map[type] || map['OTHER'];
  return `<span class="badge ${m.color}">
    <i class="icon-base ti ${m.icon} me-1"></i>${m.label}
  </span>`;
}
```

---

## 완료 기준
- [ ] engine-legal.html 페이지 생성 및 3개 탭 정상 동작
- [ ] 법령 목록에서 항수=0 빨간 배지 표시
- [ ] 판정룰 목록 obligation_type 배지 색상 구분
- [ ] 별표 현황 탭 5개 데이터 조회
- [ ] 신고(REPORT)/보고(NOTIFY) 배지 구분 적용
