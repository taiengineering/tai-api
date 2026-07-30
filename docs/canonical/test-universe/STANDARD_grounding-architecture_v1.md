---
wo: WO-E2E-DATASET-002-2B-01
class: normative
type: standard
scope: canonical
project: test-universe
title: Grounding Architecture (Universe v1 → Master Registry connection layer)
version: 1
status: active
owner: taiwang
---

# STANDARD — Grounding Architecture

> WO-2B-01. Stage 2b 목표 = **Objects Expansion → Master Grounding.**
> Universe v1(추상)을 폐기/확장하지 않고, 그 아래 **Grounding Registry + Master Registry** 계층을
> 추가해 실제 소비자 입력 Master(KSIC/KCSC/Building/Equipment)에 연결한다.
> **본 WO는 구조·관계유형·틀만 정의(DB 접근 없음). 실 코드값은 WO-2B-02(execute_sql 복구 후) 실측으로 채운다.**

## 1. 계층 구조 (확정)

```
Universe v1 (Concept, 불변)            test-universe-v1
  Taxonomy · Object(개념) · Signature · Allowed Matrix
        │  ← Grounding Registry (연결 계층, 본 WO에서 틀 정의)
        ▼
Master Registry (실 코드 참조, taeng SoT)
  제조: KSIC     industry_master · ksic_process_map
  건설: KCSC     kcsc_process_master · kcsc_work_master · construction_type
  건물:          building_use_type
  설비:          equipment_model_master · process_equipment_map
        │
        ▼
Contract (Compiler 5 + LEG 66, 불변)
        ▼
Generator → Dataset → Semantic E2E
```

## 2. 불변 경계 (인계서 원칙)

```
Universe v1   : 불변 (Object 개념·Signature·Taxonomy·Allowed Matrix 무수정)
Signature     : 불변 (grounding은 objects를 실 코드로 채울 뿐, signature/contract 미변경)
Contract      : 불변 (Compiler 5 + LEG 66)
Master 원본   : taeng이 SoT — Registry는 참조(코드체계·조인키·컬럼)만 기록, 데이터 복제 금지
Grounding     : 연결 계층만 추가 (신규 매핑만 정의)
```

## 3. Grounding Registry 스키마 (틀 — 실 코드값은 WO-2B-02에서 채움)

각 Universe 추상 Object/Signature-field 를 실 Master 코드에 잇는 매핑 레코드:

```
grounding_id        : GRD-<layer>-<nnn>
universe_ref        : Universe v1의 추상 Object 또는 signature field_code
                      (예: Object "크레인" · field "has_tower_crane")
master_source       : 실 Master 테이블명 (industry_master / kcsc_process_master / ... )   ← WO-2B-02 실측
master_code         : Master 내 실제 코드/PK 값                                            ← WO-2B-02 실측 (추측 금지, 지금은 ∅)
join_key            : Universe↔Master 조인 키 컬럼                                        ← WO-2B-02 실측
relation_type       : EXACT | PARTIAL | ONE_TO_MANY | MANY_TO_ONE | GAP
coding_system       : KSIC | KCSC | BUILDING_USE | EQUIPMENT | (해당 sector 코딩축)
sector_axis         : 제조 | 건설 | 건물 | 공통
note                : 근거/한계
```

> master_code·join_key 는 **WO-2B-02 실측 전까지 공란(∅)**. 추측으로 채우지 않는다(인계서 §7).

## 4. 관계 유형 (Relation Type) 정의

```
EXACT        Universe 추상 1건 ↔ Master 실코드 1건 정확 대응
             (예: Object "보일러" ↔ equipment_model_master 특정 std 1건)
PARTIAL      추상 개념의 일부만 Master가 표현 (개념 > 코드)
ONE_TO_MANY  추상 1 ↔ Master 다수 (예: "크레인" ↔ 여러 crane std 코드)
MANY_TO_ONE  추상 다수 ↔ Master 1 (여러 개념이 한 코드로 수렴)
GAP          추상 개념이 있으나 Master에 대응 코드 없음
             (억지 매핑 금지 — ∅ 유지, 확장 후보로 기록)
```

## 5. Sector별 Grounding 축 (실 Master 대응 — 코드값은 WO-2B-02 실측)

```
제조   objects → KSIC 축
       업종      industry_master        (코드체계·PK·컬럼 = WO-2B-02 실측)
       공정      ksic_process_map        (KSIC→공정 조인)
       설비      equipment_model_master · process_equipment_map (공정→설비 조인)

건설   objects → KCSC(건설표준코드) 축
       공정      kcsc_process_master     (BUILDING·CIVIL·COMMON)
       작업      kcsc_work_master
       유형      construction_type

건물   objects → 용도분류 축
       용도      building_use_type
```

> 각 축의 실제 **컬럼·PK·Code·Join Key·관계**는 WO-2B-02에서 read-only SELECT로 전부 실측한다(추측 금지).

## 6. WO-2B-02 실측 대상 (execute_sql 복구 후, read-only)

```
industry_master · ksic_process_map · kcsc_process_master · kcsc_work_master
· equipment_model_master · process_equipment_map · building_use_type

각 테이블: 컬럼 · PK · Code 컬럼 · Join Key · 상호 관계 → 전부 실측
→ 실측값으로 Grounding Registry의 master_code/join_key/relation_type 확정
```

## 7. Stage 2b 종료 조건 (인계서 §9)

```
Universe → Grounding Registry → Master Registry → Contract 연결 완료
  → 84 Case Dry Run (objects를 실 Master 코드로 grounding, 메모리)
  → Signature 유지 검증 (grounding 후에도 signature ⊆ contract)
  → DDL Freeze
여기까지. 공식 INSERT는 별도 승인.
```

## 8. 본 WO(2B-01) 산출/상태

```
산출  : 본 문서 (Grounding Architecture 틀 · 관계유형 · Sector 축 · Registry 스키마)
미채움: master_code · join_key · relation_type (WO-2B-02 실측 대기) — 추측 금지로 ∅
DB    : 접근 없음 (본 WO는 설계만)
Freeze: 구조 동결 (실 코드 채움은 2B-02, 채운 뒤 재검토)
```

## 9. 다음
```
WO-2B-02 (execute_sql 복구 후) : Master 7종 read-only 실측 → Registry 실 코드 채움
→ 84 Case Master-Grounding Dry Run → Signature 불변 검증 → DDL Freeze → (승인 후) INSERT
```
