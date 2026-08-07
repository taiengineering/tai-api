---
doc_id: REPORT-KENG-CENTER-SUMMARY
class: records
type: REPORT
scope: knowledge
project: knowledge
title: 지식센터(Knowledge Center) 구축 정리 — 검색·리스트/상세·SSR 전환·상단메뉴/공통헤더
version: v1
status: DONE
owner: taiwang
---

# 지식센터 구축 정리 (WO-KENG-SEARCH 001~003 + SSR 전환)

## 1. 목적과 범위

45CM 지식엔진(knowledge)이 생성한 법령 해설 콘텐츠를 taieng.co.kr 에 **실사용 가능한 SEO 페이지**로 노출한다. 이번 묶음의 결과물은 세 축이다.

1. 한글 형태소 검색(수만 건 규모 대비)
2. 리스트/상세 페이지 구조 + 검색 UI
3. 상단 안전정보 메뉴에 지식센터(/kb) 진입점 + /kb 페이지 사이트 공통 헤더

정책 전환 포함: **정적 파일 베이킹(구버전) → 엣지 SSR 렌더링(정규)**. 수만 건을 개별 정적 페이지로 굽는 방식은 무리이며, SEO·운영을 고려해 DB→렌더 방식으로 확정됨.

## 2. 아키텍처 (정규 = 엣지 SSR)

```
브라우저 → tai-www _worker.js (CF Pages 고급모드)
           ├─ /kb/{slug}      → 45cm-mkt-api /public/knowledge/{slug}
           │                     → mkt_public_render (DB→완성 HTML) → 엣지 캐시
           └─ /kb (index)     → /public/knowledge (목록 + 검색 박스)
```

- 마케팅 API 백엔드: **DB_BACKEND=rest** (Supabase REST / RestRepo). 원시 SQL 불가 → PostgREST **RPC** 경유.
- 진입 경로: **/kb** (SSR 유지). 레거시 /knowledge 는 정적 폴백 안전망으로 보존(무중단·즉시 롤백).

## 3. 완료 항목

### 3.1 검색 백엔드 — 한글 형태소 (WO-KENG-SEARCH-001)
- **Kiwi(kiwipiepy)** 형태소 분석기를 FastAPI 프로세스에 임베드(`kiwi_search.py`). 명사·외국어·숫자·한자 위주 토큰 추출, 지연 로드+캐시, 미가용 시 공백/기호 폴백(색인·질의 동일 분석기 → 정합).
- pg 기본 파서는 한글을 못 쪼개므로 토큰 문자열을 `to_tsvector('simple', tokens)` 로 감싼다. 질의도 동일 분석기 → `websearch_to_tsquery('simple', tokens)` + `ts_rank`.
- REST 호환을 위해 **PostgREST RPC** 채택: `reindex_content(p_id, p_txt)`, `search_knowledge(p_tsq, p_limit, p_offset)`, `search_knowledge_count(p_tsq)`.
- 스키마: `marketing_content.search_tsv`(tsvector) + GIN 인덱스. DDL 은 **git 마이그레이션**으로 고정(BKP-004 준수).
- 실측 검증: "관리감독자"→형태소 "관리 감독", "사업주 의무"가 본문 내용과 매칭 — 형태소+본문 색인 동작 확인.

### 3.2 리스트/상세 + 검색 UI (WO-KENG-SEARCH-002)
- /kb 목록: 주제별 정렬 전체 리스트 + 상단 검색 박스(입력 디바운스 250ms, `/public/knowledge-search` 호출, 결과 렌더).
- 상세: 실제 LLM 본문(HTML)을 그대로 렌더, JSON-LD 6종 유지, /kb 링크 통일(`url_of`/`index_url`).
- 경량화: `get_public_content`(2-쿼리), 메뉴 TTL 캐시, cache-control 강화 → TTFB 개선(cache MISS 1.5s→0.45s 관측).

### 3.3 상단 메뉴 + 공통 헤더 (WO-KENG-SEARCH-003)
- **header.js** (v3.5.7): 안전정보 서브메뉴 **최상단**에 지식센터(/kb) 링크. /kb 는 워커 SSR 루트 라우트라 절대경로.
- **_worker.js**: `injectCommonHeader()` 로 /kb SSR HTML 에 공통 GNB 주입 — `<head>`에 `<base href="/">`, `<body>` 직후 `#tai-header` placeholder, `</body>` 직전 header.js. 200 성공 분기에서만 적용(캐시 저장 전), 멱등, 라우팅/프록시/폴백 무손상.
- 유닛테스트(대표 SSR HTML): placeholder 위치·기존 콘텐츠 보존·멱등성 전부 PASS.

### 3.4 파일럿 & 데이터
- 파일럿 3건(산업안전보건법 제16/125/129조) 실제 LLM 콘텐츠로 재생성 → SSR 방식(DB status=PUBLISHED)로 라이브 발행. (구버전 정적 발행 PR 은 폐기)
- 레거시 30건은 테스트 데이터로 확인되어 CASCADE 삭제. 현재 파일럿 3건 잔존.

## 4. 배포 상태

- **tai-www PR #11 머지 완료** (squash → main). CF Pages 자동 배포.
  - https://github.com/taiengineering/tai-www/pull/11
  - header.js 지식센터 링크 + _worker.js /kb 공통헤더.
- 마케팅 API(45cm-mkt-api): 검색 RPC/색인/렌더 반영(Railway 자동배포). Supabase 마이그레이션(search_tsv, RPC 3종) 적용 완료.

## 5. 병합 후 육안검증 (오퍼레이터)

- /kb 목록·/kb/{slug} 상세 상단에 사이트 공통 GNB 노출.
- GNB 링크(서비스/업종별/역할별/안전정보)가 루트 기준 정상 이동.
- 안전정보 > 지식센터 → /kb 이동.
- /kb 내부 기존 상대 링크/에셋이 `<base href="/">` 로 깨지지 않는지(mkt_public_render 절대경로 사용 — 재확인 권장).

## 6. 후속(별건, 미착수)

- 속도/커넥션풀 최적화 — 오퍼레이터 지시로 이 작업 이후로 연기.
- 발행 훅 → 검색 색인 자동 갱신 연결.
- 레거시 /knowledge → /kb 컷오버 및 정적 폴백 파일 정리.
- 실콘텐츠 대량 생성·발행(파일럿 3건 → 본격 규모).

## 7. 운영 준수 사항(기록)

- auto_publish OFF 유지. 라이브 발행·PR 머지·법령 승급은 오퍼레이터 승인 전용.
- tai-www main 직접 푸시 금지 — PR 경유(본 건도 PR #11).
- DDL 은 콘솔이 아닌 git 마이그레이션(BKP-004).
- 시크릿 값은 문서·커밋에 미기재.
- 대용량 파일 편집은 프로그램적 fetch→정밀 치환→문법/구조 검증 후 커밋(수동 base64 붙여넣기·일괄 재작성 금지).
