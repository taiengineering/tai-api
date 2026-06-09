# 작업(work) 축 섹터별 조사 (2026-06-09)

> 질문: 작업(work)이 건설에만 있는가, 제조(산업)에도 있는가?
> 결과: 건설은 작업 축 구현됨, 제조는 미구현 (코드 수정 없음)

## 조사 결과

### 건설 (KCSC) — 작업 축 있음

```
kcsc_work_master (243건):
  process_id → 작업(title, is_work_item)
  → is_hazardous, hazard_type (위험)
  → equipment_type_codes (설비)
  → safety_standard (안전기준)

구조: 공정 → 작업 → 위험/설비 분해
→ 법령 진단의 입력 축으로 구현됨
```

### 제조 (KSIC) — 작업 축 없음

```
ksic_process_map: work 컬럼 없음 (공정 레벨까지만)
process_equipment_map: work 컬럼 없음

구조: 공정(KSIC) → 설비 (process_equipment_map)
→ 공정과 설비 사이 "작업" 레벨 부재
→ 제조 작업 축 미구현
```

### work_assignments (1,549건) — 작업 축 아님

```
schedule_id, asset_id, assigned_user_id, scheduled_date, status_code...
→ 점검 배정/실행 레코드 (누가 언제 점검)
→ 법령 진단의 작업 입력 축이 아니라 운영 실행 레코드
```

## 핵심 구분: "작업"의 두 의미

```
1. 법령 진단 작업 축 (건설만):
   kcsc_work_master — 공정 분해, 위험/설비 연결
   → 입력 대상으로서의 작업

2. 운영 작업 배정 (전 섹터):
   work_assignments — 점검 배정/실행
   → 입력이 아니라 실행 레코드
```

## 입력 대상 재정의 (건설 공정 + 작업 반영)

```
1. 시설 (facility/factory)
2. 공정 — 제조 (KSIC 기반, ksic_process_map)
3. 공정 — 건설 (KCSC 기반, kcsc_process_master)  ← 분리
4. 설비 (equipment, process_equipment_map)
5. 작업 — 건설 (kcsc_work_master)  ← 건설 전용 확인
   작업 — 제조: 구조상 없음 (개념적으론 존재 가능, 미구현)
6. 위험물 (hazard/chemical, runtime_facility_hazard)
   + 건설 작업 내장 위험 (kcsc_work_master.is_hazardous)
```

## 판정

```
작업 축:
  건설 ✅ 구현됨 (kcsc_work_master, 공정→작업→위험/설비)
  제조 ❌ 미구현 (공정→설비까지만)

  → 제조 작업 축은 "개념적으로 가능하나 데이터 없음"
  → 표준화 시: 건설은 작업 축 포함, 제조는 공정→설비
  → 제조 작업 축 신설은 별도 판단 (데이터 구축 필요)
```

## 다음 판단 필요

```
질문 1: 제조에 작업 축을 신설할 것인가?
  - 신설하면: KSIC 공정 → 제조 작업 → 설비/위험 데이터 구축 필요
  - 안 하면: 제조는 공정→설비 직접 연결 유지

질문 2: 표준은 건설/제조 작업 축 차이를 어떻게 수용하는가?
  - 공통 표준 + 섹터별 작업 축 유무
```
