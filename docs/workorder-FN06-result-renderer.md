# FN-06: 법령진단 결과 렌더러 + 리포트 페이지

> **작성일**: 2026-04-17  
> **대상 레포**: taiengineering/tai-admin (프론트엔드, safe.taieng.co.kr)  
> **의존**: BE-08 (diagnosis_transform.py) 완료 후 진행

---

## 배경

현재 `result_html`과 `result_pdf_url`이 전부 NULL.
법령진단 결과를 사용자에게 보여주는 페이지가 없음.
BE-08의 Transform API(`/diagnosis/transform/latest/{factory_id}`)를 호출하여 표준화된 결과를 렌더링.

---

## 작업 1: `diagnosis-result-v2.html` 신규 생성

### 경로
```
tadmin/full-version/html/horizontal-menu-template/diagnosis-result-v2.html
```

### 진입점
- URL: `diagnosis-result-v2.html?factory_id={uuid}`
- 또는: `diagnosis-result-v2.html?diagnosis_id={uuid}`

### 레이아웃 구조

```
┌─────────────────────────────────────────────────┐
│ 헤드라인 카드                                      │
│ ┌─────────┬─────────┬──────────┬──────────┐      │
│ │ 위험등급  │ 의무건수  │ 적용법령수  │ 과태료노출  │      │
│ │ HIGH 🔴 │ 95건    │ 12개     │ 2,600만원 │      │
│ └─────────┴─────────┴──────────┴──────────┘      │
├─────────────────────────────────────────────────┤
│ ⚠️ 경고 배너 (threshold_near 등)                   │
├──────────────────────┬──────────────────────────┤
│ 의무사항 탭 (좌 65%)   │ ROI + 요약 (우 35%)        │
│                      │                          │
│ [선임] [점검] [조치]   │ 연 구독료: 948,000원       │
│ [신고] [보고]         │ 과태료 노출: 26,000,000원   │
│                      │ ROI: 27.4배               │
│ ┌──────────────────┐ │                          │
│ │ 산안법 §16       │ │ ┌──────────────────────┐│
│ │ 안전관리자 선임   │ │ │ SaaS 구독 전환 CTA   ││
│ │ 자격: 산업안전기사 │ │ │ [월 79,000원 시작]    ││
│ │ 과태료: 500만원   │ │ └──────────────────────┘│
│ └──────────────────┘ │                          │
│ ...                  │ 점검 스케줄 요약           │
│                      │ - 정기 15건               │
│                      │ - 작업전 3건              │
│                      │ - 수시 5건                │
├──────────────────────┴──────────────────────────┤
│ 하단 액션 버튼                                     │
│ [PDF 다운로드] [SaaS 구독] [재진단]                 │
└─────────────────────────────────────────────────┘
```

### API 호출

```javascript
const API = localStorage.getItem('api_base') || 'https://api.taieng.co.kr';

// factory_id로 최신 결과 조회
const res = await fetch(`${API}/diagnosis/transform/latest/${factoryId}`, {
  headers: { 'Authorization': `Bearer ${token}` }
});
const { data } = await res.json();

// data.headline → 상단 카드
// data.obligations → 탭 콘텐츠
// data.warnings → 경고 배너
// data.exposure → 과태료 합산
// data.roi → ROI 카드
// data.inspection_schedule → 점검 스케줄 요약
```

### 의무사항 탭 UI

| 탭 | 아이콘 | 데이터 소스 |
|---|---|---|
| 선임 | 👤 | obligations[category=appointment].items |
| 점검 | 🔍 | obligations[category=inspection].items |
| 조치 | ⚡ | obligations[category=action].items |
| 신고 | 📋 | obligations[category=report].items |
| 보고 | 📤 | obligations[category=notify].items |

### 각 의무 카드 구성

```html
<div class="obligation-card">
  <div class="law-badge">산안법 §16</div>
  <h5>안전관리자 선임</h5>
  <p class="desc">상시 근로자 50인 이상 사업장...</p>
  <div class="meta-row">
    <span class="cycle">연 1회</span>
    <span class="executor">자격자만</span>
    <span class="penalty text-danger">과태료 500만원</span>
  </div>
  <div class="form-link" data-form-code="FORM_001">
    <a href="#">📄 서식 다운로드</a>
  </div>
</div>
```

---

## 작업 2: 경고 배너 컴포넌트

```html
<!-- warnings 배열 순회 -->
<div class="alert alert-warning d-flex align-items-center" role="alert">
  <i class="bx bx-error-circle me-2 fs-4"></i>
  <div>
    <strong>경계값 경고</strong><br>
    근로자 49명 — 50명 도달 시 중대재해법 적용 (1명 차이)
  </div>
</div>
```

---

## 작업 3: ROI 카드

```html
<div class="card bg-dark text-white">
  <div class="card-body text-center">
    <h6 class="text-white-50">과태료 리스크</h6>
    <h2 class="text-danger">2,600만원</h2>
    <hr class="border-secondary">
    <h6 class="text-white-50">TAI Safe 연 구독료</h6>
    <h2 class="text-success">948,000원</h2>
    <div class="mt-3">
      <span class="badge bg-success fs-5">ROI 27.4배</span>
    </div>
    <a href="pricing.html" class="btn btn-success btn-lg mt-3 w-100">
      월 79,000원부터 시작하기
    </a>
  </div>
</div>
```

---

## 작업 4: 메뉴 연결

`menu-tadmin.js`에 결과 페이지 링크 추가:
- 법령진단 > 진단결과 → `diagnosis-result-v2.html`

---

## 작업 5: 기존 `diagnosis-result.html` 유지

기존 페이지는 삭제하지 않고 유지. 새 v2 페이지가 안정화되면 리다이렉트.

---

## 체크리스트

- [ ] `diagnosis-result-v2.html` 생성
- [ ] BE-08 API (`/diagnosis/transform/latest/{factory_id}`) 연동
- [ ] 헤드라인 카드 (위험등급, 의무건수, 법령수, 과태료)
- [ ] 경고 배너 (threshold 경계값)
- [ ] 의무사항 5탭 (선임/점검/조치/신고/보고)
- [ ] ROI 카드 + SaaS CTA
- [ ] 점검 스케줄 요약
- [ ] PDF 다운로드 버튼 (FN-05, 후속)
- [ ] 메뉴 연결
- [ ] Vuexy dark theme, data-bs-theme="dark" 준수
- [ ] 모바일 반응형 (65/35 → 100% 스택)

---

## 🔴 금지사항

1. 엔진 API (`/legal-engine/diagnose/step1`) 직접 호출하여 result_data 구조 가정 금지
2. Transform API (`/diagnosis/transform/`) 응답만 사용
3. 하드코딩 가격 금지 — Transform API의 roi 필드 사용
