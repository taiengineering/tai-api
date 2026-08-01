---
wo: WO-MAPPING-001
class: records
type: policy
scope: canonical
project: test-universe
title: Sector Mapping Policy (Pattern·Conflict·Policy Candidate)
version: 1
status: active
owner: taiwang
---

# SECTOR MAPPING POLICY (FROZEN) — Pattern·Evidence·Conflict·Policy Candidate

> WO-MAPPING-001. Evidence Sheet 기반으로 적용대상 Pattern을 구조화하고 Policy Candidate를 정의. **sector 결정·Draft·DB 수정 없음.** Evidence → (별도) Decision 순서 유지.
> Input: Evidence Sheet(1f8c9fb2), Unmapped Inventory(375), 적용대상 원문(coverage_evidence). 산출: mapping_policy.md, mapping_patterns.json(Pattern↔law_id 연결).

## STEP 1 — Evidence 정독
- Evidence Sheet 368 법령(6,087 조문)의 적용대상/시설/업종 원문 전량 검토. 판단 없음.

## STEP 2 — Pattern 목록 (적용대상 원문, 등장 법령수 / 단독패턴수)
적용대상 이름만 추출. sector 연결 없음.
```text
가스 70(단독11) · 에너지 65(4) · 환경 65(9) · 건축물 60(6) · 도로 45(6)
소방대상물 42(1) · 화학물질 42(7) · 특정소방대상물 41(0) · 전기설비 28(1)
산업안전 23(2) · 주택 22(1) · 학교 21(9) · 대기 20(3) · 공동주택 18(0)
고압가스 17(0) · 사업장 15(0) · 공장 14(0) · 근로자 13(0) · 위험물 13(1)
보일러 10(0) · 폐기물 10(3) · 수질 7(2) · 다중이용 6(0) · 승강기 6(2)
방사선 6(3) · 병원 6(1) · 건설공사 5 · 사업주 5 · 터널 5 · 의료기관 3
항만 3 · 전기안전 2 · 철도 2 · 고층건축물 1 · 교량 1 · 어린이놀이시설 1
```
- (Pattern↔law_id 연결 전량은 mapping_patterns.json)

## STEP 3 — Policy Candidate (sector 결정 아님)
각 패턴은 아래 정책 후보로 분류. 실제 sector 귀속은 WO-MAPPING-002.
- **[별도 검토 필요]** 다패턴 공존이 잦은 패턴(건축물·가스·에너지·환경·도로·소방대상물·특정소방대상물 등): 단독으로 sector를 지시하지 못함. 법령 성격(소방/환경/에너지 기준인지)과 함께 판단 필요.
- **[적용대상 명확 후보]** 단독패턴 비율이 상대적으로 높은 패턴(어린이놀이시설·승강기·의료기관·터널·교량·철도·항만 등): 특정 시설을 명시하나, 그 시설의 sector 귀속은 여전히 정책 기준 필요(예: 승강기=BUILDING? SPECIAL?).
- **[도메인 판단 필수]** 어떤 패턴도 그 자체로 sector를 결정하지 못한다. 최종 귀속은 WO-MAPPING-002의 sector 정책(적용대상→sector 기준표) 확립을 전제로만 가능.

## STEP 4 — Conflict (기록만, 해결 안 함)
- **4개 이상 패턴 동시 보유: 67개 법령.** 대표: 소방 기술기준(NFTC 102~502)류가 건축물+공동주택+공장+병원+학교+도로+터널을 전부 적용대상으로 언급 → 단일 sector 귀속 불가(소방설비는 시설 종류 불문 적용).
- 패턴 공존 상위: 소방대상물+특정소방대상물 41 · 건축물+소방대상물 39 · 건축물+특정소방대상물 39 · 건축물+에너지 32 · 가스+건축물 26 …
- **패턴→sector 규칙 불성립 증거:** "건축물" 언급 60개 법령의 상당수가 소방기준(전 sector 적용)이라 BUILDING 단정 불가. 즉 domain_code가 근거 아니었듯(WO-CHG-004), 적용대상 패턴 단독도 sector 근거가 못 된다.

## STEP 5 — Policy Freeze
- Pattern 목록 · Evidence 연결(mapping_patterns.json) · Conflict · Policy Candidate 확정.
- sector 결정 0 · Draft 0 · DB 수정 0 · 자동매핑 0 · 추론 0.

## 다음 (WO-MAPPING-002)
```text
Policy Review → Sector Decision → Draft
```
- 여기서 비로소 '적용대상 패턴 + 법령 성격 → sector' 기준표를 세우고(도메인 판단), Conflict(67 다패턴 법령)를 해소하며, Draft를 작성한다. DB 반영은 그 이후 별도 CHG.

## 규율 준수
- 적용대상 패턴을 sector로 연결하지 않음. Policy Candidate는 '검토 필요/명확 후보/판단 필수' 상태 분류일 뿐 sector 결정이 아님.
- Conflict는 기록만, 해결 안 함. law_sector_mapping·Draft·DB 무변경.
- Evidence → (별도) Decision 순서 유지.

## 상태
```text
Obs-004 커버리지 파이프라인:
  ① Inventory(375)          ✓ WO-CHG-004
  ② Evidence Sheet(368)      ✓ WO-COVERAGE-001 (1f8c9fb2)
  ③ Mapping Policy(패턴 구조)  ✓ WO-MAPPING-001 ← 현재
  ④ Sector Decision → Draft   ← WO-MAPPING-002
  ⑤ DB 반영 CHG               ← 이후
```
