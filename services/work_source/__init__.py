"""Common Work Source package.

WO-E2E-OBS009-COMMON-WORK-SOURCE-IMPLEMENT-001
"""
from services.work_source.merge import (
    WorkSourceMergeConflict,
    merge_or_raise,
    merge_projected_into_facts,
)
from services.work_source.projector import project_work_row, project_work_rows
from services.work_source.registry import registry_public

__all__ = [
    "WorkSourceMergeConflict",
    "merge_or_raise",
    "merge_projected_into_facts",
    "project_work_row",
    "project_work_rows",
    "registry_public",
]
