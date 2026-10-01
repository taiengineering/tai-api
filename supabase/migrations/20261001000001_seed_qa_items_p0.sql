-- WO-QA-CONTROL-PHASE2A-001: Initial P0 seed
-- Source: tai-qa main f2c2d175 (2026-10-01)
-- 10 scenarios confirmed from feature files:
--   features/marketing/core.feature  → P0-WWW-001/003/004/005
--   features/mypage/core.feature     → P0-MYP-001/005
--   features/search/core.feature     → P0-SRCH-001/002
--   features/diagnosis/core.feature  → P0-DIAG-001
--   features/saas/core.feature       → P0-SAAS-001
-- expected_summary = display-only. assertion SoT = tai-qa scenario code.
-- ON CONFLICT DO NOTHING — idempotent re-run safe.

INSERT INTO public.qa_items
    (scenario_id, site_code, category, name, description, expected_summary, priority, runner_type, enabled)
VALUES
    -- WWW site (taieng.co.kr) — marketing/core.feature
    ('P0-WWW-001', 'WWW', 'LANDING', '마케팅 사이트 생존',
     '비로그인 상태에서 마케팅 사이트 메인페이지에 접속한다.',
     '페이지가 정상 렌더링되고 크래시가 없다.',
     'P0', 'PLAYWRIGHT', true),

    ('P0-WWW-003', 'WWW', 'AUTH', '회원 로그인',
     'QA 마케팅 계정으로 로그인 플로우를 실행한다.',
     '로그인이 성공하고 인증 에러 알림이 없다.',
     'P0', 'PLAYWRIGHT', true),

    ('P0-WWW-004', 'WWW', 'AUTH', '로그인 후 헤더 인증 상태',
     'QA 마케팅 회원 로그인 후 메인페이지의 헤더 인증 상태를 확인한다.',
     '헤더에 마이페이지 링크와 로그아웃 버튼이 표시된다.',
     'P0', 'PLAYWRIGHT', true),

    ('P0-WWW-005', 'WWW', 'AUTH', '헤더에서 마이페이지 이동',
     'QA 마케팅 회원 로그인 후 헤더의 마이페이지 링크를 클릭한다.',
     '마이페이지 대시보드가 정상 표시된다.',
     'P0', 'PLAYWRIGHT', true),

    -- MYPAGE (taieng.co.kr/mypage) — mypage/core.feature
    ('P0-MYP-001', 'WWW', 'MYPAGE', '마이페이지 대시보드',
     'QA 마케팅 회원으로 마이페이지 대시보드에 접속한다.',
     '대시보드가 정상 표시되고 무한 로딩이 없다.',
     'P0', 'PLAYWRIGHT', true),

    ('P0-MYP-005', 'WWW', 'MYPAGE', '결제내역 조회',
     'QA 마케팅 회원으로 마이페이지 결제내역 페이지에 접속한다.',
     '결제내역 페이지가 정상 표시되고 무한 로딩이 없다.',
     'P0', 'PLAYWRIGHT', true),

    -- SEARCH (taieng.co.kr) — search/core.feature
    ('P0-SRCH-001', 'WWW', 'SEARCH', '통합검색 진입',
     '비로그인 상태에서 통합검색 페이지에 접속한다.',
     '검색 페이지가 정상 표시되고 치명적 검색 에러가 없다.',
     'P0', 'PLAYWRIGHT', true),

    ('P0-SRCH-002', 'WWW', 'SEARCH', '통합검색 섹터 순서',
     '비로그인 상태에서 QA 검색어로 통합검색을 실행한다.',
     '노출된 섹터들이 정해진 순서를 따른다.',
     'P0', 'PLAYWRIGHT', true),

    -- DIAGNOSIS (taieng.co.kr) — diagnosis/core.feature
    ('P0-DIAG-001', 'WWW', 'DIAGNOSIS', '무료 법령진단 진입',
     '비로그인 상태에서 무료 법령진단 페이지에 접속한다.',
     '페이지 정상 렌더링, 입력 UI 표시, 치명적 JS 에러 없음.',
     'P0', 'PLAYWRIGHT', true),

    -- SAFE site (safe.taieng.co.kr) — saas/core.feature
    ('P0-SAAS-001', 'SAFE', 'AUTH', 'SaaS 로그인 및 대시보드',
     'QA SaaS 계정으로 로그인 후 대시보드에 접근한다.',
     'SaaS 로그인 성공, 대시보드 정상 렌더링, 치명적 API 에러 없음.',
     'P0', 'PLAYWRIGHT', true)
ON CONFLICT (scenario_id) DO NOTHING;

-- Initial schedules: all MANUAL, disabled
-- Scheduler Phase 2-E 이전: automatic dispatch 금지 (GitHub cron과 충돌 방지)
INSERT INTO public.qa_schedules (qa_item_id, enabled, frequency_type)
SELECT id, false, 'MANUAL'
FROM   public.qa_items
WHERE  scenario_id IN (
    'P0-WWW-001', 'P0-WWW-003', 'P0-WWW-004', 'P0-WWW-005',
    'P0-MYP-001', 'P0-MYP-005',
    'P0-SRCH-001', 'P0-SRCH-002',
    'P0-DIAG-001',
    'P0-SAAS-001'
)
ON CONFLICT (qa_item_id) DO NOTHING;
