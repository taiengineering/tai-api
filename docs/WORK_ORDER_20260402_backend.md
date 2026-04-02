# 백엔드 작업지시서 — 2026-04-02
> 담당: Cursor 백엔드 창  
> 우선순위 순서대로 작업

---

## 작업 1. 🔴 안전관리자 선임 OR 조건 처리 (legal_engine.py)

### 배경
현재 `_evaluate_facility_conditions_db()` 함수는 룰 1개당 조건 1개만 체크함.
건설 안전관리자 선임(산안법 시행령 제16조②)은 아래 두 조건 중 **하나라도** 충족 시 발동:
- 조건A: 공사금액 ≥ 120억(토목) / 150억(건축)
- 조건B: 상시근로자(하도급 포함) ≥ 50명

현재 DB에는 두 조건이 별개 룰로 분리되어 있어 각각 독립 체크됨 → **이 방식은 올바름**.
문제는 조건B에 해당하는 APPOINT 룰이 누락된 것.

### 작업 내용
`routers/legal_engine.py` 수정

**수정 위치**: `_evaluate_facility_conditions_db()` 함수 내 CONSTRUCTION 섹터 처리 부분

```python
# 현재 (조건 없는 룰 → 관련 법령만 적용)
if not cc or cv is None:
    if sector == "CONSTRUCTION":
        law = rule.get("law_name") or ""
        if any(prefix in law for prefix in CONSTRUCTION_RELEVANT_LAW_PREFIXES):
            applicable.append(rule)
        else:
            not_applicable.append(rule)
    else:
        applicable.append(rule)
```

**추가할 로직**: CONSTRUCTION 섹터에서 worker_count ≥ 50 조건 자동 체크

```python
# 추가: CONSTRUCTION에서 worker_count 기반 안전관리자 선임 자동 판정
# (조건 없는 APPOINT 룰 중 산안법 제16조② 해당 룰에만 적용)
if not cc or cv is None:
    if sector == "CONSTRUCTION":
        law = rule.get("law_name") or ""
        obligation_type = (rule.get("obligation_type") or "").upper()
        
        # worker_count 50명↑ → 선임 의무 자동 발동 (산안법 시행령 제16조②)
        article = rule.get("law_article") or ""
        if (obligation_type in ("APPOINT", "NOTIFY") and 
            "산업안전보건법" in law and 
            "16조" in article):
            worker_count = float(facility_ctx.get("worker_count") or 0)
            if worker_count >= 50:
                applicable.append(rule)
            else:
                not_applicable.append(rule)
        elif any(prefix in law for prefix in CONSTRUCTION_RELEVANT_LAW_PREFIXES):
            applicable.append(rule)
        else:
            not_applicable.append(rule)
    else:
        applicable.append(rule)
```

---

## 작업 2. 🔴 diagnose/step2 — BLASTING·CRANE 공종 대응

### 배경
현재 `kcsc_process_master`에 `BLASTING`, `CRANE` work_type_code가 없음.
step2 진단에서 발파·크레인 공종 선택 시 법령이 트리거되지 않는 문제.

### 작업 내용
`routers/legal_engine.py` → `diagnose_step2()` 함수

step2 쿼리에서 work_types 필터링 시, KCSC에 없는 공종도 직접 입력 가능하도록 처리:

```python
# 현재: kcsc_process_ids → work_type_code 자동 조회만 가능
# 추가: body에 직접 work_type_codes 입력 허용

work_type_codes_direct: List[str] = body.get('work_type_codes') or []
# BLASTING, CRANE 등 KCSC 미등록 공종도 직접 전달 가능
work_types = list(set(work_types + work_type_codes_direct))
```

**body 파라미터 추가**:
- `work_type_codes`: `List[str]` — KCSC 프로세스 없이 직접 공종 코드 전달
  - 허용값: `BLASTING`, `CRANE`, `CONCRETE_POUR`, `EXCAVATION` 등

---

## 작업 3. 🟠 _get_construction_summary() 키 임계값 수정

### 배경
현재 `key_thresholds_met` 딕셔너리에 임계값이 하드코딩되어 있으나
실제 법령 기준과 일부 불일치 발견.

### 확인 및 수정 대상
```python
# 현재 (routers/legal_engine.py _get_construction_summary 함수)
"key_thresholds_met": {
    "1억_산업안전보건관리비":       amount >= 100_000_000,       # ✅ 정확
    "50억_유해위험방지계획서":      amount >= 5_000_000_000,     # ✅ 정확
    "50억_기초안전보건교육":        amount >= 5_000_000_000,     # ✅ 정확
    "100억_안전관리계획서":         amount >= 10_000_000_000,    # ✅ 정확
    "120억_안전관리자선임_토목":    site_type in ("토목", "CIVIL") and amount >= 12_000_000_000,  # ✅
    "150억_안전관리자선임_건축":    site_type in ("건축", "BUILDING") and amount >= 15_000_000_000, # ✅
    "200억_안전보건관리책임자":     amount >= 20_000_000_000,    # ✅ 정확
    "1000억_건설안전판정사":        amount >= 100_000_000_000,   # ✅ 정확
}
```

**추가할 항목**:
```python
"50명↑_안전관리자선임":   worker_count >= 50,   # 근로자 조건 추가
"300명↑_안전관리자선임":  worker_count >= 300,  # 전기/특수공종 추가 기준
```

`worker_count` 값은 이미 `facility_ctx`에 있으므로 파라미터로 받아서 사용.

---

## 작업 4. 🟠 public_admin.py — AIRNOTICE-001-MFG form_url 누락 수정

### 배경
AIRNOTICE-001-MFG 룰은 form_code 적재 완료됐으나
`_build_result_html()` 함수에서 form_url을 활용하지 않고 있음.

### 작업 내용
`_build_result_html()` 함수 내 report 섹션 렌더링 시
`form_url`이 있으면 서식 다운로드 링크 추가:

```python
# report 테이블 행에 서식 링크 추가
form_code = r.get("form_code", "")
form_name = r.get("form_name", "")
form_url  = r.get("form_url", "")

form_link = ""
if form_code and form_code not in ("NONE", "UNKNOWN", "ONLINE"):
    link_url = form_url or "https://www.law.go.kr"
    form_link = f'<a href="{link_url}" target="_blank" style="font-size:0.8em">[{form_code}]</a>'
elif form_code == "ONLINE":
    online_url = form_url or "#"
    form_link = f'<a href="{online_url}" target="_blank" style="font-size:0.8em">[온라인신고]</a>'
```

---

## 작업 5. 🟡 엔진 버전 업데이트

모든 작업 완료 후 `main.py`와 `legal_engine.py` 버전 업데이트:
- `legal_engine.py`: `ENGINE_VERSION = "5.3.1"`
- `main.py`: `version = "5.2.5"`

---

## 체크리스트

- [ ] 작업1: `_evaluate_facility_conditions_db()` worker_count 50명 조건 추가
- [ ] 작업2: `diagnose_step2()` `work_type_codes` 직접 입력 파라미터 추가
- [ ] 작업3: `_get_construction_summary()` worker_count 임계값 항목 추가
- [ ] 작업4: `_build_result_html()` form_url 링크 렌더링 추가
- [ ] 작업5: 버전 업데이트 후 push → Railway 배포 확인

---

## 참고: 현재 DB 상태 (2026-04-02 기준)

| 항목 | 상태 |
|------|------|
| CONSTRUCTION stage1 룰 수 | 99개 |
| form_code 매핑 완료 | 114건 |
| form_code UNKNOWN | 1건 (CONST-TECH-004) |
| form_code 미매핑 | ~83건 (GPT 배치1·2 작업 진행 중) |
| BLASTING·CRANE KCSC 등록 | 미완료 (GPT 작업 대기) |

---

## 완료 후 테스트

```bash
# 건설 현장 150억, 근로자 60명(하도급 포함) 케이스로 step1 테스트
POST /legal-engine/diagnose/step1
{
  "sector": "CONSTRUCTION",
  "input": {
    "construction_type": "건축",
    "contract_amount_eok": 150,
    "direct_workers": 30,
    "subcon_workers": 30
  }
}
# 기대 결과: 안전관리자 선임 (공사금액 조건 + 근로자 조건 둘 다 충족)

# 공사금액 100억, 근로자 55명 케이스 (금액 미달, 인원 충족)
{
  "contract_amount_eok": 100,
  "direct_workers": 30,
  "subcon_workers": 25
}
# 기대 결과: 안전관리자 선임 (인원 조건으로 발동)
```
