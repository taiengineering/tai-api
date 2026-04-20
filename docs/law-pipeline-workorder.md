# 법령 파이프라인 보강 작업지시서

이슈 #24 참조.

## 문제
1. 법령 데이터 커버리지 부족 (1,133건/3,000~5,000건)
2. 소비자 전달 구조 부재 (무엇을/어떻게/언제 안내 못함)

## 해결 2단계

### Phase 1: 기존 파이프라인 실행으로 커버리지 확장

파이프라인 이미 구현됨 (`scripts/` 디렉토리):
- `law_collector.py` — 법제처 API 수집 + GPT JSON 변환
- `law_rule_parser.py` — AI 의무 추출
- `law_to_rules.py` — 변환
- `law_db_insert.py` — DB INSERT
- `README_law_collection.md` — 실행 가이드

실행:
```bash
python scripts/law_collector.py --sector ALL
python scripts/law_db_insert.py --all
```

### Phase 2: 소비자 전달 구조 보강

#### DB 스키마 확장 (7개 컬럼 추가)
```sql
ALTER TABLE master_building_legal_rules ADD COLUMN IF NOT EXISTS compliance_guide TEXT;
ALTER TABLE master_building_legal_rules ADD COLUMN IF NOT EXISTS required_documents TEXT;
ALTER TABLE master_building_legal_rules ADD COLUMN IF NOT EXISTS submit_to TEXT;
ALTER TABLE master_building_legal_rules ADD COLUMN IF NOT EXISTS penalty_detail TEXT;
ALTER TABLE master_building_legal_rules ADD COLUMN IF NOT EXISTS qualification TEXT;
ALTER TABLE master_building_legal_rules ADD COLUMN IF NOT EXISTS deadline_description TEXT;
ALTER TABLE master_building_legal_rules ADD COLUMN IF NOT EXISTS tai_feature_code TEXT;
```

#### 각 컬럼 용도
| 컬럼 | 용도 | 예시 |
|------|------|------|
| compliance_guide | 이행 방법 (HOW) | "자격 보유자 선임 후 14일 내 관할 노동관서에 신고" |
| required_documents | 필요 서류 | "안전관리자 선임신고서 (별지 제5호서식)" |
| submit_to | 제출처 (한글) | "관할 지방고용노동관서" |
| penalty_detail | 과태료 상세 | "미선임 500만원 / 미신고 300만원" |
| qualification | 자격요건 | "산업안전산업기사 이상" |
| deadline_description | 기한 | "14일 이내", "매 반기", "작업 전" |
| tai_feature_code | TAI 기능 연결 | APPOINTMENT/INSPECTION/REPORT/EDUCATION/DOCUMENT/FIX/CHECKLIST |

#### 파이프라인 AI 프롬프트 보강
`law_rule_parser.py`의 GPT 프롬프트에 위 7개 필드 추출 요청 추가.

#### 기존 데이터 보강
보강된 파이프라인으로 기존 1,133건 재파싱하여 새 컬럼 채우기.

#### 소비자 전달 UI
- 유료 PDF: 각 의무에 이행방법/서류/과태료/TAI연결 표시
- 웹 결과: 동일 구조
- 무료 결과: remarks만 (현재와 동일)

## 소비자 전달 목표 형태
```
📋 안전관리자 선임 (산업안전보건법 제17조)

무엇을: 상시근로자 50인 이상 → 안전관리자 1명 이상 선임
이행방법: 자격 보유자 선임 → 14일 내 신고서 작성 → 노동관서 제출
필요서류: 별지 제5호서식
과태료: 미선임 500만원 / 미신고 300만원
TAI: 선임연결 서비스에서 매칭 가능
```

## tai_feature_code 매핑
| 코드 | TAI 기능 | 의무 유형 |
|------|---------|----------|
| APPOINTMENT | 선임연결 | APPOINT |
| INSPECTION | 점검일정 관리 | INSPECT |
| REPORT | 자동신고 대행 | REPORT |
| EDUCATION | 교육사업 연결 | 교육 관련 |
| DOCUMENT | 문서서식 생성 | DOCUMENT |
| FIX | TAI Fix 수선연결 | 정비/수선 |
| CHECKLIST | 작업자 점검 | ACTION/BEFORE_WORK |
