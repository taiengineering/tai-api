from __future__ import annotations

from typing import Dict, List, Optional

from db.supabase_client import get_supabase


def _parse_article_number(law_article: str) -> Optional[int]:
    if not law_article:
        return None
    digits = "".join(ch for ch in str(law_article) if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _render_article_text(article: Dict) -> str:
    lines: List[str] = []
    title = (article.get("article_title") or "").strip()
    no = article.get("article_no")
    article_head = f"제{no}조"
    if title:
        article_head += f" ({title})"
    lines.append(article_head)
    body = (article.get("article_text") or "").strip()
    if body:
        lines.append(body)

    supabase = get_supabase()
    para_res = (
        supabase.table("law_paragraph")
        .select("id, paragraph_no, paragraph_text")
        .eq("article_id", article["id"])
        .order("paragraph_no")
        .execute()
    )
    for p in para_res.data or []:
        p_no = p.get("paragraph_no")
        p_text = (p.get("paragraph_text") or "").strip()
        if p_text:
            lines.append(f"  {p_no}. {p_text}")
        item_res = (
            supabase.table("law_item")
            .select("item_no, item_text")
            .eq("paragraph_id", p["id"])
            .order("item_no")
            .execute()
        )
        for it in item_res.data or []:
            i_no = it.get("item_no")
            i_text = (it.get("item_text") or "").strip()
            if i_text:
                lines.append(f"    {i_no}. {i_text}")
    return "\n".join(lines).strip()


async def build_full_context(law_name: str, law_article: str, article_id: str = None) -> str:
    """
    법령 원문 풀 컨텍스트 조립:
    1) 본조 전문, 2) 시행령 관련 조문, 3) 별표/서식 목록, 4) 벌칙 조항.
    """
    supabase = get_supabase()
    parts: List[str] = []

    law_res = (
        supabase.table("law_master")
        .select("id, law_name")
        .eq("law_name", law_name)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not law_res.data:
        return ""
    law_id = law_res.data[0]["id"]

    ver_res = (
        supabase.table("law_version")
        .select("id")
        .eq("law_id", law_id)
        .eq("is_current", True)
        .limit(1)
        .execute()
    )
    if not ver_res.data:
        return ""
    version_id = ver_res.data[0]["id"]

    # 1) 본조 전문
    target_article = None
    if article_id:
        a_res = (
            supabase.table("law_article")
            .select("id, article_no, article_title, article_text")
            .eq("id", article_id)
            .limit(1)
            .execute()
        )
        if a_res.data:
            target_article = a_res.data[0]
    if not target_article:
        article_no_int = _parse_article_number(law_article)
        if article_no_int is not None:
            a_res = (
                supabase.table("law_article")
                .select("id, article_no, article_title, article_text")
                .eq("law_version_id", version_id)
                .eq("article_no", article_no_int)
                .limit(1)
                .execute()
            )
            if a_res.data:
                target_article = a_res.data[0]

    if target_article:
        parts.append("[본조 전문]\n" + _render_article_text(target_article))

    # 2) 시행령 관련 조문 (같은 조번호 우선, 없으면 처음 3개)
    decree_name = f"{law_name} 시행령"
    decree_master = (
        supabase.table("law_master")
        .select("id, law_name")
        .eq("law_name", decree_name)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if decree_master.data:
        decree_ver = (
            supabase.table("law_version")
            .select("id")
            .eq("law_id", decree_master.data[0]["id"])
            .eq("is_current", True)
            .limit(1)
            .execute()
        )
        if decree_ver.data:
            decree_vid = decree_ver.data[0]["id"]
            article_no_int = _parse_article_number(law_article)
            decree_articles: List[Dict] = []
            if article_no_int is not None:
                same_res = (
                    supabase.table("law_article")
                    .select("id, article_no, article_title, article_text")
                    .eq("law_version_id", decree_vid)
                    .eq("article_no", article_no_int)
                    .limit(3)
                    .execute()
                )
                decree_articles = same_res.data or []
            if not decree_articles:
                any_res = (
                    supabase.table("law_article")
                    .select("id, article_no, article_title, article_text")
                    .eq("law_version_id", decree_vid)
                    .order("article_no_sort")
                    .limit(3)
                    .execute()
                )
                decree_articles = any_res.data or []
            if decree_articles:
                rendered = []
                for a in decree_articles:
                    rendered.append(_render_article_text(a))
                parts.append("[시행령 관련 조문]\n" + "\n\n".join(rendered))

            # 3) 별표/서식 목록 (시행령 포함)
            att_res = (
                supabase.table("law_attachment")
                .select("attachment_no, title")
                .eq("law_version_id", decree_vid)
                .order("attachment_no")
                .limit(20)
                .execute()
            )
            if att_res.data:
                att_lines = []
                for a in att_res.data:
                    no = a.get("attachment_no") or "-"
                    title = (a.get("title") or "").strip()
                    att_lines.append(f"- [{no}] {title}")
                parts.append("[시행령 별표/서식 목록]\n" + "\n".join(att_lines))

    # 본법 별표/서식
    att_main = (
        supabase.table("law_attachment")
        .select("attachment_no, title")
        .eq("law_version_id", version_id)
        .order("attachment_no")
        .limit(20)
        .execute()
    )
    if att_main.data:
        att_lines = []
        for a in att_main.data:
            no = a.get("attachment_no") or "-"
            title = (a.get("title") or "").strip()
            att_lines.append(f"- [{no}] {title}")
        parts.append("[본법 별표/서식 목록]\n" + "\n".join(att_lines))

    # 4) 벌칙 조항
    penal_like = (
        supabase.table("law_article")
        .select("id, article_no, article_title, article_text")
        .eq("law_version_id", version_id)
        .or_("article_title.ilike.%벌칙%,article_title.ilike.%과태료%,article_title.ilike.%벌금%,article_title.ilike.%양벌%")
        .order("article_no_sort")
        .limit(5)
        .execute()
    )
    if penal_like.data:
        penal_blocks = []
        for a in penal_like.data:
            penal_blocks.append(_render_article_text(a))
        parts.append("[벌칙 조항]\n" + "\n\n".join(penal_blocks))

    return "\n\n".join(p for p in parts if p).strip()
