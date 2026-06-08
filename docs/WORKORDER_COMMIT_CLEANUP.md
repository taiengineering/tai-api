# 작업지시서: 표준화 코드 커밋 + 브랜치 정리

> 문제: feature/layer-standardization-20260608 브랜치에
>       표준화 코드(STEP 1/A/B')가 커밋 안 됨 (로컬 unstaged).
>       대신 Phase 2 + 라우터 이동(PR #105/#104 중복)만 push됨.
> 목적: 표준화 코드를 깨끗한 브랜치에 커밋하고, 중복을 제거한다.
> 원칙: 엔진 수정 금지. 표준화 작업만 분리 커밋.

## 현재 상태 (확인됨)

```
origin/feature/layer-standardization-20260608:
  - Phase 2 작업 (PR #105와 동일) ← main에 이미 머지됨, 중복
  - _archive → routers 22개 복원 (PR #104) ← main에 이미 있음, 중복
  - 표준화 코드 ← 없음 (로컬 unstaged)

로컬 unstaged (표준화 작업 — 커밋 필요):
  routers/anonymous_diagnosis.py
  services/anonymous_factory_service.py
  services/diagnosis_integrated_svc.py
  services/input_normalizer.py
  services/legal_rules.py
  tests/test_anonymous_factory_service.py
  tests/test_legal_rules.py

로컬 untracked (감사 문서 — 보존):
  docs/ENGINE_CONNECTION_AUDIT.md
  docs/ENGINE_PIPELINE_MAP.md
  docs/LEGAL_DIAGNOSIS_LAYER_PROBLEMS.md
  docs/LEGAL_DIAGNOSIS_LAYER_SURVEY.md
  docs/LEGAL_ENGINE_AUDIT.md
  docs/PIPELINE_TRACE.md
```

## 작업 1: 깨끗한 브랜치 생성 (main 최신에서)

```
현재 오염된 브랜치는 버리고, main 최신에서 새로 분기:

  git stash                              # 표준화 작업 임시 보관
  git checkout main
  git pull origin main                   # 최신 main (PR #104, #105 포함)
  git checkout -b feature/input-standardization-clean
  git stash pop                          # 표준화 작업 복원
```

이유: 기존 브랜치는 PR #104/#105 내용이 중복되어 머지 시 충돌/혼란.
main 최신에는 이미 그 내용이 있으므로, 표준화 작업만 깨끗이 올린다.

## 작업 2: 표준화 코드만 커밋

```
git add \
  routers/anonymous_diagnosis.py \
  services/anonymous_factory_service.py \
  services/diagnosis_integrated_svc.py \
  services/input_normalizer.py \
  services/legal_rules.py \
  tests/test_anonymous_factory_service.py \
  tests/test_legal_rules.py

git commit -m "feat: 입력 표준화 (STEP 1/A/B')
- STEP 1: 소비자 입력 → factories 저장 (building_use_code, floor_count)
- STEP A: normalizer 소비자 경로 연결 (단위 문자열 방어)
- STEP B': sector 어휘 표준 (DB=INDUSTRIAL/엔진=MANUFACTURING)
  + 세 섹터 입력 필드 표준화
- normalize_sector_db: MANUFACTURING→INDUSTRIAL 매핑 추가
- facility_applicability_eval 미변경 (엔진 보존)"
```

## 작업 3: 감사 문서 커밋 (별도)

```
git add docs/ENGINE_*.md docs/LEGAL_*.md docs/PIPELINE_TRACE.md
git commit -m "docs: 엔진 감사 + 레이어 조사 문서"
```

## 작업 4: push + PR 생성

```
git push -u origin feature/input-standardization-clean
```

PR 생성 (Cursor가 gh 인증 없으면 URL만 보고):
  base: main
  head: feature/input-standardization-clean
  title: "feat: 법령진단 입력 표준화 (STEP 1/A/B')"
  draft: false (검증 완료됨)

## 작업 5: 머지 전 최종 검증

```
새 브랜치에서:
  pytest tests/test_anonymous_factory_service.py
  pytest tests/test_legal_rules.py
  → 전부 통과 확인

  3섹터 진단 시뮬레이션:
    BUILDING / INDUSTRIAL / CONSTRUCTION
  → 전부 정상 완료, sector_check 통과
```

## 검증 기준

```
- 새 브랜치가 main 최신에서 분기됨 (PR #104/#105 중복 없음)
- 표준화 코드만 커밋됨 (라우터 이동 중복 없음)
- git diff main..HEAD --stat 에 표준화 파일만 나옴
- 테스트 전체 통과
- 3섹터 정상
```

## 주의

- 기존 오염 브랜치(feature/layer-standardization-20260608)는 버림
- 엔진 평가 로직(facility_applicability_eval.py) 미변경 확인
- git diff에 _archive/routers 이동이 나오면 안 됨 (중복 신호)
- PR 생성 후 머지 전 보고
