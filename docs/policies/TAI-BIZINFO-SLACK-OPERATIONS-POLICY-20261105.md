# TAI Bizinfo 수집·Slack 알림 운영 정책

- 문서 ID: POLICY-TAI-BIZINFO-SLACK-OPS-20261105
- 적용 대상: `taiengineering/tai-api`의 Bizinfo 일일 수집 및 기존 Slack Relay
- 작성 기준일: 2026-11-05 (KST)
- 관련 Goal: `G-mw2vy1iq-fc4d0e` (이전 실행 주체의 ACTIVE 보고)
- 성격: 기존 구현의 운영 기준·상태·종결 경계 정리. 신규 기능 설계 아님.

## 1. 운영 목표와 기본 원칙

기업마당 공고를 매일 KST 13:00에 수집하고, 신규 또는 변경된 관련 공고에 필요한 경우 기존 Slack Relay로 알린다. 발송에 실패하거나 대기 중인 이벤트는 기존 복구 함수가 처리한다.

1. **기존 자산 재사용**: `services/slack_relay_svc.py`의 `process_relay_event()` 및 `run_relay_recovery_once()`를 유지한다. 신규 Slack 발송 모듈·인증·공개 API를 만들지 않는다.
2. **완료된 검증 재수행 금지**: 기존 Slack 토큰·채널·실발송 성공은 기확보 증거로 인정한다. 같은 목적의 테스트 메시지와 중복 수동 호출을 요구하지 않는다.
3. **데이터 보호**: 기존 공고 1,585건, IN_SCOPE 24건에 대한 Backfill·재알림을 반복하지 않는다. 기존 DB의 중복 이벤트 차단 계약을 유지한다.
4. **운영 상태와 코드 완료 분리**: Git 병합, 배포 성공, 크론 DB 등록, 크론 활성화, 첫 정기 실행 성공은 서로 다른 상태다. 하나의 완료로 나머지를 추정하지 않는다.
5. **승인된 범위만 변경**: 운영 DB 변경, 크론 활성화, 실발송, 배포는 Owner 승인 범위를 따른다. 이미 승인된 범위는 불필요하게 다시 승인받지 않는다.

## 2. 확정된 기존 실행 경로

### 공고 수집

`cron_job_master(job_code=bizinfo_daily_safety_sync)` → `direct://bizinfo_daily_safety_sync` → `services/scheduler/handlers.py::_run_bizinfo_daily_sync` → 기존 Bizinfo 수집·저장·개별 알림 등록 경로.

- 주기: `0 13 * * *` (TAI 스케줄러의 Asia/Seoul 기준)
- 알림: 개별 공고 이벤트를 기존 Slack Relay로 처리하며, 중복 일별 요약은 별도 전송하지 않음

### 알림 복구

`cron_job_master(job_code=slack_relay_recovery)` → `direct://slack_relay_recovery` → `_run_slack_relay_recovery` → 기존 `run_relay_recovery_once()`.

- 주기: `*/5 * * * *`
- 복구 함수는 PENDING/도래한 RETRY를 일괄 처리하며, 오래된 CLAIMED/SENDING도 점검한다.
- `processed`는 발송 성공 건수가 아니다. 성공한 개별 이벤트의 최종 상태는 `SENT`이며 필요 시 `slack_ts`, `sent_at`으로 확인한다.
- 수동 복구 엔드포인트는 한 이벤트만 선택 실행하는 API가 아니다. 수동 실행 전 모든 대상의 영향 범위를 확인한다.

## 3. 확인된 완료 사실과 미완료 경계

| 항목 | 2026-11-05 기준 근거/상태 |
| --- | --- |
| Bizinfo Lifecycle | PR #771 병합, DB Schema/Backfill/V2 함수 완료(인수인계서 및 이전 실행 보고) |
| 기존 Slack 실발송 | 채널 `C0CCQKVQCQP`, `ok=true`, Slack ts `1793834149.140619` (기확보 증거) |
| Slack 복구 DIRECT 핸들러 | PR #774 Squash Merged, GitHub merge `efa78c02` (독립 확인) |
| Railway 코드 반영 | 배포 `eb230055`, 커밋 `7eb42cf3`, SUCCESS (Claude Code 운영 조회 보고) |
| 복구 크론 DB 등록 | `slack_relay_recovery`: 등록됨, `is_active=false`, `is_enabled=false` (마지막 운영 보고) |
| Bizinfo 크론 DB 등록 | `bizinfo_daily_safety_sync`: 등록 완료, 비활성 (STEP B 완료 보고) |
| 수동 복구 1건 | 실행 및 `SENT` 전이 증거 없음; 1건 PENDING으로 최종 보고됨 |
| 두 크론 자동 활성화 | `is_active=true` 적용 완료 증거 없음; **운영 ACTIVE로 표시 금지** |
| 첫 정기 실행 | 성공 로그 미확인; 코드·DB 준비 완료와 구분 |

표의 운영 DB·Railway 항목은 당시 Claude Code 보고 기준이며 현 시점 재조회로 갱신한 값이 아니다.

## 4. 승인·활성화 정책

- Owner는 2026-11-05 두 크론의 활성화를 승인했지만, 당시 작업지시에는 복구 이벤트 1건 수동 검증 선행 조건이 있었다. **활성화 실제 반영 여부는 확인되지 않았다.**
- Owner는 반복적인 실발송/수동 호출 검증을 중단하고 완료된 기능을 정리하도록 지시했다. 이 판단을 근거로 같은 테스트를 새 작업으로 재발행하지 않는다.
- 다만 반복 검증 중단이 곧 미실행 크론을 활성화했다는 의미는 아니다. 운영 활성화 상태는 실제 저장된 설정으로만 판정한다.
- 크론 활성화 전 승인 대상 외 PENDING/RETRY 및 오래된 CLAIMED/SENDING, 기존 테스트 이벤트를 확인하고 예상치 못한 발송을 방지해야 한다. 신규 대량 테스트·Backfill 없이 해당 위험만 판단한다.
- `DbStore.refresh()`는 `cron_job_master.is_active=true`를 실행 대상으로 선택한다. `cron_schedule_config.is_enabled` 단독으로 실행 차단을 보장하지 않는다.
- 정책상 목표 설정은 두 크론 모두 `is_active=true`, `is_enabled=true`이지만, 실제 운영 설정을 확인하지 못한 상태에서는 문서에 활성이라고 기록하지 않는다.
- 활성화 후 첫 정기 실행의 자연 로그로 상태를 확인한다. 이미 성공한 Slack 전송 테스트를 재실행하지 않는다.

## 5. 인증·보안 경계

- `POST /cron/jobs/{job_code}/run`과 `POST /internal/slack-relay/recover`는 기존 플랫폼 관리자 `ALL` 권한을 요구한다.
- `/auth/send-otp`와 `/auth/verify-otp`는 작업자용 인증 경로이므로 관리자 복구 실행 수단으로 사용하지 않는다. 기존 `/auth/login` 관리자 세션을 사용한다.
- 관리자 비밀번호, OTP, JWT, Slack Bot 토큰은 문서·채팅·로그에 기록하지 않는다.
- 관리자 UI에 Cron Manager가 있다고 가정하지 않는다. UI 미존재를 이유로 신규 UI 개발을 시작하지 않는다.

## 6. 종료 기준·잔여 사항

**구현·기존 발송 검증 단계는 CLOSED.** PR #774가 기존 함수에 DIRECT 경로만 연결했으며 기존 전송 성공 증거가 존재한다. 추가 코드 개발·반복 수동 테스트를 요청하지 않는다.

**운영 활성화 완료는 증거 미확보 상태.** 두 크론이 실제로 활성화됐는지와 최초 정기 실행 성공 여부를 미완료/미확인으로 남긴다. 이를 허위로 `CLOSED_FINAL` 표시하지 않는다.

남은 사항은 별도의 신규 개발 과제가 아니라, 기승인된 운영 설정의 반영 여부와 첫 자연 실행 결과를 확인하는 운영 인수 사항이다. 미승인 배포·DB 변경·추가 실발송을 이 문서로 자동 승인하지 않는다.

이 문서의 작성·등록은 제품 기능 완성의 대체물이 아니다. 문서 자체를 완료 기준으로 삼지 않는다.

## 7. 관련 증거

- PR #771 — Bizinfo Lifecycle: `https://github.com/taiengineering/tai-api/pull/771`
- PR #774 — Slack Relay Recovery DIRECT: `https://github.com/taiengineering/tai-api/pull/774`
- PR #772 — 변경 범위 오류로 대체·종료 대상: `https://github.com/taiengineering/tai-api/pull/772`
- 기존 SQL: `migrations/20261106_slack_relay_recovery_cron.sql`, `migrations/20261104_bizinfo_daily_sync_cron.sql`
- 원 인수인계서: `WO-TAI-BIZINFO-RECOVERY-SCHEDULE-HANDOFF-20261105.md` (본 대화에 제공됨)

## [Owner용 쉬운 설명 및 방향 점검]

1. **원래 목표:** 정부지원사업 공고를 매일 수집하고 중요한 알림을 Slack으로 자동 전달·복구한다.
2. **이번 작업:** 이미 만든 기능의 운영 정책과 완료·미완료 상태를 Git에 기록하고 불필요한 반복 테스트를 종료한다.
3. **완료 후 변화:** 운영자는 어떤 기능이 완성됐고 실제 자동 실행이 아직 확인되지 않았는지 쉽게 구분할 수 있다.
4. **하지 않는 작업:** 기존 모듈 재개발, 반복 테스트, 신규 UI·API, DB 변경, 배포 또는 새 알림 발송.
5. **원기획 일치 여부:** **부분일치** — 2026-11-05 인수인계서와 PR #774·기존 코드에 일치. 상위 원기획 정본 미확인.
6. **방향 이탈 위험:** 반복 검증·문서 확대를 막는다. 운영 미완료를 문서 완료로 오인하지 않도록 활성화 여부는 분리한다.
