# TAI 리빌딩 (tai-rebuild)

taieng.co.kr(공개) · safe.taieng.co.kr · admin.taieng.co.kr 3개 사이트 + 공용 백엔드(tai-api) + 공용 DB(Supabase)의
유지보수성 리빌딩을 위한 **프로젝트 문서 허브**. 관련 문서는 이 폴더에 계속 이어서 관리한다.

## 문서 목록
| 번호 | 문서 | 내용 |
|---|---|---|
| 00 | [아키텍처 심층 감사](./00_아키텍처_심층감사_2026-07-23.md) | 현 상태 실측·근본원인·비가용자산·해결 로드맵 |
| 01 | [작업계획서 (Object 방식)](./01_작업계획서_object방식.md) | 의존성 그래프 + Object 단위 범위·목표·테스트 게이트 |

## 진행 원칙 (요약)
- **Object 방식**: 시간축(Phase)이 아니라 **결과물축(Object)** 으로 관리. 각 Object는 범위·작업목표·완료 테스트(게이트)를 가지며, **게이트 통과 후에만** 의존 Object를 착수한다.
- **도메인당 SSOT 1개**, **시크릿은 env(소스 금지)**, **마이그레이션은 원자적(DB+API+FE 조율)**.
- 실측 기준: 소스(taiengineering/tai-www·tai-admin·tai-api, 45cminc/*), 운영 DB(Supabase `vwlahtguyggrhvslabax`).
