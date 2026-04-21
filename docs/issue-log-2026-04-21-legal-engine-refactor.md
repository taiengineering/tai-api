# Legal Engine 리팩터링 미기재 작업내역/이슈 (2026-04-21)

## 1) 미기재 작업내역

- `routers/legal_engine.py` 슬림화 완료
  - 라우터 크기: 약 77KB -> 4,985 bytes
  - 라우터 내부 SQL/판정/포맷 로직을 서비스로 이동
  - 엔드포인트는 서비스 호출/예외 변환 중심으로 단순화

- 서비스 계층 세분화
  - `services/legal_helpers.py`: 숫자/파싱/섹터/임계값 헬퍼
  - `services/legal_context.py`: 입력/설문/factory -> context 변환
  - `services/legal_rules.py`: 조건 매칭/판정/리스크/DB 룰 평가
  - `services/legal_format.py`: 결과 포맷/분류/DB 포맷
  - `services/legal_engine_svc.py`: 오케스트레이션 + 엔드포인트 서비스 함수
  - `services/legal_runtime.py`: 런타임 DB 저장/설비/공정 평가
  - `services/legal_step1_builder.py`: step1 결과 조립

- 외부 라우터 import 경로 전환
  - `routers/anonymous_diagnosis.py`
  - `routers/diagnosis_integrated.py`
  - `routers/contract_kmong.py`
  - 연쇄 참조 정리: `construction.py`, `public_admin.py`, `engine_qa.py`, `inspection_schedule.py`, `legal_engine_v510.py`

- 호환 래퍼 제거
  - `routers/legal_engine.py`에 있던 내부 함수 재export 래퍼 전부 제거
  - 외부 라우터는 `services.*`/`schemas.*` 직접 사용

- 테스트 추가 (STEP 5)
  - `tests/test_legal_helpers.py`
  - `tests/test_legal_rules.py`
  - `tests/test_legal_format.py`
  - 실행 결과: `9 passed`


## 2) 이슈 및 처리 결과

- 이슈: `routers.legal_engine` 내부 함수 직접 import 의존으로 리팩터링 시 ImportError 발생
  - 처리: 외부 라우터 import를 서비스/스키마 경로로 전환 후 래퍼 제거

- 이슈: 서비스 분리 중 파일 크기 기준 초과
  - 처리: `legal_runtime.py`, `legal_step1_builder.py` 추가 분리로 각 파일 15KB 내 조정

- 이슈: 로컬 검증 환경에서 health `degraded`
  - 원인: 로컬 `SUPABASE_URL` 미설정(기존과 동일)
  - 처리: 컴파일/단위테스트/기동 smoke 체크로 코드 무결성 확인


## 3) 잔여/후속 메모

- DB 입력 필드 정렬용 SQL 파일 추가:
  - `sql/20260419_diagnosis_input_fields_industry_paid2_paid3_saas.sql`
  - 적용 대상: Supabase SQL Editor 또는 마이그레이션 파이프라인

