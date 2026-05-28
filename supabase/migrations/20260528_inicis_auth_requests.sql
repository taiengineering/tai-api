-- KG이니시스 통합인증(SA) 요청·결과 저장
CREATE TABLE IF NOT EXISTS inicis_auth_requests (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    mtx_id text NOT NULL UNIQUE,
    svc_code text,
    status text DEFAULT 'REQUESTED',
    tx_id text,
    svc_cd text,
    provider_dev_cd text,
    user_name text,
    user_phone text,
    user_birthday text,
    user_ci text,
    user_di text,
    user_gender text,
    result_msg text,
    verified_at timestamptz,
    created_at timestamptz DEFAULT now(),
    user_id uuid,
    company_id uuid
);

CREATE INDEX IF NOT EXISTS idx_inicis_auth_mtxid ON inicis_auth_requests(mtx_id);
CREATE INDEX IF NOT EXISTS idx_inicis_auth_ci ON inicis_auth_requests(user_ci);

COMMENT ON TABLE inicis_auth_requests IS 'KG이니시스 통합인증서비스(SA) 요청/결과';
