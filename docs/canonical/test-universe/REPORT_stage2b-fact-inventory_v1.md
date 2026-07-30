---
wo: WO-2B-FACT-001
class: records
type: report
scope: canonical
project: test-universe
title: Stage 2b Fact Inventory Recovery (Fact Baseline)
version: 1
status: active
owner: taiwang
---

# REPORT — Stage 2b Fact Inventory Recovery

> WO-2B-FACT-001. Stage 2b 미진행. 목적 = 추론 오염 제거 · Fact Baseline 복구.
> 조사·분류만 수행. 새 설계·아키텍처·Boundary 판정·Grounding 형태 결정 없음.
> 전 항목은 FACT / UNKNOWN / INVALIDATED 세 상태 중 하나로만 분류한다.
> FACT 근거 = Freeze 문서 · Repository 파일 · Commit · Validation Report · 실제 코드 · 실제 DB 실측 중 하나.

## 1. FACT

| ID | 항목 | 상태 | 근거 | 비고 |
|---|---|---|---|---|
| F-01 | Canonical Phase 1 Freeze | FACT | Repository: `tai-api docs/canonical/phase1/REPORT_legacy-asset-isolation_v1.md` (sha be671a0e) · freeze tag `canonical-phase1-freeze` → commit e4803d77 | Wrapper/_impl 경계 |
| F-02 | Universe v1 | FACT | Repository: `tai-api docs/canonical/test-universe/STANDARD_test-universe_v1.md` (sha cc201d02) | Compiler 5 + LEG 66(active 24/inactive 42) · Taxonomy · Object · Signature · GAP 5 · Allowed Matrix |
| F-03 | Representative Registry (16) | FACT | Repository: `tai-api docs/canonical/test-universe/REGISTRY_representative-seed-set_v1.md` (sha ccc28f47) | 16 REP · signature=계약필드 발산점 · GAP 6 |
| F-04 | Generator 실재 | FACT | 실제 코드: `tai-api tools/test_universe/generator.py` (sha 4bb82823) | import = hashlib, json |
| F-05 | Generator = Build Asset | FACT | 실제 코드 F-04 docstring: "Dry Run: JSON/메모리, DB write 없음" | — |
| F-06 | Generator build_contract에서 building_use_type·construction_type 값 = seed["industry"] 리터럴 | FACT | 실제 코드 F-04: `if f in ("building_use_type","construction_type"): leg[f] = seed["industry"]` | Master 테이블 조회 아님(코드상 리터럴) |
| F-07 | Dry Run 84 Case | FACT | Validation Report: `tai-api docs/canonical/test-universe/REPORT_stage2a-validation-snapshot_v1.md` (sha 0175ee35) | 84 case · VERDICT PASS |
| F-08 | Invariant PASS (signature ⊆ contract 위반 0) | FACT | Validation Report F-07 | 전수 위반 0 |
| F-09 | Dedup PASS (fingerprint 84/84 unique) | FACT | Validation Report F-07 | — |
| F-10 | Determinism PASS (2회 재실행 동일) | FACT | Validation Report F-07 | — |
| F-11 | Stage 2a 종료 (Governance Reset, DB=0) | FACT | Validation Report F-07 | 검증 PASS 후 84행 TRUNCATE |
| F-12 | WO-2B-01 Grounding Architecture 문서 커밋 | FACT | Commit: `tai-api` 6a36b8c (blob 5a8a9562) | 문서 자산(설계 틀) |
| F-13 | Stage 2a validation snapshot 문서 커밋 | FACT | Commit: `tai-api` 8824ac5 (blob 0175ee35) | — |
| F-14 | execute_sql 복구 (taeng read-only 응답) | FACT | 실제 DB 실측: taeng project_ref vwlahtguyggrhvslabax, SELECT 정상 응답 | 이 세션 실측 |
| F-15 | taeng에 Master 6종 존재 | FACT | 실제 DB 실측 F-14: information_schema.tables | industry_master · ksic_process_map · kcsc_process_master · kcsc_work_master · equipment_model_master · process_equipment_map (public) |
| F-16 | building_use_type·construction_type = 독립 테이블 아님 | FACT | 실제 DB 실측 F-14: information_schema 조회 시 동명 테이블 미조회, 컬럼으로 존재(예: kcsc_process_master.construction_type) | 정본 소스는 미확정(→ U-05) |

## 2. UNKNOWN

| ID | 항목 | 상태 | 근거 | 비고 |
|---|---|---|---|---|
| U-01 | Grounding Registry 최종 형태 (구현 클래스 / 설계 계층) | UNKNOWN | 이 세션에서 결론 5회 변경 · 확정 근거 없음 | 재조사 대상 |
| U-02 | Master Grounding 방식 | UNKNOWN | F-06(리터럴)만 확인 · Master 정렬 방식 미실측 | 재조사 대상 |
| U-03 | Boundary Verification (격리 경계 적합 여부) | UNKNOWN | 이 세션 도출 결론은 추론 · 실측 미완 | 재실측 대상 |
| U-04 | Master Registry 구조 (컬럼·PK·Code·Join Key·상호관계) | UNKNOWN | F-15 존재만 확인 · 구조 미실측 | WO-2B-02 read-only 실측 대상 |
| U-05 | building_use_type·construction_type 정본 소스 | UNKNOWN | F-16 컬럼 존재만 확인 · 정본 위치 미확정 | 재조사 대상 |
| U-06 | Grounding Registry 별도 구현 필요 여부 | UNKNOWN | 확정 근거 없음 | 재조사 대상 |

## 3. INVALIDATED

> 이번 세션에서 추론으로 도출된 뒤 근거 부족으로 철회됨. 앞으로 사실로 사용하지 않는다.

| ID | 항목 | 상태 | 근거 | 비고 |
|---|---|---|---|---|
| X-01 | "Grounding Registry가 (코드에) 없다" | INVALIDATED | 심볼 검색 0건 근거 → 존재 판정에 부적절(운영자 지적) | U-01로 이관 |
| X-02 | "Master 참조 = Legacy 의존" | INVALIDATED | 근거 부족으로 세션 중 철회 | Runtime Dependency vs Code Reference 미구분 상태의 추론 |
| X-03 | "Code Reference이므로 Boundary 적합" | INVALIDATED | 추론 · 실측 미완 | U-03으로 이관 |
| X-04 | "Grounding Registry는 구현 클래스이다" | INVALIDATED | 확정 근거 없음 | U-01로 이관 |
| X-05 | Grounding 형태 A/B 및 (가)/(나) 안 | INVALIDATED | 이 세션 추론 산물 · 미판정 | 설계 결정은 이 WO 범위 밖 |

## 4. WO 종료

| 종료 조건 | 상태 |
|---|---|
| FACT 목록 작성 | 완료 (F-01~F-16) |
| UNKNOWN 목록 작성 | 완료 (U-01~U-06) |
| INVALIDATED 목록 작성 | 완료 (X-01~X-05) |

> 이 문서는 Stage 2b의 입력 자료이다. 다음 WO에서 UNKNOWN을 하나씩 FACT로 전환하는 기준 문서로 사용한다.
