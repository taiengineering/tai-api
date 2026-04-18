# FN-05 + FN-06-T1 + FN-07: 프론트엔드 통합 작업

> **상태:** 🔲 대기 (선행조건: BE-09 완료)
> **대상 레포:** taiengineering/taieng (nexas/)
> **작업 브랜치:** main 직접 커밋
> **작업 창:** 프론트 창

---

## 선행조건

| 조건 | 내용 |
|------|------|
| BE-09 완료 | `GET /anonymous-diagnosis/{token}/recommend-plan` 엔드포인트 준비 |
| 경로 등록 | `/{token}` 파라미터 앞에 등록 — 경로 섀도잉 없음 확인 |

---

## PART 1: FN-05 — 정적 목업 → API 동적 전환

### 대상 파일
`nexas/free-diagnosis-result.html`

### 현재 상태 (추정)
정적 목업 HTML로 하드코딩된 결과 표시

### 변환 목표
```
현재: 하드코딩 목업 데이터
목표: GET /anonymous-diagnosis/{token}/transform 응답 기반 동적 렌더
```

### API
```
GET /anonymous-diagnosis/{token}/transform
→ 헤드라인 카드, 의무사항 목록, ROI, 스케줄 렌더
```

### URL 파라미터
```
free-diagnosis-result.html?token={anonymous_token}
```

### 렌더링 구조 (diagnosis-result-v2.html 참조)
- 헤드라인 카드 (`severity`, `summary`)
- 의무사항 탭 (전체/선임/점검/신고/교육/서류)
- ROI 카드 (`penalty_max_krw`, `roi_ratio`)
- 연간 스케줄 히트맵
- SaaS CTA (비구독자 전용)

### 스켈레톤 처리
```html
<!-- 로딩 중 스켈레톤 표시 → 렌더 완료 후 교체 -->
<div class="skeleton skel-line tall mb-2"></div>
```

---

## PART 2: FN-06-T1 — 플랜 추천 카드 블록

### 대상 파일
`nexas/free-diagnosis-result.html` (PART 1과 동일 파일)

### API 엔드포인트
```
GET /anonymous-diagnosis/{token}/recommend-plan
Authorization: 불필요 (익명 토큰 기반)
```

### BE-09 응답 스펙
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
  },
  "version": "v1"
}
```

### Sector 보정 테이블 (_SECTOR_NORMALIZE)
익명 진단 내부 코드 → 추천 엔진 코드 변환:

| 익명 진단 내부 코드 | 추천 엔진 코드 |
|--------------------|--------------:|
| `MANUFACTURING`     | `INDUSTRY`     |
| `INDUSTRY`          | `INDUSTRY`     |
| `SPECIAL_FACILITY`  | `BUILDING`     |
| `BUILDING`          | `BUILDING`     |
| `CONSTRUCTION`      | `CONSTRUCTION` |

### 입력 변수 fallback 체인
| 변수 | 1순위 | fallback |
|------|-------|---------|
| `severity` | `full_result.headline.severity` | `full_result.risk_level` → `"LOW"` |
| `obl_cnt` | `len(full_result.key_obligations)` | `full_result.applicable_count` → `0` |
| `workers` | `input_data.workers` | `0` |

### BE 코드 재사용 구조 (참조용)
```python
# BE-09 — BE-08 함수 import (중복 0줄)
from routers.diagnosis_plan_recommend import (
    _recommend_industry, _recommend_building, _recommend_construction,
    _build_alternatives, _build_comparison,
    VERSION as PLAN_RECOMMEND_VERSION,
)
```

### UI 위치
`PART 1` 렌더 완료 후 하단 — `next-actions` 위

```html
<div class="mt-4" id="anon-plan-recommend-section" style="display:none;">
  <div class="card">
    <div class="card-header pb-2">
      <h5 class="mb-0">📊 진단 기반 맞춤 플랜 추천</h5>
    </div>
    <div class="card-body" id="anon-plan-recommend-body"><!-- JS 렌더 --></div>
  </div>
</div>
```

### UI 구성 (좌우 2컬럼)

#### 왼쪽 (col-md-4) — 추천 플랜 카드
```
┌────────────────────────────┐
│  [BUSINESS] 뱃지            │
│  ₩149,000 / 월              │
│  이 사업장에 가장 적합합니다  │
│                             │
│  [🚀 지금 구독 시작]        │
│  [전체 플랜 비교]           │
└────────────────────────────┘
```
- 구독 CTA → `pricing.html?recommend={plan}&token={token}`
- 플랜 비교 → `pricing.html`

#### 오른쪽 (col-md-8) — 이유 + 과태료 비교
```
추천 이유:
  ✓ 의무 항목 73건 — STARTER 한도 초과
  ✓ 위험도 HIGH — 적극 대응 필요
  ✓ 작업자 120명 — 중규모 기준

과태료 리스크 vs 구독료:
  최대 과태료    21,000,000원  ← 빨간색
  BUSINESS 연간   1,788,000원  ← 초록색
  절감 효과: 11.7배

다른 플랜: STARTER · PRO
```

### 플랜별 색상 테마
```js
const PLAN_THEME = {
  STARTER:  { bg:'#f0fdf4', border:'#16a34a', text:'#15803d' },
  BUSINESS: { bg:'#eff6ff', border:'#1d4ed8', text:'#1e40af' },
  PRO:      { bg:'#fdf4ff', border:'#7c3aed', text:'#6d28d9' },
  CUSTOM:   { bg:'#fff7ed', border:'#ea580c', text:'#c2410c' },
};
const PLAN_PRICE = {
  STARTER:'79,000', BUSINESS:'149,000', PRO:'249,000', CUSTOM:'협의',
};
```

### 동작 규칙
| 조건 | 동작 |
|------|------|
| `recommended` 없음 | 섹션 `display:none` 유지 |
| API 오류 | 조용히 실패 — PART 1 렌더 블록하지 않음 |
| 정상 응답 | 섹션 표시 |

### JS 구조
```js
async function loadAnonPlanRecommend(token) {
  if (!token) return;
  try {
    const res = await fetch(
      `https://api.taieng.co.kr/anonymous-diagnosis/${token}/recommend-plan`
    );
    if (!res.ok) return;
    const data = await res.json();
    renderAnonPlanRecommend(data);
  } catch (e) {
    // 조용히 실패
  }
}

// PART 1 로드 완료 후 호출
load().then(() => loadAnonPlanRecommend(token));
```

---

## PART 3: FN-07 — "전문가 상담" 버튼 전수 삭제

### 대상
`nexas/` 전체 HTML 파일

### 삭제 대상 패턴
다음 텍스트를 포함한 버튼/링크/블록 전체 제거:
- `전문가 상담`
- `전문가 연결`
- `전문가 매칭`
- `전문가에게 문의` (문맥 확인 후 판단)

### 삭제 예시
```html
<!-- 삭제 전 -->
<a href="appointment.html" class="btn btn-primary">전문가 상담 신청</a>

<!-- 삭제 후 → 제거 또는 "도입 문의"로 대체 -->
<a href="contact.html" class="btn btn-outline-secondary">도입 문의하기</a>
```

### 대체 방향
| 삭제 버튼 | 대체 버튼 (선택적) |
|-----------|------------------|
| 전문가 상담 신청 | 도입 문의하기 → `contact.html` |
| 전문가 연결 | (삭제만, 대체 없음) |

### 확인 대상 파일 목록 (예상)
```
nexas/index.html
nexas/for-business-owner.html
nexas/for-safety-manager.html
nexas/free-diagnosis.html
nexas/free-diagnosis-result.html
nexas/service/*.html
nexas/target/*.html
```

### 주의사항
- `service/appointment.html` 자체는 삭제 금지 (직접 URL 접근 가능하도록 유지)
- 단순 버튼/CTA에서만 제거
- "전문가" 단어가 포함된 설명 텍스트(본문)는 건드리지 않음

---

## 작업 절차

### 준비
1. BE-09 완료 확인
2. `GET /anonymous-diagnosis/{token}/recommend-plan` 테스트 응답 확인

### PART 1 + 2 (같은 파일)
1. `github-tai:get_file_contents` → `nexas/free-diagnosis-result.html` SHA 확인
2. 정적 목업 → API 동적 전환 (PART 1)
3. 플랜 추천 섹션 추가 (PART 2)
4. `github-tai:create_or_update_file` → main 직접 커밋

### PART 3
1. nexas/ 파일 목록 확인
2. 각 파일에서 "전문가 상담" 패턴 검색 및 삭제
3. `github-tai:push_files` 로 한 번에 커밋

---

## 완료 체크리스트

- [ ] `free-diagnosis-result.html` — PART 1 API 동적 전환
- [ ] `free-diagnosis-result.html` — PART 2 플랜 추천 섹션 추가
- [ ] `loadAnonPlanRecommend()` — 토큰 기반 BE-09 호출
- [ ] `renderAnonPlanRecommend()` — 카드 + 이유 + 비교 렌더
- [ ] nexas/ 전체 — "전문가 상담" 버튼 전수 삭제 (PART 3)
- [ ] pricing.html URL 파라미터 `token` 전달 확인
