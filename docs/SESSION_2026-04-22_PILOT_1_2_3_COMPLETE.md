# 2026-04-22 법령엔진 Pilot 1+2+3 완료 세션

> Issue #37 (XML 파싱 파편화 버그) 대응을 위한 단계별 재수집 검증 완료일.

---

## 🎯 오늘의 성과 요약

| 지표 | Before (오늘 아침) | After (오늘 저녁) |
|---|---|---|
| 재수집 완료 법령 수 | 0 | **10** |
| 평균 valid_pct | ~2% | **~37%** (18배↑) |
| 파서 신뢰도 | 불검증 | **3단계 Pilot 통과** |
| cascade FK 커버 | 3 테이블 | **11 테이블** |
| pytest 통과 | 80 | **93** (+13) |
| 머지된 PR | 2개 누적 | **7개 누적** (오늘 5개) |
| 비용 | - | **0원** (Claude API 미사용) |

---

## 📊 재수집 완료 10법령 (Pilot 1+2+3)

### Pilot 1: 산업안전보건법 (1법령)

| 법령 | Before | After | version_id |
|---|---|---|---|
| 산업안전보건법 | 208 rows, 6.3% | **203 rows, 33.5%** | `60867079-0e99-48c7-8480-41c56aac87a4` |

### Pilot 2: 건설업 3법령

| 법령 | Before | After | version_id |
|---|---|---|---|
| 건축법 | 834 rows, 4.2% | **178 rows, 34.8%** (4.7× 압축) | `2be6f928-1ff4-414f-b041-a34f325db6eb` |
| 건축법 시행령 | 870 rows, 3.3% | **210 rows, 36.7%** (4.1× 압축) | `fa90cabe-6bab-4727-aa80-279962971390` |
| 건설기술 진흥법 | 128 rows, 0.0% | **125 rows, 36.8%** (정상화) | `af5022a1-f7b7-42ea-a33e-8dac18a21660` |

### Pilot 3: 가스·전기·소방 6법령

| 법령 | Before | After valid_pct | version_id |
|---|---|---|---|
| 화학물질관리법 시행규칙 | 4.0% | **47.9%** | `2e83ded6-7360-4cde-9938-0ed51f2cde2e` |
| 전기안전관리법 시행규칙 | 2.0% | **44.9%** | `449410ed-27d7-46a7-b5f7-97ba695956ff` |
| 소방시설 설치 및 관리에 관한 법률 | 3.3% | **38.0%** | `8b18a951-70eb-4783-95a0-c7891c94fbab` |
| 화재의 예방 및 안전관리에 관한 법률 | 0.0% | **36.7%** | `38443050-5348-40d8-a482-e7c29ba67992` |
| 고압가스 안전관리법 시행규칙 | 2.0% | **31.9%** | `564e3c16-a038-45dd-a8f2-651524c39536` |
| 위험물안전관리법 시행규칙 | 1.8% | **31.2%** | `6a59b989-10ed-4087-a883-90e609a6f18e` |

---

## 🔧 진단 → 해결 과정

### 발견된 실제 버그 (Issue #37의 오진단 교정)

**원래 가설** (Issue #37 본문):
- XPath `descendant-or-self` 버그로 한 조문이 여러 파편으로 저장됨

**실제 원인** (Pilot 1 실증으로 확인):
1. **`article_text = findtext("조문내용")` 경로 문제**: 본문이 `<항>/<호>/<목>` 하위에 분산되어 저장되는데 최상위 `<조문내용>`만 읽어 본문 소실
2. **force=true 재수집 시 article 보존**: `if art_cnt==0` 분기로 article 있으면 안 지움 → 파편 누적
3. **XPath 엄격화 필요**: 최상위 `./조문/조문단위` 우선

### 적용된 옵션 A + B + D

- **옵션 A**: XPath 엄격화 (`./조문/조문단위` 우선 + descendant 폴백)
- **옵션 B**: `article_internal_key` 기반 dedupe (본문·제목·항수 기준 유지)
- **옵션 D**: `조문내용 + [항][호][목]` 들여쓰기 합성으로 본문 완전 복원

---

## 🐛 실행 중 발견된 구조적 이슈 (전부 해결)

### Cascade FK 11개 테이블 (최종 커버)

| 테이블 | 컬럼 | 처리 | 발견 시점 |
|---|---|---|---|
| law_rule_drafts | article_id | NULL | 기본 |
| inspection_set_items | law_article_id | NULL | 기본 |
| **law_rule_source_map** | **article_id** | **NULL** | **Pilot 3 (PR #42)** |
| law_item, paragraph, article | - | DELETE cascade | 기본 |
| law_parsing_result | law_version_id | DELETE | Pilot 1 (PR #40) |
| law_attachment | law_version_id | DELETE | Pilot 1 (PR #40) |
| law_update_tracking | last_collected_version_id | SET NULL | Pilot 1 (PR #40) |
| law_article_diff | new/old_version_id | DELETE | Pilot 1 (PR #40) |
| law_change_log | new/old_version_id | SET NULL (history) | Pilot 1 (PR #40) |
| law_rule_source_map | law_version_id | DELETE | Pilot 1 (PR #40) |
| law_content_raw | law_version_id | DELETE | 기본 |

### PostgREST URL 한계 (PR #41)

건축법 834 articles cascade 삭제 시 `in_()` 쿼리가 URL 너무 길어져 400 Bad Request. 100개씩 chunking 적용.

### 새로 발견된 "정상 비-조문 요소" 3가지

파서가 손실 없이 보존하는 패턴 (파편이 아님):

1. **`article_type='전문'`**: 장/절 구분선 ("제1장 총칙")
2. **짧은 단독 조문**: 제27조처럼 한 줄짜리 실제 조항
3. **`"제XX조 삭제"` 조항** (Pilot 2 발견): 개정으로 삭제된 조항의 공식 표기

---

## 📋 머지된 PR 5개 (오늘)

| PR | 제목 | main SHA |
|---|---|---|
| [#35](https://github.com/taiengineering/tai-api/pull/35) | sanitize_master_patch 버그 수정 | `d73ed9a` |
| [#38](https://github.com/taiengineering/tai-api/pull/38) | INTERNAL_API_SECRET 로테이션 | - |
| [#39](https://github.com/taiengineering/tai-api/pull/39) | Pilot 1 XML 파싱 수정 (옵션 A+B+D) | `45262c7` |
| [#40](https://github.com/taiengineering/tai-api/pull/40) | Pilot 1 cascade FK 보완 (6 tables) | `e1dd776` |
| [#41](https://github.com/taiengineering/tai-api/pull/41) | Pilot 2 chunking + 스크립트 개선 | `17bb7f74` |
| [#42](https://github.com/taiengineering/tai-api/pull/42) | Pilot 3 발견 + 전체 확장 스크립트 | `ac0439a1` |

**main 최신 SHA**: `ac0439a1`

---

## 📁 생성된 주요 파일

### 핵심 코드
- `routers/law_collector.py` (40KB)
  - `parse_law_content_xml`, `_synthesize_article_text`, `_dedupe_articles_by_internal_key`
  - `_CHUNK_SIZE=100` + `_chunked()` helper
  - `_nullify_dependent_article_refs` (3 테이블 chunked)
  - `_clear_law_version_fk_dependents` (6 테이블)
  - `delete_law_version_cascade_for_recollect`

### 스크립트
- `scripts/reconnect_fk.py` — Pilot 1 FK 재연결
- `scripts/pilot2_recollect.py` — Pilot 2 통합 스크립트 (article_no fallback 매칭 포함)
- `scripts/pilot3_recollect.py` — Pilot 3 통합 스크립트
- `scripts/all_laws_recollect.py` — 전체 확장 배치 (체크포인트 기반 388법령)

### SQL
- `sql/20260422_law_quality_snapshot.sql`
- `sql/20260423_law_article_key_map.sql`

### 문서
- `docs/ISSUE_37_XML_ANALYSIS.md`
- `docs/WORK_ORDER_VALIDATION_PIPELINE.md`
- `docs/CURSOR_PROMPT_VALIDATION_SESSIONS.md`
- `docs/SESSION_2026-04-22_PILOT_1_2_3_COMPLETE.md` ← 이 파일

### 테스트
- `tests/test_law_collector.py` (93 passed)

---

## 📋 남은 작업 로드맵

### 🔴 Phase 1: 데이터 완성 (이번주)

**1.1 전체 확장 (388법령 재수집)** ⭐ 최우선
- 스크립트: `scripts/all_laws_recollect.py` (체크포인트 기반)
- 소요: 2~4시간
- 비용: 0원 (법제처 API 무료)
- 실행: 로컬 터미널에서 `python3 scripts/all_laws_recollect.py`

**1.2 재수집 후 DB 검증**
- 388법령 valid_pct, dedupe, 파편 검증
- MCP Supabase 쿼리 (기획창에서 수행)

**1.3 Issue #37 최종 close**
- 전체 확장 완료 시점에

### 🟡 Phase 2: 자동화 재가동 (다음주)

**2.1 Railway DATA_GOV_SERVICE_KEY 발급**
- 공공데이터포털 API 키 신청
- Railway 환경변수 설정

**2.2 `/check-updates-v2` 크론 복구**
- 15일 주기 법령 개정 감지

**2.3 auto-parse worker 재개**
- Claude API 기반 룰 추출 파이프라인
- 비용: ~$78 (388법령 기준)

### 🟢 Phase 3: AI 룰 파이프라인 (5월 초~중순)

**3.1 기존 APPROVED 룰 품질 재검증**
- 재수집 10법령의 master_building_legal_rules 참조 확인

**3.2 새 article 기반 룰 추출**
- 재수집된 법령에서 신규 룰 생성

### 🔵 Phase 4: 운영 안정화 (여유 있을 때)

**4.1 SUPABASE_KEY rotate** (보안)
**4.2 법령 품질 모니터링 자동화**
**4.3 E2E 법령 개정 알림 테스트**

---

## 🔑 주요 식별자

### Supabase
- 프로젝트: `xntdkrjhgcscmqctdzyo`
- URL: `https://xntdkrjhgcscmqctdzyo.supabase.co`

### 스냅샷 테이블
- `law_quality_snapshot_20260422`: 324법령 baseline
- `law_article_key_map`: Pilot 1/2/3 재수집 이력

### 법제처 API
- OC: `taieng` (115.68.227.222 등록 IP에서만 호출 가능)
- Railway 미등록 (DATA_GOV_SERVICE_KEY 필요)

---

## 🎓 얻은 교훈

1. **"버그 가설"은 실증 전까지 믿지 않는다**: Issue #37의 XPath 가설은 진단 단계에서 뒤집혔음. Pilot 1 옵션 C(A+B)로 수정됨.
2. **FK cascade는 한 번에 다 찾을 수 없다**: Pilot 단위로 실행해야 실전에서 드러나는 FK 발견. 3단계 걸쳐 11개 테이블 커버.
3. **PostgREST URL 제한은 실전에서만 드러난다**: 200 articles OK, 800 articles 터짐. chunking 100 기본 적용.
4. **파서 정상 패턴은 파편과 구분해야 한다**: 장 구분선, 단독 조문, "제XX조 삭제" 조항은 정상. 파편 기준 재정의 필수.
5. **체크포인트 기반 배치는 필수**: 388법령 2~4시간 배치는 중단 대응 필수.

---

## 🤝 이 세션의 협업 구조

- **기획창 (Claude Opus)**: 진단 · 검증 · 판정 · PR 관리 (MCP)
- **작업창 (Cursor)**: 코드 작성 · 테스트 · 커밋
- **사용자**: 로컬 실행 · 의사결정 · 검토

3자 협업으로 하루에 Pilot 3개 + PR 5개 완료.
