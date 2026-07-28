-- WO-5 SoftDelete: 휴지통용 deleted_at 컬럼 (Goal G-ms4je4z3-33eada)
-- is_active(정지/재개)와 별개. deleted_at IS NULL=정상, NOT NULL=휴지통. 물리삭제 안 함.
ALTER TABLE public.companies        ADD COLUMN IF NOT EXISTS deleted_at timestamptz;
ALTER TABLE public.factories        ADD COLUMN IF NOT EXISTS deleted_at timestamptz;
ALTER TABLE public.users            ADD COLUMN IF NOT EXISTS deleted_at timestamptz;
ALTER TABLE public.company_contacts ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_companies_active        ON public.companies(id)        WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_factories_active        ON public.factories(id)        WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_users_active            ON public.users(id)            WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_company_contacts_active ON public.company_contacts(id) WHERE deleted_at IS NULL;

COMMENT ON COLUMN public.companies.deleted_at IS 'WO-5 소프트삭제 마킹. NULL=정상, NOT NULL=휴지통(복구 가능).';