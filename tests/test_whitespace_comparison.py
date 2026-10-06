import json

import pytest

from edu_disagreement import (
    BoundaryProjectionError,
    ContentMismatchError,
    DisagreementRegion,
    ParsedEDU,
    compare_annotations,
    parse_annotation,
    reconstruct_text,
)


def edus(*texts):
    return tuple(ParsedEDU(i, text, i + 1) for i, text in enumerate(texts))


def test_trailing_space_mismatch_uses_fallback():
    a, b = edus("ab", "cd"), edus("ab", "cd ")

    result = compare_annotations(a, b)

    assert result.canonical_source == "whitespace_normalized"
    assert result.canonical_text == "abcd"
    assert result.a_boundaries == result.b_boundaries == result.shared_boundaries == (2,)
    assert result.disagreement_regions == ()
    assert result.a_edus == a
    assert result.b_edus == b
    assert reconstruct_text(result.b_edus) == "abcd "
    output = json.loads(json.dumps(result.to_dict()))
    assert output["canonical_source"] == "whitespace_normalized"
    assert output["warnings"] == []


def test_edu_newline_replacing_inter_word_space(tmp_path):
    a_path, b_path = tmp_path / "a.txt", tmp_path / "b.txt"
    a_path.write_bytes(b"hello world\n")
    b_path.write_bytes(b"hello\nworld\n")

    result = compare_annotations(parse_annotation(a_path), parse_annotation(b_path))

    assert result.canonical_text == "helloworld"
    assert result.a_boundaries == ()
    assert result.b_boundaries == result.b_only_boundaries == (5,)
    assert result.disagreement_regions == (DisagreementRegion(0, 10, (0,), (0, 1)),)
    assert result.a_edus[0].text == "hello world"
    assert tuple(edu.text for edu in result.b_edus) == ("hello", "world")


def test_several_whitespace_differences_preserve_region_grouping():
    result = compare_annotations(edus(" a \t", " b", "c d "), edus("ab", "c", "d"))

    assert result.canonical_source == "whitespace_normalized"
    assert result.canonical_text == "abcd"
    assert result.a_boundaries == (1, 2)
    assert result.b_boundaries == (2, 3)
    assert result.shared_boundaries == (2,)
    assert result.a_only_boundaries == (1,)
    assert result.b_only_boundaries == (3,)
    assert result.disagreement_regions == (
        DisagreementRegion(0, 2, (0, 1), (0,)),
        DisagreementRegion(2, 4, (2,), (1, 2)),
    )


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (edus(" a \t", " b", "c d "), edus("ab", "c", "d")),
        (edus("a b"), edus("a", "b")),
        (edus(" ", "ab", " "), edus("a", "b")),
    ],
)
def test_normalized_comparison_is_symmetric(a, b):
    forward = compare_annotations(a, b)
    reverse = compare_annotations(b, a)

    assert forward.canonical_source == reverse.canonical_source == "whitespace_normalized"
    assert forward.canonical_text == reverse.canonical_text
    assert forward.a_boundaries == reverse.b_boundaries
    assert forward.b_boundaries == reverse.a_boundaries
    assert forward.shared_boundaries == reverse.shared_boundaries
    assert forward.a_only_boundaries == reverse.b_only_boundaries
    assert forward.b_only_boundaries == reverse.a_only_boundaries
    assert reverse.disagreement_regions == tuple(
        DisagreementRegion(r.start_offset, r.end_offset, r.b_edu_indices, r.a_edu_indices)
        for r in forward.disagreement_regions
    )


def test_trailing_edu_space_projects_to_shared_boundary():
    result = compare_annotations(edus("aaa ", "bbb"), edus("aaa", "bbb"))

    assert result.canonical_source == "whitespace_normalized"
    assert result.canonical_text == "aaabbb"
    assert result.a_boundaries == result.b_boundaries == result.shared_boundaries == (3,)
    assert result.a_only_boundaries == result.b_only_boundaries == ()
    assert result.disagreement_regions == ()


@pytest.mark.parametrize("whitespace", [" ", "\t", "\r\n", "\u00a0", "\u2003", "\u2028"])
def test_unicode_whitespace_projection_counts_nonwhitespace_code_points(whitespace):
    result = compare_annotations(edus(f"é🙂{whitespace}", "e\u0301界"), edus("é", "🙂e\u0301界"))

    assert result.canonical_text == "é🙂e\u0301界"
    assert result.a_boundaries == (2,)
    assert result.b_boundaries == (1,)
    assert result.disagreement_regions == (DisagreementRegion(0, 5, (0, 1), (0, 1)),)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (edus("a b"), edus("a", "c")),
        (edus("é "), edus("e\u0301")),
        (edus("a, b"), edus("ab")),
        (edus("A b"), edus("ab")),
        (edus("a\u200bb"), edus("ab")),
    ],
)
def test_nonwhitespace_differences_still_raise(a, b):
    with pytest.raises(ContentMismatchError, match="even after removing whitespace"):
        compare_annotations(a, b)


@pytest.mark.parametrize("collapsed", [edus("a", " ", "b"), edus("a", "\t", " ", "b")])
@pytest.mark.parametrize("swapped", [False, True])
def test_collapsed_internal_boundaries_are_rejected(collapsed, swapped):
    a, b = (edus("ab"), collapsed) if swapped else (collapsed, edus("ab"))
    label = "B" if swapped else "A"

    with pytest.raises(BoundaryProjectionError, match=f"annotation {label} to offset 1"):
        compare_annotations(a, b)


def test_duplicates_at_structural_anchor_are_also_rejected():
    with pytest.raises(BoundaryProjectionError, match="offset 0"):
        compare_annotations(edus(" ", "\t", "ab"), edus("ab"))


def test_whitespace_only_edge_edus_do_not_create_annotation_boundaries():
    a = edus(" ", "ab", " ")
    result = compare_annotations(a, edus("a", "b"))

    assert result.a_edus == a
    assert result.a_boundaries == ()
    assert result.b_only_boundaries == (1,)
    assert result.disagreement_regions == (DisagreementRegion(0, 2, (1,), (0, 1)),)


def test_whitespace_only_document_and_empty_annotation_have_no_boundaries():
    result = compare_annotations(edus(" \t"), ())

    assert result.canonical_source == "whitespace_normalized"
    assert result.canonical_text == ""
    assert result.a_boundaries == result.b_boundaries == ()
    assert result.disagreement_regions == ()
    assert result.to_dict()["annotations"]["A"]["edu_count"] == 1


def test_exact_path_retains_whitespace_and_distinct_original_boundaries():
    a = edus("a", " ", "b")
    result = compare_annotations(a, a)

    assert result.canonical_source == result.to_dict()["canonical_source"] == "reconstructed"
    assert result.canonical_text == "a b"
    assert result.a_boundaries == result.b_boundaries == (1, 2)
    assert result.disagreement_regions == ()
