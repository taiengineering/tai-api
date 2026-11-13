# Phase 7 — TAI ↔ Check Integration Design

목표: **LEG 결과를 Check Engine으로 검증**하기 위한 TAI 측 통합 설계.

핵심 원칙 (절대 불변):

- **Check Runtime 수정 금지. Check 계약 수정 금지. Check 상태값 추가 금지.**
- **Check는 소비만 한다. TAI가 적응한다.** 모든 변환/판단/저장/표시는 TAI(host) 책임.
- Check는 도메인을 모른다(domain-blind). LEG의 도메인 의미(who/what/condition/completeness/의무유형 등)는 Check로 전달되지 않는다.
- AI는 설명을 보조하고, **모든 결정은 사람**이 한다 (Auto Governance 금지).

문서 구성:

1. `01_LEG_OUTPUT_ANALYSIS.md` — LEG 실제 출력 구조 분석
2. `02_LEG_TO_CHECK_ADAPTER_DESIGN.md` — LEG 출력 → Check 입력 매핑(TAI측 어댑터)
3. `03_CHECK_RESULT_STORAGE_DESIGN.md` — Check 결과(EvidenceReport) 저장 설계
4. `04_CHECK_INVOCATION_TIMING_DESIGN.md` — Check 호출 시점/방식 설계
5. `05_HUMAN_REVIEW_FLOW_DESIGN.md` — 사람 검토 흐름 설계

근거 출처 (실제 코드/문서, 읽기 전용 확인):

- LEG 엔진: `45cminc/leg` (법령 도메인 시맨틱 런타임 엔진)
  - `contracts/projection.boundary.md`, `contracts/signals/emitted-signals.md`
  - `docs/2026-05-31_LEG_RESULT_STANDARD_v1.md` (Obligation Standard)
  - `docs/2026-05-30_LEG_output_adapter.md` (build_result raw + adapter UI-ready)
  - `docs/2026-06-01_TAI_MVP_OUTPUT_SPEC_v1.md` (TAI MVP 제품 범위)
- Check 엔진: `45cminc/check` (Phase 4 Runtime + Phase 6 Public API; **동결**)
  - `docs/PUBLIC_API.md` — `runCheck(input): EvidenceReport`, 상태값 정의

> 본 설계는 **문서(설계)** 단계다. 구현 코드는 포함하지 않는다. PR은 **Merge 금지**.
