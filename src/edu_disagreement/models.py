"""Small immutable models using canonical Unicode code-point coordinates."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ParsedEDU:
    index: int
    text: str
    line_number: int


@dataclass(frozen=True)
class DisagreementRegion:
    """A half-open canonical span containing alternative segmentations."""

    start_offset: int
    end_offset: int
    a_edu_indices: tuple[int, ...]
    b_edu_indices: tuple[int, ...]


@dataclass(frozen=True)
class ComparisonResult:
    """Successful comparison; canonical text and parsed EDUs remain accessible."""

    canonical_text: str
    a_edus: tuple[ParsedEDU, ...]
    b_edus: tuple[ParsedEDU, ...]
    a_boundaries: tuple[int, ...]
    b_boundaries: tuple[int, ...]
    shared_boundaries: tuple[int, ...]
    a_only_boundaries: tuple[int, ...]
    b_only_boundaries: tuple[int, ...]
    disagreement_regions: tuple[DisagreementRegion, ...]
    canonical_source: Literal["reconstructed", "whitespace_normalized"] = "reconstructed"

    def to_dict(self) -> dict[str, object]:
        """Return the minimal JSON-serializable comparison schema."""
        return {
            "canonical_source": self.canonical_source,
            "annotations": {
                "A": {
                    "edu_count": len(self.a_edus),
                    "boundaries": list(self.a_boundaries),
                },
                "B": {
                    "edu_count": len(self.b_edus),
                    "boundaries": list(self.b_boundaries),
                },
            },
            "shared_boundaries": list(self.shared_boundaries),
            "a_only_boundaries": list(self.a_only_boundaries),
            "b_only_boundaries": list(self.b_only_boundaries),
            "disagreement_regions": [
                {
                    "start_offset": region.start_offset,
                    "end_offset": region.end_offset,
                    "a_edu_indices": list(region.a_edu_indices),
                    "b_edu_indices": list(region.b_edu_indices),
                }
                for region in self.disagreement_regions
            ],
            "warnings": [],
        }
