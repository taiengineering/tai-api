# TAI Safe Backend (tai-api) - Session Memory
**마지막 업데이트: 2026-04-06 (3차 세션)**

**제품·아키텍처 공유**: [`docs/TAI_전체_작업_정리_공유용.md`](./TAI_전체_작업_정리_공유용.md)

---

## ✅ 이번 세션 완료 작업 (2026-04-06 3차)

### 법령엔진 무결성 CI 파이프라인 완성 (핵심 성과)
- ✅ GitHub Actions 3-Job 파이프라인 완성 및 **78건 ALL PASS 확정**
  - Job1: DB 무결성 검증 (Supabase REST, 약 3초)
  - Job2: 정적 매핑 커버리지 검증 (condition_code ↔ 엔진 context key)
  - Job3: API 무결성 78건 (26건 + 52건, Railway 배포 완료 대기 포함)
- ✅ GitHub Secrets 등록: SUPABASE_URL, SUPABASE_SERVICE_KEY, API_URL
- ✅ `main.py` → `routers/legal_engine.py` → `tests/*.py` 수정 시 자동 실행

### DB 제약조건 5개 추가 (Supabase 실제 적용)
```sql
chk_appoint_requires_target     -- APPOINT는 target_code 필수
chk_target_code_format          -- target_code 영문 소문자+언더스코어만 허용
chk_inspect_requires_executor   -- INSPECT는 executor_type_code 필수
chk_sector_allowed_values       -- sector 8가지 허용값 제한
chk_obligation_type_allowed_values -- obligation_type 7가지 허용값 제한
```

### DB 데이터 수정
- ✅ APPOINT target 없는 6건 비활성화 (MECHFAC-001-MFG 등)
- ✅ `height_work` → `has_high_work` condition_code 정규화 (OSHSRULE-333-006-CST)

### 엔진 v5.6.4 배포 완료
- ✅ `has_high_work` (고소작업 2m이상) context 추가
- ✅ `main.py` v5.6.4 업데이트
- ✅ Railway v5.6.4 배포 완료, API 정상 응답 확인

### 테스트 스크립트 수정
- ✅ `test_legal_engine.py` v2.1: `has_appt()` 영문코드/한글레이블 둘 다 비교
- ✅ `test_legal_engine_52.py` v1.1: 동일 수정
- ✅ `check_mapping_coverage.py`: `has_high_work` ENGINE_CONTEXT_KEYS 추가

### 파일 목록 (새로 생성)
- `.github/workflows/integrity.yml` — 3-Job CI 파이프라인
- `tests/check_db_integrity.py` — DB 무결성 8항목 검증
- `tests/check_mapping_coverage.py` — condition_code↔context key 매핑 검증
- `tests/wait_for_deploy.py` — Railway 배포 완료 폴링

---

## 🔑 CI 파이프라인 구조

```
routers/legal_engine.py 또는 main.py 수정 → GitHub push
    ↓
Job1: DB 무결성 검증 (~3초)
    - 활성 룰 1000건 이상
    - APPOINT 전부 target_code 있음
    - 한글 target_code 0건
    - INSPECT 전부 executor_type_code 있음
    - BUILDING INSPECT 4완비율 80% 이상
    ↓ 통과
Job2: 정적 매핑 커버리지 (~2초)
    - DB condition_code ↔ 엔진 ENGINE_CONTEXT_KEYS 불일치 탐지
    ↓ 통과
Job3: API 무결성 78건 (~90초)
    - Railway 배포 완료 대기 (버전 폴링)
    - 기준 26건 (정방향11+역방향11+비교2+격리2)
    - 추가 52건 (복합·극단값)
    ↓ 통과
Railway 자동 배포 ("Wait for CI" 활성화 시)
```

---

## 📋 현재 상태

| 항목 | 상태 |
|------|------|
| Railway API | v5.6.4 운영 중 ✅ |
| GitHub 최신 | v5.6.4 ✅ |
| CI 파이프라인 | 78건 ALL PASS ✅ |
| DB 제약조건 | 5개 적용 완료 ✅ |
| Railway Wait for CI | 미활성 (수동 설정 필요) |

---

## 📋 다음 작업 (우선순위순)

1. **Railway "Wait for CI" 활성화** — Service → Settings → GitHub → Wait for CI
2. **법령엔진 고도화** — 다음 세션의 주 목적
   - BUILDING INSPECT 4완비율 85% → 95% 목표 (조건 없는 18건 처리)
   - MANUFACTURING INSPECT condition 완비율 72% → 85% 목표
   - 건설 BEFORE_WORK 64건 스케줄 설계
   - PENDING 263개 검토
3. **점검 → 일정 자동생성 연계** 검증
4. **공지예외주장 기한: 2026-04-28**

---

## 🔐 인증 / 계정
- **Admin**: hetto@kakao.com (role 001)
- **Supabase**: xntdkrjhgcscmqctdzyo
- **Railway API**: https://api.taieng.co.kr/ (v5.6.4)

## 📌 주의사항
1. **API 사이즈 제한**: `size <= 100` (pagination 필수)
2. **라우트 순서**: 구체적 경로(/bulk, /stats)를 /{id} 앞에 선언
3. **SHA 필수**: create_or_update_file 시 현재 SHA 먼저 조회
4. **무결성 원칙**: 법령/엔진 변경 후 CI 통과 확인 필수
5. **가스 조건값 수정 금지**: 법적 기준값 (100/300/1000 kg)
6. **has_appt() 비교**: 영문코드와 한글레이블 둘 다 비교해야 함
7. **공지예외주장 기한: 2026-04-28** (patent.go.kr)
