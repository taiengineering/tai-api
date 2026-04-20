# 법령 수집엔진 보강 작업지시서 v2.1

이슈 #24 · 2026-04-20 기획창 세션 4일차

## 1. 문제 재정의 (소비자 관점 역추적)

### 원래 이슈 프레이밍 (잘못됨)
- "커버리지 1,133 → 3,000건 확장"
- "7개 컬럼 신규 추가"

### 실제 문제
소비자가 법령진단·SaaS·매칭에서 받는 결과물의 **품질과 무결성** 부족.
원인은 기존 파싱 엔진이 82개 컬럼 중 13개만 채우고 프로덕션에 올린 것.

### 소비자 전달 품질: 6하원칙 기준 (활성 1,133건)
| 6하원칙 | 소비자 질문 | DB 필드 | 채움률 | 등급 |
|---|---|---|---|---|
| **무엇을** (WHAT) | 뭘 해야 하나 | obligation_summary | 100% | ✅ |
| **왜** (WHY) | 안 하면 어떻게 되나 | penalty_summary | 27% | ❌ |
| **누가** (WHO) | 누가 할 수 있나 | qualification_code | 3% | ❌ |
| **언제** (WHEN) | 기한·주기가 언제 | due_days, cycle_base_guide | 31~69% | ⚠️ |
| **어디서** (WHERE) | 어디에 제출하나 | submit_org_code | 100% 코드만 | ⚠️ |
| **어떻게** (HOW) | 어떤 서류로, 어떤 방법 | form_name, report_method | 0~17% | ❌ |

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

---

## 3. 보강: 기존 엔진 강화

### 변경 1: AI 입력 컨텍스트 확장
현재: 조문 텍스트 1개 (3,000자 제한)
목표: 법률 본조 + 시행령 관련 조문 + 별표 + 벌칙 조항 풀세트

DB에서 가져오는 방법:
1. `law_article` 본조 → `law_paragraph` + `law_item` 포함
2. 같은 법령의 벌칙 조항 → `law_article` WHERE article_title LIKE '%벌칙%' OR '%과태료%'
3. 시행령 관련 조문 → `law_master`에서 시행령 찾기 → `law_article` 매핑
4. 별표 → `law_attachment` WHERE law_version_id 매칭

### 변경 2: AI 출력 스키마 확장 (6하원칙 완전 커버)
현재 13개 필드 → 목표 30개+ 필드

| 6하원칙 | 추출 필드 |
|---|---|
| WHAT | obligation_summary, obligation_type, remarks |
| WHY | penalty_summary, penalty_value |
| WHO | appointment_qualification_code, appointment_qualification_level_code, appointment_count_value |
| WHEN | due_days, inspection_cycle_value, inspection_cycle_unit_code, cycle_base_guide |
| WHERE | submit_org_code (8개 코드 → 한글 라벨 자동 매핑) |
| HOW | form_code, form_name, report_method_code, report_method_std, online_system, system_url |
| TAI연결 | tai_feature_code |

### 변경 3: condition_code 마스터 완전 제공
현재 시스템 프롬프트: 12개 → 실제 DB 사용: 24개

추가 12개:
```
employee_count, is_factory_registered, contract_amount,
has_chemical_substance, annual_energy_toe, electric_capacity,
boiler_capacity_kw, is_multi_use, contractor_count,
has_high_pressure_gas, transformer_capacity_kva, has_boiler
```

### 변경 4: submit_org_code 한글 매핑 (WHERE 해결)

| 코드 | 한글명 | 소비자 안내 | 사용건수 |
|---|---|---|---|
| kosha | 한국산업안전보건공단 | 안전보건공단 관할 지역본부 | 305 |
| local_gov | 지방자치단체 | 관할 시·군·구청 | 286 |
| moel | 고용노동부 | 관할 지방고용노동관서 | 140 |
| me | 환경부 | 관할 지방환경관서 | 105 |
| kgs | 한국가스안전공사 | 가스안전공사 관할 지사 | 95 |
| mlit | 국토교통부 | 관할 지방국토관리청 | 92 |
| nfa | 소방청 | 관할 소방서 | 74 |
| kesco | 한국전기안전공사 | 전기안전공사 관할 지사 | 36 |

구현: `submit_org_code` → 프론트/PDF에서 한글 라벨 표시.
별도 테이블 불필요 — 8개이므로 프론트 상수 또는 법령엔진 응답 시 변환.

---

## 4. 신규 엔드포인트

### POST /law-rule-generator/reparse-master
기존 master 룰의 빈칸을 법령 원문 재수집(DB에서) → AI 재파싱으로 채움.

### POST /law-rule-generator/validate-master
프로덕션 룰 전체 무결성 점검 + 리포트 출력.

검증 규칙:
- condition 3종 세트 완전성
- condition_code ∈ 24개 마스터
- inspection_required=true → cycle 값 존재
- report_required=true → report_method 존재
- appointment_required=true → qualification 존재
- penalty_required=true → penalty_value 존재
- rule_id 중복 없음

---

## 5. 시스템 프롬프트 보강: few-shot + 6하원칙

잘 채워진 룰 예시를 프롬프트에 포함:
```json
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

## 6. DDL (유일)

```sql
ALTER TABLE master_building_legal_rules
  ADD COLUMN IF NOT EXISTS tai_feature_code VARCHAR(50);
```

---

## 7. AI 모델 전략

| 용도 | 모델 | 이유 |
|---|---|---|
| 신규 조문 파싱 (기존) | Haiku 4.5 | 비용 효율, 대량 처리 |
| 기존 룰 reparse (빈칸 채움) | Sonnet | 복잡한 크로스레퍼런스 |
| 자동승인/무결성 검증 | 코드 로직 | AI 불필요 |

---

## 8. 실행 순서

### Phase 1: 무결성 확보
1. validate-master 구현 → 전체 검증 리포트
2. 215건 깨진 condition → reparse로 자동 수정
3. 923건 미검증 룰 → reparse 후 활성화 또는 폐기

### Phase 2: 소비자 품질 (6하원칙 완성)
4. 시스템 프롬프트 보강 (24개 코드 + few-shot + 30개 출력)
5. reparse-master로 1,133건 빈칸 채움
6. tai_feature_code 컬럼 추가 + 자동 매핑
7. submit_org_code 한글 매핑 적용

### Phase 3: 신규 확장
8. parse-batch 프롬프트 동일 보강
9. 미파싱 조문 일괄 재처리

---

## 9. Cursor 작업지시

### 파일 수정
- `routers/law_rule_generator.py` — 프롬프트 보강 + reparse/validate 엔드포인트
- 200줄+ → Cursor 필수

### 신규 파일
- `services/law_context_builder.py` — 법령 원문 체인 조립

### DB
- ALTER TABLE: tai_feature_code 1개

### 테스트 케이스
- FIREACT-005-MFG (깨진 condition) → reparse → 수정 확인
- ENERGYACT-002 (빈 qualification) → reparse → 채움 확인
- ODORACTS-001-MFG (빈 report_method) → reparse → 채움 확인

## 10. 완료 기준: 소비자 결과 6하원칙

작업 완료 시 소비자가 받는 법령진단 결과 1건:
```
📋 소방안전관리자 선임 (화재의 예방 및 안전관리에 관한 법률 제24조)

[무엇을] 연면적 400㎡ 이상 → 소방안전관리자 1명 이상 선임
[왜]     미선임 시 300만원 이하 과태료
[누가]   소방안전관리자 1급 이상 자격 보유자
[언제]   선임 후 14일 이내 신고, 이후 6개월마다 점검
[어디서] 관할 소방서
[어떻게] 소방안전관리자 선임신고서 (별지 제5호서식) → 소방청 온라인 시스템
[TAI]   선임연결 서비스에서 매칭 가능
```
