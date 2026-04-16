# BE-06-final: legal_engine.py v2026.04 INSERT 전환 완료 보고

**작업일:** 2026-04-16  
**버전:** legal_engine.py v5.6.8, services/legal_engine_v202604.py v1.0.1  
**PR:** https://github.com/taiengineering/tai-api/pull/1 (dev→main)

---

## 배경

BE-06 continuation STEP 3으로 기존 43건 변환 완료됐으나,
legal_engine.py는 여전히 legacy 형식으로 INSERT 중.
신규 진단 생성 시 legacy가 증식하는 구조 → 즉시 차단 필요.

---

## 완료 내역

### 신규 파일

| 파일 | 버전 | 역할 |
|---|---|---|
| `services/legal_engine_v202604.py` | v1.0.1 | wrap_result_to_v202604() 래퍼 함수 |

#### wrap_result_to_v202604() 핵심 로직
- **tier 정규화**: PAID_FULL→PAID, PAID1_FACILITY→PAID1 등
- **sector 교정**: MANUFACTURING → INDUSTRY
- **evidence[] 결정론적 생성**: 알파벳 오름차순, source·factory_id 제외, 상위 5개, `"input.{key}={value}"` 형식
- **severity 판정**: risk_summary 기반 → 없으면 rule_count 추정 (≥100=HIGH, ≥50=MEDIUM, else LOW)
- **warnings 통합**: warnings + urgent_action_items + construction_specific_tips + age_warnings(object 타입 방어)
- **obligations 통합**: obligations > key_obligations > mandatory_obligations > critical_obligations
- **Pydantic 검증**: DiagnosisResultV202604.model_validate() — 실패 시 HTTP 500 raise (silently fallback 금지)

### 수정 파일

| 파일 | 변경 내용 |
|---|---|
| `routers/legal_engine.py` v5.6.8 | import + INSERT 지점 2곳 전환 |

#### INSERT 전환 지점 2개

**1. diagnose_step1** (stage=1, FREE/PAID 진단):
```python
# 추가됨
result_data_v2 = _wrap_v202604(sector_raw, 1, inp, result_data, total_applicable)
supabase.table("factory_diagnosis_results").insert({
    ...,
    "result_data": result_data_v2,
    "schema_version": "2026.04"   # 하드코딩
}).execute()
```

**2. _save_diagnosis_result** (stage=2,3 공통):
```python
# 추가됨
result_data_v2 = _wrap_v202604(sector, stage, input_data, result_data, len(matched_rules))
supabase.table('factory_diagnosis_results').insert({
    ...,
    'result_data': result_data_v2,
    'schema_version': '2026.04'   # 하드코딩
}).execute()
```

---

## 통합 테스트 결과 (3개 케이스 전체 통과)

| 케이스 | sector | 특이사항 | 결과 |
|---|---|---|---|
| 1 | BUILDING stage1 | legacy 형식, headline 자동생성 | ✅ PASS |
| 2 | CONSTRUCTION stage1 | headline_message 재활용, severity=CRITICAL | ✅ PASS |
| 3 | MANUFACTURING stage3 | sector→INDUSTRY 교정, _legacy_process_hazards 보존 | ✅ PASS |

**evidence 알파벳 순 확인:**
```
['input.electric_capacity=500', 'input.total_floor_area=3000', 'input.worker_count=85']
```

---

## 기존 43건 보존 확인

| 항목 | 결과 |
|---|---|
| schema_version='2026.04' | 43건 ✅ |
| legacy 잔존 | 0건 ✅ |
| headline 필드 | 43건 ✅ |
| evidence 필드 | 43건 ✅ |
| MANUFACTURING column | 0건 ✅ |
| is_latest 중복 | 0건 ✅ |

---

## PENDING (다음 스프린트)

- Fly.io 배포 후 실 API 호출 통합 테스트 (현재 dev 브랜치 미배포)
- diagnose_step1 예외처리: `except Exception as e: raise` (silent print 제거 완료)
