---
wo: WO-MAPPING-005
class: records
type: verification
scope: canonical
project: test-universe
title: Deployed Role-to-Sector Decision
version: 1
status: active
owner: taiwang
---

# DEPLOYED ROLE-TO-SECTOR DECISION — WO-MAPPING-005

> role_mapping 14건에 law_name→law_id 해소 후 law_id→sectors[] 결정안 작성. 14건만, 코드·DB 수정 0.
> 엔진 DB wrfcedzgdrfupenzqhur.

## 판정: POLICY_BLOCKED

## STEP 1 — C2 Wiring Selection (고정)
```text
Injection Target : public.law_sector_mapping
Runtime Consumer : _load_sector_allowed_draft_ids()
Contract         : law_id → sectors[]
```

## STEP 2 — Deployed Role Inventory (14건 전량)
```text
정확히 14건 확인. 4개 법령(+시행령):
  건설기계 안전기준에 관한 규칙   : id 1~7 (7건)
  수도용 자재와 제품의 위생안전기준 인증규칙 : id 8,9 (2건)
  어린이놀이시설 안전관리법        : id 10 (1건)
  제품안전기본법                  : id 11,12 (2건)
  제품안전기본법 시행령           : id 13,14 (2건)
Role 분포: REGULATED_OBJECT_ONLY 7 · FACILITY_ONLY 6 · UNRESOLVED 1(id 9)
pattern_id 없음: id 8,9 (수도용...)
```

## STEP 3 — law_name → law_id Resolution
```text
EXACT_MATCH 12건:
  건설기계 안전기준에 관한 규칙 → 4673f586-c098-4ca6-af62-a2dc9ce23797 (id 1~7)
  어린이놀이시설 안전관리법      → da3d6062-5ddb-46ec-bbef-e002dd4c2c99 (id 10)
  제품안전기본법                → c95ab19f-6805-4237-892f-43146a6281d7 (id 11,12)
  제품안전기본법 시행령          → a7520313-442d-4779-8ef4-62c9dad8fea5 (id 13,14)
NOT_FOUND 2건:
  수도용 자재와 제품의 위생안전기준 인증규칙 (id 8,9) → law_master에 없음
  → UNRESOLVED (억지 연결 안 함, 규율 준수)
```

## STEP 4 — Existing Sector Evidence → 차단
```text
★ 엔진 DB wrfcedzgdrfupenzqhur 스키마 실측 결과:
  law 관련 테이블 14개 존재 (law_master·law_article·law_alias·law_appendix·
    law_article_citation·law_article_delegation·law_article_part·law_attachment·
    law_content_raw·law_family_mapping·law_item·law_paragraph·law_version)
  sector_standard 존재
  ★★ law_sector_mapping 테이블이 이 DB에 존재하지 않음 (어느 스키마에도)

→ STEP4 "각 law_id의 현재 law_sector_mapping을 읽는다"의 대상 테이블 부재.
→ Existing Sector Evidence를 읽을 수 없음.
```

## STEP 5-8 — 진행 불가 (근거 부재)
```text
STEP5 Sector Decision의 근거 우선순위:
  1. 검증된 기존 manual_verified/web_search_verified 매핑  ← law_sector_mapping 부재로 확인 불가
  2. 해당 법령 원문의 명시적 적용 대상                      ← 원문 정독은 이 WO 범위 밖(별도 READ WO)
  3. 이미 승인된 sector 기준                               ← 승인된 Role→sector 규칙 없음(R-01)

세 근거가 모두 이 WO에서 확보 불가:
  - 근거1: law_sector_mapping 테이블이 이 DB에 없음
  - 근거2: 원문 정독은 별도 WO(READ 계열)
  - 근거3: Role→sector 변환 규칙 미정의(R-01, WO-WIRING-004에서 미정 확인)

이 상태에서 sector를 결정하면 이 WO가 명시적으로 금지한
  "Role=FACILITY이므로 BUILDING / Role=REGULATED이므로 INDUSTRIAL / 법령명 추정"
중 하나가 됨 → 금지 규율 위반.

따라서 STEP5~8 진행 불가. 14건 전량 UNRESOLVED로 남기는 것이 유일한 정직한 결과.
```

## STEP 9 — 판정: POLICY_BLOCKED
```text
사유:
  (1) C2 Injection Target인 law_sector_mapping이 엔진 DB에 실재하지 않음.
      → STEP1이 고정한 연결 지점의 물리적 전제가 이 DB에서 성립 안 함.
  (2) Sector 결정 근거 3종이 모두 이 WO에서 확보 불가(위 STEP5-8).
  (3) 14건 중 2건은 law_id도 NOT_FOUND(수도용...).

억지 결정 0: 근거 없이 sector를 채우지 않음.
실제 sector 결정 0건 (규율 준수).
```

## 확인 필요 (이 WO 범위 밖, 다음 단계 입력)
```text
Q1. law_sector_mapping은 어디에 있는가?
    - 가능성 a: 다른 DB/프로젝트 ref (엔진 런타임이 보는 실제 위치)
    - 가능성 b: 아직 미생성 (CHG-009는 pattern_dictionary·role_mapping만 반영)
    → WO-WIRING 시리즈는 '코드가 law_sector_mapping을 SELECT한다'까지 확인했으나,
      '이 DB ref에 그 테이블이 실재하는지'는 미확인이었음. 이번에 실측으로 드러남.
Q2. 엔진 런타임의 supabase 클라이언트가 실제로 어느 ref/스키마를 보는가?
    (anonymous_factory_service의 get_supabase() 대상 확인 필요)
```

## Exit Criteria 점검
```text
[v] C2 연결 지점 고정
[v] role_mapping 14건 전량 처리 (인벤토리)
[~] law_id 해소 (12 EXACT / 2 NOT_FOUND)
[x] Sector 결정 상태 전량 기록 → 근거 부재로 진행 불가(전량 UNRESOLVED)
[v] UNRESOLVED 억지 결정 0 (오히려 억지 안 함이 규율)
[x] Runtime Payload Dry Run → 결정 없어 불가
[x] 전량 의미검토 → 결정 없어 불가
[v] 코드·DB 변경 0
```

## 산출물 (진행분)
```text
deployed_role_inventory.csv (14건) · law_id_resolution.csv (12 EXACT/2 NOT_FOUND)
```

## 상태
```text
WIRING 설계        ✓ (STEP1~경계계약, C2 확정)
Role→Sector 결정   ✗ WO-MAPPING-005 → POLICY_BLOCKED
                     원인: law_sector_mapping 테이블이 엔진 DB에 부재 + 결정 근거 3종 확보 불가
다음(선행 필요)     : law_sector_mapping 실제 위치 확인 + 엔진 런타임 DB 타깃 확인
```
