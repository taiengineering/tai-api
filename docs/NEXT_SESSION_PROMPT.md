# TAI Safe 신규 창 시작 프롬프트
**작성일: 2026-04-06 | 컨텍스트: 데이터 분석 완료 → 데이터 정제 단계**

---

## 🎯 현재 상황 요약

**완료 (2026-04-06)**
- ✅ AI 생성 룰 937개 비활성화 (condition_code 미설정)
- ✅ PENDING 262개 분석 완료
- ✅ BUILDING 섹터 완성도 점검 완료
- ✅ inspection_sets 미생성 INSPECT 룰 50건 추출
- ✅ condition_code 입력 우선순위 목록 작성
- ✅ main.py v5.6.0 / contract_kmong v1.0.0 / law_rule_generator v1.5.0

**현재 문제**
- rule_type_code=NULL 52개 → 분류 필요 (진단 사용 불가)
- PENDING 262개 condition_code 미설정 → 우선순위대로 입력 필요
- inspection_sets 미생성 50건 → 자동 생성 필요

---

## 📋 지금부터 할 작업 (우선순위순)

### 1️⃣ 🚨 rule_type_code=NULL 52개 분류 (최우선)
```sql
SELECT rule_id, law_name, obligation_type, obligation_summary, sector
FROM master_building_legal_rules
WHERE rule_type_code IS NULL AND is_active = true
ORDER BY law_name;
```
- obligation_type 기준으로 rule_type_code 매핑:
  - APPOINT → '001'
  - INSPECT → '002'
  - NOTIFY  → '003'
  - REPORT  → '004'
  - ACTION  → '005'

### 2️⃣ condition_code 일괄 입력 (법령별)
**우선순위:**
1. 고압가스 안전관리법 42건 → `gas_capacity_kg`
2. 시설물 안전법 31건 → `building_area`
3. 도시가스사업법 28건 → `gas_capacity_m3`
4. 전기안전관리법 8건 → `electric_capacity`
5. 에너지이용 합리화법 9건 → `annual_energy_toe`

```sql
-- 예시: 고압가스 일괄 입력
UPDATE law_rule_drafts
SET condition_code = 'gas_capacity_kg'
WHERE law_name LIKE '%고압가스%'
  AND condition_code IS NULL
  AND status = 'PENDING';
```

### 3️⃣ inspection_sets 자동 생성
- 승강기 안전관리법 INSPECT 12건 우선 (주기·조건 모두 있음)
- `POST /inspection-schedule/generate-from-rules` 활용

### 4️⃣ PENDING 262개 검토
- `GET /law-rule-generator/drafts?status=PENDING&has_condition=false`
- 법령별로 묶어서 일괄 승인/거부

---

## 🗄️ 주요 현황 쿼리

```sql
-- 1. rule_type_code NULL 현황
SELECT COUNT(*) FROM master_building_legal_rules
WHERE rule_type_code IS NULL AND is_active = true;
-- 예상: 52

-- 2. BUILDING 섹터 완성도
SELECT rule_type_code, COUNT(*) AS total,
  COUNT(CASE WHEN condition_code IS NOT NULL THEN 1 END) AS has_cond
FROM master_building_legal_rules
WHERE is_active = true AND sector = 'BUILDING'
GROUP BY rule_type_code;

-- 3. inspection_sets 미생성 INSPECT 룰
SELECT COUNT(*) FROM master_building_legal_rules r
LEFT JOIN inspection_sets s ON s.legal_rule_id = r.rule_id
WHERE r.rule_type_code = '002' AND r.is_active = true AND s.id IS NULL;
-- 예상: 50+
```

---

## 📌 중요 주의사항

1. **API 사이즈 제한**: `size <= 100` (pagination 필수)
2. **라우트 순서**: 구체적 경로(/bulk, /stats)를 /{id} 앞에 선언
3. **SHA 필수**: create_or_update_file 시 현재 SHA 먼저 조회
4. **공지예외주장 제출 기한: 2026-04-28** (patent.go.kr)

---

## 🔐 현재 DB/API 상태

- **Supabase**: xntdkrjhgcscmqctdzyo
- **Railway API**: https://api.taieng.co.kr/ (v5.6.0)
- **Admin**: hetto@kakao.com (role 001)
