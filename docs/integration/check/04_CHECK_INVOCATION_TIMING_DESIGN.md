# 04 — Check Invocation Timing Design

Check를 **언제, 어떻게** 호출할지에 대한 설계.

## 1. 파이프라인 위치

```
LEG build_result()  →  leg_output_adapter.adapt()  →  [leg_to_check adapter]  →  runCheck()  →  store(03)
                                                          (02 문서)              (Check, 소비)   (TAI)
```

Check 호출은 **LEG 어댑터가 obligations[]를 산출한 직후**, 진단 실행(diagnosis run) 단위로 일어난다.

## 2. 호출 방식 — Python ↔ Check(TS) 경계 (핵심 결정)

확인된 사실: tai-api는 **Python**(`main.py`, `requirements.txt`), Check는 **TypeScript/ESM(Node ≥ 22)**. 따라서 같은 프로세스 내 함수 호출이 아니다. 두 가지 방식:

- **(A) 권장: Check Runner(Node) 사이드카.** `runCheck`를 그대로 감싼 얇은 Node 서비스(HTTP 또는 subprocess). tai-api가 `CheckInput` JSON을 보내고 `EvidenceReport` JSON을 받는다. Check는 **무수정**(consume-only) — Phase 6 Public API(`runCheck`)만 호출.
  - HTTP: 내부 전용 엔드포인트(`POST /run-check`), 입력/출력은 JSON 계약 그대로.
  - subprocess: `node check-runner.js < input.json > report.json` (네트워크 불필요, 순수성 유지에 적합).
- **(B) 비권장: 로직 재구현.** Check 로직을 Python으로 다시 구현 → **금지에 저촉**(Check 계약/동작을 TAI가 복제하면 "Check가 진실원천"이 깨짐). 채택하지 않음.

> 이 경계(A의 HTTP vs subprocess, 배포 형태)는 **인프라 결정 사항**으로 표시한다. 어느 쪽이든 Check 소스는 바뀌지 않는다.

## 3. 동기 vs 비동기

- `runCheck`는 순수·고속·무의존(네트워크 없음) 함수다. 의무 수가 많아도 연산은 가볍다.
- **MVP: 동기(inline)** — 진단 실행 완료 직후 Check Runner를 호출하고 결과를 저장. 진단 결과 화면에 구조 신호를 함께 노출 가능.
- 대량/배치 환경에서는 tai-api의 기존 `schedulers/`·worker 경로를 사용해 **비동기**로 전환 가능(설계상 동일 입력→동일 결과이므로 위치 무관).

## 4. (재)호출 트리거

| 트리거 | 이유 |
|--------|------|
| 새 진단 실행 | 새 obligations[] 생성 |
| 근거 변화(문서 업로드/삭제, Task 완료) | `attached` 재산정 → Check 재관측 필요 |
| 의무 변화(법령 버전 변경 등 LEG 재실행) | claim/chain 집합 변경 |

## 5. 멱등/캐싱

- 동일 입력(scope+claims+evidence+chains+now 동일) → Check가 동일 `report_id` 산출.
- 저장 계층(03)은 report_id로 upsert. 입력 불변이면 재계산을 생략하거나 저장본을 재사용.
- `now`는 실행마다 host가 주입하고 report와 함께 저장한다(관측 시각).

## 6. 경계 체크리스트

| 항목 | 보장 |
|------|------|
| Check 소스/계약/상태값 변경 | 없음 (runner는 runCheck만 호출) |
| 호출 위치가 결과에 영향 | 없음 (순수 함수, 동일 입력→동일 결과) |
| LEG 수정 | 없음 |
| 도메인 판단을 호출부에서 수행 | 없음 (호출부는 변환·전달만) |
