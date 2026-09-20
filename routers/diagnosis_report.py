"""
routers/diagnosis_report.py

Legacy alias:
  GET /diagnosis/report-pdf/{public_token}

Canonical Premium PDF:
  GET /diagnosis/paid-result/{public_token}/pdf
  services/paid_result_pdf_v1.py

DUPLICATE GENERATOR 0 — this route reuses get_paid_result_pdf.
on-demand only. documents INSERT 0. storage cache 0.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/diagnosis", tags=["진단리포트"])


@router.get("/report-pdf/{public_token}")
async def get_paid_report_pdf(public_token: str):
    from routers.diagnosis_result_web import get_paid_result_pdf

    return await get_paid_result_pdf(public_token)
