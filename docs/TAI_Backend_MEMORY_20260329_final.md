# TAI 백엔드 메모리 — 2026-03-29 최종

## DB 최종 현황

| 구분 | 건수 |
|------|------|
| 법률 (본법) | 37개 |
| 시행령 | 46개 |
| 시행규칙 | 36개 |
| **전체 법령** | **119개** |
| 조문 | 31,827개 |
| 항(項) | 50,569개 |
| 판정 룰 전체 | **486개** |

## 판정 룰 섹터별

| 섹터 | 룰 수 |
|------|-------|
| BUILDING | 400 |
| MANUFACTURING | 33 |
| CONSTRUCTION | 27 |
| SPECIAL_FACILITY | 26 |

## 오늘 완료 작업

### 법령 수집
- ✅ 건설업 시행령·규칙: 건설산업기본법, 건설기술진흥법 (시행령+규칙)
- ✅ 특수시설 시행령: 의료법, 다중이용업소법, 노인복지법, 어린이놀이시설법, 사회복지사업법, 학교안전사고예방법
- ✅ 특수시설 시행규칙 5개 추가 (다중이용업소, 사회복지, 노인복지, 어린이놀이시설, 학교안전사고)
- ✅ 의료법 (164조문, 항·호목 포함)
- ✅ 산안법 항·호목 재수집 (recollect 엔드포인트 — 208조문, 519항)

### 판정 룰 적재 (GPT 없이 SQL 직접)
- ✅ MANUFACTURING 18개 신규 (산안법·전기안전관리법·위험물·고압가스·화학물질·에너지·중대재해)
- ✅ CONSTRUCTION 15개 신규 (산안법·건설기술진흥법·건설산업기본법·전기안전관리법·중대재해)
- ✅ SPECIAL_FACILITY 20개 신규 (의료법·다중이용업소·노인복지·사회복지·어린이놀이시설·학교안전사고)

### 신규 스크립트
- ✅ `scripts/parse_law_rules.py` — GPT 없는 키워드 파싱 룰 생성
- ✅ `scripts/collect_kcsc.py` — KCSC API 건설공종·작업 수집

### 신규 DB 테이블
- ✅ `kcsc_process_master` — KCS 건설공종 마스터
- ✅ `kcsc_work_master` — 공종별 작업 목차

### 가상 건설현장 엔진 테스트
- 판교신도시 복합물류센터 (건축공사 280억, 85명, 200kW)
- 결과: 19개 룰 적용 / 리스크 HIGH
- 선임 6건, 점검 1건, 신고 1건, 조치 6건 정상 판정

## KCSC API 정보

- URL: https://kcsc.re.kr/OpenApi
- 인증키: BHunaeOUSfy0qKRhE7106HEQFbql_8Ew4z1ub9ccjpk
- 유효기간: 2027-03-29
- 엔드포인트:
  - GET /CodeList — 전체 공종 목록
  - GET /CodeViewer/KCS/{코드} — 공종 상세(작업 목차)
- 실행 명령: `railway run python3 scripts/collect_kcsc.py`

## 건설 로직 재설계 논의

### 핵심 이슈
1. 하도급 포함 합산 인원 로직 미구현 (산안법 시행령 제16조③)
2. 섹터별 판단 로직이 근본적으로 달라 단일 엔진으로 처리 불가
3. 건설은 공정→작업→작업자 구조가 필요하나 데이터 없음

### 재설계 방향
```
공사현장 개요
  └─ 공정 (KCS 기준 건축/토목 분류)
       └─ 작업 (공정별 세부 작업 — KCSC API 수집)
            └─ 작업자 (원청 + 하도급 구분)
                 ├─ 위험작업 → 안전작업허가서·TBM·법령 판정
                 └─ 일반작업 → 작업일보·공정관리
```

### 추가 필요 입력 필드
- `subcontractor_count` (하도급 근로자 수)
- `construction_type` (건축/토목/전문)
- `has_tunnel_bridge` (터널·교량 여부)
- `is_subcontractor_self_managed` (하도급 자체 안전관리 여부)

## 다음 세션 최우선

1. KCSC 수집 실행 (`railway run python3 scripts/collect_kcsc.py`)
2. 수집 결과 확인 후 건설 공종·작업 DB 구조 검증
3. 건설 엔진 재설계 (subcontractor_count 합산 로직 포함)
4. OpenAI 할당량 복구 시 → MANUFACTURING 룰 GPT 변환 추가
5. Navbar/Footer 18개 파일 개편 (Cursor)
