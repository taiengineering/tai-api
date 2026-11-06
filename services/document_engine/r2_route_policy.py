"""R2 route policy — server-side provision policy for 260 DOC260 documents.

Source: WO_DOC260_R2_CLASSIFICATION_MATRIX.csv
SHA256: 0a95c6a238796ab90c4be75afa8516906b6cb71f6e34eb75979057ea524971b0

Web-edit is permitted only for A_INTERNAL (route_group = "A_INTERNAL").
Provision policy is returned as READ-ONLY info; it does not modify can_create
or add new blocking conditions to POST /documents.
"""
from __future__ import annotations

from typing import Optional

# (route_group, investment_decision)
# Source: WO_DOC260_R2_CLASSIFICATION_MATRIX.csv — 260 entries, all unique doc_ids
# WO-DOC260-WEB46-C-G2: 46종 U_UNRESOLVED/HOLD → A_INTERNAL/KEEP (2026-11-05)
_POLICY: dict[str, tuple[str, str]] = {
    'DOC-BLD-001': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-002': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-003': ("F_SCOPE_OUT", "STOP"),
    'DOC-BLD-004': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-005': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-006': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-007': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-008': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-009': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-010': ("F_SCOPE_OUT", "STOP"),
    'DOC-BLD-011': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-012': ("F_SCOPE_OUT", "STOP"),
    'DOC-BLD-013': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-014': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-015': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-016': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-017': ("F_SCOPE_OUT", "STOP"),
    'DOC-BLD-018': ("F_SCOPE_OUT", "STOP"),
    'DOC-BLD-019': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-020': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-021': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-022': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-023': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-024': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-025': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-026': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-027': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-028': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-029': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-030': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-031': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-032': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-033': ("E_EXTERNAL", "STOP"),
    'DOC-BLD-034': ("E_EXTERNAL", "STOP"),
    'DOC-BLD-035': ("E_EXTERNAL", "STOP"),
    'DOC-BLD-036': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-037': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-038': ("E_EXTERNAL", "STOP"),
    'DOC-BLD-039': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-040': ("A_INTERNAL", "KEEP"),
    'DOC-BLD-041': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-042': ("E_EXTERNAL", "STOP"),
    'DOC-BLD-043': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-044': ("U_UNRESOLVED", "HOLD"),
    'DOC-BLD-045': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-001': ("F_SCOPE_OUT", "STOP"),
    'DOC-CHEM-002': ("F_SCOPE_OUT", "STOP"),
    'DOC-CHEM-003': ("A_INTERNAL", "KEEP"),
    'DOC-CHEM-004': ("F_SCOPE_OUT", "STOP"),
    'DOC-CHEM-005': ("F_SCOPE_OUT", "STOP"),
    'DOC-CHEM-006': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-007': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-008': ("A_INTERNAL", "KEEP"),
    'DOC-CHEM-009': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-010': ("F_SCOPE_OUT", "STOP"),
    'DOC-CHEM-011': ("F_SCOPE_OUT", "STOP"),
    'DOC-CHEM-012': ("F_SCOPE_OUT", "STOP"),
    'DOC-CHEM-013': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-014': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-015': ("B_OFFICIAL", "STOP"),
    'DOC-CHEM-016': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-017': ("B_OFFICIAL", "STOP"),
    'DOC-CHEM-018': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-019': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-020': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-021': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-022': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-023': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-024': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-025': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-026': ("U_UNRESOLVED", "HOLD"),
    'DOC-CHEM-027': ("U_UNRESOLVED", "HOLD"),
    'DOC-CON-001': ("U_UNRESOLVED", "HOLD"),
    'DOC-CON-002': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-003': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-004': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-005': ("U_UNRESOLVED", "HOLD"),
    'DOC-CON-006': ("A_INTERNAL", "KEEP"),
    'DOC-CON-007': ("A_INTERNAL", "KEEP"),
    'DOC-CON-008': ("A_INTERNAL", "KEEP"),
    'DOC-CON-009': ("U_UNRESOLVED", "HOLD"),
    'DOC-CON-010': ("A_INTERNAL", "KEEP"),
    'DOC-CON-011': ("A_INTERNAL", "KEEP"),
    'DOC-CON-012': ("A_INTERNAL", "KEEP"),
    'DOC-CON-013': ("A_INTERNAL", "KEEP"),
    'DOC-CON-014': ("A_INTERNAL", "KEEP"),
    'DOC-CON-015': ("A_INTERNAL", "KEEP"),
    'DOC-CON-016': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-017': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-018': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-019': ("A_INTERNAL", "KEEP"),
    'DOC-CON-020': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-021': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-022': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-023': ("A_INTERNAL", "KEEP"),
    'DOC-CON-024': ("A_INTERNAL", "KEEP"),
    'DOC-CON-025': ("A_INTERNAL", "KEEP"),
    'DOC-CON-026': ("A_INTERNAL", "KEEP"),
    'DOC-CON-027': ("A_INTERNAL", "KEEP"),
    'DOC-CON-028': ("A_INTERNAL", "KEEP"),
    'DOC-CON-029': ("A_INTERNAL", "KEEP"),
    'DOC-CON-031': ("A_INTERNAL", "KEEP"),
    'DOC-CON-032': ("A_INTERNAL", "KEEP"),
    'DOC-CON-033': ("A_INTERNAL", "KEEP"),
    'DOC-CON-034': ("U_UNRESOLVED", "HOLD"),
    'DOC-CON-035': ("A_INTERNAL", "KEEP"),
    'DOC-CON-036': ("A_INTERNAL", "KEEP"),
    'DOC-CON-037': ("A_INTERNAL", "KEEP"),
    'DOC-CON-038': ("A_INTERNAL", "KEEP"),
    'DOC-CON-039': ("A_INTERNAL", "KEEP"),
    'DOC-CON-040': ("A_INTERNAL", "KEEP"),
    'DOC-CON-041': ("A_INTERNAL", "KEEP"),
    'DOC-CON-042': ("A_INTERNAL", "KEEP"),
    'DOC-CON-043': ("A_INTERNAL", "KEEP"),
    'DOC-CON-044': ("A_INTERNAL", "KEEP"),
    'DOC-CON-045': ("A_INTERNAL", "KEEP"),
    'DOC-CON-046': ("E_EXTERNAL", "STOP"),
    'DOC-CON-047': ("A_INTERNAL", "KEEP"),
    'DOC-CON-048': ("A_INTERNAL", "KEEP"),
    'DOC-CON-049': ("A_INTERNAL", "KEEP"),
    'DOC-CON-050': ("A_INTERNAL", "KEEP"),
    'DOC-CON-051': ("A_INTERNAL", "KEEP"),
    'DOC-CON-LAW-001': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-LAW-002': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-LAW-003': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-LAW-004': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-LAW-005': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-LAW-006': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-LAW-007': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-LAW-008': ("U_UNRESOLVED", "HOLD"),
    'DOC-CON-LAW-009': ("U_UNRESOLVED", "HOLD"),
    'DOC-CON-LAW-010': ("U_UNRESOLVED", "HOLD"),
    'DOC-CON-LAW-011': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-LAW-012': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-LAW-013': ("F_SCOPE_OUT", "STOP"),
    'DOC-CON-LAW-014': ("A_INTERNAL", "KEEP"),
    'DOC-CON-LAW-015': ("A_INTERNAL", "KEEP"),
    'DOC-FAC-001': ("U_UNRESOLVED", "HOLD"),
    'DOC-FAC-002': ("A_INTERNAL", "KEEP"),
    'DOC-FAC-003': ("F_SCOPE_OUT", "STOP"),
    'DOC-FAC-004': ("U_UNRESOLVED", "HOLD"),
    'DOC-FAC-005': ("A_INTERNAL", "KEEP"),
    'DOC-FAC-006': ("U_UNRESOLVED", "HOLD"),
    'DOC-FAC-007': ("A_INTERNAL", "KEEP"),
    'DOC-FAC-008': ("A_INTERNAL", "KEEP"),
    'DOC-FAC-009': ("F_SCOPE_OUT", "STOP"),
    'DOC-FAC-010': ("U_UNRESOLVED", "HOLD"),
    'DOC-FAC-011': ("U_UNRESOLVED", "HOLD"),
    'DOC-FAC-012': ("U_UNRESOLVED", "HOLD"),
    'DOC-FAC-013': ("A_INTERNAL", "KEEP"),
    'DOC-FAC-014': ("F_SCOPE_OUT", "STOP"),
    'DOC-FAC-015': ("U_UNRESOLVED", "HOLD"),
    'DOC-FAC-016': ("A_INTERNAL", "KEEP"),
    'DOC-FAC-017': ("F_SCOPE_OUT", "STOP"),
    'DOC-FAC-018': ("U_UNRESOLVED", "HOLD"),
    'DOC-FAC-019': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-020': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-021': ("E_EXTERNAL", "STOP"),
    'DOC-FAC-022': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-023': ("A_INTERNAL", "KEEP"),
    'DOC-FAC-024': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-025': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-026': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-027': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-028': ("E_EXTERNAL", "STOP"),
    'DOC-FAC-029': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-030': ("A_INTERNAL", "KEEP"),
    'DOC-FAC-031': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-032': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-033': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-034': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-035': ("B_OFFICIAL", "STOP"),
    'DOC-FAC-036': ("E_EXTERNAL", "STOP"),
    'DOC-OSH-001': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-002': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-003': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-004': ("F_SCOPE_OUT", "STOP"),
    'DOC-OSH-005': ("F_SCOPE_OUT", "STOP"),
    'DOC-OSH-006': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-007': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-008': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-009': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-010': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-011': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-012': ("F_SCOPE_OUT", "STOP"),
    'DOC-OSH-013': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-014': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-015': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-016': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-017': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-018': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-019': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-020': ("F_SCOPE_OUT", "STOP"),
    'DOC-OSH-021': ("F_SCOPE_OUT", "STOP"),
    'DOC-OSH-022': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-023': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-024': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-025': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-026': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-027': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-028': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-029': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-030': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-031': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-032': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-033': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-034': ("F_SCOPE_OUT", "STOP"),
    'DOC-OSH-035': ("F_SCOPE_OUT", "STOP"),
    'DOC-OSH-036': ("F_SCOPE_OUT", "STOP"),
    'DOC-OSH-037': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-038': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-039': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-040': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-041': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-042': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-043': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-044': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-045': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-046': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-047': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-048': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-049': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-050': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-051': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-052': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-053': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-054': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-055': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-056': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-057': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-058': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-059': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-061': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-062': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-063': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-064': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-065': ("B_OFFICIAL", "STOP"),
    'DOC-OSH-066': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-067': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-068': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-069': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-070': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-071': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-072': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-073': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-074': ("U_UNRESOLVED", "HOLD"),
    'DOC-OSH-075': ("A_INTERNAL", "KEEP"),
    'DOC-OSH-076': ("A_INTERNAL", "KEEP"),
    'DOC-SERA-001': ("A_INTERNAL", "KEEP"),
    'DOC-SERA-002': ("A_INTERNAL", "KEEP"),
    'DOC-SERA-003': ("A_INTERNAL", "KEEP"),
    'DOC-SERA-004': ("A_INTERNAL", "KEEP"),
    'DOC-SERA-005': ("A_INTERNAL", "KEEP"),
    'DOC-SERA-006': ("A_INTERNAL", "KEEP"),
    'DOC-SERA-007': ("A_INTERNAL", "KEEP"),
    'DOC-SERA-008': ("A_INTERNAL", "KEEP"),
    'DOC-SERA-009': ("U_UNRESOLVED", "HOLD"),
    'DOC-SERA-010': ("A_INTERNAL", "KEEP"),
    'DOC-SERA-011': ("U_UNRESOLVED", "HOLD"),
    'DOC-SERA-012': ("A_INTERNAL", "KEEP"),
}

# B_OFFICIAL 16종 official_status
# CONDITIONAL_APPROVED (5종): Batch01 원본 동일성 PASS 확인 — 다운로드 허용
# HOLD (5종): 제공 보류
#   FAC-024, FAC-029, OSH-065: Owner 결정 대기
#   CHEM-017: 원본 동일성 미확정 (Batch01 PLAUSIBLE) — 확인 완료 전 제공 보류
#   FAC-019: 원본 미확보 (Batch01 UNRESOLVED) — 파일 없으므로 자연 차단됨, 명시적 HOLD 불필요
#       └→ policy는 CONDITIONAL_APPROVED 유지, storage에 파일 없어 Gate 5에서 404 처리됨
# MISMATCH (6종): Batch01 검증 결과 등록 파일이 다른 서식 — 올바른 파일 확보 전 제공 차단
#   FAC-031~035: flSeq=158967451 → 에너지이용합리화법 별지 제19호서식(설치검사증) — 의도한 서식 아님
#   CHEM-015: flSeq 불일치 확인됨 (Batch01 Task B 결과)
_OFFICIAL_STATUS: dict[str, str] = {
    'DOC-CHEM-015': "MISMATCH",
    'DOC-CHEM-017': "HOLD",
    'DOC-FAC-019': "CONDITIONAL_APPROVED",
    'DOC-FAC-020': "CONDITIONAL_APPROVED",
    'DOC-FAC-022': "CONDITIONAL_APPROVED",
    'DOC-FAC-024': "HOLD",
    'DOC-FAC-025': "CONDITIONAL_APPROVED",
    'DOC-FAC-026': "CONDITIONAL_APPROVED",
    'DOC-FAC-027': "CONDITIONAL_APPROVED",
    'DOC-FAC-029': "HOLD",
    'DOC-FAC-031': "MISMATCH",
    'DOC-FAC-032': "MISMATCH",
    'DOC-FAC-033': "MISMATCH",
    'DOC-FAC-034': "MISMATCH",
    'DOC-FAC-035': "MISMATCH",
    'DOC-OSH-065': "HOLD",
}

_WEB_EDIT_ALLOWED_GROUP = "A_INTERNAL"

# U_UNRESOLVED 제출 경로 분류 (WP-C, WP-03 조사 결과 기반 READ-ONLY 표시 주석)
# 출처: WP-03 document_submission_analysis.csv — 확인된 항목만 등록
# 미등록 U_UNRESOLVED → None (NOT_MAPPED): WP-03 조사 미완료 또는 미분류
#
# G1_DUAL_PATH        : TAI 작성·저장 + 외부 제출 별도 (이중경로 확인)
# G2_PORTAL_CONFIRMED : 기관 포털 연결 확인됨 (M8 구현 완료)
# G2_PORTAL_CANDIDATE : 기관 포털 URL 확인됨 (M8 미구현, 고객 직접 접속 필요)
# G3_AGENCY_CHANNEL   : 팝빌/이메일이 유일한 제출 채널, 별도 기관 포털 없음
# G6_UNRESOLVED       : WP-03에서 명시 미확정 분류 (별도 목록 확인 필요)
# None                : WP-03 조사 대상이나 미분류 (NOT_MAPPED)
_SUBMISSION_CATEGORY: dict[str, str] = {
    # G2_PORTAL_CONFIRMED: M8 포털 버튼 구현 완료 (2종)
    'DOC-BLD-001': 'G2_PORTAL_CONFIRMED',
    'DOC-CON-009': 'G2_PORTAL_CONFIRMED',
    # G2_PORTAL_CANDIDATE: 기관 포털 URL 확인됨, M8 미구현 (23종)
    # 접수기관·URL 검증 2026-11-04 (에이전트 조사 기반)
    # ※ BLD-008 접수기관 보정: safety.kesco.or.kr(KESCO)→keea.or.kr(한국전기기술인협회)
    # ※ BLD-013 도메인 보정: elsafe.or.kr→elevator.go.kr(국가승강기정보센터·KOELSA운영)
    # ※ CHEM-009 도메인 보정: icis.me.go.kr→icis.mcee.go.kr(화관법민원24, 환경부)
    # ※ FAC-001 분기: 도시가스(법)→지자체, LPG(법)→cyber.kgs.or.kr — Owner 결정 대기
    # ※ OSH-008/033 제조업 URL: portal.kosha.or.kr 로그인 후 메뉴 탐색 필요 (공동인증서)
    'DOC-CON-005': 'G2_PORTAL_CANDIDATE',   # 착공신고서 (www.eais.go.kr 세움터)
    'DOC-BLD-008': 'G2_PORTAL_CANDIDATE',   # 전기안전관리자 선임신고서 (keea.or.kr — KEEA, 정부24 확인)
    'DOC-BLD-013': 'G2_PORTAL_CANDIDATE',   # 승강기 사고 보고서 (elevator.go.kr — KOELSA 운영)
    'DOC-CHEM-009': 'G2_PORTAL_CANDIDATE',  # 유해화학물질 관리자 선임신고서 (icis.mcee.go.kr — 화관법민원24)
    'DOC-FAC-001': 'G2_PORTAL_CANDIDATE',   # 가스안전관리자 선임신고서 (cyber.kgs.or.kr — LPG, 도시가스는 지자체)
    'DOC-FAC-012': 'G2_PORTAL_CANDIDATE',   # 보일러 관리자 선임신고서 (min24.energy.or.kr — 한국에너지공단)
    'DOC-OSH-003': 'G2_PORTAL_CANDIDATE',   # 산업재해조사표 (labor.moel.go.kr, AH038)
    'DOC-OSH-008': 'G2_PORTAL_CANDIDATE',   # 유해위험방지계획서 — 제조업 (portal.kosha.or.kr, URL HOLD)
    'DOC-OSH-009': 'G2_PORTAL_CANDIDATE',   # 안전관리자 선임보고서 (labor.moel.go.kr, AD032)
    'DOC-OSH-010': 'G2_PORTAL_CANDIDATE',   # 보건관리자 선임보고서 (labor.moel.go.kr, AD032)
    'DOC-OSH-011': 'G2_PORTAL_CANDIDATE',   # 산업보건의 선임보고서 (labor.moel.go.kr, AD032)
    'DOC-OSH-019': 'G2_PORTAL_CANDIDATE',   # 산업재해발생보고서 (labor.moel.go.kr, AH038 통합 여부 미확인)
    'DOC-OSH-023': 'G2_PORTAL_CANDIDATE',   # 안전관리자 선임신고서 (labor.moel.go.kr, AD032)
    'DOC-OSH-024': 'G2_PORTAL_CANDIDATE',   # 보건관리자 선임신고서 (labor.moel.go.kr, AD032)
    'DOC-OSH-025': 'G2_PORTAL_CANDIDATE',   # 산업보건의 선임신고서 (labor.moel.go.kr, AD032)
    'DOC-OSH-026': 'G2_PORTAL_CANDIDATE',   # 안전관리자 변경신고서 (labor.moel.go.kr, 변경 form 코드 미확인)
    'DOC-OSH-027': 'G2_PORTAL_CANDIDATE',   # 보건관리자 변경신고서 (labor.moel.go.kr, 변경 form 코드 미확인)
    'DOC-OSH-028': 'G2_PORTAL_CANDIDATE',   # 산업보건의 변경신고서 (labor.moel.go.kr, 변경 form 코드 미확인)
    'DOC-OSH-029': 'G2_PORTAL_CANDIDATE',   # 안전관리자 해임신고서 (labor.moel.go.kr, SN113)
    'DOC-OSH-030': 'G2_PORTAL_CANDIDATE',   # 보건관리자 해임신고서 (labor.moel.go.kr, SN113)
    'DOC-OSH-031': 'G2_PORTAL_CANDIDATE',   # 산업보건의 해임신고서 (labor.moel.go.kr, SN113)
    'DOC-OSH-032': 'G2_PORTAL_CANDIDATE',   # 산업재해조사표 제출서 (labor.moel.go.kr, AH038)
    'DOC-OSH-033': 'G2_PORTAL_CANDIDATE',   # 유해위험방지계획서 제출서 — 제조업 (portal.kosha.or.kr, URL HOLD)
    # G3_AGENCY_CHANNEL: 팝빌/이메일이 유일한 제출 채널, 별도 기관 포털 없음 (4종)
    'DOC-BLD-004': 'G3_AGENCY_CHANNEL',     # 소방안전관리자 선임신고서 (소방서, 팝빌)
    'DOC-CHEM-006': 'G3_AGENCY_CHANNEL',    # 화학사고 즉시신고서 (지방환경관서, 팝빌)
    'DOC-CON-LAW-010': 'G3_AGENCY_CHANNEL', # 정기안전점검 결과보고서 (발주청/안전원, 이메일)
    'DOC-OSH-018': 'G3_AGENCY_CHANNEL',     # 사고보고서 (고용노동부, 팝빌)
    # G1_DUAL_PATH: TAI 작성·저장 + 외부 제출 별도 (이중경로 확인, 12종)
    'DOC-BLD-015': 'G1_DUAL_PATH',
    'DOC-CON-034': 'G1_DUAL_PATH',
    'DOC-SERA-011': 'G1_DUAL_PATH',
    'DOC-CON-001': 'G1_DUAL_PATH',
    'DOC-CON-LAW-008': 'G1_DUAL_PATH',
    'DOC-CON-LAW-009': 'G1_DUAL_PATH',
    'DOC-FAC-004': 'G1_DUAL_PATH',
    'DOC-FAC-006': 'G1_DUAL_PATH',
    'DOC-FAC-011': 'G1_DUAL_PATH',
    'DOC-FAC-015': 'G1_DUAL_PATH',
    'DOC-FAC-018': 'G1_DUAL_PATH',
    'DOC-SERA-009': 'G1_DUAL_PATH',
}

# WO-DOC260-WEB46-C-G2: A_INTERNAL로 전환된 46종 중 HWP 원본 다운로드 병행 제공 예외 (6종).
# 이 6종은 Storage form-originals/doc_forms/ 에 HWP 파일을 보유하므로
# A_INTERNAL 전환 후에도 기존 다운로드 엔드포인트를 허용한다.
# 이 집합 외 모든 A_INTERNAL 문서의 다운로드는 차단한다.
_SOURCE_DOWNLOAD_EXCEPTION_IDS: frozenset[str] = frozenset({
    "DOC-BLD-011",
    "DOC-CON-047",
    "DOC-CON-048",
    "DOC-CON-049",
    "DOC-CON-050",
    "DOC-CON-051",
})


def get_provision_policy(doc_id: str) -> Optional[dict]:
    """Return R2 provision policy for a doc_id, or None if not in the matrix.

    Returns:
        {
          "doc_id": str,
          "route_group": str,        # A_INTERNAL | B_OFFICIAL | E_EXTERNAL | F_SCOPE_OUT | U_UNRESOLVED
          "investment_decision": str, # KEEP | STOP | HOLD
          "official_status": str | None,  # CONDITIONAL_APPROVED | HOLD — B_OFFICIAL only, else None
          "web_edit_allowed": bool,  # True only for A_INTERNAL
          "submission_category": str | None,
              # U_UNRESOLVED: G1_DUAL_PATH | G2_PORTAL_CONFIRMED | G2_PORTAL_CANDIDATE
              #               | G3_AGENCY_CHANNEL | G6_UNRESOLVED
              #   None (NOT_MAPPED) if WP-03 research incomplete or doc not yet classified
              # non-U_UNRESOLVED: always None
          "source_download_exception": bool,
              # True only for A_INTERNAL docs in _SOURCE_DOWNLOAD_EXCEPTION_IDS (6종).
              # Controls HWP download permission alongside Storage file availability.
        }
        None if doc_id is not registered in the R2 matrix.
    """
    entry = _POLICY.get(doc_id)
    if entry is None:
        return None
    route_group, investment_decision = entry
    if route_group == "U_UNRESOLVED":
        submission_category = _SUBMISSION_CATEGORY.get(doc_id)  # None = NOT_MAPPED (WP-03 미분류)
    else:
        submission_category = None
    return {
        "doc_id": doc_id,
        "route_group": route_group,
        "investment_decision": investment_decision,
        "official_status": _OFFICIAL_STATUS.get(doc_id),
        "web_edit_allowed": route_group == _WEB_EDIT_ALLOWED_GROUP,
        "submission_category": submission_category,
        "source_download_exception": (
            route_group == "A_INTERNAL"
            and doc_id in _SOURCE_DOWNLOAD_EXCEPTION_IDS
        ),
    }


def get_all_policies() -> dict[str, dict]:
    """Return all 260 policies. Used for impact analysis."""
    return {
        doc_id: {
            "doc_id": doc_id,
            "route_group": rg,
            "investment_decision": inv,
            "official_status": _OFFICIAL_STATUS.get(doc_id),
            "web_edit_allowed": rg == _WEB_EDIT_ALLOWED_GROUP,
            "source_download_exception": (
                rg == "A_INTERNAL" and doc_id in _SOURCE_DOWNLOAD_EXCEPTION_IDS
            ),
        }
        for doc_id, (rg, inv) in _POLICY.items()
    }


def policy_count() -> dict[str, int]:
    """Return counts by route_group. Used for audit."""
    from collections import Counter
    return dict(Counter(rg for rg, _ in _POLICY.values()))
