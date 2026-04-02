# TAI Backend 세션 메모리 — 2026-04-02 (최종)

## 엔진 버전 이력 (오늘)
- v5.2.5 → v5.3.1 → v5.4.0 → v5.4.1 → v5.4.2
- **현재 GitHub**: v5.4.2 (Railway 배포 진행 중)

---

## 오늘 완료된 작업

### 1. form_code 매핑 전체 완료 (배치1~4 + 구형코드 정규화)
- 총 255건 처리, NULL 0건 달성
- 표준서식 156건 / ONLINE 22건 / NONE 16건 / SELF 31건 / UNKNOWN 30건
- 기관 약어 확정: MOEL/NFD/ME/MOLIT/MOTIE/MOHW/MOIS
- 구형 `별지 제N호서식` 87건 → 기관약어 포함 표준코드로 일괄 정규화
- ⚠️ 검증 필요 3건: NFD-별지제52호, NFD-별지제20호, ME-별지제14호

### 2. 건설 법령진단 엔진 전수 검토 및 수정

#### DB 수정 (master_building_legal_rules)
| 수정 | 내용 |
|------|------|
| CONST-TECH-002 condition_value | 1억→50억 (건설기술진흥법 시행령 제98조의3 기준) |
| CONMACT-002-CON | 비활성화 (건설기계법 선임 1억 조건 오류) |
| OSH-CON-APT-001~003 신규 추가 | 산안법 시행령 제16조 APPOINT 룰 3개 (건축150억/토목120억/50명) |
| OSHSTD-003-CON, OSHSTD-002-CON, OSHSTD-001-CON | 중복 비활성화 |
| CONST-IND-001 | APPOINT→REPORT 타입 수정 (건설업 등록의무) |
| CON-CON-102 | ACTION/10억 조건으로 수정 (건설기술인 배치) |
| OSH-CON-APT-002 | 비활성화 (건축공사에서 토목 기준 잘못 트리거) |

#### 코드 수정 (legal_engine.py)
| 버전 | 수정 내용 |
|------|----------|
| v5.4.0 | DiagnoseStep1Body CONSTRUCTION 전용 필드 7개 추가 |
| v5.4.0 | _input_to_facility_context: electrical_capacity_kw, has_blasting, has_crane |
| v5.4.0 | diagnose_step2: factory_id 없어도 익명 진단 지원 |
| v5.4.0 | diagnose_step3: 점검주기 하드코딩 2년 → DB 실제값 조회 |
| v5.4.1 | _CONSTRUCTION_AMOUNT_THRESHOLDS 단위 오류: 15억→150억, 12억→120억 |
| v5.4.1 | threshold_eok 계산: /10_000_000 → /100_000_000 |
| v5.4.2 | apply/{factory_id}: 섹터 필터 누락 수정 (전체 822개→섹터별 필터) |

---

## 테스트 결과 (v5.4.2 배포 후 예상)

| 케이스 | 기대 sm_required | 비고 |
|--------|-----------------|------|
| 건축 150억+60명 | true | ✅ 정상 |
| 건축 100억+55명 | true (50명 충족) | ✅ 정상 |
| 건축 80억+40명 | false | v5.4.1에서 수정됨 |
| 건축 149억+49명 | false | v5.4.1에서 수정됨 |
| 토목 120억+48명 | true | ✅ 정상 |
| 토목 119억+49명 | false | v5.4.1에서 수정됨 |
| 건축 50억+임시전기75kW | true (전기관리자) | ✅ 정상 |

⚠️ CONST-TECH-002(건설기술법 건설안전관리자 50억 이상)는 80억 현장에서
appoint 1건으로 나옴 — 이것은 법적으로 맞는 결과 (산안법 안전관리자와 별개)

---

## 잔여 이슈

- UNKNOWN 30건: 고시류 하위 조문 연결 불가 → 운영상 허용
- 승강기 ELEVRULEC-001: 제16조가 부품안전인증 조문으로 rule_id 조문 오류 → 추후 검토
- MANUFACTURING 섹터 REPORT 룰 43건 모두 condition_code NULL → 모든 제조업에 적용됨 → 검토 필요

---

## 크몽 페이지 주소검색 복원
- 원인: `request/v3/index.html` 파일에서 주소검색 기능 코드가 누락됨
- 수정: JUSO 모달, openJusoModal(), searchJuso(), 건축물대장 조회 복원
- 커밋: tai-admin에 push 완료

---

## 다음 세션 우선순위
1. v5.4.2 배포 완료 후 7개 테스트케이스 재검증
2. MANUFACTURING 섹터 REPORT 43건 condition_code 검토
3. GPT 배치 수집: BLASTING·CRANE 공종 KCSC 프로세스 추가
4. construction_work_type NULL 공통 98개 룰 work_type 매핑
