# FN-06 TASK 1: 진단 결과 페이지 플랜 추천 블록

**작성일**: 2026-04-18  
**작성자**: 기획창  
**선행조건**: FN-05 완료 (동적 렌더러), BE-08 완료 (플랜 추천 API)  
**적용 위치**: taiengineering/taieng → nexas/free-diagnosis-result.html  
**배포**: main 브랜치  

---

## 배경

FN-05가 진단 결과를 동적으로 렌더링한 후,
그 아래에 BE-08 API를 호출하여 **적합 플랜 추천 카드**를 표시.

사용자 경로:
```
무료진단 완료 → 결과 확인 → 플랜 추천 카드 → [이 플랜으로 시작하기]
```

---

## 데이터 소스

### API 엔드포인트

진단 결과 페이지에서 diagnosis_id가 아닌 **anonymous token** 기반이므로,
별도 매핑이 필요할 수 있음.

**방법 A (추천):** anonymous_diagnosis 응답에서 factory_diagnosis_results.id를 포함시키고,
그 id로 BE-08 호출:
```
GET /diagnosis/{diagnosis_id}/recommend-plan
```

**방법 B (대안):** anonymous_diagnosis 응답의 partialResult에서 직접 추천 로직을
프론트에서 실행 (백엔드 호출 없이). → 로직 중복 위험.

**→ 방법 A 채택. anonymous_diagnosis 응답에 `diagnosis_id` 필드 추가 필요
  (또는 partialResult에 포함).**

### BE-08 응답 구조 (recommend-plan)

```json
{
  "recommended": {
    "plan_code": "INDUSTRY_BUSINESS_V2",
    "plan_name": "산업 BUSINESS",
    "monthly_krw": 149000,
    "is_custom": false
  },
  "reasons": [
    "의무 항목 128건 — STARTER로는 관리 범위 부족",
    "위험도 HIGH — 자동 알림·누락 추적이 필수적인 수준"
  ],
  "alternatives": {
    "lower": { "plan_code": "INDUSTRY_STARTER_V2", ... },
    "upper": { "plan_code": "INDUSTRY_PRO", ... }
  },
  "comparison": {
    "annual_penalty_risk_krw": 87000000,
    "tai_safe_annual_krw": 1788000,
    "note": "TAI Safe 연간 1,788,000원으로 최대 87,000,000원 과태료 위험을 관리합니다"
  }
}
```

---

## TASK

### 1. 블록 위치

진단 결과 카드(col-lg-8) **아래**, CTA 영역 **위**에 풀너비로 배치.

```
[진단 결과 카드들]
─────────────────────
[★ 플랜 추천 블록]    ← 여기
─────────────────────
[CTA]
```

### 2. 레이아웃

```
┌─────────────────────────────────────────────┐
│  📊 이 사업장에 맞는 플랜                      │
│                                             │
│  ┌─ 추천 카드 ────────────────────────────┐  │
│  │  ★ 추천                                │  │
│  │  BUSINESS  월 149,000원                │  │
│  │                                       │  │
│  │  이 플랜이 맞는 이유:                    │  │
│  │  ✓ 의무 항목 128건 — STARTER로는 부족    │  │
│  │  ✓ 위험도 HIGH — 자동 알림 필수          │  │
│  │  ✓ 작업자 85명 — 분산 점검 지원          │  │
│  │                                       │  │
│  │  ┌ 비교 ─────────────────────┐         │  │
│  │  │ 과태료 위험  8,700만원      │         │  │
│  │  │ TAI 1년     178.8만원      │         │  │
│  │  └──────────────────────────┘         │  │
│  │                                       │  │
│  │  [이 플랜으로 시작하기]                   │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  다른 플랜 비교하기 →                          │
└─────────────────────────────────────────────┘
```

### 3. 동작

1. FN-05 진단 결과 로드 완료 후, BE-08 API 호출
2. 응답 수신 → 추천 카드 렌더링
3. 비교 블록: `comparison` 데이터로 과태료 vs 구독료 표시
4. "이 플랜으로 시작하기" → `pricing.html?highlight={plan_code}`
5. "다른 플랜 비교하기" → `pricing.html`

### 4. 에러 처리 (fallback)

- BE-08 API 실패 시 → 추천 블록 숨김, "전체 요금제 보기" 링크만 표시
- diagnosis_id 없는 경우 → 추천 블록 표시 안 함

### 5. 디자인

- 카드: 흰색 배경, border-top 4px #0f172a, 라운드 18px, 그림자
- ★ 추천 배지: 네이비 배경 + 흰색 텍스트, 좌측 상단
- reasons: ✓ 아이콘 + 텍스트, 간결하게
- 비교 블록: 라이트그레이 배경, 과태료 금액 볼드
- CTA 버튼: btn-navy 스타일
- 사업주 페이지와 동일 톤 (밝은 배경, 네이비 포인트)

---

## 선행 작업 (백엔드 수정 필요)

### anonymous_diagnosis 응답에 diagnosis_id 포함

현재 anonymous_diagnosis는 `factory_diagnosis_results`를 직접 사용하지 않고
별도 `anonymous_diagnosis_results` 테이블에 저장.

**2가지 해결 방법:**

**A. 프론트 자체 추천 (권장):**
- partialResult에 sector, risk_level, applicable_count가 이미 있음
- 프론트에서 간단한 조건 분기로 추천 (BE-08 로직의 축약 버전)
- 장점: 추가 API 호출 불필요, anonymous 테이블과 factory_diagnosis_results 연결 불필요
- 단점: 로직 중복 (하지만 무료진단은 간소화된 추천이면 충분)

**B. BE-08에 anonymous 지원 추가:**
- `GET /anonymous-diagnosis/{token}/recommend-plan` 엔드포인트 추가
- anonymous_diagnosis_results의 full_result에서 직접 추천
- 장점: 로직 단일화
- 단점: 추가 개발

**→ 프론트창에서 방법 결정 후 진행.**

---

## 완료 조건

- [ ] 진단 결과 아래 플랜 추천 카드 표시
- [ ] reasons[] 목록 렌더링 (최소 2개)
- [ ] comparison 블록 (과태료 vs 구독료) 표시
- [ ] "이 플랜으로 시작하기" → pricing.html?highlight= 연동
- [ ] API 실패 시 fallback 정상 동작
- [ ] 모바일 반응형

---

## 금기

- 전문가 상담 버튼 금지
- 데모 제공 금지
- 가격 하드코딩 금지 (API 응답값 사용)
- fullResult 비로그인 노출 금지
