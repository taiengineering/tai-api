# 법령진단 → 작업 생성 [문제1 해결] 작업지시서
## 진단 결과 DB 저장 미구현 수정
### 작성: 2026-03-31 | 담당: Code 창 (Cursor)

---

## 문제 요약

`POST /legal-engine/diagnose/step1`이 결과를 계산하고 응답만 반환할 뿐,  
`factory_diagnosis_results`, `diagnosis_rule_results` 테이블에 **저장하지 않음**.  
→ DB 확인 결과 두 테이블 모두 **0건**.

`step2`, `step3`에는 `_save_diagnosis_result()` 호출이 있으나,  
`step1`에만 해당 호출이 **누락**되어 있음.

---

## 파일 위치

`routers/legal_engine.py` (단일 파일 수정)

---

## 작업 내용

### STEP 1. `diagnose/step1` 엔드포인트에 DB 저장 추가

`POST /legal-engine/diagnose/step1` 함수 내부에서  
`return {"status": "success", "data": result_data}` 바로 **직전**에  
아래 저장 로직을 삽입합니다.

```python
# ── DB 저장 ──────────────────────────────────────────────────────
# 1. factory_id가 있을 때만 저장
diagnosis_id = None
if factory_id:
    try:
        # 기존 is_latest = True 항목 해제
        supabase.table('factory_diagnosis_results') \
            .update({'is_latest': False}) \
            .eq('factory_id', factory_id) \
            .eq('sector', sector_raw) \
            .eq('is_latest', True) \
            .execute()
    except Exception:
        pass

    try:
        save_res = supabase.table('factory_diagnosis_results').insert({
            'factory_id':     factory_id,
            'sector':         sector_raw,
            'diagnosis_stage': 1,
            'input_data':     inp,           # 진단 입력값 그대로 저장
            'result_data':    result_data,   # 전체 결과 저장
            'rule_count':     total_applicable,
            'is_latest':      True,
        }).execute()
        if save_res.data:
            diagnosis_id = save_res.data[0].get('id')
    except Exception as e:
        print(f"[DIAGNOSE STEP1] factory_diagnosis_results 저장 실패: {e}")

    # 2. diagnosis_rule_results 저장 (적용된 규칙 상세)
    if diagnosis_id and applicable:
        try:
            rule_rows = []
            for rule in applicable:
                ot = _resolve_obligation_type(rule)
                rule_rows.append({
                    'diagnosis_id': diagnosis_id,
                    'rule_code':    rule.get('rule_id') or rule.get('rule_code') or '',
                    'rule_name':    (rule.get('obligation_summary') or rule.get('remarks') or '').strip(),
                    'law_name':     rule.get('law_name') or '',
                    'law_article':  rule.get('law_article') or '',
                    'obligation':   (rule.get('obligation_summary') or '').strip(),
                    'due_date':     None,   # due_days 있으면 계산 가능하나 현재 대부분 NULL
                    'status':       'PENDING',
                    'form_code':    rule.get('form_code') or None,
                })
            # 50건씩 배치 insert
            for i in range(0, len(rule_rows), 50):
                supabase.table('diagnosis_rule_results').insert(rule_rows[i:i+50]).execute()
        except Exception as e:
            print(f"[DIAGNOSE STEP1] diagnosis_rule_results 저장 실패: {e}")

# diagnosis_id를 응답에 포함
result_data['diagnosis_id'] = diagnosis_id
# ─────────────────────────────────────────────────────────────────
```

---

### STEP 2. 변수 선언 위치 주의

현재 `step1` 함수에서 `applicable` 변수는 이미 사용됩니다.  
단, `_save_diagnosis_result()` 직접 호출은 **하지 마세요** — step1에는 맞지 않는 로직이 혼재되어 있어  
위의 인라인 코드로만 처리합니다.

---

### STEP 3. diagnosis_rule_results 테이블 컬럼 확인

현재 테이블 컬럼:
```
id, diagnosis_id, rule_code, rule_name, law_name, law_article,
obligation, due_date, status, form_code, created_at
```
→ 모두 이미 존재. **DDL 작업 불필요**.

---

### STEP 4. 응답 구조 변경 (최소)

기존 `result_data` 응답에 `diagnosis_id` 필드만 추가:  
```json
{
  "status": "success",
  "data": {
    ...(기존 필드 유지),
    "diagnosis_id": "uuid-or-null"
  }
}
```

---

## 검증 방법

1. API 호출:
```bash
curl -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -H 'Content-Type: application/json' \
  -d '{"sector": "BUILDING", "factory_id": "<실제 factories.id>", "input": {"building_use_type": "업무시설", "worker_count": 100, "total_floor_area": 5000}}'
```

2. 응답에 `diagnosis_id` 포함 확인

3. DB 확인:
```sql
SELECT * FROM factory_diagnosis_results ORDER BY created_at DESC LIMIT 5;
SELECT * FROM diagnosis_rule_results WHERE diagnosis_id = '<diagnosis_id>';
```

---

## 주의사항

- `factory_id`가 없는 익명 진단(견적용)은 저장하지 않음 — 정상
- `applicable` 리스트는 `master_building_legal_rules` 원본 행이므로 그대로 사용 가능
- 저장 실패 시 `try/except`로 감싸서 **응답은 항상 반환** (저장 실패가 진단 응답을 막으면 안 됨)
- `ENGINE_VERSION` 상수 활용 가능 (`"4.4.0"`)

---

## 배포 후 확인 항목

- [ ] `factory_diagnosis_results`: 진단 실행 후 1건 생성
- [ ] `diagnosis_rule_results`: 적용된 규칙 수만큼 생성
- [ ] `is_latest`: 동일 factory_id + sector 재진단 시 이전 항목 False로 변경
- [ ] 응답에 `diagnosis_id` 포함
- [ ] factory_id 없는 익명 진단: 저장 없이 정상 응답

---

## 다음 단계 (이 작업 완료 후)

| 순위 | 작업 |
|------|------|
| 2 | 점검주기 데이터 보완 (INSPECT 127건 inspection_cycle_value NULL) |
| 3 | 진단 완료 → inspection_set 자동 생성 API 연동 |
| 4 | work_schedules에 source_type(LEGAL/MANUAL), obligation_type 컬럼 추가 |
