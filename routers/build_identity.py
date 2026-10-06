import os
import re
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_SHA_RE = re.compile(r'^[0-9a-f]{40}$')

@router.get("/.well-known/tai-build.json")
def get_build_identity():
    sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")
    if not _SHA_RE.match(sha):
        return JSONResponse(
            status_code=503,
            content={"status": "error", "code": "DEPLOYMENT_IDENTITY_UNAVAILABLE"},
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        content={
            "schema_version": "1.0",
            "identity_type": "TAI_DEPLOYMENT_BUILD",
            "service": "tai-api",
            "repository": "taiengineering/tai-api",
            "git_commit_sha": sha,
        },
        headers={"Cache-Control": "no-store"},
    )
