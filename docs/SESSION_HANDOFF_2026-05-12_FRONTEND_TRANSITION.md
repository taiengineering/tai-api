# TAI Runtime Productization — Frontend Transition Cursor 작업지시서
## 2026-05-12

---

## 현재 상태
- Runtime Backend: v5.52.0 배포 완료
- Bridge API 6개 라우터 활성
- DB 테이블 34개 + View 1개 + CHECK 383개
- 운영 데이터: 사업장50, 설비150, 위험물100, WO129, 세션100, 증빙300, 알림500
- Stress Test: 83항목 PASS, 0 위반

---

## Bridge API 엔드포인트 매핑

### 1. Obligation Bridge (`/bridge/obligations`)
| Endpoint | Method | 프론트 연결 |
|----------|--------|------------|
| /bridge/obligations | GET | 의무 목록 페이지 |
| /bridge/obligations/{id} | GET | 의무 상세 |
| /bridge/obligation-assignments | GET/POST | 담당자 지정 |
| /bridge/obligation-schedule-policies | GET/POST | 반복주기 설정 |
| /bridge/work-orders | GET | 업무 목록 (관리자) |
| /bridge/my-work-orders | GET | 내 업무 (작업자) |

### 2. Inspection Bridge (`/bridge/my-inspection`)
| Endpoint | Method | 프론트 연결 |
|----------|--------|------------|
| /bridge/my-inspection | GET | 내 점검 목록 |
| /bridge/my-inspection/{id} | GET | 점검 상세 |
| /bridge/inspection-sessions | POST | 점검 시작 |
| /bridge/inspection-checklist | GET/POST | 체크리스트 |
| /bridge/inspection-evidence | GET/POST | 증빙 업로드 |
| /bridge/inspection-submit | POST | 점검 제출 |

### 3. Notification Bridge (`/bridge/notifications`)
| Endpoint | Method | 프론트 연결 |
|----------|--------|------------|
| /bridge/notification-events | GET/POST | 이벤트 목록 |
| /bridge/notifications | GET | 알림 큐 |
| /bridge/my-notifications | GET | 내 알림 |
| /bridge/acknowledge-notification | POST | 알림 확인 |
| /bridge/escalations | GET | 에스컬레이션 |

### 4. Review Bridge (`/bridge/review-*`)
| Endpoint | Method | 프론트 연결 |
|----------|--------|------------|
| /bridge/review-queue | GET | 검토 대기 목록 |
| /bridge/review-queue/{id} | GET | 검토 상세 |
| /bridge/review-decisions | POST | 검토 결정 |
| /bridge/approve | POST | 승인 |
| /bridge/reject | POST | 반려 |
| /bridge/reopen | POST | 재오픈 |
| /bridge/review-authority | GET | 권한 목록 |

### 5. Evidence Bridge (`/bridge/evidence-*`)
| Endpoint | Method | 프론트 연결 |
|----------|--------|------------|
| /bridge/compliance-evidence | GET | 증빙 목록 |
| /bridge/upload-evidence | POST | 증빙 업로드 |
| /bridge/verify-evidence | POST | 증빙 검증 |
| /bridge/evidence-trace | GET | 법적 추적 |
| /bridge/evidence-retention | GET | 보존 정책 |

### 6. Submission Bridge (`/bridge/submissions`)
| Endpoint | Method | 프론트 연결 |
|----------|--------|------------|
| /bridge/submissions | GET | 제출 목록 |
| /bridge/filing-registry | GET | 법정제출 목록 |
| /bridge/submit-document | POST | 문서 제출 |
| /bridge/retry-submission | POST | 재제출 |

---

## 프론트엔드 신규 페이지 작업 목록

### 신규 생성 (Cursor)
| # | 페이지 | 파일명 | Bridge API | 우선순위 |
|---|--------|---------|-----------|----------|
| 1 | **Runtime Dashboard** | runtime-dashboard.html | obligations, work-orders, review-queue, notifications, escalations | ⭐ P0 |
| 2 | **Review Console** | review-console.html | review-queue, review-decisions, approve, reject, reopen | ⭐ P0 |
| 3 | **Notification Center** | notification-center.html | my-notifications, acknowledge, escalations | ⭐ P0 |
| 4 | **My Work Queue** (작업자) | my-work-queue.html | my-work-orders, my-inspection | P1 |
| 5 | **Inspection Execute** (점검수행) | inspection-execute.html | inspection-sessions, checklist, evidence, submit | P1 |
| 6 | **Evidence Manager** | evidence-manager.html | compliance-evidence, upload, verify, trace | P1 |
| 7 | **Filing Center** | filing-center.html | submissions, filing-registry, submit-document | P2 |
| 8 | **Schedule Runtime** | schedule-runtime.html | obligation-schedule-policies, work-orders | P2 |

### 기존 수정 (Cursor)
| # | 페이지 | 수정 내용 | 우선순위 |
|---|--------|----------|----------|
| 1 | safety-dashboard.html | Runtime 메트릭스 연결 | P0 |
| 2 | worker-home.html (mobile) | Runtime Queue 연결 | P1 |
| 3 | my-inspection (mobile) | Runtime Session 연결 | P1 |

---

## Cursor 작업 규칙

1. **API 호출:** `fetch('https://api.taieng.co.kr/bridge/...')` — Legacy API 절대 금지
2. **상태 변경:** Bridge API 응답의 status/data만 사용, direct DB mutation 금지
3. **대시보드 메트릭:** Bridge API에서 실시간 조회, hardcoded 값 금지
4. **Review 버튼:** `/bridge/approve`, `/bridge/reject`, `/bridge/reopen` 만 사용
5. **알림:** `/bridge/my-notifications` 조회 + `/bridge/acknowledge-notification` 확인
6. **파일명:** Cloudflare Pages 캠시 우회용 새 파일명 사용
7. **테마:** Bootstrap5 Vuexy + TAI 브랜드 CSS (`tai-brand.css`)

---

## 최종 보고

```json
{
  "phase": "RUNTIME_PRODUCTIZATION_FRONTEND_TRANSITION",
  "runtime_dashboard_enabled": false,
  "review_console_enabled": false,
  "notification_center_enabled": false,
  "worker_runtime_enabled": false,
  "document_runtime_enabled": false,
  "schedule_runtime_enabled": false,
  "snapshot_runtime_enabled": false,
  "frontend_runtime_status": "SPEC_READY_FOR_CURSOR",
  "bridge_api_count": 6,
  "bridge_endpoint_count": 35,
  "new_pages_required": 8,
  "existing_pages_migration": 3,
  "runtime_ready_for_real_users": false,
  "next_phase": "Cursor에서 P0 3페이지 우선 구현 (Dashboard, Review Console, Notification Center)"
}
```
