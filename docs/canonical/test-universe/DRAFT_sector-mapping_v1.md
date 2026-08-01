---
wo: WO-MAPPING-002
class: records
type: draft
scope: canonical
project: test-universe
title: Sector Draft (A/UNRESOLVED/MULTI_TARGET)
version: 1
status: active
owner: taiwang
---

# SECTOR DRAFT (FROZEN) — WO-MAPPING-002

> Evidence 원문이 sector를 직접 지시하는 법령만 A(Draft). B=UNRESOLVED, C=MULTI_TARGET. **DB 수정 없음.** 추론·Pattern단독·ministry·domain_code 결정 금지.
> Input: Evidence Sheet(1f8c9fb2), Mapping Policy(93f102d2), Unmapped Inventory(375). 산출: sector_draft.md, sector_draft.json.

## 처리: 375 전량 (원문확보 368 + 원문미확보 7)
```text
A (Sector Draft) : 3
B (UNRESOLVED)   : 313  (원문확보 306 + 원문미확보 7)
C (MULTI_TARGET) : 59
합계             : 375
```

## A — Sector Draft (원문이 sector 직접 지시)
세 건 모두 적용범위 조문에 "건설공사"가 직접 명시되어 CONSTRUCTION 원문 직결(추론 없음):
1. 건설공사 안전보건대장의 작성 등에 관한 고시 — 제3조(적용범위) "총공사금액 50억원 이상인 건설공사에 적용" → CONSTRUCTION.
2. 건설업 산업안전보건관리비 계상 및 사용기준 — 제3조(적용범위) "법 제2조제11호의 건설공사 중…에 적용" → CONSTRUCTION.
3. 내진설계 일반(KDS 17 10 00) — 1.2(적용범위) "「건설산업기본법」…건설공사의 내진설계에 적용" → CONSTRUCTION.

Decision Reason 공통: 원문 적용범위가 「건설산업기본법」 건설공사로 한정 → sector 표준 CONSTRUCTION과 원문 직결. Pattern/ministry/domain_code 미사용.

## C — MULTI_TARGET (단일 sector 불가)
- 소방 화재안전기술기준(NFTC/NFPC)류: 건축물·공장·학교·병원·터널 등 시설 불문 적용 → 전 sector. (WO-MAPPING-001 Conflict와 일치)
- 4종+ 시설 언급 법령: 적용대상 복수.
- 총 59건. 목록 sector_draft.json.

## B — UNRESOLVED (Evidence 있으나 sector 결정 근거 부족)
- 원문에 적용 대상(업종/시설/모법)은 있으나 sector 표준(BUILDING/INDUSTRIAL/CONSTRUCTION/SPECIAL_FACILITY)으로 직접 한정하지 않음.
  - 예: "건축물에 설치되는 기자재"(건축물 언급이나 sector 진단 대상인지 원문이 안 정함), 염색업종(업종≠sector 표준), 수소용품·수소연료사용시설(시설≠sector), 위험기계·기구(근로자 보호이나 sector 한정 없음).
- sector 귀속에는 정책 규칙(적용대상→sector 기준표)이 선행돼야 함. 규칙 없이 결정하면 추론이므로 UNRESOLVED.
- 원문확보 B 306 + 원문미확보 7(군형법·난민법·터널설계기준 KDS27·교량 내진설계기준 KDS24 17 11/12·학교안전공제료·한국전통문화대 제3종시설물) = 313건.

## Review (추론 0건 확인)
- 1차 키워드 분류(A후보 53)에서 소방기준·우연한 '근로자'/'건축물' 단어를 A로 잡은 추론이 있었음 → Review에서 원문 대조로 검출 → 전부 재분류(소방→C, 직접한정 없음→B). 예: 고등교육법·국민건강보험법이 '근로자' 단어로 A후보였다가 B로 강등.
- 최종 A는 원문 적용범위가 sector를 직접 지시(건설공사)하는 3건만. 키워드/ministry/domain_code 단독 결정 0건. '아마/보인다/일반적으로' 0건.

## Freeze / 다음
- Sector Draft(3) · UNRESOLVED(313) · MULTI_TARGET(59) Freeze. DB 수정 0 · 자동매핑 0 · 추론 0.
- 관측(판단 아님): A가 3건뿐인 것은 원문이 sector 표준을 직접 한정하는 경우가 드물기 때문. 대다수 sector 귀속은 '적용대상→sector' 정책 규칙을 요구한다.
- 다음 WO-MAPPING-003(정책 수립): 도메인 판단으로 적용대상→sector 기준표를 세워 B/C 해소. 그 후 WO-CHG-005에서 DB 반영·Regression·Semantic Verify.

## 상태 (Obs-004 커버리지 파이프라인)
```text
① Inventory(375)           ✓ WO-CHG-004
② Evidence Sheet(368)       ✓ WO-COVERAGE-001 (1f8c9fb2)
③ Mapping Policy(패턴)       ✓ WO-MAPPING-001 (93f102d2)
④ Sector Draft(A3/B313/C59)  ✓ WO-MAPPING-002 ← 현재
⑤ 적용대상→sector 정책 기준표  ← WO-MAPPING-003
⑥ DB 반영 CHG + Verify       ← WO-CHG-005
```
