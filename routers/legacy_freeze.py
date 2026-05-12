"""TAI Legacy Write Freeze v1.0.0
Phase 1: schedule_engine, diagnosis_autofill, documents CRUD write 차단

Legacy write endpoint를 차단하고 Runtime API로 안내.
Legacy read는 유지.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["레거시 프리즈"])

FREEZE_MSG = {
    "schedule": {
        "message": "Legacy schedule write는 비활성화되었습니다. Runtime API를 사용하세요.",
        "runtime_endpoint": "/persistence/schedules",
        "runtime_method": "POST",
    },
    "document": {
        "message": "Legacy document write는 비활성화되었습니다. Runtime API를 사용하세요.",
        "runtime_endpoint": "/document-engine/documents",
        "runtime_method": "POST",
    },
    "diagnosis_autofill": {
        "message": "Legacy 진단 자동채움은 비활성화되었습니다. Runtime API를 사용하세요.",
        "runtime_endpoint": "/api/v1/diagnosis-engine/evaluate",
        "runtime_method": "POST",
    },
}

# Schedule Legacy Write Freeze
@router.post("/api/v1/schedules/legacy-create")
def freeze_schedule_create():
    raise HTTPException(410, detail=FREEZE_MSG["schedule"])

@router.put("/api/v1/schedules/legacy-update/{schedule_id}")
def freeze_schedule_update(schedule_id: str):
    raise HTTPException(410, detail=FREEZE_MSG["schedule"])

# Document Legacy Write Freeze
@router.post("/api/v1/documents/legacy-create")
def freeze_document_create():
    raise HTTPException(410, detail=FREEZE_MSG["document"])

@router.put("/api/v1/documents/legacy-update/{doc_id}")
def freeze_document_update(doc_id: str):
    raise HTTPException(410, detail=FREEZE_MSG["document"])

# Diagnosis Autofill Freeze
@router.post("/api/v1/diagnosis/legacy-autofill")
def freeze_diagnosis_autofill():
    raise HTTPException(410, detail=FREEZE_MSG["diagnosis_autofill"])

@router.post("/api/v1/diagnosis/legacy-autofill/{field}")
def freeze_diagnosis_autofill_field(field: str):
    raise HTTPException(410, detail=FREEZE_MSG["diagnosis_autofill"])
