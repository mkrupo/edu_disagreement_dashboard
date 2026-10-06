"""Symmetric EDU comparison with an exact path and whitespace-only fallback."""

from .comparison import BoundaryProjectionError, ContentMismatchError, compare_annotations
from .models import ComparisonResult, DisagreementRegion, ParsedEDU
from .parsing import parse_annotation, reconstruct_text

__all__ = [
    "BoundaryProjectionError",
    "ComparisonResult",
    "ContentMismatchError",
    "DisagreementRegion",
    "ParsedEDU",
    "compare_annotations",
    "parse_annotation",
    "reconstruct_text",
]
