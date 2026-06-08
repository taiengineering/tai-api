# 작업지시서: STEP B' — 세 섹터 입력 필드 표준화

> 목적: BUILDING / INDUSTRIAL / CONSTRUCTION 세 섹터의
>       입력 → factories 저장 경계를 표준에 맞춘다.
> 근거: ctx가 만드는 필드가 create_temp_factory INSERT에서 다수 누락됨.
>       sector 어휘 충돌 (MANUFACTURING vs DB INDUSTRIAL).
> 원칙: 엔진(legal_context, facility_applicability_eval)은 MANUFACTURING 유지.
>       DB 저장 경계에서만 표준 변환.
> 브랜치: feature/layer-standardization-20260608 (STEP 1·A와 동일 브랜치)

## 핵심 원칙: 주는 곳과 받는 곳을 같게

```
입력 표준 (소비자/저장/DB): INDUSTRIAL  ← factories_sector_check
엔진 표준 (룰/분기): MANUFACTURING       ← legal_context 변환 유지

경계 변환 지점 = create_temp_factory (저장 시):
  엔진이 MANUFACTURING으로 처리하더라도
  factories에 저장할 때는 INDUSTRIAL로 되돌린다.
```

DB factories_sector_check 허용값 (실측):
```
BUILDING, INDUSTRIAL, CONSTRUCTION, SPECIAL_FACILITY, COMMON
```

## 작업 1: sector 저장 경계 변환

파일: services/anonymous_factory_service.py → create_temp_factory

```
현재:
  "sector": sector_raw,       # MANUFACTURING → DB 거부
  "site_type": sector_raw,

표준:
  sector_db = normalize_sector_db(sector_raw)  # 이미 import됨
    # MANUFACTURING → INDUSTRIAL 변환 함수 (legal_rules에 있음, 확인)
  "sector": sector_db,        # DB 허용값으로 저장
  "site_type": _resolve_site_type(...)  # 용도(STEP 1에서 한 것)
```

확인: normalize_sector_db가 MANUFACTURING→INDUSTRIAL 하는지 검증.
없으면 SPECIAL_FACILITY→BUILDING 등도 매핑 필요.

## 작업 2: 세 섹터 공통 누락 필드 INSERT 추가

파일: create_temp_factory의 row dict

ctx에 있으나 현재 INSERT 안 되는 필드 추가:
```
"building_use_code": str(ctx.get("building_use_code") or ""),
"floor_count": int(ctx.get("floor_count") or 0),
"is_hazardous_material": 1 if ctx.get("is_hazardous_material") else 0,
"boiler_capacity_kw": float(ctx.get("boiler_capacity_kw") or 0),
"elevator_count": int(ctx.get("elevator_count") or 0),
"annual_energy_toe": float(ctx.get("annual_energy_toe") or 0),
```

주의: factories 컬럼에 실제 존재하는지 확인 후 추가.
빈 문자열/0이 CHECK 제약 위반하는 컬럼은 조건부 INSERT.

## 작업 3: 섹터별 검증

```
BUILDING (병원 5층 50명):
  sector=BUILDING, site_type=병원, building_use_code=병원,
  floor_count=5 저장 확인

INDUSTRIAL (제조 300명, ksic C):
  sector=INDUSTRIAL (MANUFACTURING 아님!) 저장 확인
  → factories_sector_check 통과
  → 진단 정상 완료 (이전엔 깨졌음)

CONSTRUCTION (78억 120명):
  sector=CONSTRUCTION, construction_amount=7,800,000,000,
  construction_type 저장 확인
```

통과 기준:
- 세 섹터 모두 factories INSERT 성공 (sector_check 통과)
- INDUSTRIAL 진단이 더 이상 깨지지 않음
- ctx 필드가 factories에 저장됨
- MATCH 건수 회귀 없음 (DIRECT 필드 기준)
- 에러 없이 완료

## 주의

- 엔진 평가 로직 수정 금지
- legal_context의 INDUSTRIAL→MANUFACTURING 변환은 유지 (엔진 표준)
- 변환은 저장 경계(create_temp_factory)에서만
- STEP 1·A와 동일 브랜치에 커밋
- Draft PR, merge 금지
- Supabase MCP 사용 가능 (project_id: vwlahtguyggrhvslabax)

## 표준 확정 (이 작업으로 정해지는 것)

```
sector 어휘 표준:
  입력/저장/DB 계층: BUILDING / INDUSTRIAL / CONSTRUCTION / SPECIAL_FACILITY
  엔진/룰 계층: BUILDING / MANUFACTURING / CONSTRUCTION / SPECIAL_FACILITY
  변환 지점: 저장 시 normalize_sector_db (단일 경계)

입력 필드 표준:
  ctx가 만드는 필드는 factories에 모두 저장 (유실 없음)
```
