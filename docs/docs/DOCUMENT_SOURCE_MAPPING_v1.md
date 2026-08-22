# 문서 소스 매핑 (Source Mapping) v1 — 실측

> 작성일: 2026-08-22
> 방식: taieng DB(vwlahtguyggrhvslabax) 구조 실측 (read-only)
> 목적: 2겹 매핑(유형→fetcher)의 데이터 근거 확정. 기획서 [확인 필요] 항목 해소.

---

## 0. 핵심 판정 — EQUIP 1템플릿 성립

**성립 확인.** 설비점검(EQUIP)은 대상별 템플릿 15개가 아니라 **유형 1템플릿 + 대상 데이터 주입**으로 성립한다.

- 설비 대상 식별: `equipment_assets.equipment_type_code` (+ equipment_category)
- 점검 실행 기록: `safety_inspections` (asset_id → equipment_assets)
- 점검항목: `safety_inspection_results`가 **행 단위**로 관리 (item_name + result_code + note + photo)
- 즉 EQUIP 템플릿이 asset의 equipment_type_code로 세부(DETAIL)를 결정하고, 그 asset의 결과 행을 점검항목으로 렌더한다.

## 1. 소스 테이블 구조 (실측)

### safety_inspections (점검 실행)
- id, assignment_id, **asset_id**(설비 자산 FK), inspector_id, inspection_date, status_code

### safety_inspection_results (점검항목 결과 · 행 단위)
- id, inspection_id, **item_name**(항목명), value_text, value_number, inspection_set_item_id, **result_code**(정상/이상), note, photo_url/photo_urls, checked_at

### equipment_assets (설비 자산 · 대상 축)
- **equipment_type_code**, **equipment_category** (설비 유형/범주)
- is_legal_target(법정 점검대상), last_inspection_date/next_inspection_date(주기)
- asset_name, asset_code, capacity_value/unit, install_year, manufacturer, factory_id, building_id (문서 기재정보)

### tbm_meetings (TBM)
- meeting_title, work_date, work_location, work_description, **risk_items(jsonb)**, **safety_items(jsonb)**, conductor_name, attendee_count, status_code, completed_at

## 2. 유형 → 소스 매핑 (2겹 fetcher 근거)

| 유형 | 소스 테이블 | 대상/세부 축 | fetcher |
|---|---|---|---|
| INSP · CHK · EQUIP | safety_inspections + safety_inspection_results | asset_id → equipment_assets.equipment_type_code | inspection_fetcher (기존) |
| TBM | tbm_meetings (risk_items·safety_items) | — | tbm_fetcher (기존) |
| PPE | safety_inspections (보호구 점검) | — | inspection_fetcher 재사용 |
| CONLOG | construction_inspections + factory | — | 신규 필요 |
| 협의체(B등급) | safety_committee_meetings + attendees | — | 신규 필요 |

> 기존 fetcher(inspection·tbm)로 A등급 즉시가용 대부분 커버. CONLOG·협의체·교육은 신규 fetcher.

## 3. 데이터 현황 (목업 · 오픈 전)

| 테이블 | approx_rows |
|---|---|
| safety_inspections | 1 |
| safety_inspection_results | 5 |
| tbm_meetings | 10 (attendees 76) |
| safety_committee_meetings | 5 (attendees 35) |
| construction_inspections | 9 |

**구조는 완비, 데이터는 목업.** 오픈 후 점검 데이터가 쌓이면 그대로 작동. 렌더 검증은 목업 데이터로 가능.

## 4. 함의

- EQUIP 세부(DETAIL) 코드표는 equipment_assets.equipment_type_code 값과 정렬되어야 한다(첫 매핑 시 실제 type_code 값 확인 필요).
- 점검 주기(next_inspection_date)가 문서 발생 스케줄과 직접 연결된다 → 기획서 "주기=문서 발생"의 데이터 근거.
- is_legal_target으로 법정 점검대상 필터 가능.

---

*소스 구조 실측 완료. 이 위에서 1겹·2겹 매핑을 확정한다. 데이터는 목업이나 구조 근거는 확정.*
