# 법령 수집엔진 보강 작업지시서 v2

이슈 #24 · 2026-04-20 기획창 세션 4일차

## 1. 문제 재정의 (소비자 관점 역추적)

### 원래 이슈 프레이밍 (잘못됨)
- "커버리지 1,133 → 3,000건 확장"
- "7개 컬럼 신규 추가"

### 실제 문제
소비자가 법령진단·SaaS·매칭에서 받는 결과물의 **품질과 무결성** 부족.
원인은 기존 파싱 엔진이 82개 컬럼 중 13개만 채우고 프로덕션에 올린 것.

### 소비자 전달 품질 (활성 1,133건 기준)
| 소비자 질문 | DB 필드 | 채움률 | 등급 |
|---|---|---|---|
| 무엇을 해야 하는가 | obligation_summary | 100% | ✅ |
| 왜 해야 하는가 | remarks | 99% | ✅ |
| 어디에 제출 | submit_org_code | 100% (코드만) | ⚠️ |
| 기한이 언제 | due_days | 69% | ⚠️ |
| 주기가 어떻게 | cycle_base_guide | 31% | ❌ |
| 과태료가 얼마 | penalty_summary | 27% | ❌ |
| 어떤 서류 필요 | form_name/url | 17% | ❌ |
| 누가 할 수 있는지 | qualification_code | 3% | ❌ |
| 신고 방법 | report_method_code | 0% (142건 전부 공백) | ❌ |

### 판정 로직 무결성
| 문제 | 건수 |
|---|---|
| condition 깨진 룰 (code는 있는데 operator 없음) | 215건 |
| needs_review=true인데 active=true | 15건 |
| inactive + needs_review (미검증 방치) | 923건 |

---

## 2. 기존 인프라 (이미 구현됨)

### 법령 원문 — 수집 완료, 재수집 불필요
| 테이블 | 데이터 |
|---|---|
| law_master | 473개 법령 |
| law_article | 33,845개 조문 |
| law_paragraph | 54,925개 항 |
| law_item | 37,083개 호·목 |
| law_attachment | 5,567개 별표/서식 |
| law_collection_target | 82개 수집 대상 |

### AI 파싱 엔진 — 이미 존재
`routers/law_rule_generator.py` (34KB)
- Claude Haiku 4.5 기반
- POST /parse, /parse-batch, /auto-parse-and-approve
- law_rule_drafts (2,152건 초안) → master 등록 워크플로우
- condition_code 12개 시스템 프롬프트에 포함

### 추가 파서
`scripts/law_rule_parser.py` — 키워드 기반 정규식 파서 (AI 미사용)
`scripts/law_collector.py` — 법제처 API + GPT-4o 변환 (일회성 스크립트)

---

## 3. 보강 방향: 새로 만들지 않음, 기존 엔진 강화

### 핵심 변경 3가지

#### 변경 1: AI 입력 컨텍스트 확장
현재: 조문 텍스트 1개 (3,000자 제한)
목표: 법률 본조 + 시행령 관련 조문 + 별표 + 벌칙 조항 풀세트

```python
# 현재
user_prompt = USER_PROMPT_TEMPLATE.format(
    law_name=law_name, article_text=article_text[:3000])

# 목표
context = build_full_context(
    law_name=law_name,
    article_id=article_id,  # 본조
    include_enforcement_decree=True,  # 시행령 관련 조문
    include_appendix=True,  # 별표
    include_penalty_articles=True,  # 벌칙 조항
)
user_prompt = ENHANCED_PROMPT.format(context=context)
```

DB에서 가져오는 방법:
1. `law_article` 본조 → `law_paragraph` + `law_item` 포함
2. 같은 법령의 벌칙 조항 → `law_article` WHERE article_title LIKE '%벌칙%' OR '%과태료%'
3. 시행령 관련 조문 → `law_master`에서 시행령 찾기 → `law_article` 매핑
4. 별표 → `law_attachment` WHERE law_version_id 매칭

#### 변경 2: AI 출력 스키마 확장
현재 13개 필드 → 목표 30개+ 필드

추가 추출 대상:
```json
{
  "condition_code": "24개 마스터에서 선택",
  "condition_operator_code": "gte|lte|eq",
  "condition_value": "숫자",
  "penalty_summary": "과태료 금액 + 조문",
  "penalty_value": "숫자 (만원 단위)",
  "form_code": "별지서식 번호",
  "form_name": "서식명",
  "submit_org_code": "제출처 코드",
  "due_days": "기한 일수",
  "report_method_code": "신고방법 코드",
  "report_method_std": "온라인/오프라인/겸용",
  "appointment_qualification_code": "자격 코드",
  "appointment_qualification_level_code": "자격 등급",
  "appointment_count_value": "선임 인원수",
  "inspection_cycle_value": "점검 주기 숫자",
  "inspection_cycle_unit_code": "주기 단위",
  "cycle_base_guide": "주기 설명",
  "online_system": "온라인 시스템명",
  "system_url": "시스템 URL",
  "remarks": "맥락 설명",
  "obligation_type": "APPOINT|INSPECT|NOTIFY|REPORT|ACTION",
  "tai_feature_code": "APPOINTMENT|INSPECTION|REPORT|EDUCATION|DOCUMENT|FIX|CHECKLIST"
}
```

#### 변경 3: condition_code 마스터 완전 제공
현재 시스템 프롬프트: 12개
실제 DB 사용 중: 24개

추가해야 할 코드 (시스템 프롬프트):
```
- employee_count: 상시근로자 수 (명) — 259건 사용 중
- is_factory_registered: 공장등록 여부 (0/1) — 123건
- contract_amount: 공사금액 (원) — 16건
- has_chemical_substance: 화학물질 취급 여부 (0/1) — 21건
- annual_energy_toe: 연간 에너지 사용량 (TOE) — 17건
- electric_capacity: 전기 수전용량 kW (중복?) — 11건
- boiler_capacity_kw: 보일러 용량 (kW) — 11건
- is_multi_use: 다중이용업소 여부 (0/1) — 10건
- contractor_count: 수급업체 수 — 5건
- has_high_pressure_gas: 고압가스 취급 여부 (0/1) — 4건
- transformer_capacity_kva: 변압기 용량 (kVA) — 4건
- has_boiler: 보일러 보유 여부 (0/1) — 2건
```

---

## 4. 신규 엔드포인트: reparse-master

기존 엔진은 "신규 조문 → 초안 → master" 흐름만 있음.
기존 master 룰의 빈칸을 채우는 역방향 흐름이 없음.

### POST /law-rule-generator/reparse-master

```
입력: { sector: "BUILDING", limit: 50, fill_empty_only: true }

동작:
1. master에서 빈칸 많은 룰 조회 (fill_empty_only=true)
2. 각 룰의 law_name + law_article로 원문 체인 조립
   - law_article 본조
   - 시행령 관련 조문 + 별표
   - 벌칙 조항
3. Claude Sonnet에게 기존 룰 + 풀 컨텍스트 제공
   - "이 룰의 빈 필드를 채워주세요"
   - few-shot: 같은 법령의 잘 채워진 룰 3~5개
4. 응답으로 빈 필드 UPDATE
5. 무결성 검증 실행
6. 검증 통과 → 바로 반영
   검증 실패 → needs_review=true + review_reason 기록
```

### POST /law-rule-generator/validate-master

```
입력: { sector: "ALL" }

동작: 프로덕션 룰 전체 무결성 점검

검증 규칙:
✓ condition_code ∈ 24개 마스터
✓ condition 3종(code/operator/value) 세트 완전성
✓ inspection_required=true → cycle 값 존재
✓ report_required=true → report_method 존재
✓ appointment_required=true → qualification 존재
✓ penalty_required=true → penalty_value 존재
✓ rule_id 중복 없음
✓ law_name + law_article 조합 유효 (law_article 테이블에 존재)

출력: 검증 리포트 (PASS/FAIL 건수, 실패 사유별 분류)
```

---

## 5. 시스템 프롬프트 보강안

### few-shot 예시 포함
잘 채워진 룰 예시를 프롬프트에 포함하여 출력 품질 향상.

```
[예시 - 잘 채워진 룰]
{
  "rule_id": "FIREACT-001",
  "law_name": "화재의 예방 및 안전관리에 관한 법률",
  "law_article": "제24조",
  "sector": "BUILDING",
  "condition_code": "building_area",
  "condition_operator_code": "gte",
  "condition_value": 400,
  "obligation_summary": "소방안전관리자 선임 의무",
  "penalty_summary": "미선임 시 300만원 이하 과태료 (제53조)",
  "penalty_value": 300,
  "form_code": "NFA-별지제5호",
  "form_name": "소방안전관리자 선임신고서",
  "submit_org_code": "nfa",
  "due_days": 14,
  "report_method_code": "online",
  "appointment_required": true,
  "appointment_target_code": "fire_safety_manager",
  "appointment_qualification_code": "fire_safety_1",
  "inspection_cycle_value": 6,
  "inspection_cycle_unit_code": "month",
  "cycle_base_guide": "최초 선임일로부터 6개월마다",
  "tai_feature_code": "APPOINTMENT",
  "remarks": "연면적 400㎡ 이상 특정소방대상물 소방안전관리자 선임"
}
```

---

## 6. tai_feature_code 컬럼 추가 (유일한 DDL)

```sql
ALTER TABLE master_building_legal_rules 
  ADD COLUMN IF NOT EXISTS tai_feature_code VARCHAR(50);

COMMENT ON COLUMN master_building_legal_rules.tai_feature_code IS 
  'TAI 기능 연결 코드: APPOINTMENT/INSPECTION/REPORT/EDUCATION/DOCUMENT/FIX/CHECKLIST';
```

---

## 7. AI 모델 전략

| 용도 | 모델 | 이유 |
|---|---|---|
| 신규 조문 파싱 (기존) | Haiku 4.5 | 비용 효율, 대량 처리 |
| 기존 룰 reparse (빈칸 채움) | Sonnet | 복잡한 크로스레퍼런스 (시행령+별표) |
| 자동승인 판단 | 코드 로직 | AI 불필요, 무결성 검증 규칙 |

---

## 8. 실행 순서

### Phase 1: 무결성 확보 (기존 데이터)
1. validate-master 엔드포인트 구현 → 전체 검증 리포트
2. 215건 깨진 condition 식별 → reparse-master로 자동 수정
3. 923건 미검증 룰 → reparse → 검증 통과시 활성화

### Phase 2: 소비자 품질 보강 (기존 데이터)
4. 시스템 프롬프트 보강 (24개 코드 + few-shot + 출력 스키마)
5. reparse-master로 1,133건 빈칸 채움 (Sonnet)
6. tai_feature_code 컬럼 추가 + 자동 매핑

### Phase 3: 신규 확장
7. 기존 parse-batch 프롬프트도 동일하게 보강
8. 미파싱 조문 대상 일괄 재처리

---

## 9. Cursor 작업지시 요약

### 파일 수정
- `routers/law_rule_generator.py` — 시스템 프롬프트 보강 + reparse/validate 엔드포인트 추가
- 200줄+ 파일이므로 반드시 Cursor 사용

### 신규 파일
- `services/law_context_builder.py` — 법령 원문 체인 조립 서비스
  (law_article + law_paragraph + 시행령 + 별표 + 벌칙 조항 → 하나의 컨텍스트)

### DB
- ALTER TABLE: tai_feature_code 1개 컬럼 추가

### 테스트
- FIREACT-005-MFG (깨진 condition) → reparse → 수정 확인
- ENERGYACT-002 (빈 qualification) → reparse → 채움 확인  
- ODORACTS-001-MFG (빈 report_method) → reparse → 채움 확인
