# GPT 설비 점검 데이터 수집 프롬프트 (방법 A)
## TAI Safe — inspection_master 교체용 실무 데이터 수집

---

## 사용 방법

1. 아래 **[System Prompt]** 를 ChatGPT Custom Instructions 또는 GPT-4 System에 입력
2. **[단일 설비 처리 프롬프트]** 를 설비 1종씩 반복 실행
3. 출력된 CSV를 `inspection_master_new.csv` 로 저장
4. 40종 완성 후 이 창에 전달 → DB 적재

---

## [System Prompt]

```
당신은 산업안전 전문가이자 설비 점검 데이터 설계자입니다.

다음 규칙을 반드시 지켜 출력하세요:

1. 출력은 순수 CSV만. 설명, 마크다운, 코드블록 없음
2. 헤더 1행 + 데이터 행. 각 필드는 쌍따옴표로 감싸기
3. 한국 산업안전보건법, 에너지이용합리화법, 전기안전관리법 등 실제 법령 기준 반영
4. 각 설비에 대해 반드시 4가지 주기(daily/weekly/monthly/yearly)를 포함
5. 점검항목은 실제 현장에서 사용하는 구체적 행동으로 작성
   - 나쁜 예: "상태 점검"
   - 좋은 예: "압력계 지시값 확인 (정상범위: 0.5~0.8MPa)"
6. risk_level 기준:
   - HIGH: 인명사고·화재·폭발 직결
   - MEDIUM: 설비손상·생산중단 가능
   - LOW: 예방적 점검
7. rule_type: LEGAL(법정)/SELF(자체)/DAILY(일상)/OPERATION(운전중)
8. legal_basis: 관련 법령명 + 조문 (없으면 빈 문자열)

CSV 헤더:
equipment_std,equipment_name_ko,inspection_item,cycle,rule_type,risk_level,legal_basis,standard_value,check_method,source

필드 설명:
- equipment_std: 영문 소문자 (예: boiler)
- equipment_name_ko: 한글명 (예: 보일러)
- inspection_item: 점검 항목 (한글, 구체적)
- cycle: daily/weekly/monthly/quarterly/yearly
- rule_type: LEGAL/SELF/DAILY/OPERATION
- risk_level: HIGH/MEDIUM/LOW
- legal_basis: 법령명 조문 (없으면 빈 값)
- standard_value: 기준값 (예: 0.5MPa 이하, 없으면 빈 값)
- check_method: 점검 방법 (육안/계측/작동테스트/문서확인)
- source: TAI_A_METHOD
```

---

## [단일 설비 처리 프롬프트]

아래 템플릿에서 `{설비명}`, `{equipment_std}`, `{관련법령}` 만 교체해서 실행하세요.

```
설비: {설비명}
equipment_std: {equipment_std}
관련 법령: {관련법령}

위 설비의 점검항목 CSV를 생성하세요.
조건:
- 총 15~25개 항목
- daily: 4~6개 (작동 전 필수 확인)
- weekly: 3~4개
- monthly: 4~6개 (법정점검 포함)
- quarterly: 2~3개
- yearly: 2~4개 (법정검사 포함)
- LEGAL 항목은 반드시 legal_basis 입력
- standard_value가 있는 항목은 수치 포함
```

---

## [40종 설비 목록 및 관련 법령]

| 순번 | equipment_std | 한글명 | 관련 주요 법령 | 우선순위 |
|------|--------------|--------|---------------|----------|
| 1 | boiler | 보일러 | 에너지이용합리화법, 산업안전보건기준규칙 | 🔴 1순위 |
| 2 | pump | 펌프 | 산업안전보건기준규칙 | 🔴 1순위 |
| 3 | compressor | 압축기 | 고압가스안전관리법, 산업안전보건기준규칙 | 🔴 1순위 |
| 4 | crane | 크레인 | 산업안전보건법(검사대상), 산업안전보건기준규칙 | 🔴 1순위 |
| 5 | elevator | 승강기 | 승강기안전관리법 | 🔴 1순위 |
| 6 | pressure_vessel | 압력용기 | 산업안전보건법, 고압가스안전관리법 | 🔴 1순위 |
| 7 | conveyor | 컨베이어 | 산업안전보건기준규칙 | 🔴 1순위 |
| 8 | press | 프레스 | 산업안전보건법(검사대상) | 🔴 1순위 |
| 9 | fan | 팬/송풍기 | 산업안전보건기준규칙 | 🔴 1순위 |
| 10 | transformer | 변압기 | 전기안전관리법, 전기사업법 | 🟠 2순위 |
| 11 | switchboard | 배전반 | 전기안전관리법 | 🟠 2순위 |
| 12 | distribution_panel | 분전반 | 전기안전관리법 | 🟠 2순위 |
| 13 | electric_motor | 전동기 | 전기안전관리법 | 🟠 2순위 |
| 14 | generator | 비상발전기 | 전기안전관리법, 소방시설법 | 🟠 2순위 |
| 15 | heat_exchanger | 열교환기 | 산업안전보건기준규칙 | 🟠 2순위 |
| 16 | storage_tank | 저장탱크 | 위험물안전관리법, 고압가스안전관리법 | 🟠 2순위 |
| 17 | gas_tank | 가스탱크 | 고압가스안전관리법 | 🟠 2순위 |
| 18 | lpg_tank | LPG탱크 | 액화석유가스법 | 🟠 2순위 |
| 19 | chemical_tank | 화학물질탱크 | 화학물질관리법 | 🟠 2순위 |
| 20 | oil_tank | 유류탱크 | 위험물안전관리법 | 🟠 2순위 |
| 21 | valve | 밸브 | 산업안전보건기준규칙 | 🟡 3순위 |
| 22 | piping | 배관 | 산업안전보건기준규칙, 가스관련법 | 🟡 3순위 |
| 23 | chiller | 칠러 | 산업안전보건기준규칙 | 🟡 3순위 |
| 24 | refrigerator | 냉동기 | 산업안전보건기준규칙, 고압가스법 | 🟡 3순위 |
| 25 | hoist | 호이스트 | 산업안전보건법 | 🟡 3순위 |
| 26 | escalator | 에스컬레이터 | 승강기안전관리법 | 🟡 3순위 |
| 27 | sprinkler | 스프링클러 | 소방시설법 | 🟡 3순위 |
| 28 | fire_detector | 자동화재탐지 | 소방시설법 | 🟡 3순위 |
| 29 | fire_extinguisher | 소화기 | 소방시설법 | 🟡 3순위 |
| 30 | fire_hydrant | 소화전 | 소방시설법 | 🟡 3순위 |
| 31 | exhaust_system | 배기시설 | 대기환경보전법, 산업안전보건기준규칙 | 🟡 3순위 |
| 32 | dust_collector | 집진기 | 대기환경보전법 | 🟡 3순위 |
| 33 | sewage_treatment | 오수처리시설 | 물환경보전법 | 🟡 3순위 |
| 34 | ups | UPS | 전기안전관리법 | 🟡 3순위 |
| 35 | crusher | 분쇄기 | 산업안전보건기준규칙 | 🟡 3순위 |
| 36 | dryer | 건조기 | 산업안전보건기준규칙 | 🟡 3순위 |
| 37 | mixer | 혼합기 | 산업안전보건기준규칙 | 🟡 3순위 |
| 38 | extruder | 압출기 | 산업안전보건기준규칙 | 🟡 3순위 |
| 39 | forklift | 지게차 | 산업안전보건법(검사대상) | 🟡 3순위 |
| 40 | robot | 산업용로봇 | 산업안전보건기준규칙 | 🟡 3순위 |

---

## [실행 예시 — 보일러]

```
설비: 보일러
equipment_std: boiler
관련 법령: 에너지이용합리화법 제39조, 산업안전보건기준에 관한 규칙 제119조~123조

위 설비의 점검항목 CSV를 생성하세요.
```

**예상 출력 (일부):**
```csv
"equipment_std","equipment_name_ko","inspection_item","cycle","rule_type","risk_level","legal_basis","standard_value","check_method","source"
"boiler","보일러","수위계 수위 확인 (최저수위 이상 유지)","daily","DAILY","HIGH","산업안전보건기준규칙 제119조","최저수위선 이상","육안","TAI_A_METHOD"
"boiler","보일러","압력계 지시값 확인","daily","DAILY","HIGH","산업안전보건기준규칙 제119조","설계압력 이하","계측","TAI_A_METHOD"
"boiler","보일러","안전밸브 누설 여부 확인","daily","OPERATION","HIGH","","","육안","TAI_A_METHOD"
"boiler","보일러","연소상태 확인 (화염색·연기색)","daily","OPERATION","HIGH","산업안전보건기준규칙 제120조","","육안","TAI_A_METHOD"
"boiler","보일러","급수펌프 작동 상태 확인","weekly","SELF","MEDIUM","","","작동테스트","TAI_A_METHOD"
...
"boiler","보일러","보일러 연차 법정검사 신청","yearly","LEGAL","HIGH","에너지이용합리화법 제39조","","문서확인","TAI_A_METHOD"
```

---

## [DB 적재 방법]

40종 CSV 수집 완료 후 이 창(Claude 아키텍처 창)에 파일을 전달하면:

1. 기존 `inspection_master` 데이터 백업
2. CSV 검증 (필드 누락, 중복 체크)
3. `inspection_master` 교체 적재
4. `equipment_type_inspection_map.map_quality` 전체 EXACT로 업그레이드

---

## 예상 수집량

| 순위 | 설비 수 | 항목 수 | 소요 시간 |
|------|---------|---------|----------|
| 🔴 1순위 9종 | 9종 | ~180개 | 30분 |
| 🟠 2순위 11종 | 11종 | ~220개 | 40분 |
| 🟡 3순위 20종 | 20종 | ~400개 | 60분 |
| **합계** | **40종** | **~800개** | **2시간** |
