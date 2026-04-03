# TAI Safe 신규 창 시작 프롬프트
**작성일: 2026-04-03 23:55 | 컨텍스트: 법령 파싱 완료 → 규칙 정제 단계**

---

## 🎯 현재 상황 요약

**완료 (2026-04-03)**
- ✅ 법령 파싱: 3,986조문 100% 
- ✅ PENDING 1,330개 → 전부 APPROVED
- ✅ master_building_legal_rules: 2,080개 (신규 AI 1,204개)
- ✅ rule_type_code: 전체 채움
- ✅ condition_code: 267개 draft에서 매핑

**현재 문제**
- 937개 규칙이 condition_code 없음 → 비활성화 여부 결정 필요
- PENDING 263개 규칙 수동 검토 필요
- 일정관리 자동화 미구현

---

## 📋 지금부터 할 작업 (우선순위순)

### 1️⃣ Haiku로 condition_code 재추출 (선택사항이지만 권장)
**목표**: 937개 미매핑 규칙에 대해 Haiku가 자동으로 적절한 condition_code 제안

```sql
-- 추출 대상 (937개)
SELECT id, rule_name, obligation_summary 
FROM master_building_legal_rules 
WHERE condition_code IS NULL AND is_active = true
LIMIT 50; -- 배치로 50개씩
```

**Haiku 프롬프트**:
```
다음 건설업 안전 규칙에 대해 가장 적절한 condition_code를 선택하세요.
[조건코드 리스트 267개 제공]

규칙명: {rule_name}
의무내용: {obligation_summary}

적절한 condition_code: 
설명:
```

**결과 처리**:
```python
# Haiku 응답 → condition_code UPDATE
UPDATE master_building_legal_rules 
SET condition_code = '{code}' 
WHERE id = {rule_id};
```

---

### 2️⃣ 937개 규칙 비활성화 결정
**옵션**:
- **A**: 전부 비활성화 (`is_active = false`) → 나중에 필요시 활성화
- **B**: condition_code 없는 것만 비활성화
- **C**: Haiku 재추출 후 결정

**추천**: A (먼저 Haiku 재추출 50개 시범 → 결과 보고)

---

### 3️⃣ PENDING 263개 규칙 수동 검토
**확인 항목**:
1. 법령명 정확성 (띄어쓰기 등)
2. 의무 내용 적절성
3. 건설업 특수 로직 필요 여부 (산안법 시행령 제16조③)
4. obligation_type 재분류

**처리 흐름**:
```
PENDING → 검토중 (reviewer_id=001) 
        → APPROVED / REJECTED (with comment)
```

---

### 4️⃣ 일정관리 "룰→일정 생성" 실행
**스키마**:
```sql
-- 의무별 일정 항목 자동 생성
CREATE TABLE IF NOT EXISTS schedule_items (
  id UUID PRIMARY KEY,
  obligation_id UUID REFERENCES legal_obligations(id),
  title VARCHAR,
  frequency VARCHAR ('DAILY', 'WEEKLY', 'MONTHLY'),
  due_date DATE,
  is_completed BOOLEAN DEFAULT false,
  created_at TIMESTAMP
);
```

**로직**:
```python
# legal_obligations 조회
for obligation in get_all_active_obligations():
  create_schedule_item(
    obligation_id=obligation.id,
    title=obligation.obligation_summary,
    frequency=determine_frequency(obligation.rule_type_code),
    due_date=calculate_due_date()
  )
```

---

## 🗄️ 주요 SQL 쿼리

```sql
-- 1. condition 없는 규칙 확인
SELECT COUNT(*) FROM master_building_legal_rules 
WHERE condition_code IS NULL AND is_active = true;
-- 예상: 937

-- 2. condition_code 분포
SELECT condition_code, COUNT(*) as cnt
FROM master_building_legal_rules
WHERE condition_code IS NOT NULL
GROUP BY condition_code
ORDER BY cnt DESC;

-- 3. PENDING 규칙 조회
SELECT id, rule_name, obligation_summary, status
FROM master_legal_rules
WHERE status = 'PENDING'
LIMIT 30;

-- 4. rule_type_code 통계
SELECT rule_type_code, COUNT(*) FROM master_building_legal_rules
GROUP BY rule_type_code ORDER BY COUNT(*) DESC;
```

---

## 🔧 구현 우선순위

| 우선순위 | 작업 | 예상 시간 | 복잡도 |
|---------|------|---------|-------|
| 🔴 높음 | Haiku condition 재추출 (배치) | 30분 | 낮음 |
| 🔴 높음 | 937개 비활성화 결정 | 10분 | 낮음 |
| 🟡 중간 | PENDING 263개 검토 | 1-2시간 | 중간 |
| 🟡 중간 | 일정 생성 자동화 | 45분 | 중간 |

---

## 📌 중요 주의사항

1. **condition_code 재추출 시**:
   - Haiku 배치: 50개씩, 10배치 = 500 호출
   - 기존 267개 매핑 데이터는 유지
   - 신규 매핑도 검토 후 적용 (100% 자동은 위험)

2. **비활성화 전**:
   - 백업 확인 (master_building_legal_rules_backup)
   - 데이터 소실 없음 (is_active만 변경)

3. **일정 생성 로직**:
   - frequency 자동 결정 규칙 명확히 (rule_type_code 기반)
   - 중복 생성 방지 (idempotent)

---

## 🔐 현재 DB/API 상태

- **Supabase**: xntdkrjhgcscmqctdzyo
- **Railway API**: https://api.taieng.co.kr/ (v4.2.0)
- **Admin**: hetto@kakao.com (role 001, ACTIVE)

---

## ✨ 마지막 체크

- [ ] Haiku condition 재추출 시작 (배치 50개)
- [ ] 937개 비활성화 결정 후 UPDATE
- [ ] PENDING 263개 검토 체크리스트 작성
- [ ] 일정 생성 스케줄러 구현 시작
