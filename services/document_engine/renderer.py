"""Document Engine Renderer

HTML 템플릿에 데이터를 주입하고, Gotenberg로 PDF를 생성합니다.

사용법:
  from services.document_engine.renderer import render_document_html, generate_document_pdf

  # 미리보기 (HTML)
  html = await render_document_html('DOC-OSH-056', data)

  # PDF 생성
  pdf_bytes = await generate_document_pdf('DOC-OSH-056', data)
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import httpx
from jinja2 import Environment, FileSystemLoader
from services.time import now_kst

# 템플릿 디렉토리
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "documents"

# Jinja2 환경
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)

# Gotenberg URL (Railway internal)
GOTENBERG_URL = os.getenv("GOTENBERG_URL", "http://gotenberg.railway.internal:3000")


async def render_document_html(doc_id: str, data: Dict[str, Any]) -> str:
    """HTML 템플릿에 데이터를 주입하여 렌더링된 HTML 문자열을 반환합니다."""
    template_name = f"{doc_id}.html"
    if not (TEMPLATE_DIR / template_name).exists():
        raise FileNotFoundError(f"Template not found: {template_name}")

    template = _env.get_template(template_name)

    # 공통 변수 주입
    data.setdefault("generated_at", now_kst().strftime("%Y-%m-%d %H:%M"))

    return template.render(**data)


async def generate_document_pdf(doc_id: str, data: Dict[str, Any]) -> bytes:
    """HTML을 Gotenberg로 보내 PDF를 생성합니다."""
    html_content = await render_document_html(doc_id, data)

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GOTENBERG_URL}/forms/chromium/convert/html",
            files={"index.html": ("index.html", html_content, "text/html")},
            data={
                "paperWidth": "8.27",  # A4
                "paperHeight": "11.69",
                "marginTop": "0.4",
                "marginBottom": "0.4",
                "marginLeft": "0.4",
                "marginRight": "0.4",
                "printBackground": "true",
            },
        )
        resp.raise_for_status()
        return resp.content
