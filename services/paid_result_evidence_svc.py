"""services/paid_result_evidence_svc.py — DETERMINISTIC ARTICLE EVIDENCE RESOLVER v1

PAID-DIAGNOSIS-VALUE-REBUILD-01 · STEP4C-2 PKG-2B

WHAT THIS IS
    저장된 LEG 결과가 이미 갖고 있는 세 값만으로 public.law_article 의 정확한
    조문 행 하나를 식별하는 내부 계층.

        normalized_obligations[].legal.law_name
        normalized_obligations[].legal.law_article
        normalized_obligations[].legal.evidence
                      |
                      v
        public.law_master  +  public.law_article   (batch read, 2 roundtrip)
                      |
                      v
        EXACT_EVIDENCE_SUBSTRING_V1
                      |
                      v
        paid_result_evidence_v1

WHY EVIDENCE IS THE KEY
    (law_name, article_no) 만으로는 조문을 특정할 수 없다. 저장된 law_article 은
    맨 숫자("221")이고, DB 의 제221조 · 제221조의2 · … · 제221조의5 는 전부
    article_no = 221 로 모인다. enforcement_date 도 같아서 정렬 tie-break 가
    무효다. 그래서 조문 번호만 쓰면 임의의 한 행을 고르게 된다.

    저장된 evidence 는 엔진이 조문 원문에서 잘라 온 문자열이다. 그 문자열이
    어느 조문 원문 안에 그대로 들어 있는지를 보면 의2 · 의3 이 분리된다.
    이것은 의미 유사도가 아니라 공백만 정규화한 문자열 포함 관계다.

NOT A SEMANTIC MATCH — 이 모듈이 하지 않는 것
    LLM · 임베딩 · 유사도 점수 · 형태소 분석 · 동의어 · 어간 추출 ·
    구두점 정규화 · 한글 정규화(NFC/NFD 변환) · 부분 점수 · 최고점 선택.
    전부 0 이다. 판정은 "포함되는가 / 아닌가" 두 값뿐이다.

FAIL CLOSED
    후보가 2개 이상 맞으면 고르지 않는다. 첫 행 · 최신 enforcement_date ·
    최소 article_sub_no 중 어느 것도 선택 근거가 아니다. 애매하면 UNRESOLVED 다.
    틀린 조문을 자신 있게 보여주는 것이 조문을 못 찾는 것보다 나쁘다.

경계 (STEP4C-2 PKG-2B 작업지시)
    PUBLIC ROUTE = 0 · ROUTER MOUNT = 0 · DB MUTATION = 0
    MATERIALIZER 변경 = 0 · PRODUCT CONTRACT 변경 = 0
    routers/law_viewer.py 재사용 = 0 (미마운트 · scalar N+1 · ILIKE fallback ·
        limit(1) 임의 선택 — 되살릴 대상이 아니다)
    판례 = 구현 0 (authoritative relation key 가 없다)
    law.go.kr URL = 생성 0 (저장된 정본 URL 이 없다. 추측 생성 금지)
    이번 PKG 에서는 Product Contract 에 attach 하지 않는다.

CUSTOMER BOUNDARY
    provenance 블록은 내부 추적용이다. 고객 화면에 law_article_id ·
    law_version_id · match_rule · source_table · unresolved reason 의 raw enum 을
    그대로 내보내지 않는다. 표시 문구는 tai-www 가 정한다 — 이 모듈은
    한국어 presentation 문장을 만들지 않는다. "제221조의5" 같은 조문 표기도
    여기서 만들지 않고, article_no · article_sub_no 구조만 넘긴다.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

EVIDENCE_VERSION = 1

RESOLUTION_RULE = "EXACT_EVIDENCE_SUBSTRING_V1"
MATCH_RULE = "WHITESPACE_NORMALIZED_EXACT_SUBSTRING_V1"
MATCH_FIELD = "normalized_obligations[].legal.evidence"
SOURCE_TABLE = "public.law_article"
LAW_TABLE = "public.law_master"

#: 후보로 인정하는 행의 종류. '전문' 은 절·장 머리글 스텁이라 조문이 아니다.
ARTICLE_TYPE_REQUIRED = "조문"
#: 삭제된 조문은 후보가 아니다.
ARTICLE_STATUS_DELETED = "DELETED"

#: 정수만 허용한다. "제19조" · "19의2" 처럼 숫자가 섞인 문자열에서 숫자를
#: 억지로 뽑지 않는다 — 뽑는 순간 의2 정보가 조용히 사라진다.
NUMERIC_ARTICLE_RE = re.compile(r"^[0-9]+$")

_WHITESPACE_RE = re.compile(r"\s+")

# UNRESOLVED reason — 고객에게 raw 로 나가지 않는 내부 enum.
REASON_ARTICLE_NO_NOT_NUMERIC = "ARTICLE_NO_NOT_NUMERIC"
REASON_LAW_NAME_MISSING = "LAW_NAME_MISSING"
REASON_EVIDENCE_MISSING = "EVIDENCE_MISSING"
REASON_LAW_NOT_FOUND = "LAW_NOT_FOUND"
REASON_LAW_NAME_AMBIGUOUS = "LAW_NAME_AMBIGUOUS"
REASON_NO_EXACT_MATCH = "NO_EXACT_EVIDENCE_MATCH"
REASON_MULTIPLE_EXACT_MATCHES = "MULTIPLE_EXACT_EVIDENCE_MATCHES"

ARTICLE_SELECT: Tuple[str, ...] = (
    "id",
    "law_id",
    "law_version_id",
    "article_no",
    "article_sub_no",
    "article_no_sort",
    "article_type",
    "article_title",
    "article_text",
    "enforcement_date",
    "article_status_code",
)

LAW_SELECT: Tuple[str, ...] = ("id", "law_name")


# ─────────────────────────────────────────────────────────────────────────────
# 정규화 — 여기서 하는 변형은 공백 하나뿐이다.
# ─────────────────────────────────────────────────────────────────────────────

def normalize_text(value: Any) -> Optional[str]:
    """앞뒤 공백 제거 + 연속 공백을 ASCII 공백 하나로.

    그 외에는 아무것도 바꾸지 않는다. 구두점 · 괄호 · 한자 · 전각문자 ·
    유니코드 정규화 형태는 원문 그대로 둔다. 정규화를 넓히면 서로 다른
    조문이 같은 문자열로 접히고, 그 순간 이 규칙은 결정적이지 않게 된다.
    """
    if not isinstance(value, str):
        return None
    collapsed = _WHITESPACE_RE.sub(" ", value).strip()
    return collapsed or None


def _text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and NUMERIC_ARTICLE_RE.match(value.strip()):
        return int(value.strip())
    return None


def parse_base_article_no(law_article: Any) -> Optional[int]:
    """저장된 law_article -> base article_no.

    v1 은 숫자로만 이루어진 값만 받는다. "221" -> 221.
    그 밖의 형태는 None 을 돌려 UNRESOLVED 로 보낸다 — 정규식으로 첫 숫자를
    긁어내면 "221의2" 가 221 로 뭉개져 애초에 풀려던 문제로 되돌아간다.
    """
    if isinstance(law_article, bool):
        return None
    if isinstance(law_article, int):
        return law_article if law_article >= 0 else None
    text = _text(law_article)
    if text is None or not NUMERIC_ARTICLE_RE.match(text):
        return None
    return int(text)


# ─────────────────────────────────────────────────────────────────────────────
# INPUT — normalized_obligations 에서 조회 요청을 만든다.
# ─────────────────────────────────────────────────────────────────────────────

def build_lookup_requests(obligations: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """의무 목록 -> 조회 요청 목록. 입력은 읽기만 한다(mutation 0).

    duty.what · title · atom_id · rule_id 는 쓰지 않는다. 사용하는 필드는
    identity.source_index · legal.law_name · legal.law_article · legal.evidence
    네 개뿐이다.
    """
    requests: List[Dict[str, Any]] = []
    for index, obligation in enumerate(obligations):
        source = obligation if isinstance(obligation, dict) else {}
        identity = source.get("identity")
        legal = source.get("legal")
        identity = identity if isinstance(identity, dict) else {}
        legal = legal if isinstance(legal, dict) else {}

        ref = identity.get("source_index")
        if not isinstance(ref, int) or isinstance(ref, bool):
            ref = index

        requests.append({
            "obligation_ref": ref,
            "law_name": _text(legal.get("law_name")),
            "base_article_no": parse_base_article_no(legal.get("law_article")),
            "raw_law_article": legal.get("law_article"),
            "evidence": _text(legal.get("evidence")),
        })
    return requests


# ─────────────────────────────────────────────────────────────────────────────
# LOADER — DB 왕복은 정확히 2회. 조문 수만큼 질의하지 않는다.
# ─────────────────────────────────────────────────────────────────────────────

class SupabaseArticleLoader:
    """public.law_master + public.law_article READ ONLY batch loader.

    호출은 두 번뿐이다.
        1) law_master   WHERE law_name IN (...)      exact only
        2) law_article  WHERE law_id IN (...) AND article_no IN (...)

    두 번째 질의는 곱집합을 받아 오므로, 실제 (law_id, article_no) 쌍으로
    다시 거르는 일은 Python 이 한다. 조문 하나당 한 번씩 질의하지 않는다.

    law_name 매칭은 exact 뿐이다. ILIKE · contains · startsWith · LIMIT 1
    fallback 은 쓰지 않는다 — '산업안전보건법' 은 세 개 법령에 부분일치한다.
    """

    def __init__(self, client: Any = None) -> None:
        self._client = client

    def _supabase(self) -> Any:
        if self._client is None:
            from db.supabase_client import get_supabase  # 지연 import: 테스트는 DB 없이 돈다
            self._client = get_supabase()
        return self._client

    def load_laws(self, law_names: Sequence[str]) -> List[Dict[str, Any]]:
        if not law_names:
            return []
        response = (
            self._supabase()
            .table("law_master")
            .select(",".join(LAW_SELECT))
            .in_("law_name", list(law_names))
            .execute()
        )
        return list(response.data or [])

    def load_articles(
        self, law_ids: Sequence[Any], article_nos: Sequence[int]
    ) -> List[Dict[str, Any]]:
        if not law_ids or not article_nos:
            return []
        response = (
            self._supabase()
            .table("law_article")
            .select(",".join(ARTICLE_SELECT))
            .in_("law_id", list(law_ids))
            .in_("article_no", list(article_nos))
            .execute()
        )
        return list(response.data or [])


# ─────────────────────────────────────────────────────────────────────────────
# CANDIDATE FILTER
# ─────────────────────────────────────────────────────────────────────────────

def is_candidate_row(row: Any) -> bool:
    """후보 자격. 넷 다 만족해야 한다.

        article_type == '조문'          ('전문' 스텁 제외)
        article_status_code != 'DELETED'
        article_text 존재
        article_no 가 정수로 읽힌다
    """
    if not isinstance(row, dict):
        return False
    if _text(row.get("article_type")) != ARTICLE_TYPE_REQUIRED:
        return False
    if _text(row.get("article_status_code")) == ARTICLE_STATUS_DELETED:
        return False
    if normalize_text(row.get("article_text")) is None:
        return False
    if _int_or_none(row.get("article_no")) is None:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# RESOLVER
# ─────────────────────────────────────────────────────────────────────────────

def _sort_key(article: Dict[str, Any]) -> Tuple[str, str, str]:
    """law_name -> article_no_sort -> law_article.id.

    article_no_sort 가 비어 있는 행이 섞여도 정렬이 깨지지 않도록 빈 문자열로
    떨어뜨린다. 없는 값에 순서를 지어내지 않고 항상 같은 자리에 둔다.
    """
    return (
        article.get("law_name") or "",
        article.get("article_no_sort") or "",
        str(article.get("provenance", {}).get("law_article_id") or ""),
    )


def resolve_articles(
    obligations: Sequence[Dict[str, Any]],
    law_rows: Sequence[Dict[str, Any]],
    article_rows: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """순수 resolver. DB 를 모른다 — 이미 읽어 온 행만 본다.

    의무를 먼저 하나씩 개별 판정하고, 그 다음 동일한 law_article.id 로 묶는다.
    같은 조문에 걸린 의무가 여러 건이면 article_text 를 반복해 싣지 않고
    related_obligation_refs 로 모은다.
    """
    requests = build_lookup_requests(obligations)

    # law_name -> [law_id]. exact 만 담는다.
    laws_by_name: Dict[str, List[Any]] = {}
    for row in law_rows:
        if not isinstance(row, dict):
            continue
        name = _text(row.get("law_name"))
        law_id = row.get("id")
        if name is None or law_id is None:
            continue
        laws_by_name.setdefault(name, []).append(law_id)

    # (law_id, article_no) -> 후보 행들
    candidates: Dict[Tuple[Any, int], List[Dict[str, Any]]] = {}
    for row in article_rows:
        if not is_candidate_row(row):
            continue
        key = (row.get("law_id"), _int_or_none(row.get("article_no")))
        candidates.setdefault(key, []).append(row)

    grouped: Dict[Any, Dict[str, Any]] = {}
    unresolved: List[Dict[str, Any]] = []

    def fail(request: Dict[str, Any], reason: str) -> None:
        unresolved.append({
            "obligation_ref": request["obligation_ref"],
            "law_name": request["law_name"],
            "law_article": request["raw_law_article"],
            "reason": reason,
        })

    for request in requests:
        law_name = request["law_name"]
        article_no = request["base_article_no"]
        evidence = request["evidence"]

        if law_name is None:
            fail(request, REASON_LAW_NAME_MISSING)
            continue
        if article_no is None:
            fail(request, REASON_ARTICLE_NO_NOT_NUMERIC)
            continue
        if evidence is None:
            fail(request, REASON_EVIDENCE_MISSING)
            continue

        law_ids = laws_by_name.get(law_name, [])
        if len(law_ids) == 0:
            fail(request, REASON_LAW_NOT_FOUND)
            continue
        if len(law_ids) > 1:
            fail(request, REASON_LAW_NAME_AMBIGUOUS)
            continue

        needle = normalize_text(evidence)
        rows = candidates.get((law_ids[0], article_no), [])
        matched = [
            row for row in rows
            if needle in (normalize_text(row.get("article_text")) or "")
        ]

        if len(matched) == 0:
            # 후보가 아예 없었던 경우도 여기로 온다 — 맞은 후보 수가 0 인 것은
            # 같은 사실이고, 그 사실에 이름을 하나 더 만들지 않는다.
            fail(request, REASON_NO_EXACT_MATCH)
            continue
        if len(matched) > 1:
            # 여기서 고르지 않는다. 고를 근거가 없기 때문이다.
            fail(request, REASON_MULTIPLE_EXACT_MATCHES)
            continue

        row = matched[0]
        article_id = row.get("id")
        entry = grouped.get(article_id)
        if entry is None:
            entry = {
                "law_name": law_name,
                "article_no": _int_or_none(row.get("article_no")),
                "article_sub_no": _int_or_none(row.get("article_sub_no")),
                "article_no_sort": _text(row.get("article_no_sort")),
                "article_title": _text(row.get("article_title")),
                "article_text": _text(row.get("article_text")),
                "enforcement_date": row.get("enforcement_date"),
                "related_obligation_refs": [],
                "provenance": {
                    "source_table": SOURCE_TABLE,
                    "law_article_id": article_id,
                    "law_version_id": row.get("law_version_id"),
                    "match_field": MATCH_FIELD,
                    "match_rule": MATCH_RULE,
                },
            }
            grouped[article_id] = entry
        refs = entry["related_obligation_refs"]
        if request["obligation_ref"] not in refs:
            refs.append(request["obligation_ref"])

    articles = sorted(grouped.values(), key=_sort_key)
    for article in articles:
        article["related_obligation_refs"] = sorted(
            article["related_obligation_refs"], key=lambda ref: (str(type(ref)), ref)
        )

    unresolved.sort(key=lambda item: (str(type(item["obligation_ref"])), item["obligation_ref"]))

    resolved_count = sum(len(a["related_obligation_refs"]) for a in articles)
    return {
        "evidence_version": EVIDENCE_VERSION,
        "resolution": {
            "rule": RESOLUTION_RULE,
            "source_obligation_count": len(requests),
            "resolved_obligation_count": resolved_count,
            "unresolved_obligation_count": len(unresolved),
            "precise_article_count": len(articles),
        },
        "articles": articles,
        "unresolved": unresolved,
    }


def build_paid_result_evidence_v1(
    materials: Any, loader: Any = None
) -> Dict[str, Any]:
    """paid_result_materials_v1 -> paid_result_evidence_v1.

    DB 왕복은 loader 가 2회만 한다. 이 함수는 그 결과를 resolver 에 넘긴다.
    입력(materials)은 읽기만 하고 바꾸지 않는다.
    """
    source = materials if isinstance(materials, dict) else {}
    raw = source.get("normalized_obligations")
    obligations = [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []

    requests = build_lookup_requests(obligations)

    law_names = sorted({r["law_name"] for r in requests if r["law_name"] is not None})
    article_nos = sorted({
        r["base_article_no"] for r in requests
        if r["base_article_no"] is not None and r["evidence"] is not None
    })

    if loader is not None:
        # INJECTED LOADER PATH — 기존 그대로 (backward-compat 테스트 보존)
        law_rows = loader.load_laws(law_names) if law_names else []
        law_ids = sorted({row.get("id") for row in law_rows
                          if isinstance(row, dict) and row.get("id") is not None}, key=str)
        article_rows = loader.load_articles(law_ids, article_nos) if (law_ids and article_nos) else []
    else:
        # PRODUCTION DEFAULT — LEG Runtime HTTP boundary. Supabase 직독 0.
        if law_names and article_nos:
            from clients.leg_runtime_client import fetch_evidence_rows   # lazy
            resp = fetch_evidence_rows(law_names, article_nos)
            law_rows = resp.get("laws") or []
            article_rows = resp.get("articles") or []
        else:
            law_rows, article_rows = [], []
    return resolve_articles(obligations, law_rows, article_rows)


__all__ = [
    "EVIDENCE_VERSION",
    "RESOLUTION_RULE",
    "MATCH_RULE",
    "ARTICLE_TYPE_REQUIRED",
    "ARTICLE_STATUS_DELETED",
    "SupabaseArticleLoader",
    "build_lookup_requests",
    "build_paid_result_evidence_v1",
    "is_candidate_row",
    "normalize_text",
    "parse_base_article_no",
    "resolve_articles",
]
