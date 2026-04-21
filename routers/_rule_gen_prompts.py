"""law_rule_generator 라우터에서 사용하는 AI 프롬프트 및 상수.
별도 파일로 분리하여 라우터 크기 축소.
"""

FEW_SHOT_RULE = {
    "draft_rule_id": "FIREACT-001-BLD",
    "obligation_type": "APPOINT",
    "sector": "BUILDING",
    "condition_code": "building_area",
    "condition_operator": "gte",
    "condition_value": "400",
    "obligation_summary": "소방안전관리자 선임 의무",
    "penalty_summary": "미선임 시 300만원 이하 과태료 (제53조)",
    "penalty_value": 300,
    "form_code": "NFA-별지제5호",
    "form_name": "소방안전관리자 선임신고서",
    "submit_org_code": "nfa",
    "due_days": 14,
    "report_method_code": "online",
    "report_method_std": "api",
    "appointment_target": "소방안전관리자",
    "appointment_qualification_code": "fire_safety_1",
    "appointment_qualification_level_code": "grade1",
    "appointment_count_value": 1,
    "inspection_cycle_value": 6,
    "inspection_cycle_unit_code": "month",
    "cycle_base_guide": "최초 선임일로부터 6개월마다",
    "online_system": "소방청 민원 시스템",
    "system_url": "https://www.safetykorea.go.kr",
    "tai_feature_code": "APPOINTMENT",
    "remarks": "연면적 400㎡ 이상 특정소방대상물",
    "diagnosis_stage": 1,
    "ai_confidence": 95,
    "ai_reasoning": "화재예방법 제24조 + 시행령 제22조 별표4 기준",
    "ai_flags": [],
}

SYSTEM_PROMPT = """당신은 한국 산업안전 법령 전문가입니다.
법령 원문(본조+시행령+별표+벌칙)을 분석하여 안전관리 시스템의 판정 룰을 JSON 형식으로 추출합니다.

추출 대상 의무 유형:
- APPOINT: 안전관리자·소방안전관리자 등 선임 의무
- INSPECT: 정기점검·안전검사 의무
- NOTIFY: 신고·보고·제출 의무
- REPORT: 기록·보존 의무
- ACTION: 조치·설치·이행 의무

조건 코드 (condition_code) 목록 (정확히 아래에서만 선택):
- building_area: 건물 연면적 (㎡)
- worker_count: 근로자 수 (명)
- electric_capacity: 전기 수전용량 (kW)
- electrical_capacity_kw: 전기 수전용량 (kW, 동의어)
- gas_capacity_kg: LPG 저장량 (kg)
- gas_capacity_m3: 도시가스 사용량 (㎥/시)
- boiler_capacity_kw: 보일러 용량 (kW)
- boiler_capacity_th: 보일러 용량 (ton/hr)
- elevator_count: 승강기 대수
- is_hazardous_material: 위험물 취급 여부 (0/1)
- annual_energy_toe: 연간 에너지 사용량 (TOE)
- construction_amount: 공사금액 (원)
- floor_count: 건물 층수
- is_factory_registered: 공장등록 여부 (0/1)
- employee_count: 상시근로자 수 (명)
- contract_amount: 공사금액 (원, 동의어)
- has_chemical_substance: 화학물질 취급 여부 (0/1)
- is_multi_use: 다중이용업소 여부 (0/1)
- contractor_count: 수급업체 수
- has_high_pressure_gas: 고압가스 취급 여부 (0/1)
- transformer_capacity_kva: 변압기 용량 (kVA)
- has_boiler: 보일러 보유 여부 (0/1)
- hospital_beds: 병상 수
- student_count: 학생 수

섹터 코드 (반드시 아래 4가지 중 하나만 사용):
- BUILDING: 건물·시설 (업무용·판매용·숙박·근린생활 등 일반 건축물)
- MANUFACTURING: 공장·제조업
- CONSTRUCTION: 건설현장
- COMMON: 전 섹터 공통
- CONSTRUCTION_MANUFACTURING: 건설+제조 공통

⚠️ 주의: 학교·병원·사회복지시설 등 특수시설 전용 법령은 건너뜁니다.
  해당 법령(의료법·학교안전법·사회복지사업법 등)의 조문에서 의무가 발견되면 []을 반환하세요.

submit_org_code는 반드시 아래 중 하나만 사용:
- kosha, local_gov, moel, me, kgs, mlit, nfa, kesco

condition_code가 있으면 condition_operator + condition_value를 함께 채웁니다.
inspection_required=true이면 inspection_cycle_value + inspection_cycle_unit_code를 채웁니다.
report_required=true이면 report_method_code를 채웁니다.
appointment_required=true이면 appointment_qualification_code를 채웁니다.
penalty_summary가 있으면 penalty_value(만원)를 가능한 범위에서 채웁니다.

응답은 반드시 순수 JSON 배열만 출력하세요. 마크다운/설명 금지.
의무가 없는 조문은 빈 배열 []을 반환하세요."""

USER_PROMPT_TEMPLATE = """다음 법령 조문을 분석하여 판정 룰을 추출해주세요.

법령명: {law_name}
핵심 조문: {article_text}

[풀 컨텍스트]
{full_context}

[좋은 예시 1개]
{few_shot}

위 조문에서 안전관리 의무(선임·점검·신고·보고·조치)를 추출하여 다음 JSON 형식으로 반환하세요.
의무가 없는 조문이면 []을 반환하세요.

[
  {{
    "draft_rule_id": "법령약어-번호-섹터약어 (예: FIREACT-001-BLD)",
    "obligation_type": "APPOINT|INSPECT|NOTIFY|REPORT|ACTION",
    "sector": "BUILDING|MANUFACTURING|CONSTRUCTION|COMMON|CONSTRUCTION_MANUFACTURING",
    "condition_code": "위 목록에서 선택 또는 null",
    "condition_operator": "gte|lte|gt|lt|eq",
    "condition_value": "숫자 문자열 또는 null",
    "obligation_summary": "의무 내용 1줄 요약 (최대 100자)",
    "remarks": "맥락 설명 (최대 100자)",
    "penalty_summary": "위반 시 벌칙 요약 또는 null",
    "penalty_value": "과태료 숫자 (만원 단위) 또는 null",
    "form_code": "별지서식 번호 또는 null",
    "form_name": "서식명 또는 null",
    "submit_org_code": "kosha|local_gov|moel|me|kgs|mlit|nfa|kesco 중 선택 또는 null",
    "due_days": "기한 일수 숫자 또는 null",
    "report_method_code": "online|offline|both 또는 null",
    "report_method_std": "api|paper|keep 또는 null",
    "online_system": "온라인 시스템명 또는 null",
    "system_url": "시스템 URL 또는 null",
    "appointment_qualification_code": "자격 코드 또는 null",
    "appointment_qualification_level_code": "자격 등급 또는 null",
    "appointment_count_value": "선임 인원수 또는 null",
    "inspection_cycle_value": "점검 주기 숫자 또는 null",
    "inspection_cycle_unit_code": "day|week|month|quarter|half_year|year 또는 null",
    "cycle_base_guide": "주기 설명 (최대 50자) 또는 null",
    "tai_feature_code": "APPOINTMENT|INSPECTION|REPORT|EDUCATION|DOCUMENT|FIX|CHECKLIST 또는 null",
    "appointment_target": "선임 대상자명 (APPOINT인 경우만) 또는 null",
    "appointment_required": "true|false",
    "inspection_required": "true|false",
    "notify_required": "true|false",
    "report_required": "true|false",
    "action_required": "true|false",
    "diagnosis_stage": 1,
    "ai_confidence": 0~100,
    "ai_reasoning": "판단 근거 1~2줄",
    "ai_flags": ["주의사항1"]
  }}
]"""
