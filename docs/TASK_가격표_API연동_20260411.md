# 작업 지시서 — new.taieng.co.kr 가격표 API 연동

> 작성일: 2026-04-11  
> 지시: 이창 (기획·PM)  
> 대상: 백엔드창 + 프론트엔드창  
> 우선순위: 높음

---

## 배경

현재 `new.taieng.co.kr` (nexas) 의 가격 정보가 하드코딩 되어 있음.
어드민에서 가격을 수정해도 프론트에 반영되지 않는 구조.

`price_policy` 테이블 + `/price-policy` API 가 완성되었으므로
new.taieng.co.kr 이 API 에서 가격을 로드하도록 연동 필요.

---

## PART 1. 백엔드 작업지시

### 담당: 백엔드창 (tai-api repo)

### 작업 1-1. CORS 확인

`new.taieng.co.kr` 에서 `/price-policy` 호출 가능한지 확인.
현재 `main.py` CORS 설정:
```python
allow_origins=[
    "https://taieng.co.kr",
    "https://www.taieng.co.kr",
    "https://new.taieng.co.kr",   # ← 이미 포함됨
    ...
]
```
→ 이미 허용되어 있으므로 추가 작업 불필요. 확인만 하면 됨.

### 작업 1-2. /price-policy 응답 확인

아래 엔드포인트가 정상 응답하는지 확인:

```
GET https://api.taieng.co.kr/price-policy?category=diagnosis
GET https://api.taieng.co.kr/price-policy?category=saas
```

예상 응답 구조:
```json
{
  "status": "success",
  "data": [
    {
      "id": 1,
      "category": "diagnosis",
      "sector": "construction",
      "tier_code": "FREE",
      "label": "무료",
      "price": 0,
      "price_display": "무료",
      "is_active": true,
      "sort_order": 1
    },
    ...
  ]
}
```

### 작업 1-3. 인증 없이 호출 가능 확인

`/price-policy` 는 공개 API (인증 불필요) 이어야 함.
현재 코드 확인 → `get_supabase()` 사용, JWT 미검증 → 공개 OK.
추가 조치 불필요.

---

## PART 2. 프론트엔드 작업지시

### 담당: 프론트엔드창 (taiengineering/taieng repo, nexas/)

### 작업 대상 파일

| 파일 | 작업 내용 |
|---|---|
| `nexas/index-1.html` | SaaS 가격 섹션 → API 연동으로 교체 |
| `nexas/pricing.html` (신규 생성) | 법령진단 + SaaS 통합 가격표 페이지 |

---

### 작업 2-1. nexas/index-1.html — SaaS 가격 섹션 API 연동

#### 현재 상태
`#pricing` 섹션에 가격이 하드코딩됨 (79,000 / 149,000 / 별도협의)

#### 수정 방향

**섹터 탭 구조로 변경:**
```
[건물·시설] [산업] [건설]
```
각 탭 클릭 시 해당 섹터의 플랜(BASIC/PRO/PREMIUM/커스터마이징)을 표시.

**API 호출:**
```javascript
const API = 'https://api.taieng.co.kr';

async function loadSaasPricing() {
  const res = await fetch(API + '/price-policy?category=saas');
  const d = await res.json();
  const data = d.data || [];
  // sector 별로 그룹핑 후 렌더링
}
```

**렌더링 규칙:**
- `price === -1` → "협의" 표시, CTA 버튼 → "문의하기" (contact.html 링크)
- `price === 0` → "무료" 표시
- `price_display` 값이 있으면 그 값 우선 표시
- `price > 0` → `price.toLocaleString() + '원/월'` 형식
- `is_featured === true` (PRO) → 추천 뱃지

**주의:**
- 가격 로드 중 스피너 표시
- API 실패 시 fallback 없이 오류 메시지 표시 (하드코딩 fallback 금지)

---

### 작업 2-2. nexas/pricing.html 신규 생성

**URL:** `new.taieng.co.kr/nexas/pricing.html`

**페이지 구조:**

```
[헤더]

[탭]
  ├─ 법령진단 가격
  └─ SaaS 요금제

[법령진단 섹션]
  섹터 3개 칸 나란히:
  ┌────────────┐ ┌────────────┐ ┌────────────┐
  │   건설      │ │  건물·시설  │ │    산업     │
  │ FREE       │ │ FREE       │ │ FREE       │
  │ 단일 199K  │ │ 베이직 49K  │ │ 베이직 79K  │
  │            │ │ 스탠다드 99K│ │ 스탠다드 149K│
  │            │ │ 프리미엄 149K│ │ 프리미엄 249K│
  └────────────┘ └────────────┘ └────────────┘

[SaaS 요금제 섹션]
  섹터 탭 [건물·시설] [산업] [건설]
  탭별 플랜 카드

[푸터]
```

**API 호출 2개:**
```javascript
const [diagRes, saasRes] = await Promise.all([
  fetch(API + '/price-policy?category=diagnosis'),
  fetch(API + '/price-policy?category=saas'),
]);
```

**디자인 요구사항:**
- tai-main.css 스타일 사용
- FREE 티어: 별도 카드 없이 각 섹터 상단에 "FREE — 기초 진단 무료" 배지로 표시
- 법령진단 CTA: "지금 진단하기 — 무료" → `free-diagnosis.html` 링크
- SaaS CTA: "시작하기" → `safe.taieng.co.kr` 링크 / "문의하기" → `contact.html`
- 하단 공통 문구: "모든 SaaS 구독에 법령진단 포함"

---

### 작업 2-3. 기존 index-1.html nav 수정

현재 `#pricing` 섹션 링크를 `pricing.html` 으로 교체:
```html
<!-- Before -->
<a href="#pricing" class="btn-outline-white">요금 보기</a>

<!-- After -->
<a href="pricing.html" class="btn-outline-white">요금 보기</a>
```

---

## 완료 기준

- [ ] `GET /price-policy?category=saas` 응답 정상
- [ ] `GET /price-policy?category=diagnosis` 응답 정상
- [ ] `nexas/index-1.html` SaaS 가격 → API에서 로드
- [ ] `nexas/pricing.html` 신규 생성 — 법령진단 + SaaS 통합 가격표
- [ ] 어드민에서 가격 수정 → new.taieng.co.kr 에 즉시 반영 확인

---

## 참고 — DB 현재 데이터

### 법령진단 (category=diagnosis)

| sector | tier_code | label | price |
|---|---|---|---|
| construction | FREE | 무료 | 0 |
| construction | PAID | 유료 | 199,000 |
| facility | FREE | 무료 | 0 |
| facility | BASIC | 베이직 | 49,000 |
| facility | STANDARD | 스탠다드 | 99,000 |
| facility | PREMIUM | 프리미엄 | 149,000 |
| industrial | FREE | 무료 | 0 |
| industrial | BASIC | 베이직 | 79,000 |
| industrial | STANDARD | 스탠다드 | 149,000 |
| industrial | PREMIUM | 프리미엄 | 249,000 |

### SaaS (category=saas)

| sector | tier_code | label | price |
|---|---|---|---|
| facility | BASIC | BASIC | 79,000 |
| facility | PRO | PRO | 149,000 |
| facility | PREMIUM | PREMIUM | 249,000 |
| facility | CUSTOM | 커스터마이징 | -1 (협의) |
| industrial | BASIC | BASIC | 99,000 |
| industrial | PRO | PRO | 199,000 |
| industrial | PREMIUM | PREMIUM | 349,000 |
| industrial | CUSTOM | 커스터마이징 | -1 (협의) |
| construction | SINGLE | 단일 플랜 | 149,000 |
| construction | CUSTOM | 커스터마이징 | -1 (협의) |
