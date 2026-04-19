# FN-05: 진단 결과 페이지 동적 렌더러

**작성일**: 2026-04-18  
**작성자**: 기획창  
**선행조건**: 없음 (현재 API 구조만으로 구현 가능)  
**적용 위치**: taiengineering/taieng → nexas/free-diagnosis-result.html  
**배포**: main 브랜치 (Cloudflare Pages 자동 배포)  

---

## 배경

현재 `free-diagnosis-result.html`은 **전체가 정적 목업 데이터**.
"위험도: 높음", "3개 항목 위반", "산업·제조" 등 모두 하드코딩.
API 호출 코드 없음. 어떤 진단을 해도 같은 결과 화면이 나옴.

이 페이지를 **동적으로 전환**하여 실제 진단 결과 데이터를 렌더링해야 함.

---

## 데이터 소스

### API 엔드포인트

**무료진단 결과 조회:**
```
GET /anonymous-diagnosis/{public_token}
```

**응답 구조:**
```json
{
  "status": "success",
  "data": {
    "publicToken": "uuid-string",
    "partialResult": {
      "risk_level": "HIGH",
      "summary": "적용된 의무 121건 발견",
      "applicable_count": 121,
      "sector": "INDUSTRY",
      "key_obligations": [...],
      "rules_preview": [...],
      "law_badges": [...],
      "message": "일부 결과만 표시됩니다..."
    },
    "fullResult": null,
    "canViewFull": false,
    "expiresAt": "2026-04-25T..."
  }
}
```

### URL 파라미터

진단 완료 후 리다이렉트: `free-diagnosis-result.html?token={public_token}`

---

## TASK

### 1. 페이지 진입 시 API 호출

```javascript
const API_BASE = 'https://api.taieng.co.kr';
const token = new URLSearchParams(location.search).get('token');

if (!token) {
  // 토큰 없이 직접 접근 → 무료진단 페이지로 리다이렉트
  location.href = 'free-diagnosis.html';
}

fetch(`${API_BASE}/anonymous-diagnosis/${token}`)
  .then(r => r.json())
  .then(data => renderResult(data.data))
  .catch(() => renderError());
```

### 2. 렌더링 영역 (동적 교체)

| 영역 | 현재 (하드코딩) | 변경 후 (API 데이터) |
|---|---|---|
| 위험도 배지 | "⚠ 위험도 : 높음" | `partialResult.risk_level` 매핑 |
| 히어로 h1 | "현재 3개 항목 위반 가능성" | `partialResult.summary` 또는 `applicable_count` 기반 |
| 사업장 유형 | "산업·제조" | `partialResult.sector` 한글 매핑 |
| 적용 법령 수 | "산업안전보건법 외 4개" | `partialResult.law_badges` 배열 길이 |
| 법정 점검 항목 | "17개 항목" | `partialResult.applicable_count` |
| 주요 위험 항목 목록 | 하드코딩 4건 | `partialResult.key_obligations` 배열 반복 렌더 |

### 3. sector 한글 매핑

```javascript
const SECTOR_LABEL = {
  INDUSTRY: '제조·산업',
  BUILDING: '건물·시설',
  CONSTRUCTION: '건설현장',
  MANUFACTURING: '제조·산업',
  SPECIAL_FACILITY: '특수시설'
};
```

### 4. risk_level 배지 매핑

```javascript
const RISK_MAP = {
  CRITICAL: { label: '매우 높음', class: 'risk-high', color: '#dc2626' },
  HIGH:     { label: '높음',     class: 'risk-high', color: '#dc2626' },
  MEDIUM:   { label: '중간',     class: 'risk-mid',  color: '#d97706' },
  LOW:      { label: '낮음',     class: 'risk-low',  color: '#1a8f4b' }
};
```

### 5. key_obligations 렌더링

각 항목 구조 (예상):
```json
{
  "title": "안전관리자 미선임",
  "description": "50인 이상 사업장은...",
  "severity": "HIGH",
  "penalty": "최대 500만원"
}
```

→ 기존 `.risk-item` HTML 구조 재사용하되 동적 생성.

### 6. 에러/만료 처리

| 상황 | 처리 |
|---|---|
| 토큰 없음 | free-diagnosis.html 리다이렉트 |
| 404 (토큰 없음) | "진단 결과를 찾을 수 없습니다" + 재진단 버튼 |
| 410 (만료) | "진단 결과가 만료되었습니다 (7일)" + 재진단 버튼 |
| 네트워크 오류 | "일시적 오류" + 새로고침 버튼 |

### 7. 로딩 상태

- API 호출 중: 스켈레톤 UI (pricing.html 패턴 재사용)
- 히어로: 배지 + h1 자리에 스켈레톤 바
- 카드 영역: skel-card 2~3개

### 8. CTA 영역 변경

현재:
```
[TAI Safe 시작하기] → service/saas.html
[전문가 상담 신청]  → contact.html     ← 삭제 대상
```

변경:
```
[이 사업장에 맞는 플랜 확인하기] → #plan-recommend (FN-06 블록 앵커)
[전체 요금제 비교하기]           → pricing.html
```

---

## 디자인 가이드

- 현재 CSS 구조 유지 (`.result-hero`, `.result-card`, `.risk-item` 등)
- 밝은 톤 유지 (사업주 페이지와 동일 원칙)
- 스켈레톤은 pricing.html의 `.skeleton`, `.skel-card` 클래스 재사용
- 색상: var(--navy), var(--red), var(--sub) 기존 변수 사용

---

## 완료 조건

- [ ] token 파라미터로 API 호출 → 결과 동적 렌더링
- [ ] 위험도 배지 동적 표시
- [ ] 사업장 유형 동적 표시
- [ ] key_obligations 목록 동적 렌더링
- [ ] law_badges 표시
- [ ] 에러/만료/토큰없음 각각 처리
- [ ] 로딩 스켈레톤 표시
- [ ] CTA에서 "전문가 상담 신청" 제거
- [ ] 하드코딩된 목업 데이터 전부 제거
- [ ] 모바일 반응형 확인

---

## 금기

- 하드코딩 데이터 잔존 금지
- 전문가 상담 버튼 금지
- 데모 제공 금지
- fullResult 비로그인 노출 금지 (partialResult만 사용)
- main 직접 커밋 금지 (예외: 프론트 taieng 레포는 main 허용)
