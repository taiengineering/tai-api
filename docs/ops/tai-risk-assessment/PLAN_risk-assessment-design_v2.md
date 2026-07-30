---
goal: G-ms5zwv4v-b88c4a
class: plans
type: PLAN
scope: ops
project: tai-risk-assessment
title: 위험성평가 모듈 설계 확정본 — 데이터모델·상태기계·판정로직
version: 2
status: active
owner: taiwang
---

# 위험성평가 모듈 설계 확정본 (v2)

산업안전보건법 제36조와 「사업장 위험성평가에 관한 지침」(고용노동부고시 제2024-76호)이
요구하는 위험성평가를 safe SaaS 안에서 실시·기록·보존하기 위한 설계다. 구현·배포·실화면
검증(2026-07-29~30)이 끝난 뒤 확정한 as-built 문서이며, 코드가 이 문서와 어긋나면 코드가
틀린 것이다.

관련 코드: `routers/risk_assessments.py`(v1.5.1), `routers/ra_items.py`(v1.1.0),
`routers/ra_settings.py`, `routers/holidays.py`, `services/ra_decision_svc.py`,
`services/ra_continuous_svc.py`(v1.1.0), `services/ra_policy_svc.py`,
`services/holiday_svc.py`. 프론트: tai-admin `vue3/src/pages/risk-assessment-*`,
`vue3/src/pages/holiday-calendar`.

## 1. 설계 원칙

첫째, 법이 사업주에게 위임한 판단(위험성 수준·판단기준·허용 가능한 수준, 고시 제9조제2항)은
코드에 박지 않고 데이터(`ra_scale`)로 둔다. 둘째, 법정 주기·기한·보존연수는
`ra_policy_param` 에서 읽는다 — 고시는 3년마다 재검토되므로(제28조) 상수로 두면 법 개정
때마다 같은 결함이 재발한다(v1.1.0의 "최초평가 1년" 결함이 그 사례). 셋째, 판정은 서버가
단일 소스다. 화면은 입력을 모아 보내고 결과만 표시한다 — 판정 로직이 화면과 서버 양쪽에
있으면 반드시 어긋나고, 어긋난 쪽이 증적으로 남는다. 넷째, 캘린더(작업일·휴무일)는 위험성
평가 전용이 아니라 공용 모듈(`holiday_svc`)로 두어, 점검 일정 등 다른 기능이 같은 판정을
재구현하지 않도록 한다.

## 2. 데이터모델

`risk_assessments` — 평가 1건. 유형(assessment_type: INITIAL·REGULAR·SPECIAL·CONTINUOUS),
평가일, 상태(status_code: DRAFT·COMPLETED), 척도 참조(scale_id), 수시평가 사유
(trigger_reason), 사전조사 안전보건정보(prep_json: machines·materials·work_standards·
accident_history), 참여 근로자(participants_json), 완료일(completed_at), 보존
(retention_years·retention_until). 시행규칙 제37조제1항의 기록 항목 중 사전조사 정보가
여기 실린다.

`ra_scale` — 척도. method(THREE_STEP·CHECKLIST·OPS·FREQ_SEV), levels_json(코드·표시명·
순서·판단기준 문장), acceptable_max(허용 가능한 최대 수준), acceptable_reason(그렇게 정한
근거), is_preset. 프리셋은 회사 소속이 없는 참고용 표본이며, 사업장이 복사해 자신의 척도로
확정해야 평가에 쓸 수 있다. 평가 생성 시 1회 선택하고 이후 고정한다 — 평가 도중 척도가
바뀌면 앞서 내린 판정의 근거가 사라진다.

`ra_item` — 유해·위험요인(시행규칙 제37조제1항제1호). hazard, work_process,
situation_result, exposed_count, legal_basis, current_controls, discovery_method,
raw_input_json(기법별 판정 입력 + 승급 플래그), 판정 결과(level·acceptable·
escalation_json). 판정 결과가 2호(위험성 결정의 내용)에 해당한다.

`ra_control` — 감소대책(제37조제1항제3호). hierarchy(0 법령 조치 / 1 제거·대체 / 2 공학적 /
3 관리적 / 4 개인용 보호구 — 고시 제12조제1항의 우선순위), content, owner, due_date,
done_at(실행 완료), is_interim(잠정 조치, 제12조제4항), budget_ref.

`ra_item_revision` — 판정 이력. item_id + seq(1부터, 1=최초 판정), level, acceptable,
raw_input_json, note. 요인 등록·수정·재판정 때마다 적재되어 반복 루프의 증적이 된다.

`ra_policy_param` — 법정 파라미터. INITIAL_DUE(최초평가 착수기한, 현행 1개월 — 고시
제15조제1항), PERIODIC_CYCLE(정기평가 주기, 현행 1년 — 제15조제3항), RETENTION(보존연수,
현행 3년 — 시행규칙 제37조제2항). 조회 실패 시 코드의 안전망 값을 쓰되 그 값은 정본이
아니다.

`org_holiday` — 조직 공용 휴무 캘린더. holiday_date, name, source(LEGAL·COMPANY),
company_id·factory_id(스코프). company_id IS NULL = 전국 공통(법정공휴일),
company_id 지정·factory_id NULL = 회사 전체 휴무, 둘 다 지정 = 시설 휴무. 법정공휴일은
연도별 시드(마이그레이션)로만 관리하고 화면에서 수정하지 않는다 — 임시·대체공휴일은 해마다
달라지므로 코드 상수로 두지 않는다(제1원칙과 동일한 이유). 이 테이블은 위험성평가 전용이
아니라 캘린더를 쓰는 모든 기능의 공용 원천이다.

## 3. 상태기계

평가는 두 상태만 갖는다: `DRAFT → COMPLETED`. 되돌림 전이는 없다 — 완료된 평가는 기록이며
보존만료일까지 읽기 전용이다. 화면도 완료 후 편집 버튼을 제거한다.

DRAFT → COMPLETED 전이는 완료 가드를 통과해야 한다(고시 제12조제3항). 가드 규칙:
acceptable=false 인 ra_item 이 하나라도 남아 있으면 409 로 거부한다. 예외로, 그 요인에
is_interim=true 인 대책이 실행되어 있으면 통과시키되 warnings 로 "항구적 대책 수립 의무가
남아 있음"을 알린다(제12조제4항). 전이 성공 시 completed_at 을 기록하고
retention_until = 완료일 + RETENTION년 을 산출·저장한다(기산점 = 완료한 날, 고시
제14조제2항).

요인 단위에는 판정 루프가 있다:

    등록(즉시 판정) → [acceptable? 종료 : 대책 등록 → 실행(done_at) → 재판정] 반복

재판정은 raw_input_json 과 잔여 exposed_count 를 다시 받아 decide 를 재실행하고
ra_item_revision 에 seq 를 올려 적재한다. 잔여 노출 인원을 다시 받는 이유: 등록 시점의
노출 인원이 매 재판정에 그대로 반영되면 대책을 실행해도 승급이 풀리지 않아 루프가 끝나지
않는다(v1.1.0 에서 정정).

## 4. 판정 로직 (ra_decision_svc.decide)

입력: ra_item(raw_input_json 포함) + ra_scale. 출력: level, acceptable, escalation[].

기법별 기본 수준 산출 — THREE_STEP: raw.level 을 그대로 수준으로. CHECKLIST: mark(O/X)를
최저/최고 수준으로 사상. OPS: is_sufficient 를 최저/최고 수준으로 사상. FREQ_SEV:
freq×sev 값을 matrix_json 구간에 사상.

승급 규칙(수준 상향) — 산출된 기본 수준에 다음을 적용한다.
LEGAL_NONCOMPLIANCE(법령 미준수): 허용 불가로 강제, 법령 조치 우선 안내.
SEVERE_EXPECTED(중대재해 명확히 예상): 최고 수준으로 상향.
INDUSTRY_PRECEDENT(동종업계 중대재해 연관): 한 단계 상향.
MANY_EXPOSED(다수 노출, exposed_count 기준): 한 단계 상향. 재판정 시 잔여 인원으로 재평가.
적용된 규칙은 escalation_json 에 남아 화면에 "수준 상향 사유"로 표시된다.

허용 판정 — 최종 수준의 order ≤ acceptable_max 의 order 이면 acceptable=true.
acceptable_max 는 사업장이 척도 확정 시 정한 값이며 코드 기본값이 없다.

실측 검증(2026-07-30): 입력 "하"+SEVERE_EXPECTED → 서버가 "상"으로 승급·사유 표시,
대책 실행·노출 0 재판정 → "하·허용 가능", 완료 가드 통과, retention_until 2029-07-29 산출.

## 5. 상시평가 판정 (ra_continuous_svc.judge_continuous)

고시 제15조제4항 — 다음 3요건을 모두 실시하면 그 달의 수시·정기평가를 실시한 것으로 본다.
판정은 별도 입력 없이 기존 운영 데이터를 실적으로 쓴다.

1호(월 1회 이상 발굴): 해당 월에 등록된 ra_item(회사/시설의 평가 소속) ≥ 1건.
2호(매주 1회 이상 논의·점검): work_schedules.completed_at(점검관리 완료 실적)을 월요일
시작 주 단위로 버킷팅해 경과한 각 주에 ≥ 1건. 진행 중인 주는 미성립으로 치지 않는다.
3호(매 작업일 TBM): tbm_meetings.work_date 가 경과한 작업일마다 존재. 작업일은 평일에서
공용 휴무 캘린더(org_holiday, holiday_svc)의 법정공휴일·사업장 휴무일을 뺀 날이다. 제외된
휴무일은 응답 excluded_holidays 로 화면에 근거로 표시된다. 오늘은 아직 끝나지 않은 날이므로
판정에서 제외한다. (교대제·주말 조업 캘린더는 아직 반영하지 않으며, 주말 실적이 있으면
집계에 자연히 잡히므로 불이익은 없다.)

API: `GET /risk-assessments/continuous-status?company_id&factory_id&month`. 응답은 요건별
성립 여부·실적 수치·결측일 목록과 종합 deemed 를 담고, 화면(평가 목록 상단 카드)은 이를
그대로 표시한다.

실측 검증(2026-07-30, 2026-07 대상): 평일 21일 중 제헌절(07-17, LEGAL)·전사 하계휴가
(07-28, COMPANY) 2일이 작업일에서 제외되어 workdays_elapsed=19, excluded_holidays 에 2건
표시. 휴무 캘린더 화면에서 법정공휴일 21건 조회 및 사업장 휴무 등록·삭제 확인.

## 6. 공용 휴무 캘린더 (holiday_svc / routers.holidays)

`holiday_svc` 는 캘린더를 쓰는 모든 기능의 공용 서비스다. `get_holidays`(스코프 병합 조회),
`holiday_map`(날짜→이름), `is_workday`/`workdays_between`(작업일 판정)을 제공한다.
조회 규칙: factory_id 미지정(회사 단위)이면 법정 + 회사의 모든 휴무(시설별 포함)를,
factory_id 지정(특정 시설 판정)이면 법정 + 회사 전체 + 그 시설 휴무만 돌려준다. 테이블
미적용 환경에서는 빈 결과로 폴백해 종전 동작(휴무 없음)과 같다.

소비자:
- 상시평가 3호 판정 — `ra_continuous_svc.judge_continuous(holidays=...)`.
- 점검 일정 다음 점검일 보정 — `inspection_sets_helpers.adjust_planned_for_holiday`.
  inspection_sets.holiday_process_type 이 BEFORE/AFTER 인 세트는 산출된 예정일이 휴무일이면
  직전/직후 작업일로 옮긴다. 미설정 세트는 보정하지 않는다(종전 동작 불변).

API: GET/POST/DELETE `/holidays`. 법정공휴일(source=LEGAL)은 등록·삭제할 수 없다.
새 기능에서 "평일이면 작업일" 같은 판정을 다시 구현하지 말고 이 모듈을 쓸 것.

## 7. API 매핑

평가 수명주기: POST /risk-assessments(생성, 유형·척도·사전조사·참여자) → POST
/ra/assessments/{id}/items(요인 등록·즉시 판정) → POST /ra/items/{id}/controls(대책) →
PATCH /ra/controls/{id}(실행 완료) → POST /ra/items/{id}/reevaluate(재판정) → GET
/ra/assessments/{id}/readiness(완료 가능 점검) → POST /risk-assessments/{id}/complete
(가드 + 보존만료 산출). 이력: GET /ra/items/{id}/revisions. 설정: /ra/scales CRUD
(ra_settings). 상시평가: GET /risk-assessments/continuous-status. 휴무 캘린더: /holidays
(holidays).

## 8. 범위 밖 (후속)

KOSHA 인정신청 대행, 화학물질 MSDS 전용 모듈, 건설업 전용 공종 라이브러리, 빈도강도법
프리셋 확충(척도 설정으로 이미 확장 가능), 사업장 교대제·주말 조업 캘린더(3호 판정 추가
정밀화), 공휴일 Open API 실시간 동기화(현재는 연도별 시드), 중대재해처벌법 시행령 제4조
3호 반기 증적 리포트 화면.
