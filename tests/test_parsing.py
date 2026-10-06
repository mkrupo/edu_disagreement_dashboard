import pytest

from edu_disagreement import ParsedEDU, parse_annotation, reconstruct_text


def test_empty_lines_preserve_original_line_numbers(tmp_path):
    path = tmp_path / "annotation.txt"
    path.write_bytes(b"\nalpha\n\n\nbeta\n\n")

    edus = parse_annotation(path)

    assert edus == (ParsedEDU(0, "alpha", 2), ParsedEDU(1, "beta", 5))
    assert reconstruct_text(edus) == "alphabeta"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("trailing_newline", [False, True])
def test_line_endings_remove_only_terminators(tmp_path, newline, trailing_newline):
    path = tmp_path / "annotation.txt"
    text = newline.join(["aaa ", "bbb", "ccc"])
    if trailing_newline:
        text += newline
    path.write_bytes(text.encode("utf-8"))

    edus = parse_annotation(path)

    assert edus == (
        ParsedEDU(0, "aaa ", 1),
        ParsedEDU(1, "bbb", 2),
        ParsedEDU(2, "ccc", 3),
    )
    assert reconstruct_text(edus) == "aaa bbbccc"


def test_whitespace_only_lines_are_non_empty_edus(tmp_path):
    path = tmp_path / "annotation.txt"
    path.write_bytes(b"  alpha\t \n\n \t\nbeta  ")

    edus = parse_annotation(path)

    assert edus == (
        ParsedEDU(0, "  alpha\t ", 1),
        ParsedEDU(1, " \t", 3),
        ParsedEDU(2, "beta  ", 4),
    )
    assert reconstruct_text(edus) == "  alpha\t  \tbeta  "


@pytest.mark.parametrize("content", [b"", b"\n\n", b"\r\n\r\n"])
def test_empty_annotation(tmp_path, content):
    path = tmp_path / "annotation.txt"
    path.write_bytes(content)

    assert parse_annotation(path) == ()
    assert reconstruct_text(parse_annotation(path)) == ""


def test_unicode_line_separators_inside_an_edu_are_preserved(tmp_path):
    path = tmp_path / "annotation.txt"
    path.write_bytes("a\u2028b\u2029c\nv".encode("utf-8"))

    assert parse_annotation(path) == (
        ParsedEDU(0, "a\u2028b\u2029c", 1),
        ParsedEDU(1, "v", 2),
    )


def test_invalid_utf8_is_not_silently_replaced(tmp_path):
    path = tmp_path / "annotation.txt"
    path.write_bytes(b"a\xff\n")

    with pytest.raises(UnicodeDecodeError):
        parse_annotation(path)
