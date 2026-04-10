# TAI 작업 세션 — 2026-04-10 (이창)

> 창 역할: 서비스 기획 / PM
> 작업 범위: 기획 문서 보관 + 백엔드 구조 설계 + API 점검

---

## 완료 작업

### 1. 안전정보 API 점검 (`/posts`)

- 엔드포인트 3개 모두 200 정상 응답 확인
- `posts` 테이블 데이터 **0건** (테이블 스키마는 정상)
- 실제 경로: `/posts` (not `/safety-news`)

| 엔드포인트 | 상태 |
|---|---|
| `GET /posts?page=1&size=3` | ✅ 200 OK |
| `GET /posts/latest?limit=3` | ✅ 200 OK |
| `GET /posts/stats/today` | ✅ 200 OK |

**내일 진행 필요:** posts 데이터 채우기 (크롤러 or 어드민 등록 UI)

---

### 2. 가격 컨트롤 구조 설계 및 구축

**문제 인식:** 어드민과 new.taieng.co.kr의 가격이 각각 하드코딩되어 있어 불일치 위험 존재

**설계한 구조:**
```
어드민 price-setting.html
        ↓ PATCH
API /products/pricing/{id}
        ↓ ↑
DB product_pricing 테이블
        ↑
GET /products/pricing
        ↓
new.taieng.co.kr + pricing.html 양쪽 동시 적용
```

#### DB — `product_pricing` 테이블 생성

| 컬럼 | 내용 |
|---|---|
| `plan_code` | BASIC / PREMIUM / ENTERPRISE |
| `price_monthly` | 월 기본 가격 (정수, 원) |
| `features` | JSONB — 기능 목록 |
| `is_active` | 노출 여부 |
| `is_featured` | 추천 뱃지 여부 |
| `badge_text` | 뱃지 텍스트 |
| `cta_text` | 버튼 텍스트 |

초기 데이터: BASIC(79,000) / PREMIUM(149,000) / ENTERPRISE(협의) 3건 삽입

#### 백엔드 — `routers/product_pricing.py` 신규 생성

| 엔드포인트 | 용도 |
|---|---|
| `GET /products/pricing` | 공개 — 프론트에서 호출 |
| `GET /products/pricing/admin/all` | 어드민 전용 (비활성 포함) |
| `PATCH /products/pricing/{id}` | 어드민 가격·기능·활성화 수정 |

#### `main.py` v5.7.7 업데이트
- `product_pricing_router` 등록

#### ⚠️ 미완성
- 어드민 `price-setting.html` — push 중 잘림, 내일 완성 필요
- `pricing.html` (safe) — API 연동 교체 필요
- `nexas/index-1.html` (new) — API 연동 교체 필요

---

### 3. 기획 문서 보관 (tai-api/docs/)

| 파일명 | 내용 |
|---|---|
| `TAI_서비스_장점_이창안전관리자_리뷰.md` | 20년 현장 안전관리자 시각의 서비스 장점 정리 |
| `TAI_법령진단가격기획.md` | 건설/시설/산업별 진단 가격 구조 전략 |
| `TAI_전체과금수익구조_전략통합.md` | 법령진단 + 전체 SaaS/연결/수익 구조 통합 정책 |

---

### 4. 창 운영 구조 논의 및 확정

**결론:** 가격 정책 토론은 별도 창에서 진행
- 이창 역할: 확정된 내용 보관 + 실행 연결
- 토론 창 역할: 가격/정책 옵션 검토
- 확정 후 이창에 가져와서 깃 보관

---

## 내일 진행 예정

1. **어드민 `price-setting.html` 완성** — 가격/기능 편집 UI
2. **`pricing.html` API 연동** — 하드코딩 제거
3. **`nexas/index-1.html` API 연동** — 하드코딩 제거
4. **안전정보 데이터 채우기** — 방향 결정 후 진행
5. **DB 인덱스 최적화** — seq_scan 높은 테이블 대상 (law_parsing_result 등)

---

## 변경된 파일 목록

### taiengineering/tai-api
| 파일 | 변경 내용 |
|---|---|
| `main.py` | v5.7.7 — product_pricing_router 등록 |
| `routers/product_pricing.py` | 신규 — 요금제 공개/어드민 API |
| `docs/TAI_서비스_장점_이창안전관리자_리뷰.md` | 신규 |
| `docs/TAI_법령진단가격기획.md` | 신규 |
| `docs/TAI_전체과금수익구조_전략통합.md` | 신규 |
| `docs/SESSION_20260410.md` | 신규 (이 파일) |

### Supabase DB
| 항목 | 변경 내용 |
|---|---|
| `product_pricing` 테이블 | 신규 생성 + 초기 데이터 3건 |
