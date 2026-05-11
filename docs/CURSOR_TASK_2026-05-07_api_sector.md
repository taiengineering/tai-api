# Cursor 작업지시서 — API sector 단일화 (`tai-api`)

**날짜**: 2026-05-07  
**범위**: 백엔드에서 **sector 문자열의 단일 진실 소스(`VALID_SECTORS`)** 확립 + 전역 비교·검증 정렬  
**목표**: `BUILDING` / `INDUSTRIAL`(또는 기존 `INDUSTRY` 명칭) / `CONSTRUCTION` 등 **표기·의미 불일치 제거**, 진단·가격·플래그 API가 동일 enum을 사용.

---

## 0. 사전 결정 (실행 전 PM/코드 확인)

1. **캐논 컬렉션**: 예) `("BUILDING", "INDUSTRIAL", "CONSTRUCTION")` — 현재 스키마에 `INDUSTRY`가 있으면 **한쪽으로 통일**할지 결정 (`schemas/diagnosis_integrated.py` 등).
2. **하위 호환**: 기존 클라이언트가 `INDUSTRY`를 보내면 **수용 별칭(alias)** 로 매핑할지, 400으로 거절할지.

---

## 1. 작업 묶음 (약 20파일)

### A. `VALID_SECTORS` 중심 (3파일 — “정의 + 노출”)

| 역할 | 제안 경로 | 내용 |
|------|-----------|------|
| 단일 정의 | `utils/sector_constants.py` (신규) 또는 기존 `utils/constants.py` | `VALID_SECTORS: tuple[str, ...]`, 필요 시 `normalize_sector(raw: str) -> str` |
| 요청 스키마 | `schemas/diagnosis_integrated.py` (및 sector 필드를 가진 공통 베이스) | `Literal[*VALID_SECTORS]` 또는 `Field(..., pattern=...)` |
| OpenAPI/공유 | 진단 라우터 또는 `main.py` 태그 설명 | 문서상 enum 일치 |

### B. sector 분기·비교 정렬 (약 17파일 — 라우터·서비스·유틸)

아래는 **grep으로 추가 확인 후 목록 확정** (`grep -rl "sector\|BUILDING\|CONSTRUCTION\|INDUSTRY" tai-api --include='*.py'`).

**우선 검토 라우터 (예시)**:

- `routers/diagnosis_integrated.py`, `routers/diagnosis.py`, `routers/anonymous_diagnosis.py`
- `routers/diagnosis_fields.py`, `routers/diagnosis_plan_recommend.py`, `routers/diagnosis_report.py`, `routers/diagnosis_roi.py`, `routers/diagnosis_transform.py`
- `routers/public_pricing.py`, `routers/admin_pricing.py`, `routers/price_policy.py`, `routers/price_setting.py`
- `routers/feature_flags.py`, `routers/engine_legal.py`, `routers/legal_engine_*.py`

**작업 내용 (각 파일)**:

- 하드코드 문자열 리스트 제거 → `VALID_SECTORS` 또는 `normalize_sector` 사용.
- `if sector == "INDUSTRY"` vs `"INDUSTRIAL"` 혼재 시 **한 규칙**으로 통일.

---

## 2. 구현 규칙

- **단일 import**: 비즈니스 코드는 `from utils.sector_constants import VALID_SECTORS, normalize_sector` 형태만 사용.
- **검증 위치**: 라우터 진입 또는 Pydantic 모델에서 잘못된 값은 422/400 + 명확한 메시지.
- **테스트**: 최소 1개 — 유효 sector / 별칭(허용 시) / 무효 값.

---

## 3. 완료 조건

- [ ] `VALID_SECTORS` 정의 1곳, 나머지는 참조만.
- [ ] `diagnosis_integrated` 등 주요 POST body의 sector 설명·enum이 코드와 일치.
- [ ] `INDUSTRY`/`INDUSTRIAL` 혼선 해소 (문서 + 코드 동일).
- [ ] 린트/기존 테스트 통과.

---

## 4. 참고 (현재 스키마 예)

`schemas/diagnosis_integrated.py` — `DiagnosisRunBody.sector` 설명에 `BUILDING | INDUSTRY | CONSTRUCTION` 명시됨. 본 작업에서 **캐논 명칭과 통일**할 것.
