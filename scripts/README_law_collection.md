# TAI 법령 수집 실행 가이드

## 사전 준비

```bash
# 1. 패키지 설치
pip install requests openai supabase python-dotenv

# 2. 환경변수 설정 (.env 파일 또는 export)
export OPENAI_API_KEY=sk-...
export SUPABASE_URL=https://xntdkrjhgcscmqctdzyo.supabase.co
export SUPABASE_KEY=eyJ...
```

---

## STEP 1. 법령 원문 수집 + GPT 변환

### 섹터별 실행

```bash
# 건물·시설 섹터 (소방/전기 룰) -- 가장 먼저
python scripts/law_collector.py --sector BUILDING

# 공장·제조업 섹터 (KSIC별 안전관리자 선임, 위험물)
python scripts/law_collector.py --sector MANUFACTURING

# 건설현장 섹터 (공사금액 기준)
python scripts/law_collector.py --sector CONSTRUCTION

# 설비 법정검사 룰 (3단계)
python scripts/law_collector.py --sector EQUIPMENT

# 전체 진행 (1~2시간 소요)
python scripts/law_collector.py --sector ALL
```

### 출력 확인
```
scripts/output/
  rules_building_20260329.json
  rules_building_20260329.csv
  rules_manufacturing_20260329.json
  ...
```

---

## STEP 2. 수집된 JSON 검토

- JSON 파일 열어서 룰 내용 확인
- condition_field, threshold_value 등이 정확한지 직접 확인
- 오류사항은 해당 rule 직접 수정 후 다음 단계

---

## STEP 3. DB 적재

```bash
# 특정 파일 1개 적재
python scripts/law_db_insert.py --file scripts/output/rules_building_20260329.json

# 수집된 전체 파일 적재
python scripts/law_db_insert.py --all
```

---

## STEP 4. DB 확인

```sql
-- 적재 후 섹터별 룰 수 확인
SELECT sector, diagnosis_stage, COUNT(*)
FROM master_building_legal_rules
GROUP BY sector, diagnosis_stage
ORDER BY sector, diagnosis_stage;
```

---

## 정리 테이블 (수집 대상)

| 섹터 | 룰 항목 | 주요 입력 변수 |
|------|--------|----------------|
| BUILDING | 소방안전관리자 선임 / 전기안전관리자 선임 | building_use_category, gross_floor_area, electric_capacity_kw |
| MANUFACTURING | KSIC별 안전관리자 / 위험물 / 고압가스 | ksic_lv1_code, worker_count, has_hazardous_material |
| CONSTRUCTION | 공사금액 구간별 | contract_amount, worker_count |
| EQUIPMENT | 유해위험기계기구 법정검사 | equipment_code, capacity |

---

## 두 스크립트 역할 분리

```
law_collector.py   ←──  법제처 API 원문 수집 + GPT JSON 변환 + 파일 저장
law_db_insert.py   ←──  JSON 파일 확인 후 Supabase DB 적재
```

---

## Claude Code 터미널 명령어

```bash
cd /Users/taiwangsim/Library/Mobile\ Documents/com~apple~CloudDocs/1.TAI엔지니어링/admin/tai-api/tai-api

# BUILDING 먼저 실행
python scripts/law_collector.py --sector BUILDING

# 결과 확인 후 DB 적재
python scripts/law_db_insert.py --file scripts/output/rules_building_최신.json
```
