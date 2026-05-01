# TAI Safe 종합 정비 세션 — 2026-05-01

## 완료된 작업

### 1. KOSHA API callApiId 변경 대응 [COMPLETED]

KOSHA 포털 개편으로 callApiId 체계가 변경됨. data.go.kr 문서 확인 + 범위 스캔(1000~1100)으로 정확한 값 확인.

| API | 이전 callApiId | 신규 callApiId | 수집 건수 |
|---|---|---|---|
| 안전보건자료 | `1030` | `1030` (변경 없음) | **10,000건** |
| 국내재해사례 | `"한글 문자열"` | **`1040`** | **2,802건** |
| 건설 중대재해 | `1010` | **`1050`** | **1,039건** |
| 건설안전신호등 | `1020` | 모든 값 실패 | ❌ KOSHA 서버 장애 |
| 위험성평가 | 없음 | 모든 값 실패 | ❌ KOSHA 서버 장애 |

**변경 파일:**
- `routers/kosha_collect.py` v1.5.0 — 자동 분류 + callApiId 변경 + items() dict 파싱
- `routers/kosha_apis.py` v1.8.1 — debug-raw/test 엔드포인트 + callApiId 교체
- `docs/KOSHA_CALLAPIID_CHANGE.md` — callApiId 변경 이력 문서

### 2. 안전보건자료 자동 분류 [COMPLETED]

10,000건에 제목 기반 카테고리/업종 자동 분류 적용.

**카테고리 (11종):**
| 카테고리 | 건수 | 비율 |
|---|---|---|
| CASE_STUDY | 1,511 | 15.1% |
| FOREIGN | 1,448 | 14.5% |
| HEALTH | 1,062 | 10.6% |
| RESEARCH | 1,045 | 10.5% |
| POSTER | 870 | 8.7% |
| EDUCATION | 809 | 8.1% |
| GUIDE | 673 | 6.7% |
| VIDEO_VR | 655 | 6.6% |
| CHECKLIST | 53 | 0.5% |
| REGULATION | 7 | 0.1% |
| OTHER | 1,867 | 18.7% |

**업종 (4종):** COMMON(68%), CONSTRUCTION(14.7%), MANUFACTURING(13.4%), SERVICE(3.8%)

**DB 변경:** `kosha_safety_materials`에 `category`, `sector` 컬럼 + 인덱스 추가

### 3. 안전정보 4개 페이지 재설계 [COMPLETED]

**메뉴 재구성 (header.js):**
```
안전정보 > 안전자료 / 재해사례 / 개정법령 / 판례검색
```

| 페이지 | 파일 | 데이터 | 상태 |
|---|---|---|---|
| 안전자료 | `safety-news.html` | 10,000건+ | ✅ 검색 중심 재설계 + 최신 리스트 |
| 재해사례 | `accident-cases.html` | 2,802+1,039건 | ✅ 신규 생성 (탭 분리) |
| 개정법령 | `law-updates.html` | 95건 | ✅ 기존 유지 |
| 판례검색 | `precedent-search.html` | 849건 | ✅ 재구성 |

### 4. Supabase anon key 교체 [COMPLETED]

- `safety-news.html` — 깨진 JWT 서명 수정 (sed로 payload만 바뀌어 서명 무효화된 토큰)
- 서울 프로젝트 정식 anon key 적용
- `law_revision_board` status 통일: `PUBLISHED` 95건

### 5. 로고 이미지 최적화 [COMPLETED]

| 항목 | 변경 전 | 변경 후 | 절감 |
|---|---|---|---|
| 원본 | 1024×1024, **263KB** | 96×96, **21KB** | **92%** |
| 페이지당 | 526KB (헤더+푸터) | 42KB | **484KB** |

- Storage 업로드: `tai-icon-48.png`(6KB), `tai-icon-96.png`(21KB), `tai-icon-192.png`(84KB)
- `header.js` — ICON_URL을 `tai-icon-96.png`으로 교체
- 모바일 로고 크기 `!important` 오버라이드 (템플릿 CSS 충돌 수정)

### 6. 마이페이지 탑 메뉴 경로 버그 수정 [COMPLETED]

**원인:** `header.js`의 `legacyRelBase()` 함수에서 `/mypage/` (trailing slash만) 패턴 미처리 → `base = ''` → 모든 링크가 `/mypage/service/...`로 잘못 생성

**수정:** v3.5.1 — `/mypage(/|$)` 정규식으로 변경
```javascript
// 변경 전 (버그)
var m = path.match(/\/mypage\/(.+)/);
// 변경 후 (수정)
if (/\/mypage(\/|$)/.test(path)) {
  var after = path.replace(/.*\/mypage\/?/, '');
  ...
}
```

### 7. 요금제 페이지 관리 [COMPLETED - REVERTED]

- Cursor가 pricing.html, saas.html, diagnosis.html을 V3 가격으로 수정
- **이니시스 카드 심사 중이므로 원복 완료** (`git revert`)
- 이니시스 결제 정상 작동 확인: SaaS(145,000+VAT) + 법령진단(99,000+VAT) 결제창 로드 OK
- 작업지시서: `docs/WORK_INSTRUCTION_PRICING.md` (심사 후 적용)

### 8. for-business-owner 이미지 교체 [COMPLETED]

- `owner-vs.png` → `check.png` MCP로 직접 교체 완료

### 9. 히어로 높이 통일 작업 [REVERTED - PENDING]

- Cursor가 작업했으나 "이미지에 맞춰서 다 다르게 변경"되어 **원복됨** (`git revert bb52200`)
- 작업지시서: `docs/WORK_INSTRUCTION_HERO_HEIGHT.md` v2
- **대표님 요청:** 새 세션에서 한 페이지씩 직접 확인하며 MCP로 수정

---

## PENDING 이슈

| # | 이슈 | 상태 | 우선순위 |
|---|---|---|---|
| **HERO-01** | 히어로 높이 통일 (diagnosis 기준 420px, 안전정보 4개 제외) | 원복됨, 새 세션에서 재작업 | 🟡 |
| **HERO-02** | 스크롤 시 탑 배경색 통일 (navy gradient, tai-main.css) | 원복됨, 새 세션에서 재작업 | 🟡 |
| **MENU-01** | header.js에서 pricing.html 메뉴 숨김 | `sed -i '' '/pricing\.html/d'` 명령 실행 필요 | 🔴 |
| **FOOTER-01** | footer.js 로고 tai-icon-96.png 교체 | 터미널에서 sed 실행 필요 | 🟡 |
| **PRICE-01** | 요금제 V3 가격 반영 | 원복됨, 이니시스 심사 후 재적용 | ⚪ |
| **KOSHA-01** | 안전보건자료 나머지 20,547건 수집 | MAX_PAGES 제한 해제 필요 | 🟡 |
| **KOSHA-02** | 건설안전신호등/위험성평가 | KOSHA 서버 장애 대기 | ⚪ |
| **KOSHA-03** | 파일 다운로드 → Storage 저장 | Phase 2 | ⚪ |
| **PREC-01** | 판례 sector/hazard_type 자동 태깅 | 미착수 (849건 전부 NULL) | 🟡 |

---

## 변경된 파일 목록

### tai-api (백엔드)
- `routers/kosha_collect.py` v1.5.0 — 자동 분류 + callApiId 변경 대응 + items() dict 파싱
- `routers/kosha_apis.py` v1.8.1 — debug-raw/test + callApiId 교체
- `docs/KOSHA_CALLAPIID_CHANGE.md` — callApiId 변경 이력

### taieng (마케팅)
- `nexas/safety-news.html` — 검색 중심 재설계 + 최신 리스트 + anon key 교체
- `nexas/accident-cases.html` — 신규 생성 (국내재해+건설 탭)
- `nexas/precedent-search.html` — 재구성
- `nexas/law-updates.html` — anon key 교체
- `nexas/for-business-owner.html` — 이미지 check.png 교체
- `nexas/assets/js/header.js` v3.5.1 — 메뉴 4섹션 + 로고 최적화 + 모바일 로고 수정 + 마이페이지 경로 버그 수정
- `docs/WORK_INSTRUCTION_SAFETY_PAGES.md` — 안전정보 4개 페이지 작업지시서
- `docs/WORK_INSTRUCTION_PRICING.md` — 요금제 V3 가격 반영 작업지시서
- `docs/WORK_INSTRUCTION_HERO_HEIGHT.md` v2 — 히어로 높이 + 탑 배경색 통일 작업지시서

### Supabase
- `kosha_safety_materials`: category, sector 컬럼 + 인덱스 + 10,000건 분류
- `kosha_accident_cases`: title 필드 2,802건 채우기 + trigram 인덱스
- `industrial_accident_precedents`: trigram 인덱스 추가
- Storage: `tai-icon-48.png`(6KB), `tai-icon-96.png`(21KB), `tai-icon-192.png`(84KB) 업로드

---

## 지재권 확인

KOSHA 안전보건자료 → 저작권법 제24조의2 + 공공누리 제1유형 → 출처표시 조건 하 자유 이용 가능.
파일 스토리지 저장도 원본 그대로 제공 시 합법. 출처 표시 필수.

## 다음 세션 TODO

1. **히어로 높이 통일** — 새 세션에서 한 페이지씩 확인하며 MCP로 수정
2. **스크롤 탑 배경색 통일** — tai-main.css에 navy override 추가
3. **pricing.html 메뉴 숨김** — sed 명령 실행
4. **footer.js 로고 교체** — sed 명령 실행
5. **판례 자동 태깅** — sector/hazard_type 849건
6. **안전보건자료 추가 수집** — MAX_PAGES 해제 후 나머지 20,547건
