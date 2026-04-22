# Cursor 작업지시서: 엔진 파일 5개 서비스 계층 분리

> 규칙 문서: `docs/DEV_RULES_SERVICE_LAYER.md` (반드시 먼저 읽을 것)
> 브랜치: `dev` → PR → `main`
> 핵심: **STEP 0(테스트) 없이 STEP 1로 절대 넘어가지 말 것**
> 작업 순서: 파일 1개씩 완료 후 다음 파일로. 동시에 2개 이상 건드리지 말 것.

---

## ⚠️ 사고 방지 규칙 (매 파일마다 적용)

```
1. git stash 또는 브랜치 생성 후 시작 — 언제든 원복 가능하게
2. 매 STEP 완료 후 uvicorn main:app --reload 로 서버 확인
3. 서버가 안 뜨면 즉시 git stash pop 또는 git checkout -- . 으로 원복
4. 한 번에 1개 파일만 분리. 2개 동시 작업 금지
5. 테스트가 깨지면 분리를 멈추고 테스트를 먼저 수정
6. 기존 API 응답 형식 절대 변경 금지
7. 20KB 이상 파일을 통째로 덮어쓰기 금지 — 함수 단위로 이동
```

## 작업 순서

| 순서 | 파일 | 크기 | 역할 |
|---|---|---|---|
| 1 | construction.py | 58KB | 건설업 법령엔진 |
| 2 | contracts_engine.py | 34KB | 계약 엔진 |
| 3 | diagnosis_integrated.py | 32KB | 통합진단 엔진 |
| 4 | legal_engine_v510.py | 25KB | 법령엔진 v510 |
| 5 | engine_equipment.py | 24KB | 설비 엔진 |

## 전체 작업지시서: /mnt/user-data/outputs/CURSOR_ENGINE_REFACTOR_5FILES.md 참조

## [TAI 개발 규칙]
문서: docs/DEV_RULES_SERVICE_LAYER.md
STEP 0(테스트) → STEP 1(헬퍼) → STEP 2(스키마) → STEP 3(서비스) → STEP 4(라우터) → STEP 5(테스트 보강)
