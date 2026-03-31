# TAI 설비 점검데이터 수집 프롬프트 (GPT Data팀용 — 방법 A)
## 작성일: 2026-03-31

---

## 사용 방법

1. ChatGPT에 접속
2. **아래 [문단 1]을 System Prompt(Custom Instructions)로 설정**
3. 이후 설비별로 **[문단 2]~[문단 3]을 수정하여 요청**
4. **CSV 파일로 출력 요청** 후 클라우드 담당자에게 전달

---

## [문단 1] System Prompt

```
당신은 산업 안전관리 시스템 TAI의 설비 점검 데이터 수집 전문가입니다.
당신의 역할은 한국 산업현장에서 실제로 사용하는 설비별 점검항목을
실무 기준에 맞게 정리하여 CSV로 출력하는 것입니다.

출력 규칙:
1. 모든 출력은 반드시 CSV 형식으로
2. 컨마 포함된 항목명은 따옴표로 감싸기
3. 헤더행 포함
4. 한국어로 작성 (설비명, 점검항목 이름)
5. 각 점검항목은 실무에서 실제로 점검하는 내용만 작성
6. 주기는 daily/weekly/monthly/quarterly/annual 중 하나
7. 법적 근거가 있는 사항은 반드시 표시
8. 위험등급: HIGH(좌상/실화위험), MEDIUM(성능저하), LOW(운영효율)
```

---

## [문단 2] 단일 설비 요청 틀렇릿

다음 형식으로 사용하된 설비명과 코드를 교체하여 ChatGPT에 요청하세요:

```
다음 설비의 점검항목 데이터를 CSV로 출력해주세요.

설비명: [설비 한글명] (equipment_type_code: [3자리 코드])

요청 사항:
- 실제 산업현장에서 음, 이룹으로 다루는 점검항목으로만 구성
- 한국 산업안전보건법, KS 규격, 제조사 권장사항 기준 적용
- 점검항목당 최소 1문장의 점검 기준/판단 방법 포함
- 설비별 특성을 반영한 실질적 항목으로 구성 (보일러마다 다른 항목, 펜프마다 다른 항목)

CSV 컨럼:
equipment_type_code, equipment_std, inspection_item, inspection_detail, cycle, rule_type, risk_level, legal_basis
```

**컨럼 설명:**

| 컨럼 | 설명 | 예시 |
|------|------|------|
| equipment_type_code | system_codes 코드 | `014` |
| equipment_std | 영문 표준명 | `boiler` |
| inspection_item | 점검항목명 (한글) | `안전밸브 작동 확인` |
| inspection_detail | 점검 기준/방법 (한글) | `스프링 작동 여부, 누설 여부 육안 확인` |
| cycle | 점검 주기 | `daily` / `weekly` / `monthly` / `quarterly` / `annual` |
| rule_type | 점검 유형 | `LEGAL`(법정) / `SELF`(자체) / `DAILY`(일상) |
| risk_level | 위험등급 | `HIGH` / `MEDIUM` / `LOW` |
| legal_basis | 법적 근거 (없으면 비우기) | `산업안전보건법 제36조` |

---

## [문단 3] 40종 설비 요청 목록

아래 40종을 **각각 별도 요청**하세요. (한 번에 1~3종씩 요청)

### 콘단산당 요청 명령 (틀덼)

다음 문단 2 틀덼에 설비명과 코드를 채워서 요청:

```
[선철 1] 설비명: 변압기 (equipment_type_code: 001)
[선철 2] 설빔명: 기중차단기 (equipment_type_code: 002)
[선철 3] 설비명: 진공차단기 (equipment_type_code: 003)
[선철 4] 설비명: 배선용차단기 (equipment_type_code: 004)
[선철 5] 설비명: 누전차단기 (equipment_type_code: 005)
[선철 6] 설비명: 배전반 (equipment_type_code: 006)
[선철 7] 설비명: 분전반 (equipment_type_code: 007)
[선철 8] 설비명: 전동기 (equipment_type_code: 008)
[선철 9] 설비명: UPS (equipment_type_code: 009)
[선철10] 설비명: 비상발전기 (equipment_type_code: 010)
[선철11] 설비명: 펜프 (equipment_type_code: 011)
[선철12] 설비명: 압축기 (equipment_type_code: 012)
[선철13] 설비명: 열교환기 (equipment_type_code: 013)
[선철14] 설비명: 보일러 (equipment_type_code: 014)
[선철15] 설비명: 탱크 (저장탱크) (equipment_type_code: 015)
[선철16] 설비명: 밸브 (equipment_type_code: 016)
[선철17] 설비명: 배관 (equipment_type_code: 017)
[선철18] 설비명: 팬 (송풍기) (equipment_type_code: 018)
[선철19] 설비명: 냉동기 (equipment_type_code: 019)
[선철20] 설비명: 칠러 (equipment_type_code: 020)
[선철21] 설비명: 크레인 (equipment_type_code: 021)
[선철22] 설비명: 호이스트 (equipment_type_code: 022)
[선철23] 설비명: 프레스 (equipment_type_code: 023)
[선철24] 설비명: 컨베이어 (equipment_type_code: 024)
[선철25] 설비명: 승강기 (equipment_type_code: 025)
[선철26] 설비명: 에스컈레이터 (equipment_type_code: 026)
[선철27] 설비명: 가스탱크 (압력용기) (equipment_type_code: 027)
[선철28] 설비명: LPG탱크 (equipment_type_code: 028)
[선철29] 설비명: 화학물질탱크 (equipment_type_code: 029)
[선철30] 설비명: 유류탱크 (equipment_type_code: 030)
[선철31] 설비명: 스프링클러 (equipment_type_code: 031)
[선철32] 설비명: 자동화재탐지설비 (equipment_type_code: 032)
[선철33] 설비명: 소화기 (equipment_type_code: 033)
[선철34] 설비명: 소화전 (equipment_type_code: 034)
[선철35] 설비명: 배기시설 (국소배기장치) (equipment_type_code: 035)
[선철36] 설비명: 집진기 (equipment_type_code: 036)
[선철37] 설비명: 오수처리시설 (equipment_type_code: 037)
[선철38] 설비명: 압력용기 (equipment_type_code: 038)
[선철39] 설비명: 냉동기-냉각탐 (equipment_type_code: 039)
[선철40] 설비명: 기타 산업설비 (범용) (equipment_type_code: 040)
```

---

## [문단 4] CSV 시작 예시 (출력 품질 검증용)

GPT 첫 번째 요청 시 아래 형식이 나와야 정상:

```csv
equipment_type_code,equipment_std,inspection_item,inspection_detail,cycle,rule_type,risk_level,legal_basis
014,boiler,안전밸브 작동 확인,레버스프링 작동 여부 확인 및 누설 얬부 육안,daily,DAILY,HIGH,산업안전보건기준에 관한 규칙 제36조
014,boiler,수위계 수위 확인,저수위 경보 작동 및 실제 수위 보유 여부,daily,DAILY,HIGH,엔너지이용 합리화법 제39조
014,boiler,연소상태 확인,연소색 정상 여부 및 웰 스택 상태 확인,daily,LEGAL,HIGH,엔너지이용 합리화법 제39조
014,boiler,갉재향펼프 작동,폌프 시동 여부 및 압력 안정성 확인,weekly,SELF,MEDIUM,
014,boiler,본체 외관 균열 점검,검사창 통해 비정상 열팔창 (사용하지 않음) 및 언더 상태 확인,monthly,SELF,HIGH,산업안전보건법 제36조
```

---

## 이후 작업

1. GPT가 출력한 CSV를 클라우드 담당자에게 전달
2. 담당자가 품질 검증 후 `inspection_master` 테이블에 적재
3. `equipment_type_inspection_map`의 `has_direct_map = TRUE`, `inspection_std` 업데이트
4. 자동으로 서비스 품질 향상

---

## 수집 우선순위 (1~3 먼저, 이후 나머지)

| 순위 | 설비코드 | 설비명 | 이유 |
|------|------|------|------|
| 1 | 014 | 보일러 | 산안법/에너지법 안전검사 의무 설비 |
| 1 | 012 | 압축기 | 고압가스 안전관리법 대상 |
| 1 | 021 | 크레인 | 산안법 안전검사 대상 |
| 1 | 025 | 승강기 | 승강기안전관리법 정기검사 |
| 1 | 038 | 압력용기 | 산안법 안전검사 대상 |
| 2 | 001 | 변압기 | 전기안전관리법 대상 |
| 2 | 006 | 배전반 | 전기안전관리ubc95 대상 |
| 2 | 031 | 스프링클러 | 소방시설법 점검 대상 |
| 2 | 027 | 가스탱크 | 고압가스/도시가스법 대상 |
| 2 | 011 | 펜프 | 일반산업에서 가장 많이 사용 |
| 3 | 나머지 30종 | - | 순차 진행 |
