---
wo: WO-ANALYSIS-001
class: records
type: report
scope: canonical
project: test-universe
title: Obs-003 Analysis (Measurement Input Incomplete)
version: 1
status: active
owner: taiwang
---

# REPORT — WO-ANALYSIS-001 Obs-003 Analysis

> Obs-003(Measurement Input Incomplete) 하나만 분석. 원인·영향까지. 수정·구현·CHG·코드변경 없음.
> Input: Observation Inventory(6be576e4), Priority Table(c78ccf7c).

## 1. Observation
Obs-003 — Measurement Input Incomplete. 관측: 측정 결과가 preview(rules_table=rules_preview=12)만 반영되고 전체 의무(*_required, 합=applicable_count)가 검토에 사용되지 않음. 범위: 전체. 영향: Critical.

## 2. Evidence (객관적 증거만)

### E1 — 스냅샷은 전체 응답을 담고 있다 (입력은 완전)
- 파일: `before_clean/SNAP-0019-001.json` (Runner 산출 스냅샷).
- 최상위 키에 `response` 존재. `response.partialResult`에 `appointment_required·inspection_required·action_required·report_required` 존재.
- 실행결과: `action_required` 길이=70, `rules_table` 길이=12. (전체 의무 합 107 = applicable_count)
- 결론적 사실: **원본 엔진 응답 전체가 스냅샷에 저장되어 있다.** 절단은 저장 단계가 아니다.

### E2 — Runner 요약 로직이 preview 필드만 집계한다
- 파일: `e2e_runner_all.py`, 함수 `extract_meta(body)` (라인 48~65).
- 라인 51: `r = body.get("partialResult")`.
- 라인 52: `rules = r.get("rules_table")` — preview 필드만 취함.
- 라인 58: `obligation_total = r.get("applicable_count") or summary.total` — 숫자만 취함.
- `*_required` 배열(appointment/inspection/action/report)을 **참조하는 라인이 없음**.
- 산출: `rule_count = len(rules)` = 12 (preview 길이), `evidence_count`도 rules(preview)에서 계산.

### E3 — 엔진 응답 자체가 preview임을 명시
- `response` 최상위: `hasFullResult:true`, `message:"일부 결과만 표시됩니다. 전체 법령·의무 목록은 로그인 후 확인할 수 있습니다."`
- `rules_table` == `rules_preview` (둘 다 12, 동일 preview).
- 익명 엔드포인트(`/anonymous-diagnosis`)는 preview(rules_table 12)를 노출하되, 전체 의무 배열(*_required)도 함께 반환한다.

### E4 — 전체 재구성 가능성으로 역증명
- `review_full.json`을 before_clean 스냅샷의 `*_required`에서 재구성했고 `full_count == applicable_count`가 112/112 일치.
- 즉 전체 의무는 스냅샷에 이미 존재했고, 재구성 가능했다. 부족했던 것은 데이터가 아니라 **집계 대상 필드 선택**이다.

## 3. Root Cause
Evidence 기반 확정:
- 스냅샷 입력은 완전하다(E1, E4). 엔진 응답의 preview 필드(rules_table)와 전체 의무 필드(*_required)가 **둘 다** 스냅샷에 저장된다.
- Runner의 `extract_meta`가 **preview 필드(rules_table)만 읽어 요약/집계**를 만든다(E2). `*_required`를 집계에 포함하지 않는다.
- 따라서 이후 모든 검토·비교가 preview(12) 기준으로 수행되었다.
- **Root Cause: Runner 요약 단계(extract_meta)의 필드 선택이 preview(rules_table)로 한정되어, 스냅샷에 존재하는 전체 의무(*_required)가 집계·검토에 반영되지 않음.**
- 명칭 정정: 'Input Incomplete'가 아니라 'Aggregation/Consumption Incomplete'가 정확하다. 입력(스냅샷)은 완전, 소비(집계)가 부분적이다.

## 4. Impact
- **Runner**: 요약 산출(rule_count·evidence_count 등)이 preview 기준. (직접 영향)
- **Snapshot**: 영향 없음 — 전체 응답을 이미 저장(E1). (무영향)
- **Measurement**: 집계 지표(rule_count 등)가 preview 기준이라 전체 규모(applicable_count)와 불일치. (영향)
- **Review**: preview 기준 검토가 과거 오판을 유발(CHG-001/002 preview 착시). 단 전체 재구성은 가능했음(E4). (영향, 회복 가능)
- 影響 경계: Engine 로직에는 영향 없음(응답은 정상적으로 full 포함). 문제는 소비측(Runner/Review).

## 5. Conclusion
- Obs-003의 Root Cause는 **Runner `extract_meta`의 preview-한정 집계**로 확정.
- 스냅샷·엔진에는 결함 없음 — 전체 의무는 이미 존재·저장됨.
- 본 WO는 원인까지만. '어떻게 preview 대신 전체를 집계하도록 할 것인가'(구현)는 다음 CHG WO의 책임.
- 완료 상태: Root Cause 확정 · Evidence 문서화 · 수정 0 · CHG 0 · 다른 Observation 분석 0. 다음 CHG WO 실행 가능.
