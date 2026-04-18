# FN-07: 점검 미이행 대시보드 + 작업자 알림 UI

> **작성일**: 2026-04-17
> **대상 레포**: taiengineering/tai-admin (safe.taieng.co.kr)
> **의존**: BE-10 완료 후 진행
> **API**: `GET /overdue/summary` + `GET /overdue/history`

---

## 작업 1: 안전관리자 대시보드 — 미이행 위젯

### 위치
안전관리자 대시보드(home.html 또는 dashboard.html)에 신규 카드 추가

### 레이아웃
```
┌─────────────────────────────────────────────┐
│ 🔴 점검 미이행 현황                    [상세] │
│                                             │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐        │
│ │ 경고     │ │에스컬레이션│ │ OVERDUE │        │
│ │ 2건     │ │ 2건     │ │ 1건     │        │
│ │ (D+1)   │ │ (D+2)   │ │ (D+7+)  │        │
│ └─────────┘ └─────────┘ └─────────┘        │
│                                             │
│ ⚠️ 법적 리스크: 과태료 최대 5,000만원 노출    │
│                                             │
│ 최근 미이행:                                 │
│ • 김작업 — 타이어 점검 (D+3) [독촉]          │
│ • 박안전 — 소화기 점검 (D+1) [독촉]          │
└─────────────────────────────────────────────┘
```

### API 호출
```javascript
const res = await apiCall('GET', '/overdue/summary');
const { total_overdue, by_level, by_user, legal_risk } = res.data;
```

### [독촉] 버튼 동작
- 클릭 시 해당 작업자에게 즉시 알림 발송
- `POST /overdue/nudge/{assignment_id}` (BE-10에서 추가)

---

## 작업 2: 미이행 상세 페이지

### 파일
`tadmin/full-version/html/horizontal-menu-template/overdue-list.html`

### 구성
- 필터: 기간 / 시설 / 작업자 / 에스컬레이션 레벨
- 테이블: No. / 작업자 / 점검 내용 / 기한 / 경과일 / 상태 / 액션
- 액션: [독촉] [재배정] [해소처리]
- 하단: 법적 리스크 요약 카드

### API
```javascript
// 목록 조회
const list = await apiCall('GET', '/overdue/history?page=1&size=20');

// 해소 처리
await apiCall('POST', `/overdue/resolve/${id}`);
```

---

## 작업 3: 작업자 홈 — 미이행 경고 배너

### 위치
worker-home.html 상단

### 조건
work_assignments에서 본인의 OVERDUE 또는 scheduled_date < today인 PENDING 건이 있을 때 표시

### UI
```html
<div class="alert alert-danger">
  <strong>⚠️ 미완료 점검 2건</strong>
  <p>기한이 경과한 점검이 있습니다. 즉시 완료해주세요.</p>
  <ul>
    <li>타이어 상태 점검 (D+3) <a href="#">지금 하기 →</a></li>
    <li>소화기 월간 점검 (D+1) <a href="#">지금 하기 →</a></li>
  </ul>
  <small class="text-muted">
    미이행 시 안전관리자에게 자동 보고됩니다.
    산안법 §36 위반 시 과태료 500만원
  </small>
</div>
```

---

## 작업 4: 메뉴 연결

`menu-tadmin.js`에 추가:
- 안전관리 > 미이행 관리 → `overdue-list.html`

---

## 체크리스트

- [ ] 안전관리자 대시보드 미이행 위젯
- [ ] overdue-list.html 상세 페이지
- [ ] 작업자 홈 미이행 경고 배너
- [ ] [독촉] 버튼 동작
- [ ] [재배정] 모달
- [ ] [해소처리] 확인 모달
- [ ] 메뉴 연결
- [ ] 법적 리스크 카드 (과태료 금액 표시)
- [ ] 모바일 반응형

---

## 🔴 금지사항

1. 엔진 API 직접 호출 금지 → overdue API만 사용
2. 가격/과태료 하드코딩 금지 → API legal_risk 필드 사용
