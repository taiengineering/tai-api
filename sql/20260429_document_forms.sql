-- document_forms table (engine-document v2)
-- Created from docs/WORKORDER_ENGINE_DOCUMENT_V2.md (Phase 1)

CREATE TABLE IF NOT EXISTS document_forms (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  doc_id TEXT UNIQUE NOT NULL,
  doc_name TEXT NOT NULL,
  sector TEXT NOT NULL,
  category TEXT NOT NULL,
  law_ref TEXT,
  regulation_ref TEXT,
  obligation TEXT DEFAULT '법정필수',
  penalty TEXT,
  submit_to TEXT,
  submit_timing TEXT,
  retention TEXT,
  writer TEXT,
  frequency TEXT,
  tai_grade TEXT DEFAULT 'X',
  tai_difficulty TEXT DEFAULT 'X',
  ticket_cost INTEGER DEFAULT 0,
  existing_data TEXT,
  additional_input TEXT,
  priority INTEGER DEFAULT 5,
  note TEXT,
  file_url TEXT,
  tab_type TEXT DEFAULT '법정서식',
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_forms_sector ON document_forms(sector);
CREATE INDEX IF NOT EXISTS idx_document_forms_category ON document_forms(category);
CREATE INDEX IF NOT EXISTS idx_document_forms_tai_grade ON document_forms(tai_grade);
CREATE INDEX IF NOT EXISTS idx_document_forms_tab_type ON document_forms(tab_type);

