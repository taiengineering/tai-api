# 세션 로그 — 2026-04-26 (기획창 + Cursor 협업)

## 1. safe.taieng.co.kr 기능/오류 분석 + 치명적 이슈 수정

### 분석 (Chrome MCP + GitHub MCP + Supabase)
- 메뉴→파일 매핑 35/35 전부 존재 (깨진 링크 없음)
- DB: `master_building_legal_rules` 3,820 active, `companies` 27, `users` 18
- 14건 발견 (🔴3 / 🟡6 / 🟢5)

### 수정 완료

| # | 이슈 | 수정 |
|---|---|---|
| 🔴1 | BUILDING→FACILITY 섹터 매핑 불일치 | `auth-login-cover.html` PLAN_MAP 수정 |
| 🔴2 | 비밀번호 찾기 API 미연동 | `pw_reset.py` 신규 + 프론트 모달 API 연동 |
| 🔴3 | STANDARD plan_code 미등록 | PLAN_MAP legacy 호환 + DB null→INDUSTRY_STARTER_V2 |
| 🟡4 | 로고 404 | tai-logo.png → branding/logo.png |
| 🟡5 | 통계 473 → 3,820 | 반영 |
| 🟡6 | 요금제 링크 깨짐 | pricing.html → new.taieng.co.kr/pricing |

### 배포
- tai-admin main: `e3979a9` (Cloudflare Pages)
- tai-api main: `a95b8dc` v5.36.1 (Railway 자동배포)
- DB: contracts null plan_code UPDATE

---

## 2. 서비스 레이어 분리 — DEV_RULES 대상 6건 전부 완료

기획창(Claude)에서 설계서 작성 → Cursor에서 STEP 0~5 실행 → 기획창에서 검증 + 머지

### payment.py (72KB → 12KB)
- 설계서: `docs/WORKORDER_payment_split.md` + `docs/WORKORDER_payment_html_split.md`
- Cursor 1차: STEP 0~5 (helpers, schemas, svc) — 72→62KB
- Cursor 2차: HTML 3개 파일 분리 (templates/payment/) — 62→30KB
- Cursor 3차: 잔여 로직 분리 (payment_ops.py) — 30→12KB
- 테스트 16개, 전부 PASS

### matching.py (42KB → 5.3KB)
- 설계서: `docs/WORKORDER_matching_split.md`
- Cursor: STEP 0~5 한번에 완료
- matching_svc/ 패키지 분할 (request, results, dashboard, errors)
- matching_commission.py 별도 라우터 분리, main.py import 경로 변경
- 테스트 11개, 전부 PASS

### inspection_sets.py (38KB → 3.2KB)
- 설계서: `docs/WORKORDER_inspection_sets_split.md`
- Cursor: STEP 0~5 한번에 완료
- inspection_sets_svc/ 패키지 분할 (law_engine, queries, anchors, schedules, errors)
- 테스트 11개, 전부 PASS

### 최종 성과
| 파일 | 원본 | 현재 | 축소율 |
|---|---|---|---|
| legal_engine.py | 77KB | 5KB | 93% |
| construction.py | 58KB | 1.8KB | 97% |
| payment.py | 72KB | 12KB | 83% |
| law_rule_generator.py | 46KB | 16KB | 65% |
| matching.py | 42KB | 5.3KB | 87% |
| inspection_sets.py | 38KB | 3.2KB | 92% |
| **합계** | **333KB** | **43KB** | **87%** |

---

## 3. PR #53 머지 (갭 B 편향 교정 + payment 분리)

- main.py + law_rule_generator.py 충돌 → Cursor에서 수동 머지
- 3회 dev→main 머지 완료 (payment, matching, inspection_sets 각각)
- 모든 배포 후 `/health` healthy 확인

---

## 4. QA 대시보드 테스트 등록

- `auto_qa_checks` 테이블에 29건 INSERT (T-01~T-29)
- 대시보드 전체 체크: 57 → 86, 활성화됨: 11 → 40
- 모든 pytest 테스트 파일이 대시보드에 등록됨

---

## 5. 이슈 처리

| 이슈 | 제목 | 상태 |
|---|---|---|
| #29 | 서비스 계층 분리 6건 | ✅ closed |
| #53 | 갭 B 편향 교정 PR | ✅ closed (merged) |

---

## 6. DEV_RULES 문서 갱신

- `docs/DEV_RULES_SERVICE_LAYER.md` v4
- 분리 대상 현황 테이블 6건 전부 ✅ 완료 반영
- 추가 20KB 초과 파일 9개 목록 추가

---

## 커밋 이력 (주요)

### tai-api
- `bac91ea` pw_reset.py main 직접 배포
- `a95b8dc` main.py v5.36.1 pw_reset 라우터 등록
- `c59d2fd` payment 서비스 분리 STEP0-5
- `ec92805` payment HTML 3개 분리
- `a5d6077` payment 잔여 로직 분리
- `3ad2162` matching 서비스 분리 STEP0-5
- `30daf9e` inspection_sets 서비스 분리 STEP0-5
- `90b724b` DEV_RULES v3
- `63e6e97` DEV_RULES v4

### tai-admin
- `e3979a9` auth-login-cover.html (FACILITY 매핑 + 비밀번호찾기 + 로고 + 통계)
