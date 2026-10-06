"""Compare exact reconstructions with a bounded whitespace-only fallback."""

from bisect import bisect_left, bisect_right
from itertools import accumulate
from typing import Literal

from .models import ComparisonResult, DisagreementRegion, ParsedEDU
from .parsing import reconstruct_text


class ContentMismatchError(ValueError):
    """Texts differ even after removing whitespace; no comparison is possible."""


class BoundaryProjectionError(ValueError):
    """Whitespace removal collapses distinct internal annotation boundaries."""


def _boundaries(edus: tuple[ParsedEDU, ...]) -> tuple[int, ...]:
    # Exclude the last endpoint: document end is a structural anchor.
    return tuple(accumulate(len(edu.text) for edu in edus[:-1]))


def _projected_endpoints(edus: tuple[ParsedEDU, ...], label: str) -> tuple[int, ...]:
    endpoints = tuple(
        accumulate(sum(not char.isspace() for char in edu.text) for edu in edus[:-1])
    )
    for previous, current in zip(endpoints, endpoints[1:]):
        if previous == current:
            raise BoundaryProjectionError(
                f"Whitespace normalization collapses distinct internal EDU "
                f"boundaries in annotation {label} to offset {current}. "
                "No disagreement regions were computed."
            )
    return endpoints


def compare_annotations(
    a_edus: tuple[ParsedEDU, ...], b_edus: tuple[ParsedEDU, ...]
) -> ComparisonResult:
    """Compare two parsed annotations in shared code-point coordinates.

    Prefer exact reconstruction. Otherwise remove only Unicode whitespace and
    project endpoints into the shared non-whitespace sequence, preserving EDUs.
    Raise ContentMismatchError if content still differs, or BoundaryProjectionError
    if distinct internal boundaries collapse. Empty annotations are valid.
    """
    canonical_text = reconstruct_text(a_edus)
    b_text = reconstruct_text(b_edus)
    canonical_source: Literal["reconstructed", "whitespace_normalized"] = "reconstructed"
    if canonical_text == b_text:
        a_endpoints = a_boundaries = _boundaries(a_edus)
        b_endpoints = b_boundaries = _boundaries(b_edus)
    else:
        canonical_text = "".join(char for char in canonical_text if not char.isspace())
        b_text = "".join(char for char in b_text if not char.isspace())
        if canonical_text != b_text:
            raise ContentMismatchError(
                "Reconstructed annotation A and B texts differ even after removing "
                "whitespace. No disagreement regions were computed."
            )
        canonical_source = "whitespace_normalized"
        a_endpoints = _projected_endpoints(a_edus, "A")
        b_endpoints = _projected_endpoints(b_edus, "B")
        # Whitespace-only edge EDUs can end at structural anchors. Retain their
        # projected endpoints for EDU indexing, but not as boundary decisions.
        a_boundaries = tuple(p for p in a_endpoints if 0 < p < len(canonical_text))
        b_boundaries = tuple(p for p in b_endpoints if 0 < p < len(canonical_text))
    a_set, b_set = set(a_boundaries), set(b_boundaries)
    shared = tuple(sorted(a_set & b_set))
    a_only = tuple(sorted(a_set - b_set))
    b_only = tuple(sorted(b_set - a_set))
    differing = tuple(sorted(a_set ^ b_set))

    regions = []
    anchors = (0, *shared, len(canonical_text))
    for start, end in zip(anchors, anchors[1:]):
        # No shared boundary lies inside this interval. Any differing internal
        # boundary therefore makes the whole interval one disagreement region.
        next_difference = bisect_right(differing, start)
        if next_difference == len(differing) or differing[next_difference] >= end:
            continue

        # A boundary at start ends the previous EDU; one at end ends this span.
        a_start = bisect_right(a_endpoints, start)
        a_end = bisect_left(a_endpoints, end) + 1
        b_start = bisect_right(b_endpoints, start)
        b_end = bisect_left(b_endpoints, end) + 1
        regions.append(
            DisagreementRegion(
                start_offset=start,
                end_offset=end,
                a_edu_indices=tuple(edu.index for edu in a_edus[a_start:a_end]),
                b_edu_indices=tuple(edu.index for edu in b_edus[b_start:b_end]),
            )
        )

    return ComparisonResult(
        canonical_text=canonical_text,
        a_edus=a_edus,
        b_edus=b_edus,
        a_boundaries=a_boundaries,
        b_boundaries=b_boundaries,
        shared_boundaries=shared,
        a_only_boundaries=a_only,
        b_only_boundaries=b_only,
        disagreement_regions=tuple(regions),
        canonical_source=canonical_source,
    )
