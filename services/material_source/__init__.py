"""Common Material Source package.

WO-E2E-OBS009-COMMON-MATERIAL-SOURCE-IMPLEMENT-001
"""
from services.material_source.canonical_adapter import (
    CANONICAL_FIELDS,
    CLASSIFICATION_TO_CANONICAL,
    MaterialCanonicalMergeConflict,
    merge_material_canonical_into_facts,
    project_material_canonical_facts,
    project_material_canonical_facts_from_rows,
)
from services.material_source.projector import (
    project_factory_material_rows,
    project_material_row,
)
from services.material_source.registry import registry_public
from services.material_source.store import MaterialSourceLoadError

__all__ = [
    "CANONICAL_FIELDS",
    "CLASSIFICATION_TO_CANONICAL",
    "MaterialCanonicalMergeConflict",
    "MaterialSourceLoadError",
    "merge_material_canonical_into_facts",
    "project_factory_material_rows",
    "project_material_canonical_facts",
    "project_material_canonical_facts_from_rows",
    "project_material_row",
    "registry_public",
]
