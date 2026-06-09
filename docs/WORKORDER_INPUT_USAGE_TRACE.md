# 작업지시서: 입력 화면의 값 사용 흐름 조사 (정본 대조)

> 목적: INPUT_CONTRACT_STANDARD.md(정본)대로 만들어진 입력 화면이
>       실제로 입력값을 어떻게 수집→전송→저장하는지 확인.
> 원칙: 조사만. 수정 금지. 추측 금지. 코드에서 사실만.
> 배경: 정본(diagnosis_input_fields) + 계약 문서는 확인됨.
>       이제 "문서대로 만들어진 화면이 값을 어떻게 쓰는가"를 검증.

## 정본 (기준)

```
입력 정본: diagnosis_input_fields (is_active=true)
  컬럼: sector, tier, field_group, field_code, field_type,
        input_options, unit, is_required, auto_source, unknown_handler
  활성: BUILDING 34 / INDUSTRIAL 18 / CONSTRUCTION 15

계약 문서: docs/INPUT_CONTRACT_STANDARD.md
표준 계층: factories → factory_process → equipment_assets
          factory_id 중심, 진단·SaaS 공용
```

## 조사 대상 (저장소 3곳)

```
1. tai-admin (tadmin/, safe.taieng.co.kr) — 입력 화면
   진단 입력:
     diagnosis-input-building.html
     diagnosis-input-construction.html
     diagnosis-input-industry-paid1~3.html
     diagnosis-step1~3.html
   SaaS 운영:
     factory-list.html, process-manage.html, my-equipment.html

2. tai-api — 입력 받는 API
   routers/diagnosis.py (결제/factory_id 중심)
   services/diagnosis_service.py (evaluate)

3. taieng (nexas/) — 회원게이트·결제 전
   nexas/paid-diagnosis.html
```

## 조사 항목

### A. 화면이 값을 어떻게 수집하는가
```
diagnosis-input-building.html 기준:
  1. diagnosis_input_fields를 동적 로드하는가,
     아니면 필드가 하드코딩인가?
  2. field_type(boolean/select/table)을 어떻게 렌더링하는가?
     - tri-state-toggle.js, autofill-address.js 사용 확인
  3. auto_source(building_register 자동채움)가 실제 작동하는가?
  4. unknown_handler(모름 처리)가 구현됐는가?
```

### B. 화면이 값을 어떻게 전송하는가
```
  1. saveDraft() → 어떤 API? (/diagnosis/create·PATCH 확인)
  2. 전송 payload 구조 — field_code 그대로? 변환?
  3. factory_id를 어떻게 싣는가?
  4. 진단 입력과 SaaS 등록이 같은 API를 쓰는가?
```

### C. API가 값을 어떻게 저장하는가
```
  routers/diagnosis.py:
  1. 받은 입력을 factories/factory_process/equipment_assets에
     어떻게 분배 저장하는가?
  2. field_code → DB 컬럼 매핑이 있는가?
  3. process_list → factory_process, equipment_list → equipment_assets
     변환이 실제 구현됐는가?
```

### D. 정본과 화면의 일치 여부
```
  diagnosis_input_fields(정본)의 field_code와
  화면의 실제 입력 필드를 대조:
  - 정본에 있는데 화면에 없음 (누락)
  - 화면에 있는데 정본에 없음 (불필요)
  - field_type 불일치 (오입력 위험)
```

## 산출물

파일: docs/INPUT_USAGE_TRACE.md

```markdown
# 입력 화면 값 사용 흐름

## A. 수집
  - 동적 로드 vs 하드코딩: [확인]
  - field_type 렌더링: [확인]
  - auto_source 작동: [확인]
  - unknown_handler: [확인]

## B. 전송
  - saveDraft → API: [경로]
  - payload 구조: [field_code 그대로/변환]
  - factory_id 처리: [확인]

## C. 저장
  - factories/factory_process/equipment_assets 분배: [확인]
  - field_code → 컬럼 매핑: [확인/없음]
  - process_list/equipment_list 변환: [구현/미구현]

## D. 정본 ↔ 화면 대조 (BUILDING부터)
  | field_code | 정본 | 화면 | 일치 |

## 발견된 불일치
  - 누락 / 불필요 / 오입력 위험

## 결론
  - 정본대로 화면이 값을 쓰는가?
  - 끊기는 지점은?
```

## 주의

- 수정 금지 (조사만)
- 한 섹터(BUILDING)부터, 폭주 금지
- tai-admin 저장소 접근 필요 (tadmin/)
- 추측 금지 — HTML/JS 코드에서 실제 확인
- Supabase MCP project_id: vwlahtguyggrhvslabax
- 정본 = diagnosis_input_fields, 계약 = INPUT_CONTRACT_STANDARD.md
