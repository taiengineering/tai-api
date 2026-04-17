# FN-06 워크오더 (상세) — diagnosis-result-v2.html

**저장소:** tai-admin  
**브랜치:** main (기존 패턴 따름)  
**의존:** BE-08 Transform API 완료 후 착수  
**우선순위:** P1

---

## 배경

기존 `diagnosis-result.html`은 원시 법령엔진 JSON을 직접 파싱해 렌더링하는 구조였으나,
BE-08에서 Transform API(`GET /diagnosis/{id}/result/transformed`)가 완성됨에 따라
클라이언트 파싱 로직을 전면 제거하고 Transform API 응답만 소비하는 v2 렌더러 신규 제작.

---

## API 계약 (BE-08 기준)

```
GET /diagnosis/{id}/result/transformed
Authorization: Bearer {token}

Response 200:
{
  "diagnosis_id": "uuid",
  "sector": "BUILDING|INDUSTRY|CONSTRUCTION",
  "tier": "FREE|PAID1|PAID2|PAID3",
  "company_name": "string",
  "generated_at": "ISO8601",
  "schema_version": "v2026.04",
  "headline": {
    "summary": "string",
    "severity": "LOW|MEDIUM|HIGH|CRITICAL"
  },
  "obligations": [
    {
      "id": "uuid",
      "category": "선임|점검|신고|교육|서류",
      "title": "string",
      "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
      "description": "string",
      "evidence": ["string"],
      "action_url": "string|null",
      "auto_schedulable": bool
    }
  ],
  "warnings": [
    { "level": "INFO|WARN|DANGER", "message": "string" }
  ],
  "roi": {
    "penalty_max_krw": number,
    "subscription_annual_krw": number,   // DB에서 조회, 하드코딩 금지
    "roi_ratio": number,
    "breakeven_days": number
  },
  "inspection_schedule": [
    { "month": 1-12, "count": number, "items": ["string"] }
  ],
  "next_actions": [
    { "label": "string", "url": "string", "type": "primary|secondary" }
  ]
}
```

> **엔진 API 직접 호출 절대 금지.** 모든 데이터는 Transform API 단일 호출로만 취득.

---

## 레이아웃 명세

```
[상단] 헤드라인 카드 (severity 배지 + summary + company_name + generated_at)
[경고] warnings 배너 행 (level별 색상: INFO=blue, WARN=yellow, DANGER=red)

[2열 그리드 65/35]
┌─────────────────────────────────┬──────────────────────┐
│ 좌: 의무사항 5탭                │ 우: ROI 카드         │
│  탭: 선임/점검/신고/교육/서류   │     스케줄 히트맵    │
│  카드 리스트 (risk_level 정렬)  │     SaaS CTA         │
│  evidence 접힘 패널             │                      │
└─────────────────────────────────┴──────────────────────┘

[하단] next_actions 버튼 행
```

---

## 구현 상세

### 1) 헤드라인 카드
- severity → 배지 색상: LOW=secondary, MEDIUM=warning, HIGH=danger, CRITICAL=dark+빨강테두리
- company_name + sector + tier 표시
- generated_at 포맷: `YYYY년 MM월 DD일 HH:mm`

### 2) 경고 배너
- `warnings` 배열 순회. level별 `alert-info / alert-warning / alert-danger`
- 0건이면 배너 섹션 숨김

### 3) 의무사항 탭 (좌측 65%)
- 탭: 선임 / 점검 / 신고 / 교육 / 서류 (5개 고정)
- 각 탭 카운트 배지: `category` 필드 기준 분류
- 카드 내부: risk_level 아이콘 + title + description
- evidence 접힘: `<details>` 또는 Bootstrap collapse
- `auto_schedulable=true`이면 "자동일정 등록 가능" 배지 표시
- `action_url` 있으면 "해결하기" 버튼 노출 (없으면 숨김)
- 탭 내 카드가 0개이면 "해당 의무 없음" 빈 상태

### 4) ROI 카드 (우측 35%)
- `roi.penalty_max_krw` 강조 (font-size ≥ 32px, color #dc2626)
- `roi.subscription_annual_krw` 대비 절감액/비율 표시
- **가격 하드코딩 절대 금지** — API 응답값만 사용
- `roi.breakeven_days` → "손익분기 {N}일" chip
- "ROI 상세 보기" → `diagnosis-roi-dashboard.html?diagnosis_id={id}`

### 5) 스케줄 히트맵
- `inspection_schedule` 12개월 히트맵
- count 0=회색, 1-2=연파랑, 3-5=파랑, 6+=진파랑
- 클릭 시 해당 월 items 툴팁

### 6) SaaS CTA
- 비구독자: "구독 시 자동 처리" 배지 + 요금제 링크
- 구독자: "일정 자동 등록" 버튼 → work-schedule-list.html
- 구독 여부: `localStorage.get('contract_level')` 기준

### 7) next_actions
- `type=primary` → `btn-primary`, `type=secondary` → `btn-outline-secondary`
- 버튼 행, 우측 정렬

---

## 엣지 케이스

| 케이스 | 처리 |
|--------|------|
| `schema_version` != `v2026.04` | 상단 경고 배너 + 재진단 유도 CTA, 렌더링 중단 |
| `obligations` 빈 배열 | "적용 의무 없음" 카드 표시 |
| `roi` null | ROI 카드 섹션 숨김, 대신 "진단 업그레이드" CTA |
| API 404 | "진단 결과를 찾을 수 없습니다" + 목록 이동 버튼 |
| API 403 | 로그인 페이지 리다이렉트 |
| API 500 | 에러 메시지 + 재시도 버튼 |

---

## 파일 경로

```
tai-admin/
  tadmin/full-version/html/horizontal-menu-template/
    diagnosis-result-v2.html          ← 신규
```

기존 `diagnosis-result.html`은 삭제하지 않고 유지 (하위 호환).

---

## 완료 조건

- [ ] Transform API 단일 호출로 전체 렌더링 (엔진 API 직접 호출 0건)
- [ ] 5탭 모두 정상 분류 (탭별 빈 상태 처리 포함)
- [ ] ROI 수치 API 응답 기반 (하드코딩 0건)
- [ ] schema_version 불일치 시 graceful fallback
- [ ] 모바일 360px 가독성
- [ ] 인쇄(@media print) 기본 지원

---

## 금기

- 엔진 API(`/diagnosis/run`, `/legal/engine` 등) 직접 호출 금지
- 가격/비율 하드코딩 금지 (`roi` 객체 필드만 사용)
- 카카오 공유 금지
- v2026.04 미준수 JSON 임의 보완 렌더링 금지

---

## 실행 프롬프트

```
FN-06 착수. BE-08 완료 확인 후.
참고: tai-api/docs/workorder-FN06-result-renderer.md
신규 파일: diagnosis-result-v2.html
Transform API만 사용. 엔진 API 직접 호출 금지. 가격 하드코딩 금지.
```
