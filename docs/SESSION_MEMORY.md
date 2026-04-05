# TAI Safe Backend (tai-api) - Session Memory
**마지막 업데이트: 2026-04-03 23:50**

**제품·아키텍처 공유 (다른 창·에이전트 참조)**: [`docs/TAI_전체_작업_정리_공유용.md`](./TAI_전체_작업_정리_공유용.md)

---

## ✅ 오늘 완료된 작업 (2026-04-03)

### 법령 수집 & 파싱
- **법령 파싱: 3,986조문 100% 완료** ✅
- PENDING 1,330개 → 전부 APPROVED ✅
- 법령 정규화 (띄어쓰기 등) 검증 완료

### master_building_legal_rules 데이터
- **총 2,080개 규칙** (초기 876 + AI 신규 1,204)
- `rule_type_code` 전체 채움 ✅
- `condition_code` 267개 draft에서 가져옴 ✅

---

## 📋 다음 작업 (신규 창에서 진행)

### 1️⃣ AI 생성 룰 조정 (우선순위 높음)
- **937개 규칙 condition 없음** → 비활성화(is_active=false) 여부 결정
  - 옵션A: 모두 비활성화 후 나중에 선별
  - 옵션B: condition_code 재추출 필요한 것만 표시
- Haiku로 condition_code 재추출 필요시 준비

### 2️⃣ PENDING 규칙 검토 (수동)
- **PENDING 263개** 검토
  - 법령 정확성 확인
  - 건설업 특수 로직 필요 여부 검토
  - obligation 타입별 분류

### 3️⃣ 건설업 알고리즘 (구조적 분리)
```
건설업 특수 계산:
- 하도급인 수 포함 여부 (산안법 시행령 제16조③)
- 건축 150억 / 토목 120억 사업비 기준
- process → work → worker → report 완전 연계
```

### 4️⃣ 일정관리 "룰→일정 생성" 실행
- 각 의무별 일정 항목 자동 생성
- 스케줄러 구현 (Daily/Weekly/Monthly)

---

## 🗄️ 현재 DB 상태

### 테이블 (Live)
| 테이블 | 행 수 | 상태 |
|-------|------|------|
| `master_building_legal_rules` | 2,080 | 937개 condition 없음 |
| `master_legal_obligation_types` | 7 | 스키마 확정 |
| `factory_diagnosis_results` | - | 3단계 진단 구현 |
| `kcsc_process_master` | 161 | 건축/토목/공통 |
| `kcsc_work_master` | 243 | 위험작업 88 |

### API 엔드포인트
- POST `/legal-engine/diagnose/step1~3` — 3단계 진단
- GET `/rules/building` — 건설 규칙 조회

---

## 📞 상태 확인 명령어

```python
# DB 최신 상태
SELECT COUNT(*) FROM master_building_legal_rules WHERE is_active = true;
SELECT COUNT(*) FROM master_building_legal_rules WHERE condition_code IS NULL;
SELECT COUNT(*) FROM master_legal_rules WHERE status = 'PENDING';

# 조건코드 통계
SELECT condition_code, COUNT(*) FROM master_building_legal_rules 
GROUP BY condition_code ORDER BY COUNT(*) DESC;
```

---

## 🔐 인증 / 계정
- **Admin**: hetto@kakao.com (role 001, ACTIVE)
- **Supabase**: xntdkrjhgcscmqctdzyo
- **Railway API**: https://api.taieng.co.kr/

---

## 📌 주의사항
1. **condition_code 없는 규칙**: 비활성화 전 CTO 승인 필요
2. **건설업 로직**: 산안법 시행령 제16조③ 참고
3. **API 사이즈 제한**: `size <= 100` (pagination 필수)
