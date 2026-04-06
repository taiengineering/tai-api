# 작업지시서 — 2026-04-06 SPECIAL_FACILITY 전면 제외 & 이벤트 수정

## 완료된 작업 (Claude MCP 직접 처리)

### 1. engine_qa.py v1.2.0
- 전체 커버 시 100점, DB이슈 감점 (HIGH -5점, MEDIUM -2점)
- SPECIAL_FACILITY 테스트케이스 제거
- 3개 섹터(BUILDING·MANUFACTURING·CONSTRUCTION) × 정방향/역방향

### 2. legal_engine.py v5.5.2 (현재 v5.6.3에 포함)
- _classify_rules_db에 appointment_target_code 기준 dedup 추가
- energy_manager(4→1), fire_safety_manager(3→1) 중복 제거

### 3. SPECIAL_FACILITY 전면 제외
- 이유: 병원·연구실 등 용도별로 법령이 완전히 다름
- master_building_legal_rules SPECIAL_FACILITY 49개 비활성화 (Supabase 직접)
- law_rule_drafts 전체 삭제 827개 리셋 (Supabase 직접)
- law_rule_generator.py v1.1.0: SYSTEM_PROMPT, USER_PROMPT, parse/batch/drafts/approve 전구간 차단

### 4. 현재 활성 SEC_KR
BUILDING · MANUFACTURING · CONSTRUCTION · COMMON · CONSTRUCTION_MANUFACTURING (5개)

---

## 커서 작업지시 — 이벤트 관리 수정 모달 시작날짜 필수 해제

### 대상 파일
이벤트 관리 페이지 HTML (파일명 검색: `event`, `이벤트`, `start_date required`)

### 수정 내용

**수정 모달 내 시작날짜 input에서 `required` 제거:**

```html
<!-- 변경 전 -->
<input type="date" id="editStartDate" ... required>

<!-- 변경 후 -->
<input type="date" id="editStartDate" ...>
```

**라벨에 필수 표시(*)가 있으면 제거:**
```html
<!-- 변경 전 -->
<label for="editStartDate">시작 날짜 <span class="text-danger">*</span></label>

<!-- 변경 후 -->
<label for="editStartDate">시작 날짜</label>
```

**JS 유효성 검사에서 start_date 필수 체크가 있으면 제거:**
```javascript
// 삭제 대상 (이런 패턴이 있으면)
if (!startDate || startDate === '') {
    alert('시작 날짜를 입력하세요');
    return;
}
```

### 커밋 메시지
`fix: 이벤트 수정 모달 시작날짜 필수 → 선택으로 변경`

### 배경
이벤트는 시작날짜를 지정하지 않고 진행될 수 있음 (상시 이벤트 등)

---

## 다음 세션 우선 작업
1. 전체 법령 파싱 재실행 (SPECIAL_FACILITY 제외 상태로)
2. 파싱 완료 후 QA 실행 확인
3. Haiku condition_code 재추출 (50개 파일럿) — docs/HAIKU_CONDITION_EXTRACT_TASK.md 참조
