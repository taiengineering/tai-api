---
wo: WO-REVIEW-003
class: records
type: report
scope: canonical
project: test-universe
title: before_clean 112 Observation Inventory
version: 2
status: active
owner: taiwang
---

# OBSERVATION INVENTORY — before_clean 112 전량 정독

> §12 E2E_REVIEW. Review에서 확정되는 것은 **관측·범위·영향**뿐이다. **분류(Rule/Data/Engine/Query)는 Analysis이므로 여기 넣지 않는다.** 원인·수정·가설·우선순위·Dependency·CHG 없음 — 모두 후속 WO.
> (v1에서 '분류' 컬럼을 넣은 것은 §12 위반이었음. v2에서 제거.)

## 정독 범위
제조 46 · 건축 29 · 건설 27 · 특수 10 = 112 전량. 각 sector applicable_count 값별 대표 + 동일입력 편차쌍(PF-0020 vs PF-0021 등)의 의무 전문 정독.

## Observation Inventory

### Obs-001 — 동일 입력, 다른 출력
- 관측: 동일 (site_kind,scale,workers) 그룹 안에서 의무 집합이 profile마다 다르다. building/medium/50 — PF-0021엔 [KEC 231.5]·[KEC 351.6]·[KEC 503.2.4]·[KEC 605.32.1]·에너지절약형주택이 존재하고 PF-0020엔 없다(차이 4~5건). construction/large/450 — PF-0028엔 에너지절약형주택 존재, PF-0030엔 없음. special/large/300 — PF-0039엔 존재, PF-0038엔 없음.
- 범위: building · construction · special. (manufacturing 동일입력군은 균일 — 미관측)
- 영향: Critical. Confidence: High.

### Obs-002 — 동일 (law, obligation)의 다중 등장
- 관측: 112/112 profile에서 같은 (법령,의무)가 2회 이상 등장. 소방 자체점검 결과의 조치가 report에 6~7회(건축), 건설기술진흥법 안전관리계획 수립이 report에 3회(건설), 안전보건교육규정·장애인복지법 신고가 2회(특수), 중대재해 안전보건교육이 다회.
- 범위: 전 sector 112/112.
- 영향: High. Confidence: High.

### Obs-003 — Measurement Input Incomplete
- 관측: 측정 입력(스냅샷)이 전체 결과가 아니다. 응답 message="일부 결과만 표시됩니다...", hasFullResult=true, rules_table=rules_preview=12. 이전 Runner 파싱이 이 preview만 사용. 전체 의무는 *_required 배열에 있으며 합=applicable_count.
- 범위: 전 측정.
- 영향: Critical. Confidence: High.
- 비고: 명칭을 'Preview만 저장'에서 'Measurement Input Incomplete'로 일반화 — 향후 Sampling/Pagination/Compression/Partial 등 다른 형태로 나타나도 동일 Issue로 관리.

### Obs-004 — 특정 sector에 타 도메인으로 보이는 법령이 존재
- 관측(등장 사실만; 오적용/정책/Rule정의/데이터 여부 판단하지 않음):
  - '산업안전보건기준에 관한 규칙 | 표면공급식 잠수작업 시 조치' → manufacturing·building·construction 존재.
  - '에너지절약형 친환경주택의 건설기준 | 설계조건' → 4개 sector 전부 존재.
  - '방사선 안전관리 등의 기술기준에 관한 규칙 | 화재방호시설' → building·construction·special 존재.
  - building 일반 profile에 '도로터널 화재안전기준'·'다중이용업소'·'초고층 복합건축물'·'공동주택'·'고층건축물'이 함께 존재.
- 범위: 전 sector(항목별 상이).
- 영향: Critical(광범위). Confidence: 등장 사실 High.

### Obs-005 — 선임류 의무가 report category에 위치
- 관측: '전기안전관리자 선임'·'승강기 안전관리자'·'안전관리자 선임 등'·'유해화학물질관리자'가 report에 위치. '안전보건관리규정의 작성'이 산안법·산안법 시행규칙에 분산 등장.
- 범위: 광범위.
- 영향: High. Confidence: 등장 사실 High.

### Obs-006 — 동일 사안이 법/시행령/시행규칙으로 분리 등장
- 관측: 같은 사안이 법과 시행규칙으로 나뉘어 각각 등장. '기계설비법 | 선임'+'기계설비법 시행규칙 | 선임', '산업안전보건법 | 안전보건관리규정의 작성'+'산업안전보건법 시행규칙 | 안전보건관리규정의 작성'.
- 범위: 광범위.
- 영향: Medium. Confidence: 등장 사실 High.

## Observation 표 (관측·범위·영향만 — 분류 없음)

| ID | 관측 | 범위 | 영향 |
|---|---|---|---|
| Obs-003 | Measurement Input Incomplete (preview만 저장) | 전체 | Critical |
| Obs-004 | 타 도메인으로 보이는 법령 존재 | 전 sector | Critical |
| Obs-001 | 동일 입력, 다른 출력 | building/construction/special | Critical |
| Obs-002 | 동일 (law,obligation) 다중 등장 | 112/112 | High |
| Obs-005 | 선임류 의무가 report에 위치 | 광범위 | High |
| Obs-006 | 법/시행령/시행규칙 분리 등장 | 광범위 | Medium |

## 후속 WO로 이관되는 것 (본 Review 범위 밖)
- **분류** (Rule/Data/Engine/Query/UI/Measurement): Analysis WO에서 처음 부여.
- **원인·가설·수정**: 각 Issue의 별도 CHG WO.
- **우선순위·Dependency**: 우선순위 결정 WO에서 합의 (예: 003 선행 여부 등). 본 문서는 순서를 확정하지 않는다.

## §12 준수
- 관측·등록·보류·후순위·분류(제외)만. 원인·수정·가설 없음.
- Review 흐름(읽음→등록→다음→…→112 완료→Inventory)을 끝까지 유지.
- 이 Inventory 확정 전/후 어떤 CHG도 생성하지 않음. CHG는 우선순위 WO 이후.
