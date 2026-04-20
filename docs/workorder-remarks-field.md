# 작업지시서: 법령엔진 remarks 필드 연결 + PDF 리포트 콘텐츠 보강

## 문제
유료 진단 PDF에 "조치 의무 (규칙 제32조)"처럼 법령명+조문번호만 표시됨.
**무엇을, 어떻게** 해야 하는지 구체적 내용이 없음.

## 원인
DB `master_building_legal_rules` 테이블에 `remarks` 필드가 있고, 구체적 내용이 들어있음:
- "건축물 정기점검 — 연면적 1,000㎡ 이상, 2년마다"
- "보건관리자 선임 — 50명 이상 (시행령 기준)"
- "승강기 자체점검 — 월 1회"

하지만 법령엔진이 이 필드를 `full_result`에 포함하지 않음.

## 수정 대상 파일 (우선순위순)

### 1. 법령엔진 (핵심)
`routers/legal_engine.py` 또는 `routers/legal_engine_v510.py` — 둘 다 확인

#### 찾을 곳
`master_building_legal_rules` 테이블에서 SELECT 하는 부분.
grep 키워드: `select`, `master_building`, `obligation_summary`

#### 수정 내용
현재 SELECT에 `remarks` 컬럼이 빠져 있음. 추가 필요:
```python
# 현재 (예시)
.select("rule_id, law_name, law_article, obligation_summary, ...")

# 변경
.select("rule_id, law_name, law_article, obligation_summary, remarks, ...")
```

그리고 rules_table 딕셔너리 조립 부분에서도 `remarks`를 포함:
```python
rule_item = {
    ...
    "obligation_summary": r.get("obligation_summary", ""),
    "remarks": r.get("remarks", ""),  # ← 추가
    "description": r.get("remarks") or r.get("obligation_summary", ""),  # ← remarks 우선
    ...
}
```

### 2. 진단 통합 엔드포인트
`routers/diagnosis_integrated.py` — `run_diagnosis()` 함수

법령엔진 호출 결과를 `full_result`에 저장하는 부분 확인.
법령엔진이 `remarks`를 포함해서 반환하면 자동으로 `full_result`에도 포함됨.
별도 수정 불필요할 수 있으나 확인 필요.

### 3. PDF 템플릿
`templates/diagnosis_report_paid.html`

규칙 목록 렌더링 부분에서 `obligation_summary` 대신 `description` (또는 `remarks || obligation_summary`)을 표시:

```html
<!-- 현재 -->
<td>{{ rule.obligation_summary }}</td>

<!-- 변경 -->
<td>{{ rule.remarks or rule.obligation_summary }}</td>
```

## DB 스키마 참고

### master_building_legal_rules 주요 컬럼
| 컬럼 | 설명 | 예시 |
|------|------|------|
| `obligation_summary` | 의무 요약 (현재 PDF에 표시) | "점검 의무 (건축법 제35조)" |
| `remarks` | **구체적 상세 설명** | "건축물 정기점검 — 연면적 1,000㎡ 이상, 2년마다" |
| `condition_code` | 매칭 조건 | "building_area", "worker_count", "elevator_count" |
| `inspection_cycle_value` | 점검 주기 숫자 | "1", "2" |
| `inspection_cycle_unit_code` | 주기 단위 코드 | "003"(월), "004"(년), "007"(2년) |

### remarks 필드 현황
```sql
SELECT count(*) as total,
  count(*) FILTER (WHERE remarks IS NOT NULL AND remarks != '') as has_remarks
FROM master_building_legal_rules WHERE is_active = true;
-- 약 1,133건 중 일부에 remarks 있음
```

## 테스트
```bash
# 진단 실행 후 full_result에 remarks 포함 확인
curl -s -X POST https://api.taieng.co.kr/diagnosis/run \
  -H "Content-Type: application/json" \
  -d '{"sector":"BUILDING","area":500,"building_use":"OFFICE","completion_year":2010}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('full_result',{}).get('rules_table',[]); print(json.dumps(r[0], indent=2, ensure_ascii=False))" 2>/dev/null

# remarks 필드가 출력에 포함되어야 함

# PDF 테스트
curl -s -o /tmp/test-report.pdf \
  "https://api.taieng.co.kr/diagnosis/report-pdf/e2e-ind-paid-c1269589a61e61091c8d"
open /tmp/test-report.pdf
```

## 커밋
- 브랜치: `dev`
- 메시지: `feat(engine): add remarks field to rules_table output for detailed PDF content`

## 주의사항
1. `remarks`가 NULL인 규칙도 있음 — fallback으로 `obligation_summary` 사용
2. SELECT에 `*` 사용하면 간단하지만, 현재 명시적 컬럼 리스트면 `remarks` 추가
3. `legal_engine.py`와 `legal_engine_v510.py` 둘 다 확인 — 어느 것이 실제 사용되는지 파악
4. `diagnosis_integrated.py`의 `run_diagnosis()`가 어느 엔진을 호출하는지 추적
