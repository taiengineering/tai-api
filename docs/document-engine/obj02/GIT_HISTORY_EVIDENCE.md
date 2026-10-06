# GIT_HISTORY_EVIDENCE

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
실행자: Claude Code

---

## Git Anchor (OBJ02-A 조사 시점)

| 항목 | 값 |
|---|---|
| tai-api local HEAD | `7f3b5bf9a69c6bda25947da869fdf75c9db11d55` |
| tai-api origin/main | `d9ae49d05a4c35f19e842823d5cde9bebbd3f99a` |
| working branch | `docs/integrated-search-document-plan-20261007` |
| OBJ00 기준 SHA (initial) | `aa46bbb7ed07416784f3310681540c9fce7eef92` |

local HEAD는 branch tip (docs 커밋). origin/main과 diverged.

---

## OBJ01 이후 document scope drift 확인

| 항목 | 값 |
|---|---|
| OBJ01 close commit | `f5c035ec` docs(document): freeze OBJ01 canonical web-document architecture |
| OBJ02 WO commit | `7f3b5bf9` docs(document): add OBJ02-A binding and read-model discovery WO |
| document-engine source 변화 여부 | NO (origin/main 신규 커밋은 public-data-sync/KOSHA scope) |
| document_type_mapping scope drift | NO |
| runtime_form_schema scope drift | NO |

---

## Branch 최근 커밋 이력

```
7f3b5bf9 docs(document): add OBJ02-A binding and read-model discovery WO
f5c035ec docs(document): freeze OBJ01 canonical web-document architecture
b6de21f4 docs(document-engine): OBJ00 final evidence correction CORR-1/2/3
6d9d4762 docs(document-engine): OBJ00 read-only discovery evidence + CORR-A~F
ad91df39 docs(document): add object-based completion master plan v1
```

---

## Document-engine 관련 Source 파일 최근 커밋

### document_engine_svc.py / engine_document.py

| SHA | 메시지 |
|---|---|
| `1560f237` | fix(document-engine): generate_document() writes PENDING not GENERATED (WO-DOCUMENT-ARCH-03C) (#190) |
| `e496e794` | fix: 문서엔진 서비스 v1.1.0 — Audit WARNING 4건 수정 |
| `df697c62` | feat: 문서엔진 API v1.1.0 — schema + service + router (main 직접 배포) |
| `e35270a3` | feat: engine_document v1.0.0 — 문서메뉴 API 4개 + main.py v5.5.3 |

### document_forms_service.py / document_forms.py

| SHA | 메시지 |
|---|---|
| `7b99a577` | fix(17): 서식 목록 라우터에 {status,data} 봉투 추가 — 항상 빈 목록 해소 (#161) |
| `b837777e` | fix(engine-document): 서식 목록/상세에 penalty 별칭(=penalty_summary) (LEDGER §49 매핑분) |

---

## document_type_mapping / document_type_registry 관련

| 테이블 | created_at 범위 | 최초 DB 삽입 시점 |
|---|---|---|
| document_type_mapping | 2026-08-22 19:56:34 전체 동일 | 2026-08-22 단일 배치 삽입 |
| document_type_registry | 2026-08-22 20:18:14 / 20:44:53 | 2026-08-22 단일 배치 삽입 |

소스 코드에서 document_type_mapping을 생성/사용하는 migration 파일: git log에서 발견되지 않음 (docs/sql/ 경로의 NOT EXECUTED SQL 파일만 존재).

document_type_mapping을 읽는 Python service: 없음 (codebase 검색 결과 0건).

---

## runtime_form_schema 생성·승격 관련 코드

| 항목 | 경로 | 상태 |
|---|---|---|
| schema 생성 pipeline | `docs/sql/20260825_WP_PERSISTENCE_02A_STEP4A_UP.sql` | NOT EXECUTED 마커 있음 |
| CANDIDATE→APPROVED 승격 | `docs/sql/20260825_WP_PERSISTENCE_02A_STEP4D_UP.sql` | NOT EXECUTED 마커 있음 |
| Python API | `document_schema.py` (LEGACY, NOT MOUNTED) | 미사용 |
| 현재 DB APPROVED 1건 | dc79ac3c-388c-42dc-b029-3dd9bda54a47 | 승격 경로 미확인 (SQL 직접 실행 추정) |

---

## 관련 PLAN/WO/RESULT/HANDOFF 문서

| 커밋 | 문서 |
|---|---|
| `ad91df39` | docs/document-engine/master-plan/ (OBJ00~OBJ10 계획) |
| `6d9d4762` | docs/document-engine/obj00/ (16개 증거 파일) |
| `f5c035ec` | docs/document-engine/obj01/OBJ01_CANONICAL_DOCUMENT_ARCHITECTURE_v1.md |
| `7f3b5bf9` | docs/document-engine/obj02/WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001.md |

---

## MUTATION

| 항목 | 건수 |
|---|---:|
| application code change | 0 |
| DB write | 0 |
| storage write | 0 |
| deploy | 0 |
