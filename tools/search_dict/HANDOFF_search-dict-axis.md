---
title: TAI 검색어 사전(축) 인수인계 — TAI 검색엔진/법령엔진 프로젝트로 이관
work_order: MASTER-WO-TAI-SEARCH-DICT-001 · OBJECT OBJ-SEARCH-DICT
snapshot: SEARCH-DICT-LEGPROD-2026-09-16
status: DONE (2026-09-16 main 병합 완료)
handoff_date: 2026-09-16
from: 검색어 사전 축 (기획창 Claude 설계 + Claude Code 런타임 실행)
to: TAI 검색엔진 / 법령엔진 프로젝트
owning_subsystem: LEG Candidate Enrichment / ON_DEMAND (services/leg_ondemand_enrichment.py, services/leg_candidate_adapter.py)
---

# 0. 이 문서의 목적

TAI 검색엔진은 여러 축(axis)으로 구성되며, 본 인수인계는 그중 **"검색어(lexical/dictionary) 축"** 하나를 완결·이관하는 문서다. 이 축은 사용자가 입력한 **검색어**를 법령/기관/장비/화학 등 **주제(subject)**로 결정론적으로 해소(resolve)하는 어휘 계층이다. 상류는 법령엔진의 `dict_legal_terms`(정부 원천 기반 ~14,942행)이며, 하류는 검색 API(`/search-dict/*`)와 런타임 tier들이다.

받는 팀이 이 문서만으로 **운영·재빌드·검증·확장**할 수 있도록 자기완결적으로 작성했다.

> **소속 서브시스템 (오너 지정):** 이 검색어 축은 백엔드의 **LEG Candidate Enrichment / ON_DEMAND 보강 로직**에 속한다. 기존 구조상 관련 코드는 `services/leg_ondemand_enrichment.py` 와 `services/leg_candidate_adapter.py` 계열이다. 따라서 본 산출물은 `tai-api`에 귀속되며(`tai-www`/`tai-admin` 아님), RISK-04 canonical/source 작업(PR #366)과는 **검증 범위 분리**를 위해 별도 브랜치/PR로 이관한다.

---

# 1. 인계 범위 · 경계

## 1.1 이 축이 담당하는 것 (IN SCOPE)
- 검색어 사전: term(검색어) / relation(관계) / subject(주제) 데이터 모델
- 결정론적 정규화 + `term_id` 해시
- 결정론 컴파일러(스냅샷 → 산출물, 같은 입력 → 동일 SHA)
- 어휘 검색 엔진 tier T1–T6 (아래 §5)
- 검색 API (`/search-dict/lookup`, `/health`, `/census`)
- 벤치마크 + 품질 게이트

## 1.2 이 축이 담당하지 않는 것 (OUT OF SCOPE — 다른 축/소유자)
- **법령엔진(GPT 담당)**: 결정론 제약 컴파일러/런타임. `dict_legal_terms`·`law_master`·`law_alias` 원천 데이터의 **생성·수정**은 법령엔진 소유. 본 축은 이를 **읽기 전용으로 소비만** 한다. **법령엔진 로직은 절대 수정 금지.**
- 의미검색(semantic/embedding), 문서 본문 검색, 랭킹 학습 등 다른 검색 축 — 별도.
- 결제/UI/진단 제품화 — 별도 파이프라인.

## 1.3 핵심 원칙 (이관 후에도 반드시 유지)
> **검색어 ≠ Canonical ID · 같은 이름 ≠ 같은 개념 · 유사도(형태소/trigram/LLM) ≠ 병합 · APPROVED만 프로덕션 인덱스 · 정확도 > 재현율 · 병합은 오너 결정 · 지표 날조 금지**

---

# 2. 산출물 위치 (병합 완료)

| 구분 | 저장소 | 경로 | PR |
|---|---|---|---|
| 코드 | `taiengineering/tai-api` | `tools/search_dict/`, `routers/search_dictionary.py`, `services/search_query_svc.py` | #368 (squash-merged 2026-09-16) |
| 문서 | `taiengineering/taieng` | `docs/knowledge/search-dict/` | #31 (squash-merged 2026-09-16) |
| 인계문서(본문) | `taiengineering/tai-api` | `tools/search_dict/HANDOFF_search-dict-axis.md` | 별도 PR (branch feature/leg-search-enrichment, #366과 분리) |

> 정확한 병합 커밋 SHA는 각 저장소 main 로그에서 확인(본 인계 시점 미기록). 병합 직전 브랜치 HEAD: tai-api `bca9af4b`, taieng `e644dcc`. 소스 브랜치 `feature/search-dictionary-v2-legprod`는 양 저장소에 보존(삭제 안 함). v1 브랜치 `feature/search-dictionary-v1`도 보존.

## 2.1 코드 파일 인벤토리 (`tools/search_dict/`)
- `normalize.py` — 정규화 + `term_id`/`relation_id` (순수 stdlib)
- `seed_v1.py` / `seed_v2.py` — 스냅샷 정의(시드). **현행 프로덕션 = seed_v2**
- `build_dictionary.py` — 결정론 컴파일러/검증/CLI (`census|validate|build|export-kiwi`). 시드 선택 env `SEARCH_DICT_SEED`(기본 seed_v1)
- `search_core.py` — 엔진 tier T1–T3 + PUNCTUATION tier (순수 stdlib)
- `search_runtime_ext.py` — TokenTier(T4, Kiwi) + TrigramTier(T6, pg_trgm)
- `extract_legprod.py` — 런타임 전체코퍼스 추출기 (`verify` / `full`)
- `benchmark_run.py` / `benchmark_runtime_ext.py` — 측정형 벤치마크
- `selftest.py` — stdlib 회귀(12케이스)
- `extract/GROUND_TRUTH_464.tsv`, `extract/LAW_ALIAS_15.tsv` — 체크섬 핀 고정 실추출 입력
- `artifacts/BUILD_SHA256SUMS.txt` — 골든 SHA 매니페스트
- `tests/test_search_dict_{normalize,build,search}_v1.py` — pytest (seed-aware 골든표)
- 라우터: `routers/search_dictionary.py` (등록: `router_registry/public.py`)
- 서비스: `services/search_query_svc.py` (`lookup`이 T1–T6 오케스트레이션)

## 2.2 문서 파일 인벤토리 (`docs/knowledge/search-dict/`)
- `SEARCH_CONSTITUTION_v1.md`, `SEARCH_TERM_CONTRACT_v1.md` — 헌법/계약(불변식·enum)
- `SEARCH_ENGINE_ARCHITECTURE_v1.md`, `SEARCH_FINAL_AUDIT_v1.md`
- `SEARCH_DICT_V2_LEGPROD_SNAPSHOT.md` — v2 실추출 감사
- `RECEIPT_v2-runtime-closeout.md` — **최종 게이트 결과의 authoritative 소스**
- `SEARCH_BENCHMARK_v1.tsv`, `SEARCH_BENCHMARK_RESULT_v1.tsv`
- `measurements/{KIWI_BEFORE_AFTER_v1, SEARCH_BENCHMARK_v2_kiwi_trgm, LATENCY_HTTP_v1}.tsv`
- `2026-09-16_MASTER-WO-TAI-SEARCH-DICT-001.md` — 원 작업지시서

---

# 3. 데이터 출처 · 검증 (Provenance)

## 3.1 상류 원천 (읽기 전용)
- Supabase 프로젝트 **`wrfcedzgdrfupenzqhur` (leg-prod)**
  - `public.dict_legal_terms` — 총 **14,942행** = verified 1,725 + PROPOSED(verified=false) 13,217 + null 0
    - verified 분해: LAW_NAME(law_name) 366 + LAW_NAME(law_name_short) 57 + AGENCY_NAME 26 + TECH_TERM(manual:whitelist) 15 + GENERIC(NNG) 1,250 + GENERIC(NNP) 11
  - `public.law_alias` — 검증된 약칭↔전체명 15쌍
  - `public.law_master` — 정부 발행 원천(법령엔진 소유)

## 3.2 스냅샷 무결성 (핀 체크섬)
검증 ground-truth를 서버측 SHA-256과 바이트 대조 → **드리프트 0** 확인됨. (각 행을 개행문자로 조인, 마지막 개행 없음)
- `extract/GROUND_TRUTH_464.tsv` (464행) = `9cf9d73cb35a8884164dd999ff8aa10b59e0098c96e3a940205f801825fea178`
- `extract/LAW_ALIAS_15.tsv` (15행) = `e3006ed67d4b93f435419ce47288aced44bcb3bdb97e97e3308bc31780cbabbe`

라이브 재검증: `DATABASE_URL=<leg-prod RO> python3 extract_legprod.py verify` → 두 값 재현. (2026-09-16 railway 경유 PASS)

## 3.3 정직성 기록 (over-claim 방지)
- 프로브한 복합어 30개 중 14개만 실존 → 나머지는 canon 날조 없이 SEARCH_PHRASE/KIWI 후보로만 입력.
- 13,217 PROPOSED(verified=false)는 **비프로덕션** — APPROVED-only 게이트로 프로덕션 인덱스 제외.

---

# 4. 데이터 모델 (계약)

## 4.1 term 튜플 (seed → 컴파일러 입력)
`(source_id, source_key, term_type, original_term, language, pos_hint, subject_type, subject_key, status, quality_flag, curation_method, confidence, evidence_ref)`

- **`term_id` = SHA256(source_id · source_key · term_type · original_term, 각 필드 개행문자 구분)** — 콘텐츠 주소. **Canonical ID 아님.** 다른 source가 같은 표면을 명명하면 의도적으로 다른 term_id(같은 이름 ≠ 같은 개념).
- `term_type` ∈ {CANONICAL_NAME, SOURCE_NAME, ALIAS, SYNONYM, ABBREVIATION, FIELD_TERM, ENGLISH_TERM, SPELLING_VARIANT, SPACING_VARIANT, PUNCTUATION_VARIANT, SEARCH_PHRASE, KIWI_USER_WORD}
- `status` ∈ {PROPOSED, REVIEWED, APPROVED, REJECTED, HOLD} — **APPROVED만 프로덕션 인덱스**
- `subject_type` ∈ {RISK_REVIEW_CONCEPT, RISK_SOURCE, LEGAL_TERM, KOSHA_TERM, KALIS_TERM, CHEM_TERM, ACCIDENT_TERM, EQUIPMENT_TERM, GENERAL_TERM}

## 4.2 relation 튜플
`(source_original, source_id, target_original, target_id, relation_type, status, curation_method, confidence, evidence_ref)`
- `relation_type` ∈ {EXACT_ALIAS, SYNONYM_OF, ABBREVIATION_OF, ENGLISH_OF, FIELD_TERM_OF, SPELLING_VARIANT_OF, SPACING_VARIANT_OF, PUNCTUATION_VARIANT_OF, RELATED_TERM, BROADER_SEARCH_TERM, NARROWER_SEARCH_TERM, AMBIGUOUS_WITH}
- 확장 tier에서 쓰는 expansion 관계(APPROVED만): EXACT_ALIAS, SYNONYM_OF, ABBREVIATION_OF, ENGLISH_OF, SPELLING/SPACING/PUNCTUATION_VARIANT_OF

## 4.3 현행 스냅샷 규모 (seed_v2, SEARCH-DICT-LEGPROD-2026-09-16)
- **495 terms / 24 relations** (검증 ground-truth 464 − alias 약칭 6 dedup + alias term 15 + 큐레이션 오버레이 20)
- 구성: 법령명·부처·법제용어(APPROVED) + 약칭/띄어쓰기 변형 + KOSHA/화학 오버레이(국소배기장치·위험성평가·밀폐공간작업·산업용로봇 등 4종은 WO-2에서 APPROVED 승격)

---

# 5. 검색 엔진 tier (런타임)

`services/search_query_svc.py::lookup` 이 아래 순서로 tier를 오케스트레이션. 우선순위(WO §63):
**EXACT > NORMALIZED_EXACT > PUNCTUATION > ALIAS/ABBREVIATION > SYNONYM > TOKEN > TRIGRAM**

| tier | 위치 | 매칭 | 비고 |
|---|---|---|---|
| T1 EXACT | search_core | term_normalized 완전일치 | score 100 |
| T2 NORMALIZED_EXACT | search_core | term_compact(공백무시) 일치 | score 90 |
| T2b PUNCTUATION | search_core | term_no_punctuation 일치 | score 88. **한글 아래아 ㆍ(U+318D) 구분자 처리** — 실제 갭 수정분 |
| T3 ALIAS/SYNONYM | search_core | APPROVED expansion 관계 | score=관계별 |
| T4 TOKEN | search_runtime_ext (Kiwi) | 형태소 명사 토큰 overlap | **G1/G2 게이트로 leak 차단**(§8) |
| T6 TRIGRAM | search_runtime_ext (pg_trgm) | 유사도 fallback | score=30+sim*50, 항상 호출 |

- **APPROVED-only**: 프로덕션 인덱스/토큰 인덱스는 status=APPROVED만. PROPOSED/REVIEWED는 `non_production=true`로 제외.
- 모든 결과에 `match_type` + `matched_term` 부착(설명가능성, WO §62).
- 랭킹 결정론: score desc, subject_key asc.

---

# 6. 빌드 · 검증 · 배포 절차

## 6.1 결정론 빌드 (프로덕션 = seed_v2)
```bash
cd tools/search_dict
SEARCH_DICT_SEED=seed_v2 python3 build_dictionary.py build <out_dir>
# 산출: TAI_TERM_MASTER_v1.tsv, TAI_TERM_RELATIONS_v1.tsv,
#       TAI_SEARCH_RUNTIME_PROJECTION_v1.json, TAI_KIWI_TERMS_v1.tsv,
#       TAI_KIWI_USER_DICTIONARY_v1.txt, BUILD_SHA256SUMS.txt
```
- **재현가능 아티팩트 패턴**: 대용량 산출물 blob은 커밋 안 함. `artifacts/BUILD_SHA256SUMS.txt`(지문)만 커밋 → 배포 시 재빌드 후 `sha256sum -c`로 골든 대조.
- 현행 골든(seed_v2, WO-2 이후): MASTER `a906b95a…`, PROJECTION `4c1c7bb9…` (정확한 전체값은 매니페스트 참조; 시드 변경 시 반드시 갱신)

## 6.2 검증
```bash
python3 build_dictionary.py validate                        # 구조 검증(중복 term_id/무효 관계/미해소 subject 0)
SEARCH_DICT_SEED=seed_v2 python3 selftest.py                # stdlib 회귀 12케이스
SEARCH_DICT_SEED=seed_v1 pytest -q tools/search_dict/tests  # 13 passed/1 skip
SEARCH_DICT_SEED=seed_v2 pytest -q tools/search_dict/tests  # 14 passed
```
- 결정론: `build` 2회 → 바이트 동일이어야 함.

## 6.3 전체코퍼스 추출 (런타임, 읽기전용)
```bash
DATABASE_URL=<leg-prod RO> python3 extract_legprod.py verify        # 핀 체크섬 재현
DATABASE_URL=<leg-prod RO> python3 extract_legprod.py full <out>    # 14,942행(13,217 PROPOSED 포함)
```

---

# 7. API · 런타임 통합

## 7.1 엔드포인트 (prefix `/search-dict`)
- `GET /search-dict/lookup?q=<검색어>&limit=<n>` → 결정론 검색 결과(subject, match_type, score)
- `GET /search-dict/health` → `snapshot`, `subjects`, `indexed_terms`, `expansions`, `token_tier`, `trigram_tier`
- `GET /search-dict/census` → term_type 분포 등
- 기존 `/search` 등과 비충돌 확인됨. 라우터 등록: `router_registry/public.py`의 ROUTERS.

## 7.2 런타임 환경변수
- 프로젝션/사전 경로: `TAI_SEARCH_PROJECTION`, `TAI_SEARCH_KIWI_DICT`
- pg_trgm DSN: **스크래치 전용** `TAI_SEARCH_SCRATCH_DSN`(예 localhost). **TrigramTier는 DSN에 leg-prod ref(`wrfcedzgdrfupenzqhur`) 포함 시 RuntimeError로 즉시 거부** — 프로덕션 오염 방지 하드가드.
- 의존성: `kiwipiepy>=0.22.0`(tai-api 기존 통합, T4), Postgres+pg_trgm(T6, 스크래치)

## 7.3 라이브 확인 (병합 후)
- `/health` → `token_tier: true, trigram_tier: true`
- `?q=산안법` → 산업안전보건법 / EXACT · `?q=소음진동관리법` → 소음ㆍ진동관리법 / PUNCTUATION · `?q=MSDS` → 물질안전보건자료 / EXACT

---

# 8. 벤치마크 · 품질 게이트 (최종)

**게이트(오너 확정): MORPHOLOGY/COMPOUND_NOUN Top-3 ≥ 0.95, TYPO/TRIGRAM Top-3 ≥ 0.85, EXACT Top-1 = 1.0, NO_MATCH precision = 1.0.**

최종 상태: **8게이트 PASS + NO_MATCH precision 1.0**. 오프라인 tier(EXACT/SPACING/PUNCTUATION/ABBREVIATION) 100% 유지.

> **주의(authoritative 소스):** T4 실측치는 leak 봉합·재측정을 거치며 리포트마다 소수점이 미세 변동했다(예: MORPHOLOGY 0.9917 vs 0.9876, TYPO 0.9000 vs 0.9091). **확정 수치는 main에 병합된 `docs/knowledge/search-dict/RECEIPT_v2-runtime-closeout.md` + `SEARCH_BENCHMARK_RESULT_v1.tsv`를 authoritative로 삼을 것.** 모든 변동판이 게이트는 통과.

## 8.1 개선 궤적 (봉합 아님을 증명)
| category | WO-1 | R1(seed) | R2(튜닝) | leak봉합 후 |
|---|---|---|---|---|
| MORPHOLOGY | 0.8388 | 0.8719 | 0.99+ | ~0.99 (풀서비스 1.0) |
| COMPOUND_NOUN | 0.3333 | 0.6667 | 1.0000 | 1.0000 |
| TYPO (top-3) | 0.6500 | 0.6591 | 0.9000 | 0.90 |
| TRIGRAM (top-3) | 0.7500 | 0.7727 | 0.9773 | 0.9773 |
| NO_MATCH precision | 1.0 | — | 0.875(결합) | **1.0000 (봉합)** |

## 8.2 검증이 잡아낸 실제 결함 3건 (봉합 완료 — 참고용)
1. **EXACT 99.36%**: 약칭이 self+alias 이중 표면 → law_alias 약칭을 ground-truth self-emit에서 dedup(full 법령으로 해소) → 100%.
2. **TOKEN tier leak**: 무의미 쿼리 `없는법령명입니다` → `법`(1음절 일반명사) Kiwi noun-overlap 매칭. → TokenTier G1(overlap≥1 OR equal_compact OR substr_shorter_len≥2) + G2(강신호 5종)로 1음절 subject substring/약한 overlap 차단. NO_MATCH precision 0.875→1.0.
3. **leg-prod 42개 테이블 RLS 비활성** (§10 보안).

---

# 9. 성능

HTTP 풀파이프라인 T1–T6 (n=500, warm): **mean 10.3ms · p95 11.9ms · p99 21.3ms.**
- p99가 T1–T3 단독(1.1ms) 대비 ~2배 상승 = **TrigramTier(T6) 항상 호출** 대가. 절대값은 검색 UX로 충분.
- **후속 최적화 여지**: "T1–T3에서 히트 시 T6 skip"으로 p99 회복 가능(현재 미적용, 필수 아님).

---

# 10. 알려진 한계 · 후속 과제 (인계 항목)

| # | 항목 | 성격 | 권고 |
|---|---|---|---|
| 1 | **leg-prod 42개 테이블 RLS 비활성** | (보안, 범위 밖 발견) | 별도 검토 필요. 본 축과 무관하나 상류 DB 위험 |
| 2 | TrigramTier 항상 호출 → p99 2배 | 성능 | 트래픽 관측 후 "T1-T3 히트면 skip" 최적화 |
| 3 | TYPO top-1 참조대비 -0.06 | 트레이드오프 | precision 위해 recall 양보(정확도>재현율 부합). Top-3 게이트 통과. 조치 불요 |
| 4 | 13,217 PROPOSED 미적재 | 설계 | 필요 시 curation 후 APPROVED 승격 → 재빌드. 자동 승격 금지 |
| 5 | seed는 파이썬 리터럴/TSV 수작업 | 유지보수 | 대규모 확장 시 curation UI/DB화 검토 |
| 6 | 골든 SHA는 시드 변경마다 수동 갱신 | 유지보수 | CI에 `build`+`sha256sum -c` 게이트 편입 권고 |

---

# 11. 가드레일 (이관 후 필수 준수)

1. **leg-prod 읽기전용 SELECT만.** 쓰기/DDL/migration 금지. pg_trgm은 스크래치 DB에서만(하드가드 있음).
2. **법령엔진 로직·원천 데이터 수정 금지** (GPT 소유 계층).
3. **지표 날조 금지** — 실행 불가/미달은 PENDING/FAIL로 정직 기록.
4. **결정론 불변** — term_id 규칙·정렬·해시 불변. 시드 변경은 반드시 재빌드+골든 갱신+회귀.
5. **APPROVED-only 프로덕션.** 유사도(형태소/trigram)로 자동 병합 금지.
6. **병합은 오너 결정** — main 직접 push 금지, PR 경유.

---

# 12. 통합 지점 (검색엔진 전체 관점)

- **상류 의존:** `dict_legal_terms`/`law_alias`/`law_master` (법령엔진). 원천이 갱신되면 → `extract_legprod.py verify`로 핀 체크섬 재확인 → 필요 시 스냅샷 갱신·재빌드. 원천 스키마 변경 시 `extract_legprod.py`의 컬럼 매핑 점검.
- **하류 소비 (소속 서브시스템):** 이 축은 **LEG Candidate Enrichment / ON_DEMAND 보강 로직**의 일부다. 개념상 연결 대상은 `services/leg_ondemand_enrichment.py`(온디맨드 보강)와 `services/leg_candidate_adapter.py`(후보 어댑터)이며, `/search-dict/lookup`이 반환하는 `(subject_type, subject_key)`가 이들 후보 보강의 입력 신호가 되는 접점이다.
  - **[확인 필요, 정직]** 본 축은 `services/search_query_svc.py`(T1–T6 오케스트레이션)와 `/search-dict` API로 구현되었으나, `search_query_svc` ↔ `leg_ondemand_enrichment.py`/`leg_candidate_adapter.py` **간의 구체 배선(호출 경로)이 현재 코드에 존재하는지는 미확인**이다. 받는 팀은 (a) 이미 배선돼 있으면 계약 정합만 확인, (b) 아직이면 `search_query_svc.lookup` 결과를 후보 보강 파이프라인에 연결하는 어댑터를 명시적으로 작성해야 한다. 어느 쪽이든 APPROVED-only·정확도>재현율 특성을 high-precision 신호로 우선 사용 권장.
  - subject_key는 법령엔진의 주제 키와 정합해야 함(현재 법령명/부처명은 `law_master` 원천 문자열과 일치).
- **다른 검색 축과의 관계:** 본 축은 "정확한 어휘 해소" 담당. 의미검색/랭킹 축이 추가되면 본 축 결과를 high-precision 신호로 우선 사용 권장(정확도>재현율 특성).

---

# 13. 유지보수 가이드 (자주 할 작업)

- **검색어 추가:** seed_v2의 `_OVERLAY_TERMS`/관계에 추가(또는 신규 시드) → `validate` → `build` → 골든 갱신 → `selftest`+`pytest` → PR. status는 근거 있을 때만 APPROVED, 애매하면 PROPOSED/REVIEWED.
- **원천 재추출:** `extract_legprod.py verify`(드리프트 확인) → 변동 시 `extract/*.tsv` 갱신 + 핀 체크섬 갱신.
- **벤치마크 재측정:** `benchmark_run.py`(오프라인) + `benchmark_runtime_ext.py`(Kiwi/pg_trgm) → RESULT.tsv 갱신. 게이트 판정은 실측으로만.
- **성능 최적화(항목 2):** `search_query_svc.lookup`에서 T1–T3 히트 시 조기 반환 조건 추가 후 지연 재측정.

---

# 14. 이력 요약

- **v1** (PR #367/#30, 병합): 60-term 시드 + 스캐폴드. 오프라인 결정론만.
- **v2 실추출** (PR #368/#31): leg-prod 464행 바이트 검증 + 495-term. PUNCTUATION tier 엔진 갭 수정.
- **WO-1 런타임**: T1–T7 실측(Kiwi/pytest/HTTP), T4는 게이트 미확정으로 PROVISIONAL.
- **최종 클로즈아웃**: T1(a) live verify PASS, T3 CLOSED(14,942), T4 게이트 확정 → 초기 4/4 FAIL.
- **WO-2**: 핵심 복합어 4종 APPROVED 승격 + pg_trgm 튜닝 + T4/T6 HTTP 배선 → T4 4/4 PASS.
- **검증+leak 봉합**: pg_trgm precision 무혐의 확인, TOKEN tier leak 봉합 → NO_MATCH precision 1.0.
- **병합 완료** (2026-09-16, 오너 승인): 양 저장소 main. 상태 DONE.

---

# 15. 연락 · 소유

- 설계/기획: 기획창(Claude) — product/runtime 아키텍트
- 런타임 실행: Claude Code (로컬 Mac, Homebrew Postgres16, kiwipiepy 0.23.1)
- 법령엔진(원천): GPT 담당 — 수정 금지
- 최종 승인/병합: 오너(심태왕)

**끝.** 질의는 `RECEIPT_v2-runtime-closeout.md`(게이트 authoritative) + `SEARCH_DICT_V2_LEGPROD_SNAPSHOT.md`(추출 감사)를 1차 참조.
