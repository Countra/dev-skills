"""Complex Coding Reviewer 的确定性契约、派发与目标工具。"""

from .assemble import assemble_receipt
from .contract import CODE_LENSES, PLAN_LENSES, validate_receipt
from .context import (
    build_context_target,
    load_context_brief,
    validate_context_target_shape,
    validate_review_brief,
    verify_context_freshness,
)
from .errors import ReviewError
from .dispatch import prepare_dispatch, validate_preparation
from .dispatch_lifecycle import finalize_dispatch, validate_dispatch
from .package import build_review_package
from .target import (
    build_commit_range_target,
    build_file_manifest_target,
    build_plan_bundle_target,
    build_working_tree_target,
    verify_target_freshness,
)

__all__ = [
    "CODE_LENSES",
    "PLAN_LENSES",
    "ReviewError",
    "assemble_receipt",
    "build_context_target",
    "build_commit_range_target",
    "build_file_manifest_target",
    "build_plan_bundle_target",
    "build_working_tree_target",
    "build_review_package",
    "finalize_dispatch",
    "load_context_brief",
    "prepare_dispatch",
    "validate_context_target_shape",
    "validate_dispatch",
    "validate_preparation",
    "validate_receipt",
    "validate_review_brief",
    "verify_context_freshness",
    "verify_target_freshness",
]
