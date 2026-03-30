# 룰 없는 법령 13개 판정룰 추가 작업
## 담당: Claude Code
## Supabase MCP 활용

---

## 작업 배경

아래 법령들은 수집된 조문은 있지만 판정룰이 전혀 없음.
판정룰 (master_building_legal_rules) INSERT 필요.

---

## 그룹 A: 건설 핵심 법령 (CONSTRUCTION)

대상: 건설기술 진흥법 시행령(165조) / 시행규칙(82조) / 건설산업기본법 시행규칙(72조)

아래 SQL로 Supabase MCP execute_sql 실행:

```sql
-- 건설기술 진흥법 시행령 핵심룸 3개
INSERT INTO master_building_legal_rules
  (rule_id, law_name, law_article, obligation_type, sector,
   obligation_summary, penalty_summary, is_active, created_at)
VALUES
  ('CONST-TECH-001', '건설기술 진흥법 시행령', '제98조',
   'ACTION', 'CONSTRUCTION',
   '건설안전관리계획 수립 의무 (건설기술 진흥법 시행령 제98조)',
   '1엵원 이하 과태료', true, now()),
  ('CONST-TECH-002', '건설기술 진흥법 시행령', '제98조의바321',
   'APPOINT', 'CONSTRUCTION',
   '건설안전관리자 선임 의무 (건설기술 진흥법 시행령 제98조의바3)',
   '1엵원 이하 과태료', true, now()),
  ('CONST-TECH-003', '건설기술 진흥법 시행령', '제101조',
   'INSPECT', 'CONSTRUCTION',
   '건설안전점검 실시 의무 (건설기술 진흥법 시행령 제101조)',
   '500만원 이하 과태료', true, now()),
  ('CONST-TECH-004', '건설기술 진흥법 시행령', '제101조의바2',
   'REPORT', 'CONSTRUCTION',
   '건설안전점검 결과 보고 의무 (건설기술 진흥법 시행령 제101조의바2)',
   '500만원 이하 과태료', true, now()),
  ('CONST-TECH-005', '건설기술 진흥법 시행령', '제60조',
   'ACTION', 'CONSTRUCTION',
   '건설현장 품질관리 의무 (건설기술 진흥법 시행령 제60조)',
   '1엵원 이하 과태료', true, now())
ON CONFLICT DO NOTHING;

-- 건설기술 진흥법 시행규칙 핵심룸 3개
INSERT INTO master_building_legal_rules
  (rule_id, law_name, law_article, obligation_type, sector,
   obligation_summary, penalty_summary, is_active, created_at)
VALUES
  ('CONST-TECHR-001', '건설기술 진흥법 시행규칙', '제58조',
   'REPORT', 'CONSTRUCTION',
   '건설안전점검 결과 제없 신고 의무 (건설기술 진흥법 시행규칙 제58조)',
   '300만원 이하 과태료', true, now()),
  ('CONST-TECHR-002', '건설기술 진흥법 시행규칙', '제59조',
   'ACTION', 'CONSTRUCTION',
   '안전관리계획 수립확인 의무 (건설기술 진흥법 시행규칙 제59조)',
   '300만원 이하 과태료', true, now()),
  ('CONST-TECHR-003', '건설기술 진흥법 시행규칙', '제60조',
   'INSPECT', 'CONSTRUCTION',
   '건설현장 안전해송 검사 의무 (건설기술 진흥법 시행규칙 제60조)',
   '300만원 이하 과태료', true, now())
ON CONFLICT DO NOTHING;

-- 건설산업기본법 시행규칙 핵심룸 3개
INSERT INTO master_building_legal_rules
  (rule_id, law_name, law_article, obligation_type, sector,
   obligation_summary, penalty_summary, is_active, created_at)
VALUES
  ('CONST-IND-001', '건설산업기본법 시행규칙', '제13조',
   'APPOINT', 'CONSTRUCTION',
   '건설업 등록 의무 (건설산업기본법 시행규칙 제13조)',
   '500만원 이하 과태료', true, now()),
  ('CONST-IND-002', '건설산업기본법 시행규칙', '제28조',
   'REPORT', 'CONSTRUCTION',
   '하자 기술인 신고 의무 (건설산업기본법 시행규칙 제28조)',
   '300만원 이하 과태료', true, now()),
  ('CONST-IND-003', '건설산업기본법 시행규칙', '제41조',
   'ACTION', 'CONSTRUCTION',
   '건설업 시공능력 유지 의무 (건설산업기본법 시행규칙 제41조)',
   '300만원 이하 과태료', true, now())
ON CONFLICT DO NOTHING;
```

---

## 그룹 B: SPECIAL_FACILITY 법령 10개

대상 섹터: SPECIAL_FACILITY

```sql
-- 의료법 시행규칙
INSERT INTO master_building_legal_rules
  (rule_id, law_name, law_article, obligation_type, sector,
   obligation_summary, penalty_summary, is_active, created_at)
VALUES
  ('SPEC-MED-001', '의료법 시행규칙', '제34조',
   'APPOINT', 'SPECIAL_FACILITY',
   '의료기관 안전관리자 선임 의무 (의료법 시행규칙 제34조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-MED-002', '의료법 시행규칙', '제35조',
   'INSPECT', 'SPECIAL_FACILITY',
   '의료기관 안전점검 실시 의무 (의료법 시행규칙 제35조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-MED-003', '의료법 시행규칙', '제38조',
   'REPORT', 'SPECIAL_FACILITY',
   '의료기관 개설 신고 의무 (의료법 시행규칙 제38조)',
   '300만원 이하 과태료', true, now()),
-- 노인복지법 시행규칙
  ('SPEC-ELDER-001', '노인복지법 시행규칙', '제4조',
   'APPOINT', 'SPECIAL_FACILITY',
   '노인복지시설 안전관리자 선임 의무 (노인복지법 시행규칙 제4조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-ELDER-002', '노인복지법 시행규칙', '제22조',
   'INSPECT', 'SPECIAL_FACILITY',
   '노인복지시설 안전점검 의무 (노인복지법 시행규칙 제22조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-ELDER-003', '노인복지법 시행규칙', '제28조',
   'ACTION', 'SPECIAL_FACILITY',
   '노인복지시설 화재안전 조치 의무 (노인복지법 시행규칙 제28조)',
   '300만원 이하 과태료', true, now()),
-- 사회복지사업법 시행규칙
  ('SPEC-SOC-001', '사회복지사업법 시행규칙', '제5조',
   'APPOINT', 'SPECIAL_FACILITY',
   '사회복지시설 안전관리자 선임 의무 (사회복지사업법 시행규칙 제5조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-SOC-002', '사회복지사업법 시행규칙', '제34조',
   'INSPECT', 'SPECIAL_FACILITY',
   '사회복지시설 안전점검 의무 (사회복지사업법 시행규칙 제34조)',
   '300만원 이하 과태료', true, now()),
-- 다중이용업소법 시행령
  ('SPEC-MULTI-001', '다중이용업소의 안전관리에 관한 특별법 시행령', '제13조',
   'INSPECT', 'SPECIAL_FACILITY',
   '다중이용업소 안전점검 실시 의무 (다중이용업소법 시행령 제13조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-MULTI-002', '다중이용업소의 안전관리에 관한 특별법 시행규칙', '제9조',
   'ACTION', 'SPECIAL_FACILITY',
   '다중이용업소 안전시설 설치 의무 (다중이용업소법 시행규칙 제9조)',
   '300만원 이하 과태료', true, now()),
-- 어린이놀이시설 안전관리법 시행령
  ('SPEC-PLAY-001', '어린이놀이시설 안전관리법 시행령', '제11조',
   'INSPECT', 'SPECIAL_FACILITY',
   '어린이놀이시설 안전점검 의무 (어린이놀이시설법 시행령 제11조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-PLAY-002', '어린이놀이시설 안전관리법 시행령', '제12조',
   'REPORT', 'SPECIAL_FACILITY',
   '어린이놀이시설 파손 신고 의무 (어린이놀이시설법 시행령 제12조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-PLAY-003', '어린이놀이시설 안전관리법 시행규칙', '제15조',
   'ACTION', 'SPECIAL_FACILITY',
   '어린이놀이시설 안전조치 의무 (어린이놀이시설법 시행규칙 제15조)',
   '300만원 이하 과태료', true, now()),
-- 학교안전법 시행령
  ('SPEC-SCH-001', '학교안전사고 예방 및 보상에 관한 법률 시행령', '제13조',
   'INSPECT', 'SPECIAL_FACILITY',
   '학교 안전점검 실시 의무 (학교안전법 시행령 제13조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-SCH-002', '학교안전사고 예방 및 보상에 관한 법률 시행령', '제14조',
   'APPOINT', 'SPECIAL_FACILITY',
   '학교 안전관리자 선임 의무 (학교안전법 시행령 제14조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-SCH-003', '학교안전사고 예방 및 보상에 관한 법률 시행규칙', '제9조',
   'ACTION', 'SPECIAL_FACILITY',
   '학교안전계획 수립 의무 (학교안전법 시행규칙 제9조)',
   '300만원 이하 과태료', true, now()),
-- 공공보건의료법
  ('SPEC-PUB-001', '공공보건의료에 관한 법률', '제7조',
   'APPOINT', 'SPECIAL_FACILITY',
   '공공보건의료기관 안전관리자 선임 의무 (공공보건의료법 제7조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-PUB-002', '공공보건의료에 관한 법률', '제14조',
   'INSPECT', 'SPECIAL_FACILITY',
   '공공보건의료기관 안전점검 의무 (공공보건의료법 제14조)',
   '300만원 이하 과태료', true, now()),
  ('SPEC-PUB-003', '공공보건의료에 관한 법률', '제15조',
   'ACTION', 'SPECIAL_FACILITY',
   '공공보건의료기관 시설 안전조치 의무 (공공보건의료법 제15조)',
   '300만원 이하 과태료', true, now())
ON CONFLICT DO NOTHING;
```

---

## 콘플릭트 없으면 law_category_code는 NULL 허용 확인

만약 NOT NULL 에러나면 맨 스킬링 빈값(\'\') 대신 삽입:
```sql
law_category_code = ''
```

---

## 완료 후 검증

```sql
SELECT law_name, sector, COUNT(*) as 룰수
FROM master_building_legal_rules
WHERE is_active=true
  AND law_name IN (
    '건설기술 진흥법 시행령','건설기술 진흥법 시행규칙',
    '건설산업기본법 시행규칙','의료법 시행규칙',
    '노인복지법 시행규칙','사회복지사업법 시행규칙',
    '다중이용업소의 안전관리에 관한 특별법 시행령',
    '다중이용업소의 안전관리에 관한 특별법 시행규칙',
    '어린이놀이시설 안전관리법 시행령',
    '어린이놀이시설 안전관리법 시행규칙',
    '학교안전사고 예방 및 보상에 관한 법률 시행령',
    '학교안전사고 예방 및 보상에 관한 법률 시행규칙',
    '공공보건의료에 관한 법률'
  )
GROUP BY law_name, sector ORDER BY law_name;

-- 전체 섹터 룰 현황
SELECT sector, COUNT(*) as 룰수
FROM master_building_legal_rules WHERE is_active=true
GROUP BY sector ORDER BY 룰수 DESC;
```

목표:
- [ ] CONSTRUCTION 룰수 110개 이상
- [ ] SPECIAL_FACILITY 룰수 45개 이상
- [ ] 룰 없는 법령 0개

완료 후 회의실 창에 결과 보고.
