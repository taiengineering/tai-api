# FN-06: 진단 기반 SaaS 플랜 추천 UI

**작성일:** 2026-04-18  
**선행조건:** BE-08(`GET /diagnosis/{id}/recommend-plan`) 완료 ✅  
**담당:** 프론트엔드 창

---

## 변경 위치 3곳

### 1. 진단 결과 페이지 하단 (주요)

진단 완료 직후 자동으로 BE-08 API를 호출하여 추천 플랜 카드를 노출.

**추가할 블록 구성:**

```
[추천 플랜 카드]
  ├── 플랜명 + 월 요금 (big badge)
  ├── 추천 이유 2~4개 (bullet)
  ├── 과태료 비교 bar (비교 시각화)
  │     과태료 위험 213,000,000원
  │     TAI Safe 연간   2,988,000원  ← 71.3배 절감
  ├── [지금 시작하기] 버튼 → pricing.html?plan=INDUSTRY_PRO
  └── [전체 요금제 비교] 링크 → pricing.html
```

**API 호출:**
```javascript
const res = await fetch(
  `https://api.taieng.co.kr/diagnosis/${diagnosisId}/recommend-plan`
);
const data = await res.json();
// data.recommended, data.reasons, data.comparison, data.alternatives, data.cta
```

---

### 2. pricing.html 하단

**추가:** "어떤 플랜이 맞는지 모르시겠다면?" 유도 블록

```html
<div class="pricing-cta-diag">
  <p>어떤 플랜이 맞는지 모르시겠다면?</p>
  <a href="/free-diagnosis.html">→ 무료 법령 진단으로 맞춤 추천 받기</a>
</div>
```

위치: 요금제 카드 섹션 하단, 문의하기 섹션 위

---

### 3. for-business-owner.html

**변경 없음** — 이미 진단 연결 흐름 포함

---

## 전체 사용자 플로우

```
경로 A (대다수):
  마케팅 → 무료진단 → 결과 + 플랜 추천(BE-08) → 결제

경로 B (소수):
  pricing 직접 방문 → "모르겠다" → 진단 유도(FN-06) → 경로 A 합류
```

---

## 추천 카드 UI 상세 스펙

### 카드 레이아웃

```
┌─────────────────────────────────────────────┐
│  🏆 회원님께 추천하는 플랜                   │
│                                             │
│  ┌──────────────────┐                       │
│  │  산업 PRO        │  월 249,000원         │
│  │  (배지: 추천)    │  (부가세 별도)        │
│  └──────────────────┘                       │
│                                             │
│  추천 이유                                  │
│  ✓ 위험도 CRITICAL — 전사적 관리 필요       │
│  ✓ 법적 의무 499건 — 전수 자동 관리         │
│  ✓ 작업자 499명 — 200인+ 전담 기능 포함     │
│                                             │
│  ─── 과태료 위험 절감 효과 ──────────────   │
│  과태료 위험액   ████████████  213,000,000원 │
│  TAI Safe 연간  █            2,988,000원   │
│                 → 71.3배 비용 절감           │
│                                             │
│  [지금 시작하기 →]  [전체 요금제 비교]       │
└─────────────────────────────────────────────┘
```

### 대안 플랜 (하단 작은 링크)
```
💡 비용을 줄이고 싶다면: 산업 BUSINESS 149K →
💡 더 많은 기능이 필요하다면: 맞춤 견적 문의 →
```

---

## pricing.html?plan= 파라미터 처리

pricig.html에서 URL 파라미터로 특정 플랜 하이라이트:

```javascript
const params = new URLSearchParams(location.search);
const planCode = params.get('plan'); // 'INDUSTRY_PRO'
if (planCode) {
  // 해당 플랜 카드에 '추천' 배지 + 스크롤
  document.querySelector(`[data-plan="${planCode}"]`)
    ?.classList.add('recommended');
}
```

---

## 파일 위치 (taiengineering/taieng 레포)

| 파일 | 작업 내용 |
|---|---|
| `nexas/free-diagnosis.html` | 진단 결과 하단에 추천 카드 블록 추가 |
| `nexas/pricing.html` | 하단에 진단 유도 CTA 추가 + plan 파라미터 처리 |
