import json
from itertools import combinations

import pytest

from edu_disagreement import (
    ContentMismatchError,
    DisagreementRegion,
    ParsedEDU,
    compare_annotations,
    parse_annotation,
)


def edus(*texts):
    return tuple(ParsedEDU(i, text, i + 1) for i, text in enumerate(texts))


def test_identical_segmentations():
    result = compare_annotations(edus("ab", "cd", "ef"), edus("ab", "cd", "ef"))

    assert result.canonical_text == "abcdef"
    assert result.a_boundaries == result.b_boundaries == (2, 4)
    assert result.shared_boundaries == (2, 4)
    assert result.a_only_boundaries == result.b_only_boundaries == ()
    assert result.disagreement_regions == ()


def test_one_extra_boundary_in_a():
    result = compare_annotations(edus("a", "b", "cd"), edus("ab", "cd"))

    assert result.shared_boundaries == (2,)
    assert result.a_only_boundaries == (1,)
    assert result.b_only_boundaries == ()
    assert result.disagreement_regions == (DisagreementRegion(0, 2, (0, 1), (0,)),)


def test_different_boundary_positions_produce_one_region():
    result = compare_annotations(edus("ab", "cd"), edus("a", "bcd"))

    assert result.shared_boundaries == ()
    assert result.a_only_boundaries == (2,)
    assert result.b_only_boundaries == (1,)
    assert result.disagreement_regions == (DisagreementRegion(0, 4, (0, 1), (0, 1)),)


def test_multiple_differences_between_shared_anchors_produce_one_region():
    result = compare_annotations(
        edus("a", "bc", "d", "ef"), edus("ab", "cde", "f")
    )

    assert result.a_only_boundaries == (1, 3, 4)
    assert result.b_only_boundaries == (2, 5)
    assert result.disagreement_regions == (
        DisagreementRegion(0, 6, (0, 1, 2, 3), (0, 1, 2)),
    )


def test_multiple_regions_separated_by_a_shared_boundary():
    result = compare_annotations(edus("a", "bc", "d", "ef"), edus("ab", "c", "def"))

    assert result.shared_boundaries == (3,)
    assert result.disagreement_regions == (
        DisagreementRegion(0, 3, (0, 1), (0, 1)),
        DisagreementRegion(3, 6, (2, 3), (2,)),
    )


def test_agreeing_intervals_around_a_region_are_excluded():
    result = compare_annotations(
        edus("ab", "c", "de", "fg"), edus("ab", "cd", "e", "fg")
    )

    assert result.shared_boundaries == (2, 5)
    assert result.disagreement_regions == (DisagreementRegion(2, 5, (1, 2), (1, 2)),)


def test_unicode_offsets_count_code_points_not_bytes_or_graphemes(tmp_path):
    a_path, b_path = tmp_path / "a.txt", tmp_path / "b.txt"
    a_path.write_bytes("é🙂\ne\u0301界".encode("utf-8"))
    b_path.write_bytes("é\n🙂e\u0301界".encode("utf-8"))

    result = compare_annotations(parse_annotation(a_path), parse_annotation(b_path))

    assert result.canonical_text == "é🙂e\u0301界"
    assert len(result.canonical_text) == 5
    assert result.a_boundaries == (2,)
    assert result.b_boundaries == (1,)
    assert result.disagreement_regions == (DisagreementRegion(0, 5, (0, 1), (0, 1)),)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (edus("ab", "c"), edus("abd")),
        (edus("abc"), edus("abcd")),
        (edus("aaa ", "bbb"), edus("aaa", "bbb")),
        (edus("é"), edus("e\u0301")),
        ((), edus("a")),
    ],
)
def test_content_mismatches_are_rejected_cleanly(a, b):
    with pytest.raises(ContentMismatchError, match="texts differ"):
        compare_annotations(a, b)


def test_start_and_end_are_anchors_only():
    result = compare_annotations(edus("a", "bc"), edus("abc"))

    assert result.a_boundaries == (1,)
    assert result.b_boundaries == result.shared_boundaries == ()
    assert result.disagreement_regions == (DisagreementRegion(0, 3, (0, 1), (0,)),)
    for boundaries in (
        result.a_boundaries,
        result.b_boundaries,
        result.shared_boundaries,
        result.a_only_boundaries,
        result.b_only_boundaries,
    ):
        assert 0 not in boundaries
        assert len(result.canonical_text) not in boundaries


@pytest.mark.parametrize("annotation", [(), edus("abc")])
def test_no_internal_boundaries(annotation):
    result = compare_annotations(annotation, annotation)

    assert result.a_boundaries == result.b_boundaries == ()
    assert result.shared_boundaries == ()
    assert result.disagreement_regions == ()


def test_minimal_machine_readable_output():
    result = compare_annotations(edus("ab", "cd"), edus("a", "bcd"))
    expected = {
        "canonical_source": "reconstructed",
        "annotations": {
            "A": {"edu_count": 2, "boundaries": [2]},
            "B": {"edu_count": 2, "boundaries": [1]},
        },
        "shared_boundaries": [],
        "a_only_boundaries": [2],
        "b_only_boundaries": [1],
        "disagreement_regions": [
            {
                "start_offset": 0,
                "end_offset": 4,
                "a_edu_indices": [0, 1],
                "b_edu_indices": [0, 1],
            }
        ],
        "warnings": [],
    }

    assert result.to_dict() == expected
    assert json.loads(json.dumps(result.to_dict())) == expected


def test_end_to_end_with_different_line_endings_and_empty_lines(tmp_path):
    a_path, b_path = tmp_path / "a.txt", tmp_path / "b.txt"
    a_path.write_bytes(b"\r\naaa \r\n\r\nbbb\r\nccc\r\n")
    b_path.write_bytes(b"aaa bbb\n\nccc")

    result = compare_annotations(parse_annotation(a_path), parse_annotation(b_path))

    assert result.canonical_text == "aaa bbbccc"
    assert result.a_boundaries == (4, 7)
    assert result.b_boundaries == result.shared_boundaries == (7,)
    assert tuple(edu.line_number for edu in result.a_edus) == (2, 4, 5)
    assert result.disagreement_regions == (DisagreementRegion(0, 7, (0, 1), (0,)),)


def test_all_segmentations_of_a_tiny_document_follow_overlap_and_symmetry_rules():
    # Exhaust all 16 segmentations of five code points, comparing all pairs
    # against a direct span-overlap oracle independent of the bisect algorithm.
    text = "abcde"
    segmentations = []
    for count in range(len(text)):
        for boundaries in combinations(range(1, len(text)), count):
            anchors = (0, *boundaries, len(text))
            segmentations.append(
                edus(*(text[start:end] for start, end in zip(anchors, anchors[1:])))
            )

    for a in segmentations:
        for b in segmentations:
            result = compare_annotations(a, b)
            reverse = compare_annotations(b, a)
            a_spans, b_spans = [], []
            for annotation, spans in ((a, a_spans), (b, b_spans)):
                offset = 0
                for edu in annotation:
                    spans.append((offset, offset + len(edu.text)))
                    offset += len(edu.text)
            a_boundaries = {end for _, end in a_spans[:-1]}
            b_boundaries = {end for _, end in b_spans[:-1]}
            anchors = (0, *sorted(a_boundaries & b_boundaries), len(text))
            expected = []
            for start, end in zip(anchors, anchors[1:]):
                internal_a = {p for p in a_boundaries if start < p < end}
                internal_b = {p for p in b_boundaries if start < p < end}
                if internal_a != internal_b:
                    expected.append(
                        DisagreementRegion(
                            start,
                            end,
                            tuple(i for i, (s, e) in enumerate(a_spans) if s < end and e > start),
                            tuple(i for i, (s, e) in enumerate(b_spans) if s < end and e > start),
                        )
                    )

            assert result.disagreement_regions == tuple(expected)
            assert reverse.shared_boundaries == result.shared_boundaries
            assert reverse.a_only_boundaries == result.b_only_boundaries
            assert reverse.b_only_boundaries == result.a_only_boundaries
            assert reverse.disagreement_regions == tuple(
                DisagreementRegion(r.start_offset, r.end_offset, r.b_edu_indices, r.a_edu_indices)
                for r in expected
            )
