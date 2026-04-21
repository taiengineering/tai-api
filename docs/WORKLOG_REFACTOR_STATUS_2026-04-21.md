# 작업 미기재 내역 및 이슈 정리 (2026-04-21)

## 1) 이번 사이클 반영 내역 (요약)
- 대상: `construction.py`, `contracts_engine.py`, `diagnosis_integrated.py`, `legal_engine_v510.py`, `engine_equipment.py`
- 공통 수행:
  - STEP 0 현재 동작 스냅샷 테스트 추가
  - 헬퍼/스키마/서비스 분리
  - 라우터 슬림화 (15KB 기준 충족)
  - 리팩터링 후 회귀 테스트 재실행

## 2) 파일별 상태
- `routers/construction.py`: 서비스/서브라우터 분리 완료
- `routers/contracts_engine.py`: helper/ai/svc 분리 완료
- `routers/diagnosis_integrated.py`: helper/schema/svc 분리 완료
- `routers/legal_engine_v510.py`: helper/schema/svc 분리 완료
- `routers/engine_equipment.py`: helper/schema/svc 분리 완료

## 3) 테스트/검증 결과
- 회귀 테스트 세트 최종 통과: `46 passed`
- 포함 테스트:
  - `tests/test_construction_current.py`
  - `tests/test_contracts_engine_current.py`
  - `tests/test_contract_helpers.py`
  - `tests/test_diagnosis_integrated_current.py`
  - `tests/test_diagnosis_helpers.py`
  - `tests/test_legal_engine_v510_current.py`
  - `tests/test_legal_v510_helpers.py`
  - `tests/test_engine_equipment_current.py`
  - `tests/test_equipment_helpers.py`
- 운영 헬스체크:
  - `GET https://api.taieng.co.kr/health` 정상 (`healthy`)

## 4) 작업 중 발생 이슈 및 처리
- 이슈: `tests/test_diagnosis_helpers.py`의 SHA256 스냅샷 기대값 오기입
  - 증상: `test_sha256_snapshot` 실패
  - 원인: 테스트 상수값 오타 (코드 로직은 정상)
  - 조치: 기대값을 실제 `sha256("tai")` 값으로 수정
  - 결과: 관련 테스트 포함 전체 회귀 통과

## 5) 브랜치/배포 관점 메모
- 원격 `dev` 선행 커밋으로 푸시 거절 1회 발생
  - 조치: `git pull --rebase --autostash origin dev` 후 재푸시 성공
- 리팩터 커밋은 원격 `dev`에 반영 완료 상태

## 6) 후속 권장
- PR 생성 시 본 문서를 체크리스트로 첨부
- 운영 배포 전 아래 2개 재확인:
  - 핵심 엔드포인트 스모크 테스트
  - `/health` + 주요 진단 API 실응답 검증
