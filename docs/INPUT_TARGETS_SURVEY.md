# 입력 대상 5종 × 2진입점 조사 결과 (2026-06-09)

> 목적: 진단/SaaS 두 진입점에서 시설·공정·설비·작업·위험물의 입력→저장→엔진 경로 조사
> 결과: 5개 대상의 단절은 하나의 구조적 원인에서 비롯 (코드 수정 없음)

## 요약 매트릭스

| 대상 | 진단 입력 | SaaS 등록 | 저장(동일?) | 엔진 반영 | 단절 지점 |
|------|----------|-----------|------------|----------|----------|
| 시설 | △ preset 4필드만 | ✅ /factories | △ temp vs 영구 분리 | △ DIRECT만(인원·면적·전력) | API→Body 유실, factory_id 무시 |
| 공정 | △ Body ksic_major만 | ✅ /factory-process | ❌ 진단 미사용 | △ ksic 존재만(C26=C20) | ksic_process_map 미조인, scope value=null |
| 설비 | ❌ Step3만 | ✅ /equipment-assets | ❌ | ❌ | EQUIPMENT_JOIN 미구현 |
| 작업 | ❌ Step2 | △ KCSC 공정만 | ❌ | ❌ | FIELD_MAP 없음 |
| 위험물 | △ Body 플래그 | ✅ factories 플래그·용량 | △ | △ gas AMBIGUOUS만 | is_hazardous_material FIELD_MAP 없음 |

## 핵심 발견: 단일 구조적 원인

```
5개 대상의 단절은 증상이고, 원인은 하나:

  1. Compiler 진단은 항상 temp factory 1행만 읽음
     → SaaS가 등록한 factory_process / equipment_assets / factory_id 미사용
     → SaaS에서 등록해도 진단이 안 봄

  2. 엔진 scope 조건이 value=null (존재검사만)
     → process_type/equipment_type/facility_type
     → 값 비교 불가 (C26=C20)
```

## KSIC E2E와 일치

- 공정은 ksic_code 유무만 반영 (+146 POSSIBLE)
- C26 vs C20 결과 동일 (scope value=null)
- draft_slot IF_SCOPE value=null 확인

## 표준화 분류

### 입력 표준화 (엔진 안 건드림)
```
1. Anonymous API에 Body 필드 노출 (ksic_major, 위험물, 면적 등)
2. factory_id로 SaaS 시설 row 재사용 ★ 핵심
   - temp factory 대신 등록된 factory를 읽으면
     공정·설비·위험물이 자동으로 평가에 포함
   - 5개 대상을 한 번에 잇는 열쇠
3. input_data에 실입력 기록
```

### 엔진 v2 (scope value 정규화 필요)
```
- process_type / equipment_type 값 비교
- ksic_process_map 조인
- is_hazardous_material / concentration_level FIELD_MAP
- 작업(work) 축 applicability 연동
```

## 다음 설계 방향

```
부분 수정 금지. 전체를 보면:

  핵심 = "temp factory" → "등록된 factory 재사용"
  이 하나가 SaaS 등록 데이터(공정/설비/위험물)를
  진단 평가에 한 번에 연결.

  단, 익명 진단(factory 없음)은 temp factory 유지 필요
  → 익명: temp factory (현행)
  → SaaS: 등록된 factory_id 재사용 (신규 표준)

  이것이 진단/SaaS 두 진입점의 표준 분기점.
```

## 엔진 v2 과제 누적 (이번 조사 반영)

```
1. 단위 정합 (monetary/voltage/storage)
2. facility_type 정밀 매칭
3. process_type(KSIC) 정밀 매칭 + ksic_process_map 조인
4. equipment_type 매칭 + EQUIPMENT_JOIN
5. 위험물 concentration FIELD_MAP
6. 작업(work) applicability 축

→ 전부 scope value 정규화 / draft_slot 정규화 선행
→ 엔진 v2에서 일괄 재설계
```
