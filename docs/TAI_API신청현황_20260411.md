# TAI 외부 API 신청 현황

> 최종 업데이트: 2026-04-11

---

## 승인 완료 + 개발 완료

| API | 파일 | 승인일 |
|---|---|---|
| 행정안전부_안전정보 통합공개 | safety_info.py | 2026-03-18 |
| 법제처 국가법령정보 | law_collector.py | 2026-03-30 |
| KOSHA_MSDS | kosha_apis.py | 2026-03-28 |
| KOSHA_안전보건법령 스마트검색 | kosha_apis.py | 2026-03-28 |
| KOSHA_건설업 일별 중대재해 | kosha_apis.py | 2026-03-28 |
| KOSHA_안전보건자료 링크 | kosha_apis.py | 2026-03-28 |
| KOSHA_국내재해사례 | kosha_apis.py | 2026-03-28 |
| KOSHA_코샤가이드 | kosha_apis.py | 2026-03-28 |
| 국세청_사업자등록 진위확인 | biz_verify.py | 2026-03-28 |
| 소방청_국가 위험물 정보 | fire_hazmat.py | 2026-03-18 |

## 승인 완료 + 개발 진행 중

| API | 파일 | 비고 |
|---|---|---|
| 근로복지공단_산재판례 판결문 | precedent_api.py | 작업지시 발행됨 |
| 기상청_단기예보 | weather.py | 개발 완료, API Hub 403 이슈 해결 중 |
| 기상청_특보 | weather.py | 동일 |
| 기상청_특보구역정보 | weather.py | 동일 |

## 신청 필요

| API | 신청처 | 용도 |
|---|---|---|
| 대법원 판례 | data.go.kr | 과태료·처벌 판례 |
| Q-Net 국가기술자격 | hrdkorea.or.kr (기업 신청) | 공급자 자격 검증 |

## API 키 관리

| 환경변수명 | 용도 |
|---|---|
| BUILDING_API_KEY | data.go.kr 공통 키 (건축물대장·국세청·KOSHA 등) |
| DATA_GOV_SERVICE_KEY | 법제처 data.go.kr 키 (현재 미설정, law.go.kr 폴백) |
| LAW_API_OC | law.go.kr 인증값 (taieng) |
| KMA_SERVICE_KEY | 기상청 API Hub 전용 키 |
| JUSO_API_KEY | 도로명주소 API 키 |
