# Cursor 작업지시 — 법령엔진 수집엔진 보강

## 배경
TAI Safe 법령엔진의 수집 파이프라인 보강. 이슈 #24.
기존 Haiku 파싱 엔진(`routers/law_rule_generator.py`)이 조문 1개만 받아 13개 필드만 출력.
결과: 프로덕션 master 테이블 82컬럼 중 ~15개만 채워짐.
소비자 6하원칙(WHAT/WHY/WHO/WHEN/WHERE/HOW) 전달 불가.

## 기준 문서
`docs/law-engine-enhancement-workorder.md` (dev 브랜치, v2.1) — 반드시 먼저 읽을 것.

## 작업 개요
기존 엔진 보강 (새로 만들지 않음). 3개 파일 작업.

---

## TASK 1: services/law_context_builder.py 신규 작성

### 목적
법령 원문을 DB에서 풀세트로 조립하여 AI에게 제공할 컨텍스트를 만드는 서비스.

### 입력
- law_name (str): 법령명
- law_article (str): 조문번호 (예: "제24조")
- article_id (str, optional): law_article 테이블 UUID

### 출력
하나의 텍스트 문자열. 아래 4개를 합쳐서 반환:
1. 본조 전문 (law_article + law_paragraph + law_item)
2. 시행령 관련 조문 (같은 법률의 시행령에서 관련 조문)
3. 별표/서식 목록 (law_attachment)
4. 벌칙 조항 (같은 법률의 벌칙/과태료 조문)

### DB 테이블 구조
```
law_master (id, law_name, law_type_code, is_active)
  └─ law_version (id, law_id, is_current)
       ├─ law_article (id, law_version_id, article_no, article_title, article_text, ai_parsed_at)
       │    ├─ law_paragraph (id, article_id, paragraph_no, paragraph_text)
       │    └─ law_item (→ paragraph 하위)
       └─ law_attachment (id, law_version_id, ...)
```

### 구현 로직
```python
async def build_full_context(law_name: str, law_article: str, article_id: str = None) -> str:
    supabase = get_supabase()
    parts = []
    
    # 1. 본조 전문
    # law_master에서 law_name으로 찾기 → law_version(is_current=True) → law_article
    # article_id가 있으면 직접 조회, 없으면 law_article 컬럼에서 article_no 매칭
    # law_paragraph, law_item 포함
    
    # 2. 시행령 관련 조문
    # law_master에서 "법률명 시행령" 검색 (예: "화재의 예방 및 안전관리에 관한 법률" → "화재의 예방 및 안전관리에 관한 법률 시행령")
    # 해당 시행령의 전체 조문 중 관련 조문 포함 (article_title에 키워드 매칭 또는 전체)
    # 별표도 포함
    
    # 3. 별표/서식
    # law_attachment에서 해당 법률 버전의 첨부 목록
    
    # 4. 벌칙 조항
    # 같은 법률의 law_article 중 article_title에 '벌칙', '과태료', '벌금', '양벌' 포함된 조문
    
    return "\n\n".join(parts)
```

### 주의사항
- `from db.supabase_client import get_supabase` 필수
- 컨텍스트 총량이 너무 크면 Claude API 토큰 초과 → 시행령은 관련 조문만, 별표는 목록만
- 시행령이 DB에 없을 수 있음 → 없으면 빈 문자열 반환 (에러 아님)
- async 함수로 작성

---

## TASK 2: routers/law_rule_generator.py 보강

⚠️ 이 파일은 34KB (900줄+). 반드시 Cursor에서 작업.

### 2-1: 시스템 프롬프트 보강

현재 `SYSTEM_PROMPT`의 condition_code 12개 → 24개로 확장.
추가할 코드:
```
- employee_count: 상시근로자 수 (명)
- is_factory_registered: 공장등록 여부 (0/1)
- contract_amount: 공사금액 (원)
- has_chemical_substance: 화학물질 취급 여부 (0/1)
- annual_energy_toe: 연간 에너지 사용량 (TOE)
- electric_capacity: 전기 수전용량 kW (electrical_capacity_kw와 동일 의미, 둘 다 유지)
- boiler_capacity_kw: 보일러 용량 (kW)
- is_multi_use: 다중이용업소 여부 (0/1)
- contractor_count: 수급업체 수
- has_high_pressure_gas: 고압가스 취급 여부 (0/1)
- transformer_capacity_kva: 변압기 용량 (kVA)
- has_boiler: 보일러 보유 여부 (0/1)
```

### 2-2: AI 출력 스키마 확장

현재 `USER_PROMPT_TEMPLATE`의 JSON 출력 필드 13개 → 30개+.
추가 필드:
```json
{
  "penalty_value": "과태료 숫자 (만원 단위) 또는 null",
  "form_code": "별지서식 번호 (예: NFA-별지제5호) 또는 null",
  "form_name": "서식명 또는 null",
  "submit_org_code": "kosha|local_gov|moel|me|kgs|mlit|nfa|kesco 중 선택 또는 null",
  "due_days": "기한 일수 (숫자) 또는 null",
  "report_method_code": "online|offline|both 또는 null",
  "report_method_std": "api|paper|keep 또는 null",
  "appointment_qualification_code": "자격 코드 또는 null",
  "appointment_qualification_level_code": "자격 등급 또는 null",  
  "appointment_count_value": "선임 인원수 (숫자) 또는 null",
  "inspection_cycle_value": "점검 주기 숫자 또는 null",
  "inspection_cycle_unit_code": "day|week|month|quarter|half_year|year 또는 null",
  "cycle_base_guide": "주기 설명 (최대 50자) 또는 null",
  "online_system": "온라인 시스템명 또는 null",
  "system_url": "시스템 URL 또는 null",
  "tai_feature_code": "APPOINTMENT|INSPECTION|REPORT|EDUCATION|DOCUMENT|FIX|CHECKLIST 또는 null",
  "remarks": "맥락 설명 (최대 100자)"
}
```

### 2-3: few-shot 예시 추가

SYSTEM_PROMPT 또는 USER_PROMPT에 잘 채워진 룰 예시 포함:
```json
[예시]
{
  "draft_rule_id": "FIREACT-001-BLD",
  "obligation_type": "APPOINT",
  "sector": "BUILDING",
  "condition_code": "building_area",
  "condition_operator": "gte",
  "condition_value": "400",
  "obligation_summary": "소방안전관리자 선임 의무",
  "penalty_summary": "미선임 시 300만원 이하 과태료 (제53조)",
  "penalty_value": 300,
  "form_code": "NFA-별지제5호",
  "form_name": "소방안전관리자 선임신고서",
  "submit_org_code": "nfa",
  "due_days": 14,
  "report_method_code": "online",
  "appointment_target": "소방안전관리자",
  "appointment_qualification_code": "fire_safety_1",
  "appointment_qualification_level_code": "grade1",
  "appointment_count_value": 1,
  "inspection_cycle_value": 6,
  "inspection_cycle_unit_code": "month",
  "cycle_base_guide": "최초 선임일로부터 6개월마다",
  "tai_feature_code": "APPOINTMENT",
  "remarks": "연면적 400㎡ 이상 특정소방대상물",
  "diagnosis_stage": 1,
  "ai_confidence": 95,
  "ai_reasoning": "화재예방법 제24조 + 시행령 제22조 별표4 기준"
}
```

### 2-4: submit_org_code 매핑 상수 추가

```python
SUBMIT_ORG_LABELS = {
    "kosha": "한국산업안전보건공단 (관할 지역본부)",
    "local_gov": "관할 시·군·구청",
    "moel": "관할 지방고용노동관서",
    "me": "관할 지방환경관서",
    "kgs": "한국가스안전공사 (관할 지사)",
    "mlit": "관할 지방국토관리청",
    "nfa": "관할 소방서",
    "kesco": "한국전기안전공사 (관할 지사)",
}
```

### 2-5: POST /validate-master 엔드포인트 신규

```python
@router.post("/validate-master")
async def validate_master(body: dict = None):
    """
    프로덕션 룰 전체 무결성 점검.
    입력: { sector: "ALL" 또는 "BUILDING" 등, fix_auto: false }
    출력: 검증 리포트 JSON
    """
    # 검증 규칙:
    # 1. condition_code가 있으면 condition_operator_code + condition_value도 있어야 함
    # 2. condition_code ∈ 24개 마스터 목록
    # 3. inspection_required=true → inspection_cycle_value + inspection_cycle_unit_code 존재
    # 4. report_required=true → report_method_code 존재 (현재 0%)
    # 5. appointment_required=true → appointment_qualification_code 존재
    # 6. penalty_required=true → penalty_value 존재
    # 7. rule_id 중복 없음
    # 8. obligation_summary NOT NULL 및 비어있지 않음
    #
    # 출력 형태:
    # { total: 1133, passed: 800, failed: 333, 
    #   failures: { "condition_incomplete": 215, "missing_report_method": 142, ... } }
```

### 2-6: POST /reparse-master 엔드포인트 신규

```python
CLAUDE_SONNET_MODEL = "claude-sonnet-4-20250514"

@router.post("/reparse-master")
async def reparse_master(body: dict):
    """
    기존 master 룰의 빈칸을 법령 원문 재수집(DB) + AI 재파싱으로 채움.
    
    입력: { 
      sector: "BUILDING", 
      limit: 50, 
      fill_empty_only: true,
      secret: "tai-internal-2026"
    }
    
    동작:
    1. master에서 빈칸 많은 룰 조회 (빈칸 수 기준 정렬)
    2. 각 룰의 law_name + law_article로 build_full_context() 호출
    3. Claude Sonnet에게 기존 룰 JSON + 풀 컨텍스트 제공
       프롬프트: "아래 룰의 빈 필드(null)를 법령 원문을 참고하여 채워주세요. 채울 수 없는 필드는 null 유지."
    4. 응답에서 null이 아닌 새 값만 UPDATE
    5. 무결성 검증 실행 (validate 로직 재사용)
    6. 결과 리포트 반환
    """
    # 빈칸 많은 룰 조회 SQL 예시:
    # SELECT * FROM master_building_legal_rules
    # WHERE is_active = true AND sector = :sector
    #   AND (penalty_summary IS NULL 
    #        OR report_method_code IS NULL 
    #        OR appointment_qualification_code IS NULL
    #        OR form_name IS NULL)
    # LIMIT :limit
    
    # Sonnet 호출 시 few-shot 예시도 포함
    # 같은 법령의 잘 채워진 룰 3~5개를 DB에서 조회하여 제공
```

### 2-7: _auto_approve_to_master 함수 보강

기존: 13개 필드만 master에 INSERT.
보강: 30개+ 필드 INSERT. draft에 새 필드가 있으면 함께 등록.

`law_rule_drafts` 테이블에 새 필드 컬럼이 없을 수 있음.
→ draft에 없는 필드는 reparse-master에서 별도로 채움. 충돌 없음.

---

## TASK 3: DB 마이그레이션 (Supabase MCP 또는 터미널)

```sql
ALTER TABLE master_building_legal_rules
  ADD COLUMN IF NOT EXISTS tai_feature_code VARCHAR(50);

COMMENT ON COLUMN master_building_legal_rules.tai_feature_code IS 
  'TAI 기능 연결: APPOINTMENT/INSPECTION/REPORT/EDUCATION/DOCUMENT/FIX/CHECKLIST';
```

---

## 테스트 케이스

### 테스트 1: validate-master
```bash
curl -X POST https://api.taieng.co.kr/law-rule-generator/validate-master \
  -H 'Content-Type: application/json' \
  -d '{"sector": "ALL"}'
```
기대: total=1133, failed > 0, failures 항목별 건수

### 테스트 2: reparse-master (깨진 condition)
```bash
curl -X POST https://api.taieng.co.kr/law-rule-generator/reparse-master \
  -H 'Content-Type: application/json' \
  -d '{"sector": "MANUFACTURING", "limit": 3, "fill_empty_only": true, "secret": "tai-internal-2026"}'
```
기대: FIREACT-005-MFG의 condition_operator_code, condition_value 채워짐

### 테스트 3: reparse-master (빈 qualification)
```bash
# ENERGYACT-002 rule_id로 단건 테스트
curl -X POST https://api.taieng.co.kr/law-rule-generator/reparse-master \
  -H 'Content-Type: application/json' \
  -d '{"rule_ids": ["ENERGYACT-002"], "secret": "tai-internal-2026"}'
```
기대: appointment_qualification_code 채워짐

---

## 개발 규칙
- `from db.supabase_client import get_supabase`
- /health 절대 503 금지 (200 고정)
- dev 브랜치에서 작업 → PR → main
- ANTHROPIC_API_KEY 환경변수 필요
- Haiku: claude-haiku-4-5-20251001 (기존 파싱)
- Sonnet: claude-sonnet-4-20250514 (reparse)
- FastAPI route 순서: 구체 경로 먼저 (/drafts/stats → /drafts/{id})
