"""Compare boundaries only after verifying exact reconstructed-text equality."""

from bisect import bisect_left, bisect_right
from itertools import accumulate

from .models import ComparisonResult, DisagreementRegion, ParsedEDU
from .parsing import reconstruct_text


class ContentMismatchError(ValueError):
    """Reconstructed texts differ; a later alignment layer must handle them."""


def _boundaries(edus: tuple[ParsedEDU, ...]) -> tuple[int, ...]:
    # Exclude the last endpoint: document end is a structural anchor.
    return tuple(accumulate(len(edu.text) for edu in edus[:-1]))


def compare_annotations(
    a_edus: tuple[ParsedEDU, ...], b_edus: tuple[ParsedEDU, ...]
) -> ComparisonResult:
    """Compare two parsed annotations in shared code-point coordinates.

    Raises ContentMismatchError without computing regions if reconstructed
    texts differ. Empty annotations are valid and reconstruct to empty text.
    """
    canonical_text = reconstruct_text(a_edus)
    if canonical_text != reconstruct_text(b_edus):
        raise ContentMismatchError(
            "Reconstructed annotation A and B texts differ; exact comparison "
            "requires identical content. No disagreement regions were computed."
        )

    a_boundaries = _boundaries(a_edus)
    b_boundaries = _boundaries(b_edus)
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
        a_start = bisect_right(a_boundaries, start)
        a_end = bisect_left(a_boundaries, end) + 1
        b_start = bisect_right(b_boundaries, start)
        b_end = bisect_left(b_boundaries, end) + 1
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
    )
