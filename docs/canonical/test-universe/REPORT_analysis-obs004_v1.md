---
wo: WO-ANALYSIS-004
class: records
type: report
scope: canonical
project: test-universe
title: Obs-004 계층 추적 (왜 도달했는가)
version: 1
status: active
owner: taiwang
---

# REPORT — WO-ANALYSIS-004 Obs-004 Analysis (도달 경로 추적)

> 핵심 질문: "왜 예상 밖 sector profile까지 도달했는가"(사실 추적). "왜 있으면 안 되는가"(당위)는 다루지 않는다. 오적용/과적용 판단 없음 — 도달 경로만. 수정·CHG 없음.
> Input: Obs-004 재확인(VALID, d7d4043e), Observation Inventory(6be576e4).

## 1. Observation
Obs-004 — 지목 항목이 예상 밖 sector profile에 등장(VALID, 전량 정독 확인). 대표 3항목: 에너지절약형 친환경주택, 표면공급식 잠수작업, 방사선 화재방호시설.

## 2. Evidence (도달 경로, 계층별)

### E1 — 대표 항목의 law_sector_mapping 상태
- 에너지절약형 친환경주택의 건설기준: **UNMAPPED**(sectors 비어있음).
- 방사선 안전관리 기술기준 / 방사선기기 설계승인 / 의료분야 방사선안전관리: **UNMAPPED** 3건.
- (대조) 산업안전보건기준에 관한 규칙: **mapped** = {BUILDING, INDUSTRIAL, CONSTRUCTION}, mapping_method=auto_regex, confidence=HIGH.

### E2 — 엔진의 미매핑 통과 정책 (services/anonymous_factory_service.py)
- `_load_sector_allowed_draft_ids` docstring(명시적 규칙, "사장님 확정"):
  - sector가 sectors에 포함된 draft → 통과
  - **law_sector_mapping에 매핑이 아예 없는 법령의 draft → 통과(가지고 감)** — "미매핑은 나중에 매핑을 채운 뒤 제외 예정. 지금 빼면 의무 누락 위험".
  - 다른 sector 전용으로 명시된 법령 → 제외
- 코드 일치(4단계 판정):
  ```
  if secs is None:   allowed.add(did)   # 미매핑 → 통과
  elif key in secs:  allowed.add(did)   # 해당 sector → 통과
  # else:            제외               # 타 sector 전용
  ```
- 즉 미매핑 통과는 버그가 아니라 **문서화된 의도된 동작**(누락 방지 목적).

### E3 — 미매핑 규모
- 활성 법령 768개 중 **미매핑 375개(48.8%)**. 에너지절약형주택 article은 executable_draft로 실재(도달 경로 상류 확인, status=CANDIDATE).

### E4 — 교차검증(매핑된 항목의 sector 분포가 매핑값과 일치)
- 잠수작업 = 산업안전보건기준에 관한 규칙 = 매핑 {BUILDING, INDUSTRIAL, CONSTRUCTION}.
- Review(d7d4043e) 관측: 잠수작업이 제조(INDUSTRIAL)·건축(BUILDING)·건설(CONSTRUCTION)에 존재, 특수(SPECIAL_FACILITY)엔 부재.
- **매핑값과 등장 sector가 정확히 일치** → 엔진이 매핑을 올바르게 읽고 거른다는 증거. 매핑이 있으면 매핑대로 sector가 갈리고, 없으면(에너지절약형주택·방사선) 전 sector 통과.

## 3. 도달 경로 (Evidence 종합)
```text
법령(law_master) — domain_code는 있으나 law_sector_mapping 미매핑(E1,E3)
   ↓
_load_sector_allowed_draft_ids: secs is None → allowed.add (E2, 미매핑 통과 정책)
   ↓
_load_draft_slot_groups: allowed에 포함되어 평가 대상 적재
   ↓
evaluate_single_factory: facility 조건 평가 → 충족 시 applicability 생성
   ↓
_compiler_result_to_step1_format: profile 출력
```
- 매핑된 항목(잠수작업)은 이 경로의 sector 필터에서 매핑대로 갈림(E4). 미매핑 항목(에너지절약형주택·방사선)은 필터를 통과.

## 4. Root Cause (계층)
- **계층 = Metadata (law_sector_mapping 미완성).** Applicability 엔진 로직이 아니다 — 엔진은 설계대로(미매핑=통과) 동작하며, 매핑된 법령은 정확히 sector를 가른다(E4).
- "왜 도달했는가" = **해당 법령의 sector 매핑이 없고(미매핑 375/768), 엔진이 미매핑 법령을 누락 방지 목적으로 전 sector 통과시키기 때문.**
- 성격: 데이터 미완성(매핑 커버리지 48.8% 미완) + 명시적 통과 정책의 결합. 코드 결함 아님.

## 5. Impact
- 도달 범위: 미매핑 법령(375개)의 의무가 sector 무관하게 전 profile 후보로 진입(facility 조건 충족 시 등장). 에너지절약형주택은 4 sector 전부(112/112).
- 계수: 미매핑 법령이 applicable_count에 포함.
- 참고(당위 아님): 미매핑 375개 중 실제로 특정 sector 전용이어야 할 법령이 있다면 매핑 완성으로 걸러질 것이나, 어떤 법령이 어느 sector여야 하는지는 본 WO 범위 밖(정오 판단 = 별도).

## 6. Conclusion
- Obs-004 Root Cause = **law_sector_mapping 미완성(Metadata 계층) + 미매핑 통과 정책.** 엔진 로직 정상(E4가 증명).
- 본 WO는 도달 경로까지. "이 법령이 이 sector에 있으면 안 된다"(당위)와 "어떻게 매핑을 채울/거를 것인가"(수정)는 다음 CHG WO의 몫.
- 완료: Root Cause 계층 확정 · Evidence(E1~E4) · 수정 0 · CHG 0 · 당위 판단 0.

## 상태
```text
Obs-003 : RESOLVED
Obs-001 : RESOLVED
Obs-002 : RESOLVED
Obs-004 : ANALYZED (Root Cause = Metadata/law_sector_mapping 미완성) → CHG 대상
Obs-005 : OPEN (재확인 필요)
Obs-006 : OPEN (재확인 필요)
```
