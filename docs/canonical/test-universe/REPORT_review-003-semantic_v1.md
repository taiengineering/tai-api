---
wo: WO-REVIEW-003
class: records
type: report
scope: canonical
project: test-universe
title: Semantic Read-through Issue Inventory
version: 1
status: active
owner: taiwang
---

# REPORT — WO-REVIEW-003 112 전량 의무 Semantic 정독

> E2E_REVIEW(§12). review_full.json(before_clean 전량) 의무 전문을 실제 정독. 관측·등록·분류·영향도까지. **CHG 생성 없음(다음 WO).** 표현: 관측/등록/보류/후순위/분류.

## 0. 정정
WO-REVIEW-001은 통계적 이상 탐지였고 의미 정독이 아니었음. 본 WO에서 4 sector 전 의무구성을 실제로 읽어 의미 이상을 관측함. (그룹 내 의무 내용은 동일 → 대표 정독이 곧 전량 의미 검토)

## 1. Issue Inventory (누적)

| ID | Issue | Profile/범위 | Evidence(관측) | Confidence |
|---|---|---|---|---|
| 001 | 동일 입력 → 다른 출력 | 10 (building·construction·special) | 동일 (site_kind,scale,workers) 그룹 내 applicable_count 편차(예 building/medium/50 → 3 vs 7). `.order` 수정은 same-profile만 안정화, identical-input 편차 잔존 | High |
| 002 | 의무 정확 중복 | 112/112 | 동일 (law,의무) x2~x4 반복(소방 자체점검 x4, 스프링클러 헤드 x3, 중대재해 안전보건교육 x3 등). applicable_count에 중복 포함 | High |
| 003 | Preview만 저장(측정) | 전체 측정 | Runner가 `/anonymous-diagnosis` preview(12)만 저장. 전량 의무는 `*_required`에 존재 | High |
| 004 | 오적용/교차도메인 의무 | 전 sector 광범위 | (관측) 제조·건축·건설·특수 전반에 '표면공급식 잠수작업 시 조치', '에너지절약형 친환경주택의 건설기준\|설계조건' 부착. 건축물에 '도로터널 화재기준', '방사선 화재방호시설', 배타적 건물유형(다중이용업소·초고층·고층·공동주택) 동시 적용, 상호대체 소화설비(스프링클러·미분무·포·할론·CO2·분말) 전량 동시 | High |
| 005 | 카테고리(버킷) 오분류 | 광범위 | (관측) 선임 항목이 report 버킷에: '안전관리자 선임', '전기안전관리자 선임신고', '승강기 안전관리자', '안전보건관리담당자 선임'. 동일 의무가 action·report 양쪽에 동시('소방시설 관리 등') | High |
| 006 | 법 + 시행령/시행규칙 이중 계상 | 광범위 | (관측) 같은 의무가 상위법과 하위규칙에서 각각: 기계설비법/기계설비법 시행규칙(유지관리자 선임), 소방시설법/시행규칙(자체점검), 산안법/산안법 시행규칙(안전보건관리규정) | Medium |

## 2. 분류 (Engine/Data/Query/UI/Rule/Performance/Measurement)

| ID | 분류(후보) |
|---|---|
| 001 | Engine / Query (결정성) — Measurement Gate 미탐지 |
| 002 | Data / Query (중복 행 / DISTINCT 부재 후보) |
| 003 | Measurement (하네스) |
| 004 | Rule / Data (sector·조건 게이팅 부재 후보) |
| 005 | Query / Engine (버킷 매핑 후보) |
| 006 | Data / Rule (상위법·하위규칙 이중 등록 후보) |

## 3. 영향도 표 (완성 — 이 표 완성 전 CHG 생성 금지)

| ID | Issue | 범위 | 영향도 | CHG 여부 |
|---|---|---|---|---|
| 003 | Preview 저장 | 전체 | Critical | 후보 |
| 004 | 오적용/교차도메인 | 전 sector | Critical | 후보 |
| 001 | 동일 입력 다른 출력 | 10 profile | Critical | 후보 |
| 002 | 의무 정확 중복 | 112 profile | High | 후보 |
| 005 | 카테고리 오분류 | 광범위 | High | 후보 |
| 006 | 법+시행규칙 이중 | 광범위 | Medium | 후보 |

## 4. 후순위/처리 순서 (관측 기반 제안, 수정 아님)
- 측정 완전성(003)이 선행: 측정이 전량을 담아야 이후 모든 검증이 전량 위에서 성립(§11.6).
- 그다음 correctness Critical(004 오적용, 001 결정성) → High(002 중복, 005 오분류) → Medium(006).
- 각 항목은 별도 WO에서 Evidence+재현+영향범위 확인 후에만 CHG로 승격(§12.5/12.7).

## 5. 관측 노트 (보류 항목)
- 004의 '친환경주택 설계조건'·'표면공급식 잠수작업'이 전 profile 무차별 부착 → 특정 규칙군의 게이팅 부재로 보이나 원인 미확정(보류).
- 001과 002의 연관 가능성(중복 계수 편차가 applicable_count 편차에 기여) → 보류, 다음 WO에서 관측.
