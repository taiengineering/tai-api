# FN-06: 진단 기반 SaaS 플랜 추천 UI

> **상태:** ✅ 구현 완료 (2026-04-18)
> **선행조건:** BE-08 `GET /diagnosis/{diagnosis_id}/recommend-plan` 완료
> **연관 파일:**
> - `tadmin/.../diagnosis-result-v2.html` (tai-admin main)
> - `nexas/pricing.html` (taieng main)

---

## 1. 진단 결과 페이지 — 추천 플랜 블록

### 위치
`diagnosis-result-v2.html` → `result-grid` 아래, `next-actions` 위

```html
<!-- FN-06: 진단 기반 플랜 추천 섹션 -->
<div class="mt-4" id="plan-recommend-section" style="display:none;">
  ...
</div>
```

### API 호출
```
GET /diagnosis/{diagnosis_id}/recommend-plan
Authorization: Bearer {token}
```

**응답 스펙 (BE-08 기준):**
```json
{
  "recommended": "BUSINESS",
  "reasons": [
    "의무 항목 73건 — STARTER 한도(50건) 초과",
    "위험도 HIGH — 적극적 대응 플랜 필요",
    "작업자 120명 — 중규모 사업장 기준 적합"
  ],
  "alternatives": ["STARTER", "PRO"],
  "comparison": {
    "penalty_max_krw": 21000000,
    "subscription_annual_krw": 1788000,
    "roi_ratio": 11.7
  }
}
```

### UI 구성 (좌우 2컬럼)

| 영역 | 내용 |
|------|------|
| 왼쪽 (col-md-4) | 추천 플랜 카드 — 플랜명·월 요금·구독 CTA 버튼 |
| 오른쪽 (col-md-8) | 추천 이유 체크리스트 + 과태료 비교 박스 + 대안 플랜 링크 |

### 플랜별 색상 테마
| 플랜 | 배경 | 테두리 | 텍스트 |
|------|------|--------|--------|
| STARTER  | `#f0fdf4` | `#16a34a` | `#15803d` |
| BUSINESS | `#eff6ff` | `#1d4ed8` | `#1e40af` |
| PRO      | `#fdf4ff` | `#7c3aed` | `#6d28d9` |
| CUSTOM   | `#fff7ed` | `#ea580c` | `#c2410c` |

### 과태료 비교 bar 스펙
```
[최대 과태료 노출] ██████████████████████  21,000,000원
[BUSINESS 연간]    ████                    1,788,000원
                   ──────────────────────
                   절감 효과: 11.7배
```
- `comparison.penalty_max_krw` → 빨간색 강조
- `comparison.subscription_annual_krw` → 초록색 강조
- `comparison.roi_ratio` → `badge bg-label-success`

### 동작 규칙
- `recommended` 필드 없으면 → 섹션 `display:none` 유지 (조용히 실패)
- API 오류 시 → 섹션 숨김 (메인 렌더 블록하지 않음)
- 구독 시작 버튼 → `pricing.html?recommend={plan}&diagnosis_id={id}`
- 대안 플랜 링크 → `pricing.html?highlight={plan}`

---

## 2. pricing.html — 진단 유도 CTA

### 위치
`nexas/pricing.html` → FAQ 섹션 아래, 기존 `price-cta` 위

```html
<section class="diag-nudge-section"> ... </section>
<section class="price-cta"> ... </section>
```

### UI 구성 (좌우 flex)

| 영역 | 내용 |
|------|------|
| 왼쪽 | eyebrow + 제목 "어떤 플랜이 맞는지 모르시겠습니까?" + 설명 |
| 오른쪽 | 체크리스트 4개 + 주 CTA 버튼 + 보조 링크 |

**체크리스트:**
1. 내 사업장에 적용되는 법령 자동 도출
2. 의무 항목 수 기반 플랜 자동 추천
3. 과태료 리스크 vs 구독료 비교 제공
4. 진단 결과에서 바로 구독 가능

**주 CTA:** `3분 무료 진단으로 플랜 추천받기 →` → `free-diagnosis.html`
**보조 링크:** `직접 상담을 원하시면 →` → `contact.html`

**배경:** `linear-gradient(135deg, #1e1b4b, #312e81)` (인디고-다크)

---

## 3. URL 파라미터 — 플랜 하이라이트

### 스펙
```
pricing.html?plan=INDUSTRY_PRO
pricing.html?highlight=BUSINESS
pricing.html?recommend=starter&diagnosis_id=abc123
```

### 동작
- 파라미터 수신 시 해당 플랜명 카드에 `outline: 3px solid #7c3aed` 적용
- `card.scrollIntoView({ behavior:'smooth', block:'center' })`
- 타이밍: `setTimeout 800ms` (카드 렌더 완료 대기)
- 대소문자 무시: `.toUpperCase()` 정규화

### 파라미터 우선순위
`plan` = `recommend` > `highlight` (동일 동작)

---

## 4. 사용자 플로우

```
경로 A (대다수):
  마케팅 → free-diagnosis.html
       → 진단 완료
       → diagnosis-result-v2.html?diagnosis_id=xxx
       → [플랜 추천 카드] 노출
       → "지금 구독 시작" 클릭
       → pricing.html?recommend=BUSINESS&diagnosis_id=xxx
       → BUSINESS 카드 하이라이트 + 결제 진행

경로 B (소수):
  pricing.html 직접 방문
       → FAQ 읽다가 하단 [진단 유도 블록] 발견
       → "3분 무료 진단으로 플랜 추천받기" 클릭
       → 경로 A 합류
```

---

## 5. 구현 완료 체크리스트

- [x] `diagnosis-result-v2.html` — `#plan-recommend-section` HTML 추가
- [x] `loadPlanRecommend()` — BE-08 API 비동기 호출
- [x] `renderPlanRecommend()` — 플랜 카드 + 이유 + 비교 박스 렌더
- [x] 플랜별 색상 테마 (`PLAN_THEME` 맵)
- [x] `pricing.html` — `.diag-nudge-section` 추가
- [x] URL 파라미터 `highlight` / `recommend` 처리 → `highlightPlan()`
- [ ] BE-08 실 API 연동 테스트 (BE-08 완료 후)
- [ ] 과태료 비교 bar 시각화 고도화 (v2 예정)

---

## 6. 향후 개선 (v2)

- 과태료 비교를 숫자 텍스트 → 실제 progress bar 시각화
- 추천 플랜 카드에 "현재 내 의무 항목 N건" 수치 표시
- 플랜 추천 섹션 스켈레톤 로딩 (현재: 섹션 숨김 → 표시)
- A/B 테스트: 추천 섹션 위치 (result-grid 우측 사이드바 vs 하단 전체폭)
