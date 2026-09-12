---
wo: WO-REVIEW-003
class: records
type: report
scope: canonical
project: test-universe
title: before_clean 112 Observation Inventory
version: 3
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

## Official LEG Semantic Review Addendum — 2026-09-12

Source: GPT semantic full-result review of `GPT_SEMANTIC_REVIEW_BUNDLE_112.zip`.
This addendum is not a Compiler mechanical comparator result.

- BEFORE: `BEFORE_BASELINE_V1`
- BEFORE checksum: `d2d2e39f1a328d4ccbd9f2e5dc7e772c788098ad9a215e3b72a48464915c7fc3`
- AFTER: `AFTER_OFFICIAL_LEG_V1`
- AFTER checksum: `2ebfe2e907e2639485acea31484987a04894b1e00c5c86d7bcb8f73d9141b1e4`
- Profile: 112 / 112
- GPT review method: actual legal meaning review
- ID matching: NO
- rule_id ↔ atom_id mapping: NO

Existing Obs-001 ~ Obs-006 remain the historical before_clean record. Their wording, scope, and evidence are not rewritten here.

Scope boundary: Safety Manager CORE22 applicability transport issue is tracked separately and is intentionally excluded from this addendum.

### Review Context — Observation ID 부여 금지

OLD BASELINE = comparison reference ≠ Golden.

기존 BEFORE는 실제 설비·작업 입력 해상도가 낮아 서로 다른 사업장이 동일하거나 광범위한 의무집합을 받는 사례가 존재했다. Official LEG AFTER는 실제 facility applicability 반영 수준이 높아졌다.

따라서 BEFORE와 다름 ≠ 자동 Regression.

이 내용은 Context Note로만 기록한다. Issue / CHG로 승격하지 않는다.

### Obs-007 — Generic capability와 subtype-specific 의무 동시 등장

- 관측: Official LEG 결과에서 일반적인 capability 입력이 존재하는 Profile에 보다 세부적인 설비형식·작업조건을 전제로 하는 의무들이 함께 존재함.
  - 관측 사례: `has_crane=true`가 있는 결과에서 타워크레인, 지브 크레인, 갠트리/주행 크레인, 이동식 크레인 등 세부 유형 의무가 함께 존재하는 사례. Evidence: PF-0001 Official request `form_data.has_crane=true`와 동일 Profile AFTER full_result에 해당 세부 유형 의무가 함께 존재.
  - 그 외 동일 계열 관측: `has_elevator` → 특정 승강기 유형 / 설치·조립·수리 전제 의무. `has_welding` → 아세틸렌 발생기 / 가스집합용접 / 터널·고압작업 등 세부조건 의무. `has_dust_work` → 특정 분진원·물질·터널작업 전제 의무. `has_boiler` → 보일러 내부 특정 작업 전제 의무. `has_pressure_vessel` → 압축공기 작업실 등 세부 전제 의무.
- 범위: Official LEG AFTER / 복수 Profile.
- 영향: High. Confidence: 등장 사실 High.

### Obs-008 — 철거 입력 Profile에서 타 대상 철거 의무 관측

- 관측: PF-0099 등 건설 철거 관련 입력을 가진 결과에서 일반 건설 철거와 직접 동일한 대상으로 보기 어려운 어린이놀이시설 폐쇄·철거 관련 의무가 존재함.
  - Evidence: PF-0099 Frozen `sector=CONSTRUCTION`, company industry `철거`, Official request `form_data.has_demolition=true`. AFTER full_result에 `어린이놀이시설 안전관리법` · `어린이놀이시설 안전관리법 16` · evidence `관리주체는 어린이놀이시설을 이용 금지ㆍ폐쇄ㆍ철거하는 경우에는 어린이 등이 출입하지 못하도록 조치를 하고`.
- 범위: 현재 확인 Evidence 기준 PF-0099.
- 영향: High. Confidence: 등장 사실 High.

Obs-004는 before_clean 당시의 역사적 관측으로 유지한다. Official LEG 철거 대상 Evidence는 측정 시점과 관측 단위가 달라 새 ID로 등록한다.

### Obs-009 — Consumer Work 입력의 canonical applicability 미표현

- 관측: Frozen Profile에는 실제 작업정보(용접, 고소작업, 전기작업, 밀폐공간, 도장, 화학물질취급 등)가 존재하지만, Official LEG request / canonical applicability에서는 이 work 문자열 자체를 법령 applicability 값으로 추론·변환하지 않는다. 현재 Bridge 원칙: work string → synthetic `has_*` inference = NO. 따라서 Frozen에 작업정보가 존재해도 별도의 exact canonical field가 없으면 해당 작업정보가 Runtime applicability에 표현되지 않는 범위가 존재한다.
  - Evidence: PF-0001 Frozen `layers.work=["용접","고소작업"]`. 동일 Profile Official request에는 `work` 문자열이 없고 `form_data` facility flags만 존재.
- 범위: Official LEG consumer input contract.
- 영향: High. Confidence: High.

이 Observation은 자동 `has_*` 변환을 만들어야 한다는 수정 제안이 아니다.

### Obs-010 — Manufacturing ksic_major Runtime contract 관측

- 관측: Manufacturing Profile 46 / 46. Official request에는 `ksic_major` = PRESENT. GPT Semantic Review에서 확인한 Runtime contract 결과에는 `unknown_fields` → `ksic_major`가 존재한다.
  - Evidence: Manufacturing 46/46 Official request `ksic_major` 비어 있지 않음. 동일 46 Profile AFTER full_result `unknown_fields`에 `ksic_major` 존재.
- 범위: Manufacturing 46 / 46.
- 영향: High. Confidence: High.

### Addendum Observation 표 (관측·범위·영향만 — 분류 없음)

| ID | 관측 | 범위 | 영향 |
|---|---|---|---|
| Obs-007 | Generic capability와 subtype-specific 의무 동시 등장 | Official LEG AFTER / 복수 Profile | High |
| Obs-008 | 철거 입력 Profile에서 타 대상 철거 의무 관측 | PF-0099 | High |
| Obs-009 | Consumer Work 입력의 canonical applicability 미표현 | Official LEG consumer input contract | High |
| Obs-010 | Manufacturing ksic_major Runtime contract 관측 | Manufacturing 46 / 46 | High |

