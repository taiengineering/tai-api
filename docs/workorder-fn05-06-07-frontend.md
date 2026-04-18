# FN-05+06+07 통합: 진단 결과 동적 전환 + 플랜 추천 + 상담버튼 삭제

**작성일**: 2026-04-18
**작성자**: 기획창
**선행조건**: BE-09 완료 (anonymous 플랜 추천 API)
**적용 위치**: taiengineering/taieng → nexas/
**배포**: main 브랜치 (Cloudflare Pages 자동 배포)

---

## 대상 파일

| 파일 | 변경 내용 |
|---|---|
| **free-diagnosis-result.html** | 전면 재작성 (정적→동적 + 플랜 추천 블록 + 상담버튼 삭제) |
| **pricing.html** | "직접 상담을 원하시면" 링크 삭제 |
| **기타 nexas/*.html** | "전문가 상담" 버튼 전수 스캔 + 삭제 |

---

## PART 1: free-diagnosis-result.html 동적 전환 (FN-05)

### 데이터 소스

```javascript
const API = 'https://api.taieng.co.kr';
const token = new URLSearchParams(location.search).get('token');

if (!token) {
  location.href = 'free-diagnosis.html';
  return;
}

// 1. 진단 결과 로드
const resultRes = await fetch(`${API}/anonymous-diagnosis/${token}`);
const resultData = await resultRes.json();

// 2. 플랜 추천 로드 (BE-09)
const planRes = await fetch(`${API}/anonymous-diagnosis/${token}/recommend-plan`);
const planData = await planRes.json();
```

### 동적 렌더링 영역

| 영역 | 현재 (하드코딩) | 변경 후 |
|---|---|---|
| 위험도 배지 | "⚠ 위험도 : 높음" | `partialResult.risk_level` → RISK_MAP 매핑 |
| h1 | "현재 3개 항목 위반 가능성" | `partialResult.summary` 또는 applicable_count 기반 |
| 사업장 유형 | "산업·제조" | `partialResult.sector` → SECTOR_LABEL 매핑 |
| 적용 법령 수 | "산업안전보건법 외 4개" | `partialResult.law_badges` 배열 길이 |
| 법정 점검 항목 | "17개 항목" | `partialResult.applicable_count` |
| 위험 항목 목록 | 하드코딩 4건 | `partialResult.key_obligations` 배열 반복 렌더 |

### 매핑 상수

```javascript
const SECTOR_LABEL = {
  INDUSTRY: '제조·산업', MANUFACTURING: '제조·산업',
  BUILDING: '건물·시설', CONSTRUCTION: '건설현장',
  SPECIAL_FACILITY: '특수시설'
};

const RISK_MAP = {
  CRITICAL: { label: '매우 높음', class: 'risk-high' },
  HIGH:     { label: '높음',     class: 'risk-high' },
  MEDIUM:   { label: '중간',     class: 'risk-mid' },
  LOW:      { label: '낮음',     class: 'risk-low' }
};
```

### 에러/만료 처리

| 상황 | 동작 |
|---|---|
| 토큰 없음 | `free-diagnosis.html`로 리다이렉트 |
| 404 | "진단 결과를 찾을 수 없습니다" + [다시 진단하기] |
| 410 (만료) | "진단 결과가 만료되었습니다 (7일)" + [다시 진단하기] |
| 네트워크 오류 | "일시적 오류" + [새로고침] |

### 로딩 상태

- 히어로: 배지 + h1 자리에 스켈레톤 바
- 카드 영역: skel-card 2~3개
- pricing.html의 `.skeleton`, `.skel-card` 클래스 재사용

---

## PART 2: 플랜 추천 블록 (FN-06-T1)

### 위치

진단 결과 카드 **아래**, 하단 CTA **위**에 풀너비 배치.

### 데이터

`GET /anonymous-diagnosis/{token}/recommend-plan` 응답 사용.

### 레이아웃

```
┌──────────────────────────────────────────────┐
│  📊 이 사업장에 맞는 플랜                      │
│                                              │
│  ┌─ 추천 카드 ──────────────────────────────┐ │
│  │  ★ 추천                                 │ │
│  │  BUSINESS  월 149,000원                  │ │
│  │                                         │ │
│  │  이 플랜이 맞는 이유:                      │ │
│  │  ✓ 의무 항목 128건 — STARTER로는 부족      │ │
│  │  ✓ 위험도 HIGH — 자동 알림 필수            │ │
│  │                                         │ │
│  │  ┌ 비교 ─────────────────┐               │ │
│  │  │ 과태료 위험  8,700만원  │               │ │
│  │  │ TAI 1년     178.8만원  │               │ │
│  │  └────────────────────────┘               │ │
│  │                                         │ │
│  │  [이 플랜으로 시작하기]                     │ │
│  └──────────────────────────────────────────┘ │
│                                              │
│  전체 요금제 비교하기 →                         │
└──────────────────────────────────────────────┘
```

### 동작

| 버튼 | 동작 |
|---|---|
| "이 플랜으로 시작하기" | `pricing.html?highlight={plan_code}` 이동 |
| "전체 요금제 비교하기" | `pricing.html` 이동 |

### API 실패 시

추천 블록 숨기고 "전체 요금제 보기" 링크만 표시.

### 디자인

- 카드: 흰색 배경, border-top 4px #0f172a, 라운드 18px, 그림자
- ★ 추천 배지: 네이비 배경 + 흰색 텍스트, 좌측 상단
- reasons: ✓ 아이콘 + 텍스트
- 비교 블록: 라이트그레이 배경, 과태료 금액 볼드
- CTA 버튼: btn-navy 스타일
- **밝은 톤 유지** (사업주 페이지와 동일 원칙)

---

## PART 3: "전문가 상담" 버튼 전수 삭제 (FN-07)

### 원칙

> TAI는 상담 서비스가 아닙니다.
> 데이터 입력 → 엔진 가동 → 자동 판단 → 실행 구조입니다.

### 대상

nexas/ 전체 HTML에서 아래 텍스트 포함 **버튼/링크** 삭제:

| 검색 키워드 | 삭제 대상 |
|---|---|
| `전문가 상담 요청` | `<a>` 또는 `<button>` 전체 |
| `전문가 상담 신청` | `<a>` 또는 `<button>` 전체 |
| `직접 상담을 원하시면` | 해당 링크 전체 |

### 확인된 잔존 위치

| 파일 | 위치 | 상태 |
|---|---|---|
| for-business-owner.html | 히어로, CTA | ✅ 이미 삭제됨 |
| **free-diagnosis-result.html** | CTA 사이드바 | ❌ 잔존 → 삭제 |
| **pricing.html** | 진단유도 블록 하단 | ⚠️ 잔존 → 삭제 |
| 기타 | 미확인 | 전수 스캔 필요 |

### 예외 (삭제하지 않는 것)

- `contact.html` 페이지 자체 (문의 폼 페이지 유지)
- "도입 문의하기" 버튼 (상담이 아닌 문의)
- 본문에서 "전문가"를 언급하는 경우 (버튼이 아니면 유지)

---

## CTA 최종 구조 (free-diagnosis-result.html)

### 변경 전
```
[TAI Safe 시작하기]      → service/saas.html
[전문가 상담 신청]        → contact.html       ← 삭제
[결과 이메일로 받기]      ← 유지
[← 다시 진단하기]        ← 유지
```

### 변경 후
```
[이 사업장에 맞는 플랜 확인하기]  → #plan-recommend 앵커
[전체 요금제 비교하기]           → pricing.html
[결과 이메일로 받기]             ← 유지
[← 다시 진단하기]               ← 유지
```

---

## 완료 조건

### FN-05 (동적 전환)
- [ ] token 파라미터로 API 호출 → 결과 동적 렌더링
- [ ] 위험도 배지 동적 표시
- [ ] 사업장 유형 동적 표시
- [ ] key_obligations 목록 동적 렌더링
- [ ] 에러/만료/토큰없음 각각 처리
- [ ] 로딩 스켈레톤
- [ ] 하드코딩 데이터 전부 제거

### FN-06-T1 (플랜 추천)
- [ ] BE-09 API 호출 → 추천 카드 렌더링
- [ ] reasons[] 목록 표시 (최소 2개)
- [ ] comparison 블록 (과태료 vs 구독료)
- [ ] "이 플랜으로 시작하기" → pricing.html?highlight= 연동
- [ ] API 실패 시 블록 숨김 + fallback

### FN-07 (상담 버튼 삭제)
- [ ] free-diagnosis-result.html "전문가 상담 신청" 삭제
- [ ] pricing.html "직접 상담을 원하시면" 삭제
- [ ] nexas/ 전체 스캔 완료
- [ ] 삭제 후 레이아웃 깨짐 없음

---

## 금기

- 전문가 상담 버튼 신규 추가 금지
- 하드코딩 데이터 잔존 금지
- 데모 제공 금지
- 가격 하드코딩 금지 (API 응답값 사용)
- fullResult 비로그인 노출 금지 (partialResult만 사용)
