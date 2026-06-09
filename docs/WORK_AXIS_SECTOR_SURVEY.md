# 작업(work) 축 섹터별 조사 (2026-06-09, v2 정정)

> 질문: 작업(work)이 건설에만 있는가, 제조(산업)에도 있는가?
> 결과(정정): 두 섹터 모두 작업 축 있음. 표현 방식만 다름. (코드 수정 없음)
> v1 정정 사유: 제조는 별도 work 테이블이 없어 "미구현"으로 봤으나,
>   ksic_process_map.process_lv4가 작업 행위 수준임을 추가 확인.

## 조사 결과

### 건설 (KCSC) — 작업이 독립 테이블

```
kcsc_work_master (243건):
  process_id → 작업(title, is_work_item)
  → is_hazardous, hazard_type (위험)
  → equipment_type_codes (설비)
  → safety_standard (안전기준)

구조: 공정 → 작업(독립 테이블) → 위험/설비/안전기준
```

### 제조 (KSIC) — 작업이 공정 계층의 최하위(lv4)

```
ksic_process_map: 공정 4단계 계층
  lv1: 전자제조        (공정 大분류)
  lv2: 전공정/후공정/세정/검사/유틸리티/출하  (공정 단계)
  lv3: 웨이퍼·기판 준비 / 증착·코팅 / 노광·식각  (세부 공정)
  lv4: 증착 및 코팅 / 노광 및 식각 / 공정 세정   (작업 행위) ★

process_equipment_map:
  process_lv1~4 → equipment_role, mapped_equipment_count
  → 작업(lv4) → 설비 연결 있음 ✅

구조: 공정 4단계(lv4=작업) → 설비
```

### 두 섹터 작업 축 비교

```
            건설(KCSC)              제조(KSIC)
  ─────────────────────────────────────────────────
  작업 위치  kcsc_work_master       ksic_process_map.lv4
            (독립 테이블)           (공정 최하위 계층)
  작업→설비  equipment_type_codes   process_equipment_map ✅
  작업→위험  is_hazardous ✅        없음 ❌
  안전기준   safety_standard ✅     없음 ❌
```

### work_assignments (1,549건) — 작업 축 아님

```
schedule_id, asset_id, assigned_user_id, scheduled_date, status_code...
→ 점검 배정/실행 레코드 (누가 언제 점검)
→ 법령 진단의 작업 입력 축이 아니라 운영 실행 레코드
```

## 핵심 결론 (정정)

```
작업은 두 섹터 모두 존재 (사용자 직관이 맞음):

  건설: 공정 → 작업(독립 테이블 kcsc_work_master)
  제조: 공정 4단계의 최하위 lv4가 작업 행위

  표현 방식만 다름:
    건설 = 작업이 별도 테이블, 위험/설비/안전기준 풍부하게 연결
    제조 = 작업이 공정 lv4, 설비만 연결 (위험/안전기준 없음)
```

## "작업"의 두 의미 (구분 유지)

```
1. 법령 진단 작업 축 (두 섹터):
   건설 kcsc_work_master / 제조 ksic_process_map.lv4
   → 입력 대상으로서의 작업

2. 운영 작업 배정 (전 섹터):
   work_assignments — 점검 배정/실행
   → 입력이 아니라 실행 레코드
```

## 입력 대상 재정의 (작업 정정 반영)

```
1. 시설 (facility/factory)
2. 공정 — 제조 (KSIC, ksic_process_map lv1~3)
3. 공정 — 건설 (KCSC, kcsc_process_master)
4. 설비 (equipment, process_equipment_map / equipment_type_codes)
5. 작업
   - 제조: ksic_process_map.lv4 (작업 행위) → 설비 연결
   - 건설: kcsc_work_master → 설비+위험+안전기준 연결
6. 위험물
   - runtime_facility_hazard
   - 건설 작업 내장 위험 (kcsc_work_master.is_hazardous)
   - 제조 작업 위험: 없음 (lv4에 위험 연결 부재)
```

## 표준화 시사점

```
작업 축은 두 섹터 공통 입력 대상이나, 연결 깊이가 다름:

  제조 작업(lv4): → 설비
  건설 작업(work_master): → 설비 + 위험 + 안전기준

표준에서:
  "작업"을 공통 입력 대상으로 포함
  섹터별 소스 매핑:
    제조 = ksic_process_map.lv4
    건설 = kcsc_work_master
  연결 깊이 차이는 그대로 수용
    (제조 작업→위험은 데이터 없음 → 엔진 v2 또는 데이터 구축 과제)
```

## 다음 판단 필요

```
질문 1: 제조 작업(lv4)을 진단 입력/평가에 연결할 것인가?
  - lv4는 이미 데이터 있음 (증착/노광/세정 등)
  - 설비 연결도 있음 (process_equipment_map)
  - 단, draft_slot의 process_type가 value=null이라
    엔진이 값 비교 못 함 (KSIC 테스트에서 확인)
  → 입력 연결은 가능, 정밀 매칭은 엔진 v2

질문 2: 제조 작업→위험 연결을 구축할 것인가?
  - 현재 lv4에 위험 정보 없음
  - 건설은 있음 (is_hazardous)
  → 데이터 구축 과제 (별도)
```
