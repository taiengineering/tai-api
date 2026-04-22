# 📋 다음 세션 Cursor 프롬프트 (Pilot 전략 버전)

> TAI 법령엔진 AI 검증 파이프라인 구축. **Pilot 3단계** 순차 진행 — 각 단계 후 Go/No-Go 판단.
> 전체 작업지시서: `docs/WORK_ORDER_VALIDATION_PIPELINE.md`

---

## 🎯 Pilot 전략 개요

| 단계 | 범위 | 예상 비용 | Go/No-Go 체크포인트 |
|---|---|---|---|
| **SESSION 1** | XML 구조 진단 | 0원 | 수정 옵션 A/B/C 결정 |
| **SESSION 2 (Pilot 1)** | 산업안전보건법 **1건만** | 약 2만원 | valid_pct 80%+, 기존 rule FK 정상? |
| **SESSION 3 (Pilot 2)** | 건설 **3법령** + 큐 구축 | 약 10만원 | 각 법령 rule 30+, MULTI_VERIFY 품질 OK? |
| **SESSION 4 (Pilot 3)** | 가스·전기·소방 **6법령** | 약 15만원 | 누적 rule 500+, 전문가 관점 합격? |
| SESSION 5+ | 나머지 360법령 확장 | 조건부 | Pilot 3 통과 후에만 결정 |

**핵심 원칙:**
- 각 Pilot 끝에서 반드시 기획창(Claude Opus) 보고 + 본인 샘플 검토
- Go/No-Go 실패 시 **다음 단계 절대 진입 금지** → 원인 파악 후 재시도
- 전체 절감 효과: 200만원 → 약 30만원 (85% ↓)

---

## 🛠️ 사전 준비: 작업지시서 git 푸시

```
안녕 Cursor. TAI 법령엔진 AI 검증 파이프라인 구축을 Pilot 전략으로 시작한다.

첫 작업: 기획창에서 준비한 작업지시서 2개 파일을 repo에 저장한다.

## 작업
1. 아래 두 파일을 docs/ 에 저장 (내가 내용 복붙해줄 테니 그대로 저장):
   - docs/WORK_ORDER_VALIDATION_PIPELINE.md
   - docs/CURSOR_PROMPT_VALIDATION_SESSIONS.md

2. dev 브랜치에 커밋 + 푸시:
   git add docs/WORK_ORDER_VALIDATION_PIPELINE.md docs/CURSOR_PROMPT_VALIDATION_SESSIONS.md
   git commit -m "docs: AI 검증 파이프라인 작업지시서 (Pilot 전략)

   - Phase 1~3 통합 작업지시서 (3주 로드맵)
   - Pilot 3단계 체크포인트 프롬프트 (SESSION 1~4+)
   - 옵션 C 하이브리드 큐 아키텍처
   - 예상 비용: 200만원 → 30만원 (85% 절감)
   
   관련: Issue #37 data quality critical"
   
   git push origin dev

3. main 병합은 Pilot 1 완료 후로 유예. dev에만 푸시.

기획창에 푸시 완료 보고 후 SESSION 1 진입 대기.
```

---

## 🎯 SESSION 1: Phase 1-1 (XML 구조 진단)

```
Phase 1-1 진단 시작. Pilot 전략 SESSION 1.

## 배경
- Issue #37: law_collector.py XML 파싱 버그로 373법령 조문이 파편화
- 건축법 예: 834 row / 116 unique article, 유효 조문 4%
- 목표: 파싱 버그 원인 확정 → Pilot 1에서 실제 수정

## 작업 범위: 진단만 (DB 쓰기 최소화)

### STEP 1: 건축법 raw XML 추출
1. Supabase 쿼리로 건축법 law_content_raw.raw_xml 조회
2. 로컬 파일로 저장: scripts/debug/geonchuk_raw.xml
3. xmllint --format 또는 Python ET.dump 로 구조 분석

### STEP 2: 핵심 확인 사항
docs/ISSUE_37_XML_ANALYSIS.md 에 정리:
- <조문단위> 태그의 nesting 구조 (최상위? 중첩?)
- 조문키 속성의 고유성 (중복 있나?)
- 중복 발생 지점 (어디서 파편이 만들어지나?)
- 수정 옵션 A/B/C 중 권장 옵션 + 근거
  - A: XPath 엄격화 (./조문/조문단위 등)
  - B: article_internal_key 기반 중복 제거
  - C: A + B 조합

### STEP 3: 산업안전보건법 구조도 확인
Pilot 1 대상이므로 사전 파악 필수. 같은 방식으로 raw XML 조회 → 건축법과 구조 동일한지 확인.

### STEP 4: 스냅샷 테이블 생성 (수정 전 baseline)
작업지시서 Phase 1-1-2 SQL 실행:
  CREATE TABLE law_quality_snapshot_20260422 AS SELECT ...

## 제약사항
- DEV_RULES v2 준수
- DB 쓰기는 스냅샷 테이블 생성만. 기존 데이터 수정 금지
- 기존 파이프라인 (check_law_update, save_law_to_db) 건드리지 말 것

## 완료 후 기획창 보고
```
✅ SESSION 1 완료 (Phase 1-1 진단)
- 분석 파일: docs/ISSUE_37_XML_ANALYSIS.md
- 건축법 <조문단위> 구조: [최상위 N개 / 중첩 M개]
- 산안법 구조: 건축법과 [동일 / 다름]
- 권장 수정 옵션: [A/B/C 중 하나]
- 근거: [간단 설명]
- 스냅샷 테이블 row 수: 373
- 다음: SESSION 2 Pilot 1 (산안법 1건 재수집) 준비 완료
```

시작해줘.
```

---

## 🎯 SESSION 2: **Pilot 1** — 산업안전보건법 1건 재수집 🛑

> **Cursor 복사:** 아래 **코드펜스 1개**를 통째로 채팅에 붙여넣기.  
> 범위: 첫 줄 `## SESSION 1 판정` → 마지막 줄 `시작해줘.` (맨 아래 닫는 펜스 줄은 포함해도 됨).  
> 바깥 펜스는 **백틱 5개**로 열고 닫아서, 안쪽 SQL/쉘용 **백틱 3개** 펜스와 충돌하지 않음.

`````
## SESSION 1 판정: GO (기획창 확인 완료)

### SESSION 2 범위 확장 (원래 계획에 4가지 추가)

SESSION 1 분석으로 "XPath 엄격화만으론 해결 불가"가 확인됐다.
진짜 버그 2개 + 안전망 2개를 Pilot 1에 모두 포함할 것.

**반드시 수행 (우선순위 순):**

1. 🔴 **버그 2 수정 (최우선)**: `collect_single_law()` force 재수집 로직
   - 현재: `if (art_cnt.count or 0) == 0:` 일 때만 삭제
   - 변경: force=true면 **조건 없이** law_article, law_paragraph, law_item, law_content_raw, law_version 순서로 삭제 후 재삽입
   - FK cascade 주의: 매핑 테이블 생성은 삭제 전에

2. 🔴 **버그 1 수정 (본문 합성)**: parse_law_content_xml() 리팩토링
   - article_text를 다음 규칙으로 합성:
 조문내용
 [항번호] 항내용
   [호번호] 호내용
     [목번호] 목내용
   [호번호] ...
 [항번호] ...
   - 기존 law_paragraph/law_item 분할 저장은 유지 (별도 활용 용도)
   - article_text는 "검색·AI 컨텍스트·품질 지표"용 전체 본문

3. 🟡 **옵션 B (dedupe)**: article_internal_key 기반 중복 제거
   - 산안법 조문키 5쌍 중복 대비
   - 같은 키가 여러 노드면 더 완전한 쪽 선택 (길이 + title 기준)

4. 🟡 **옵션 A (방어 XPath)**: `root.findall("./조문/조문단위")`로 변경
   - 현재 API 기준 효과 동일하나 스키마 변경 대비

### 테스트 추가
tests/test_law_collector.py 에 다음 2개 추가:
- test_article_text_includes_hang_ho_mok_content
  (조문 1개에 항 1개, 호 2개 있을 때 article_text가 모두 포함하는지)
- test_force_recollect_deletes_existing_articles
  (force=true 호출 시 기존 article 모두 삭제되는지)

### Pilot 1 검증 기준 조정

기존 기준: valid_articles LENGTH(article_text) > 500
이제는: article_text에 조문내용+항+호+목이 합성되어 있으므로
  - 산안법 목표: valid_pct >= 30% (Cursor 측정 68/208 = 33% 기준)
  - 추가: article row 수 = 원본 XML <조문단위> 개수 (±5 이내)
    - 산안법 기준: 208 ± 5
  - 추가: article_internal_key 고유값 = article row 수 (1:1)
    - dedupe 로직 작동 확인

### 기획창(Claude Opus) 역할
- SESSION 2 PR 리뷰 시 위 4가지 모두 반영됐는지 확인
- force 재수집 테스트 (산안법 재수집 전후 row 수 비교)
- Issue #37에 SESSION 2 결과 코멘트 작성

---

Pilot 1 시작. 산업안전보건법 1건만 전체 플로우 검증.

## 배경
- SESSION 1 진단 완료. 수정 옵션 C(A+B) + 옵션 D(본문 합성) 채택
- 목표: 산안법 1건으로 "파싱 수정 → 재수집 → FK 무결성" 전 과정 검증
- 실패 시 Pilot 2, 3 절대 진입 금지

## 작업 범위

### STEP 1: parse_law_content_xml() + collect force 로직 수정 (TDD)
1. tests/test_law_collector.py 신규/보강 — 최소 6개:
   - test_parse_clean_xml_returns_correct_count
   - test_parse_nested_xml_deduplicates
   - test_parse_keeps_more_complete_version
   - test_parse_sanbohoeonbeop_sample (실제 산안법 XML 파편으로)
   - test_article_text_includes_hang_ho_mok_content (본문 합성)
   - test_force_recollect_deletes_existing_articles (force=true 삭제)
2. pytest 실행 → 실패 확인 (현재 버그)
3. routers/law_collector.py 수정 (위 SESSION 2 확장 4가지 반영)
4. pytest → 전부 PASSED

### STEP 2: FK 무결성 전략 구현
작업지시서 Phase 1-4 "전략 B" (새 version + 매핑 테이블) 구현:
- sql/20260423_law_article_key_map.sql: 매핑 테이블 DDL
- scripts/reconnect_fk.py: 구→신 article_id 매핑 후 참조 업데이트

### STEP 3: Pilot 1 실행 — 산업안전보건법만
```
# 1. 기존 산안법 version 백업 (Supabase SQL)
#    SELECT * FROM law_version WHERE law_id = (산안법 ID) AND is_current=true
#    → JSON으로 로컬 저장

# 2. 재수집 실행
curl -X POST "https://api.taieng.co.kr/law-collector/collect/산업안전보건법?force=true"

# 3. FK 재연결
python3 scripts/reconnect_fk.py --law-name "산업안전보건법"
```

### STEP 4: Pilot 1 검증 (🛑 Go/No-Go 결정)

아래 검증 쿼리를 실행한다 (기준은 상단 **Pilot 1 검증 기준 조정** 참고).

```
-- 4-1. valid_articles 비율 (article_text = 조문내용+항+호+목 합성 후)
SELECT 
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE LENGTH(article_text) > 500) AS valid,
  ROUND(100.0 * COUNT(*) FILTER (WHERE LENGTH(article_text) > 500) / NULLIF(COUNT(*), 0), 1) AS valid_pct
FROM law_article la
JOIN law_version lv ON la.law_version_id = lv.id
JOIN law_master lm ON lv.law_id = lm.id
WHERE lm.law_name = '산업안전보건법' AND lv.is_current = true;
-- 🎯 기준: valid_pct >= 30%

-- 4-1b. article row 수 vs 원본 XML 조문단위 수 (재수집 직후 law_content_raw 등과 대조 가능)
SELECT COUNT(*) AS article_rows
FROM law_article la
JOIN law_version lv ON la.law_version_id = lv.id
JOIN law_master lm ON lv.law_id = lm.id
WHERE lm.law_name = '산업안전보건법' AND lv.is_current = true;
-- 🎯 기준: 208 ± 5 (원본 XML 조문단위 개수와 일치)

-- 4-1c. article_internal_key 고유 = row 수 (dedupe 확인)
SELECT
  COUNT(*) AS article_rows,
  COUNT(DISTINCT la.article_internal_key) AS distinct_keys
FROM law_article la
JOIN law_version lv ON la.law_version_id = lv.id
JOIN law_master lm ON lv.law_id = lm.id
WHERE lm.law_name = '산업안전보건법' AND lv.is_current = true;
-- 🎯 기준: article_rows = distinct_keys

-- 4-2. unique article_no 수 (참고 지표)
SELECT COUNT(DISTINCT article_no) FROM law_article la
JOIN law_version lv ON la.law_version_id = lv.id
JOIN law_master lm ON lv.law_id = lm.id
WHERE lm.law_name = '산업안전보건법' AND lv.is_current = true;
-- 참고: 175 전후 등 법제처 원본과 비교

-- 4-3. 기존 master rule 83개 FK 무결성
SELECT COUNT(*) AS broken_fk
FROM master_building_legal_rules m
WHERE m.law_name = '산업안전보건법'
  AND m.is_active = true
  AND NOT EXISTS (
    SELECT 1 FROM law_article la
    JOIN law_version lv ON la.law_version_id = lv.id
    WHERE lv.law_id = (SELECT id FROM law_master WHERE law_name='산업안전보건법')
      AND lv.is_current = true
      AND la.law_article = m.law_article
  );
-- 🎯 기준: 0 (모든 기존 rule이 새 law_article와 매칭)

-- 4-4. 재수집 후에 파편 row 남아있는지
SELECT COUNT(*) FROM law_article la
JOIN law_version lv ON la.law_version_id = lv.id
JOIN law_master lm ON lv.law_id = lm.id
WHERE lm.law_name = '산업안전보건법' AND lv.is_current = true
  AND LENGTH(article_text) < 50;
-- 🎯 기준: < 10건

-- 4-5. 법령개정 알림 파이프라인 영향 없는지
SELECT * FROM law_revision_board
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
-- 🎯 기준: 빈 결과 (알림 안 감)
```

### STEP 5: 샘플 눈으로 확인
재수집된 산안법 조문 10개를 랜덤 추출해서 화면에 표시.
본인(기획창)이 "이 조문이 정상적으로 파싱됐는지" 판단 가능한 형식.

## 완료 후 기획창 보고 (🛑 Go/No-Go 판단용)
```
✅ Pilot 1 완료 (SESSION 2)

### 기술 검증 (쿼리 결과)
- 4-1. valid_pct: [X]% (기준 30%+)
- 4-1b. article_rows: [N] (기준 208 ± 5, 원본 XML 조문단위와 대조)
- 4-1c. rows vs distinct article_internal_key: [일치 Y/N]
- 4-2. unique article_no: [N]개 (참고)
- 4-3. broken_fk: [M]건 (기준 0)
- 4-4. 파편 row (LENGTH<50): [K]건 (기준 <10)
- 4-5. 알림 오발송: [Y/N]

### 코드 반영 체크 (PR)
- force 재수집 삭제 로직: [Y/N]
- article_text 항·호·목 합성: [Y/N]
- dedupe (조문키): [Y/N]
- XPath ./조문/조문단위: [Y/N]

### 샘플 조문 10개
[표시]

### 판정
- 위 기준 모두 통과? [Y/N]
- 샘플 품질 OK? [Y/N]
- 총평: [Go to Pilot 2 / No-Go, 원인 파악 필요]
```

기획창이 "GO" 판정 주기 전까지 SESSION 3 절대 시작하지 말 것.

시작해줘.
`````

---

## 🎯 SESSION 3: **Pilot 2** — 건설 3법령 + Phase 2 큐 구축 🛑

```
Pilot 2 시작. 건설업 3법령 재수집 + 큐 아키텍처.

## 사전 조건
- Pilot 1 GO 판정 받았음 (기획창 확인)
- 산안법 재수집 성공 → 파싱 로직 검증됨

## 작업 범위

### STEP 1: 건설업 3법령 재수집
대상: 건축법, 건축법 시행령, 건설기술 진흥법
- 각각 force=true 재수집
- FK 재연결 스크립트 실행
- Pilot 1 STEP 4의 5개 검증 쿼리를 3법령 각각에 실행

### STEP 2: Phase 2 하이브리드 큐 구축
작업지시서 Phase 2 섹션 전체 구현:
- sql/20260423_ai_validation_queue.sql
- master_building_legal_rules.verification_level 컬럼 추가
- save_law_to_db() 에 enqueue 1줄 추가 (try/except 필수)
- services/validation_worker.py 뼈대
- 엔드포인트 3개
- Railway cron 등록 (30분마다, limit=10)

**단, Phase 3 구현 전이므로 dispatcher는 NotImplementedError로 두기.**

### STEP 3: Pilot 2 검증 (🛑 Go/No-Go 결정)

```
-- 5-1. 3법령 재수집 결과
SELECT 
  lm.law_name,
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE LENGTH(article_text) > 500) AS valid,
  ROUND(100.0 * COUNT(*) FILTER (WHERE LENGTH(article_text) > 500) / COUNT(*), 1) AS valid_pct
FROM law_article la
JOIN law_version lv ON la.law_version_id = lv.id
JOIN law_master lm ON lv.law_id = lm.id
WHERE lm.law_name IN ('건축법', '건축법 시행령', '건설기술 진흥법')
  AND lv.is_current = true
GROUP BY lm.law_name;
-- 🎯 기준: 각 법령 valid_pct >= 80%

-- 5-2. 큐 enqueue 동작 확인
SELECT * FROM ai_validation_queue 
WHERE enqueued_by = 'law_collector.save_law_to_db'
ORDER BY enqueued_at DESC LIMIT 10;
-- 🎯 기준: 3건 법령별 자동 enqueue 확인

-- 5-3. Worker 정상 동작 (FAILED로라도)
SELECT status, COUNT(*) FROM ai_validation_queue GROUP BY status;
-- 🎯 기준: PENDING + FAILED 만 있음 (DONE은 Phase 3 이후)

-- 5-4. 기존 알림 파이프라인 응답시간 측정
-- check_law_update 실행 전후 로그 비교
-- 🎯 기준: 응답시간 변화 없음
```

## 완료 후 기획창 보고
```
✅ Pilot 2 완료 (SESSION 3)

### 재수집 결과
- 건축법: valid_pct [X]% (rule [N]개 기존 유지)
- 건축법 시행령: valid_pct [X]%
- 건설기술 진흥법: valid_pct [X]%

### 큐 시스템
- ai_validation_queue 생성: [Y/N]
- enqueue 자동 동작: [Y/N] (3건 확인)
- Worker 실행: [Y/N] (NotImplementedError로 FAILED 처리)
- Cron 등록: [Y/N]

### 회귀 없음
- check_law_update 응답시간 변화: [없음/증가]
- law_revision_board 오발송: [Y/N]

### 판정
- 기준 모두 통과? [Y/N]
- 총평: [Go to Pilot 3 / No-Go, 원인 파악]
```

기획창 GO 판정 후 SESSION 4 진입.

시작해줘.
```

---

## 🎯 SESSION 4: **Pilot 3** — 가스·전기·소방 6법령 + MULTI_VERIFY 🛑

```
Pilot 3. 가스/전기/소방 6법령 재수집 + 실제 AI 검증 로직.

## 사전 조건
- Pilot 2 GO 판정
- 큐 + Worker 뼈대 동작

## 작업 범위

### STEP 1: 6법령 재수집
대상:
- 고압가스 안전관리법 시행규칙
- 위험물안전관리법 시행규칙
- 화학물질관리법 시행규칙
- 전기안전관리법 시행규칙
- 소방시설 설치 및 관리에 관한 법률
- 화재의 예방 및 안전관리에 관한 법률

각각 force=true → FK 재연결 → 5개 검증 쿼리

### STEP 2: Phase 3-1, 3-2 구현 (MULTI_VERIFY)
작업지시서 Phase 3-1, 3-2 섹션:
- services/validation_tasks.py: dispatcher + run_multi_verify
- _extract_with_haiku, _verify_with_sonnet, _results_agree, _compute_diff
- tests/test_validation_tasks.py 10개 이상
- MIN_SONNET_CONF = 90 (auto-approve 기준 상향)

### STEP 3: Phase 3-3 구현 (MISSING_DETECT)
작업지시서 Phase 3-3 섹션:
- services/validation_tasks.py 에 run_missing_detect 추가

### STEP 4: Pilot 3 실행
- 6법령 enqueue
  - MULTI_VERIFY priority 10
  - MISSING_DETECT priority 20
- Worker가 자동 소화 (Cron 30분마다 limit 10)
- 약 6~12시간 후 전체 완료 예상

### STEP 5: 실비용 측정
- Anthropic Console에서 Pilot 3 구간 API 비용 확인
- 법령당 평균 비용 → 전체 확장 시 예상 비용 extrapolate

### STEP 6: Pilot 3 검증 (🛑 최종 Go/No-Go)

```
-- 6-1. 6법령 Before/After rule 수
SELECT 
  m.law_name,
  COUNT(*) FILTER (WHERE m.created_at < '2026-04-22') AS before_rules,
  COUNT(*) FILTER (WHERE m.created_at >= '2026-04-22') AS new_rules,
  COUNT(*) AS total
FROM master_building_legal_rules m
WHERE m.law_name IN ('고압가스 안전관리법 시행규칙', '위험물안전관리법 시행규칙', 
                     '화학물질관리법 시행규칙', '전기안전관리법 시행규칙',
                     '소방시설 설치 및 관리에 관한 법률',
                     '화재의 예방 및 안전관리에 관한 법률')
  AND m.is_active = true
GROUP BY m.law_name;

-- 6-2. verification_level 분포
SELECT verification_level, COUNT(*) FROM master_building_legal_rules
WHERE is_active = true AND created_at >= '2026-04-22'
GROUP BY verification_level;

-- 6-3. MISSING_DETECT 결과
SELECT law_name, COUNT(*) AS missing_candidates
FROM law_rule_drafts
WHERE status = 'PENDING' 
  AND 'missing_detected_by_sonnet' = ANY(ai_flags)
GROUP BY law_name;

-- 6-4. multi_verify_disagreement 수
SELECT COUNT(*) FROM law_rule_drafts
WHERE 'multi_verify_disagreement' = ANY(ai_flags);
```

### STEP 7: 샘플 품질 검수 (본인 수동)
- 신규 추가 rule 중 랜덤 20개 추출
- 화면에 rule + 원문 조항 병기 표시
- 본인이 "이 정도면 유료 출시?" 판단

## 완료 후 기획창 보고 (🛑 최종 판정)
```
✅ Pilot 3 완료 (SESSION 4)

### 재수집 + AI 검증 결과
| 법령 | Before | +AI추출 | Total |
| ...  |        |         |       |

### 품질 지표
- verification_level AI_MULTI: [N]건
- verification_level AI_SINGLE: [N]건 (신뢰도 부족 or 불일치)
- missing_detect 후보: [N]건
- multi_verify 불일치: [N]건 (수동 검토 대상)

### 실비용
- Pilot 3 구간 Claude API: [XX]만원
- 법령당 평균: [Y]만원
- 나머지 360법령 확장 시 예상: [Z]만원

### 샘플 20건 품질 (본인 판단)
- "이 정도면 유료 출시 가능" 판단: [Y/N]
- 눈에 띄는 오류: [있음/없음, 있다면 샘플]

### 최종 판정
- 기준 모두 통과? [Y/N]
- 전체 확장 가능? [Y/N]
- 총평: [Phase 확장 진행 / 파싱/프롬프트 재조정]
```

기획창 **최종 GO** 판정 후에만 SESSION 5+ 진입.

시작해줘.
```

---

## 🎯 SESSION 5+: **Pilot 3 통과 시에만** 전체 확장

```
SESSION 5 이후는 Pilot 3 통과 확정 후 구체화.

## 가능한 경로 (Pilot 3 결과에 따라)

### 경로 A: 순탄 통과 (rule 품질 만족)
- 나머지 360법령 일괄 재수집 + 검증
- 작업지시서 원래 Phase 3-4 (CROSSCHECK) + 3-5 (전체 배치)
- 예상 소요: 1~2주
- 예상 비용: Pilot 3 법령당 평균 × 360

### 경로 B: 부분 통과 (일부 품질 이슈)
- 프롬프트 개선: SYSTEM_PROMPT, USER_PROMPT_TEMPLATE 재작성
- 재Pilot: 동일 6법령으로 AI 검증 재실행
- 비용: 추가 약 15만원

### 경로 C: 중대 결함 발견
- 대규모 재설계 필요
- 기획창과 논의 후 결정

세부 계획은 Pilot 3 결과 공유 후 기획창이 별도 프롬프트로 제공 예정.
```

---

## ⚠️ 공통 주의사항 (모든 SESSION)

### DEV_RULES v2
- services/ 에 `from fastapi` import 금지
- 신규 파일 400줄 이내 유지
- 테스트 우선 (TDD)

### 기존 파이프라인 보호
- `check_law_update()`, `save_law_to_db()` 의 알림 흐름 변경 금지
- enqueue 1줄 추가는 try/except로 감싸기 (절대 기존 플로우 실패시키지 말 것)

### PR 단위
- 각 SESSION마다 별도 PR 권장
- PR 크기 400줄 이하 (리뷰 용이)

### 커밋 메시지 규약
```
<type>: <한 줄 요약>

- 변경 내용 1
- 변경 내용 2
- 변경 내용 3 (필요 시)

관련: <issue/PR 번호>
검증: <테스트/메트릭 결과>
```

### 긴급 중단 기준
- Railway 배포 실패
- 기존 master_building_legal_rules FK 5건 이상 끊김
- 법령개정 오발송 알림 발생
- Claude API 비용이 Pilot 예산 2배 초과
→ 즉시 중단하고 기획창 보고

---

## 📋 기획창(Claude Opus) 역할

각 SESSION에서:
- **시작 전**: 이전 SESSION 결과 검증 (DB 쿼리, PR 리뷰)
- **중간**: 진행률 모니터링 (요청 시)
- **완료 후**: Go/No-Go 판정 + 다음 SESSION 조건 확정
- **전체**: Issue #37 업데이트, 통합 리포트 작성

---

## 🔄 세션별 체크리스트 (복붙용)

세션 시작할 때 Cursor에게 아래 복붙:
- SESSION 1 → 사전준비 섹션 + SESSION 1 블록
- SESSION 2 → SESSION 2 블록 (Pilot 1)
- SESSION 3 → SESSION 3 블록 (Pilot 2, Pilot 1 GO 확정 후만)
- SESSION 4 → SESSION 4 블록 (Pilot 3, Pilot 2 GO 확정 후만)

중간에 Go/No-Go가 No면 해당 SESSION 재시작, 다음 진입 금지.
