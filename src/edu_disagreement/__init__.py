"""Exact, symmetric comparison of line-separated EDU annotations."""

from .comparison import ContentMismatchError, compare_annotations
from .models import ComparisonResult, DisagreementRegion, ParsedEDU
from .parsing import parse_annotation, reconstruct_text

__all__ = [
    "ComparisonResult",
    "ContentMismatchError",
    "DisagreementRegion",
    "ParsedEDU",
    "compare_annotations",
    "parse_annotation",
    "reconstruct_text",
]
