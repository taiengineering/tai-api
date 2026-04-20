# 세션 핸드오프 — 2026-04-20 세션4 마무리

> 작성: 기획창 (Claude)
> 일시: 2026-04-20 21:00 KST

---

## 오늘 완료된 작업

### 1. 법령엔진 수집엔진 보강 (이슈 #24)
- `services/law_context_builder.py` 신규 — 법령 원문 풀세트 조립
- `routers/law_rule_generator.py` 보강 (34KB→46KB+)
  - 시스템 프롬프트 24개 condition_code + 30개+ 출력 필드
  - POST /validate-master 신규 (무결성 검증)
  - POST /reparse-master → BackgroundTasks 전환 (서버 다운 방지)
  - GET /reparse-master/status/{job_id} 신규
  - GET /reparse-master/jobs 신규
- `reparse_job_log` DDL 생성 완료
- tai_feature_code ALTER TABLE + 자동 매핑 92.1%
- PR #25 머지, law_context_builder 버그 수정 (main 직접 push)
- reparse-master BackgroundTasks 코드 main push 완료

### 2. 법령엔진 크론 설정
- RULE_REPARSE: 활성화 + 엔드포인트 변경 (매주 수 04:00)
- VALIDATE_MASTER: 신규 등록 (매주 금 06:00)
- AUTO_PARSE_NEW: 신규 등록 (비활성, 래퍼 엔드포인트 필요)
- OVERDUE_DISPATCH, OVERDUE_PREPARE: 비활성화 (404 반환 — 엔드포인트 미구현)

### 3. reparse-master 전체 실행 중
- job_id: a31fbf20-62fb-4d76-b091-480908ed1435
- 진행: 540/1,000 (54%) — RUNNING
- 업데이트: 308건 성공
- 에러: 218건 (확인 필요)
- 주요 보강 필드: penalty_summary 288, cycle_base_guide 152, form_name 142, online_system 130, appointment_qualification_code 78

### 4. DB 정리
- process_equipment_map: 1,188,161건 → 187,319건 (MUST+CORE만 남김)
- OPTIONAL+REFERENCE 100만건 삭제 + 아카이브 테이블 DROP
- 예상 공간 절약: ~580MB

### 5. 점검항목 세팅 기획
- 조합형만 (템플릿은 프리필 데이터로 활용)
- L1: 빈 화면, L2+: 추천 항목 프리필
- inspection-anchor.html에 병합 (별도 페이지 만들지 않음)
- 작업지시서 v2 push 완료: docs/inspection-checklist-setup-workorder.md

### 6. 가격표 업데이트
- PRICING_FINAL.md v2.1
- 연결 수수료 가안 추가 (선임연결: 정액/정률 혼합, 수선연결: 구간별 차등)
- 설치비(세팅 대행) 확정 추가: 기본 20만 + 설비당 2~3만

---

## 현재 상태

| 항목 | 상태 |
|---|---|
| 서버 | ✅ healthy |
| reparse | 🔄 540/1000 RUNNING (내일 아침 완료 예상) |
| 활성 크론 | 12개 |
| DB process_equipment_map | ✅ 187,319건으로 정리 |
| SaaS 수용 가능 | 30~50곳 (현재 구조) |

---

## 내일 아침 확인사항

1. reparse 완료 확인
```bash
curl -s "https://api.taieng.co.kr/law-rule-generator/reparse-master/status/a31fbf20-62fb-4d76-b091-480908ed1435" | python3 -m json.tool
```

2. 에러 218건 원인 확인 — error_details 조회
```sql
SELECT error_details FROM reparse_job_log WHERE job_id = 'a31fbf20-62fb-4d76-b091-480908ed1435';
```

3. After 6하원칙 채움률 확인
```sql
SELECT COUNT(*) as total,
  COUNT(NULLIF(penalty_summary,'')) as why,
  COUNT(appointment_qualification_code) as who,
  COUNT(CASE WHEN due_days > 0 THEN 1 END) as when_days,
  COUNT(submit_org_code) as where_to,
  COUNT(form_name) as how_form,
  COUNT(report_method_code) as how_method,
  COUNT(tai_feature_code) as tai
FROM master_building_legal_rules WHERE is_active = true;
```

---

## PENDING 작업 (우선순위)

### 즉시 (이번 주)
- [ ] reparse 에러 218건 원인 분석 → 재처리 또는 수동 보정
- [ ] Before vs After 6하원칙 비교 보고
- [ ] 프론트 첫 장 검수 시작 (법령진단 입력 → 순서대로)

### 백엔드 (다음 주)
- [ ] 점검항목 세팅 API (prefill + setup) — routers/inspection_setup.py
- [ ] inspection_master DDL 보강 + GPT 데이터 보강
- [ ] AUTO_PARSE_NEW 래퍼 엔드포인트
- [ ] 법령엔진→일정생성→담당자배정→알림 파이프라인 연결

### 프론트 (5월)
- [ ] 프론트 페이지 한 장씩 검수 (고객 흐름 순)
- [ ] inspection-anchor.html 점검항목 탭 병합
- [ ] nexas 홈페이지 최소 MVP

### 기타
- [ ] dev/main 히스토리 diverge → rebase 정리
- [ ] KG이니시스 PG 승인 확인
- [ ] 혁신장터(ppi.go.kr) 등록 준비
