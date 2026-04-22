# 📋 Cursor 작업지시 프롬프트

> 아래 내용을 **통째로 복사해서 Cursor의 채팅창에 붙여넣으세요.**

---

## 🚀 프롬프트 (전체 복사용)

```
안녕 Cursor. TAI 법령엔진의 reparse 파이프라인 sanitize 버그를 수정해줘.

## 컨텍스트
어제(2026-04-21 21:30 KST) 시작한 reparse job이 24건 에러로 크래시해서 10시간 좀비 상태로 방치됐어. 진단 결과:
- UUID 에러 22건: 이미 커밋 801728로 해결됨 (배포 타이밍 race였음)
- numeric 에러 3건: 현재 코드도 penalty_value를 numeric 변환 안 함 → 이번에 수정
- varchar 에러 1건: 이미 커버됨

전체 상세 스펙은 이 파일에 있어:
👉 `docs/WORK_ORDER_REPARSE_SANITIZE_FIX.md` (dev 브랜치, 방금 기획창에서 푸시함)

**이 파일을 먼저 읽고 시작해.**

## 작업 규칙
- DEV_RULES v2 준수: 테스트 먼저(STEP 0) → 구현 → 검증
- 수정 대상: `services/rule_gen_helpers.py`, `tests/test_rule_gen_helpers.py` 두 개만
- `services/rule_gen_reparse.py`는 건드리지 마 (이미 sanitize 호출하고 있음)
- services 레이어 규칙: `from fastapi` import 금지
- 파일 크기: rule_gen_helpers.py를 150줄 이내로 유지

## 작업 순서

### STEP 0: 테스트 먼저 (tests/test_rule_gen_helpers.py에 추가)
docs/WORK_ORDER_REPARSE_SANITIZE_FIX.md의 STEP 0 섹션에 있는 4개 테스트 함수를 그대로 파일 하단에 추가:
1. test_sanitize_master_patch_uuid_removal
2. test_sanitize_master_patch_numeric_coercion
3. test_sanitize_master_patch_varchar_truncate
4. test_sanitize_master_patch_preserves_valid_fields

이 시점에 `pytest tests/test_rule_gen_helpers.py -v` 돌리면 numeric 테스트는 실패해야 정상. 결과 보고해줘.

### STEP 1: sanitize_master_patch 확장 (services/rule_gen_helpers.py)
docs의 STEP 1 섹션에 명시된 대로:
1. `_NUMERIC_FIELDS` frozenset 추가 (condition_value 포함 5개 필드)
2. `_coerce_numeric(value)` 헬퍼 함수 추가
3. 기존 `sanitize_master_patch` 함수를 문서 버전으로 교체

### STEP 2: 검증
```
pytest tests/test_rule_gen_helpers.py -v       # 7개 전부 PASSED
pytest tests/ -v --tb=short                    # 기존 테스트 regression 없음
wc -l services/rule_gen_helpers.py              # 150줄 이내
grep -E "from fastapi|import fastapi" services/rule_gen_helpers.py  # 0
```

### STEP 3: 커밋 + 푸시
```bash
git add services/rule_gen_helpers.py tests/test_rule_gen_helpers.py
git commit -m "fix: sanitize_master_patch에 penalty_value 등 numeric 필드 확장

- _NUMERIC_FIELDS frozenset 도입 (penalty_value, appointment_count_value,
  inspection_cycle_value, equipment_condition_value)
- _coerce_numeric() 헬퍼 추가: 문자열에서 숫자 추출 fallback
  (\"과태료 500만원\" → 500, \"true\"/\"charging_business\" → None)
- test_rule_gen_helpers.py에 sanitize 테스트 4개 신설 (기존 0건)

관련: reparse job 8756176e의 numeric 타입 오류 3건 대응
(UUID 오류 22건은 커밋 801728의 배포 race로 이미 해결)

Made-with: Cursor"
git push origin dev
```

푸시 완료되면 dev PR 올리고 내(기획창)에게 보고해줘. PR 번호, 테스트 결과, 바뀐 줄 수 포함.

### STEP 4 (선택 - 이번엔 건너뛰어도 됨)
AUTO_PARSE_NEW cron 래퍼 엔드포인트. 별도 작업으로 분리 가능. 시간 여유되면 docs의 STEP 4 섹션 참고해서 진행, 아니면 그냥 완료 보고해.

---

## 기대 결과

완료 시 기획창에 이 형식으로 보고:
```
✅ 완료
- 수정 파일: services/rule_gen_helpers.py (XX줄 → YY줄), tests/test_rule_gen_helpers.py (+40줄)
- 테스트: 7/7 PASSED (기존 3 + 신규 4)
- 커밋: <SHA 7자리>
- PR: https://github.com/taiengineering/tai-api/pull/NN
```

시작해줘!
```

---

## 💡 사용 팁

1. **붙여넣기 전 확인**: Cursor가 현재 `tai-api` repo의 `dev` 브랜치를 보고 있는지 확인
2. **첫 응답 체크**: Cursor가 docs/WORK_ORDER_REPARSE_SANITIZE_FIX.md를 **먼저 읽는지** 확인 (안 읽으면 다시 지시)
3. **STEP 0 결과 보고**: numeric 테스트가 실패하는 게 정상. Cursor가 "실패했습니다" 하면 "정상입니다, STEP 1 진행하세요"라고 답
4. **중간 확인**: STEP 1 후 diff를 먼저 보여달라고 하면 안전 (바로 커밋 X)

---

## 🔁 Fallback: Cursor가 막힌다면

다음 질문이 Cursor에서 나올 수 있음:

**Q: "_is_valid_uuid, _VARCHAR_30_FIELDS, Optional, Any가 이미 import되어 있나요?"**
A: "네. 기존 rule_gen_helpers.py에 이미 있어요. 파일 상단 import만 건드리지 말고 함수만 추가/교체하세요."

**Q: "re 모듈을 import 해야 하나요?"**
A: "`import re`는 파일 최상단에 이미 있습니다 (_UUID_RE 때문에). 추가 import 불필요."

**Q: "테스트가 전부 pass해버리는데요?"**
A: "그럼 sanitize가 이미 부분적으로 작동하는 거예요. 그래도 _NUMERIC_FIELDS 확장이 필요하니 STEP 1 그대로 진행. 최종 commit에 '기존 UUID 로직은 유지, numeric 확장만 추가'라고 명시해요."

**Q: "Supabase 연결 없이 테스트 돌아가나요?"**
A: "네. sanitize_master_patch는 순수 함수라 DB 접근 없어요. unit test 단독 실행 OK."

---

## 📎 참고 리소스

- **전체 스펙**: `docs/WORK_ORDER_REPARSE_SANITIZE_FIX.md` (dev 브랜치)
- **현재 helpers 파일**: https://github.com/taiengineering/tai-api/blob/dev/services/rule_gen_helpers.py
- **현재 테스트 파일**: https://github.com/taiengineering/tai-api/blob/dev/tests/test_rule_gen_helpers.py
- **실패 job**: `reparse_job_log.job_id = '8756176e-e938-4a87-a47a-f33404d1411a'` (FAILED 처리됨)
- **관련 커밋**: `801728` (sanitize 초기 fix), `e81af3c` (rule_gen_reparse 분리)

---

## ⚙️ 작업 검증 (기획창에서 PR 올라오면 실행)

```bash
# 1) PR 체크아웃해서 로컬 확인
gh pr checkout <PR번호>
pytest tests/test_rule_gen_helpers.py -v

# 2) 코드 diff 확인
git diff main -- services/rule_gen_helpers.py tests/test_rule_gen_helpers.py
```

머지 승인 기준:
- [ ] 테스트 7개 PASSED
- [ ] rule_gen_helpers.py 150줄 이내
- [ ] `from fastapi` import 없음
- [ ] 커밋 메시지 규약 준수 (fix: prefix, 3줄 body)
- [ ] PR description에 "관련 이슈: reparse job 8756176e" 언급

머지 후: Railway 배포 5분 대기 → reparse job 새로 시작 → 에러 0 확인

---

**다음 세션에서**: worker 결과 (몇 시간 파싱됐는지) + Cursor PR 결과 함께 보고 주시면 master 룰 품질 관점에서 다음 작업 우선순위 정리해 드립니다.
