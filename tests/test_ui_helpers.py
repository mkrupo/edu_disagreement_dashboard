from html.parser import HTMLParser
from pathlib import Path
import runpy

import pytest
from streamlit.testing.v1 import AppTest

from edu_disagreement import ParsedEDU


helpers = runpy.run_path(str(Path(__file__).parents[1] / "app" / "streamlit_app.py"))
APP_PATH = str(Path(__file__).parents[1] / "app" / "streamlit_app.py")


class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.indices = []
        self.selected = []
        self.text = []
        self.in_text = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-edu-index" in attrs:
            self.indices.append(int(attrs["data-edu-index"]))
        if "selected" in attrs.get("class", "").split():
            self.selected.append(int(attrs["data-edu-index"]))
        if attrs.get("class") == "edu-text":
            self.in_text = True

    def handle_endtag(self, tag):
        if tag == "div":
            self.in_text = False

    def handle_data(self, data):
        if self.in_text:
            self.text.append(data)


def upload_pair(at, a, b):
    at.file_uploader(key="upload_a").upload("a.txt", a, "text/plain")
    at.file_uploader(key="upload_b").upload("b.txt", b, "text/plain")
    return at.run()


def test_upload_adapter_uses_existing_parser_and_preserves_lines():
    result = helpers["compare_uploads"](b"\r\naaa \r\n\r\nbbb\r\n", b"aaa\nbbb\n")

    assert result.canonical_source == "whitespace_normalized"
    assert result.a_edus == (ParsedEDU(0, "aaa ", 2), ParsedEDU(1, "bbb", 4))
    assert result.shared_boundaries == (3,)
    assert result.disagreement_regions == ()


def test_rendering_escapes_original_text_and_marks_only_selected_indices():
    texts = ("  <script>alert('x')</script> & **text**  ", "\t ", "é🙂")
    edus = tuple(ParsedEDU(i, text, i + 1) for i, text in enumerate(texts))
    rendered = helpers["render_edus"](edus, (1, 2))
    parsed = Rows()
    parsed.feed(rendered)

    assert "<script>" not in rendered
    assert parsed.selected == [1, 2]
    assert tuple(parsed.text) == texts


@pytest.mark.parametrize(
    ("selected", "expected"),
    [((0, 1), (0, 1, 2)), ((2,), (1, 2, 3)), ((3, 4), (2, 3, 4)), ((), ())],
    ids=["document-start", "middle", "document-end", "no-selection"],
)
def test_local_context_calculation(selected, expected):
    edus = tuple(ParsedEDU(i, text, i + 1) for i, text in enumerate(("a ", "b", "c", "d", "e")))

    visible = helpers["local_context"](edus, selected)

    assert visible == tuple(edus[i] for i in expected)


def test_local_context_uses_edu_indices_in_annotation_order():
    edus = (ParsedEDU(7, "before", 8), ParsedEDU(8, "selected", 10), ParsedEDU(9, "after", 11))

    assert helpers["local_context"](edus, (8,)) == edus


def test_context_edus_remain_unselected_and_preserve_text():
    edus = tuple(ParsedEDU(i, text, i + 1) for i, text in enumerate(("a ", "b\t ", "<c>", "d", "e")))
    selected = (2,)
    visible = helpers["local_context"](edus, selected)
    rendered = helpers["render_edus"](visible, selected)
    rows = Rows()
    rows.feed(rendered)

    assert rows.indices == [1, 2, 3]
    assert rows.selected == [2]
    assert rows.text == ["b\t ", "<c>", "d"]


def test_automatic_comparison_navigation_and_upload_replacement():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef", b"ab\nc\ndef")

    assert not at.exception
    assert at.session_state["difference_index"] == 0
    assert at.button(key="previous_difference").disabled
    assert not at.button(key="next_difference").disabled
    assert not at.selectbox
    assert all(not expander.proto.expanded for expander in at.expander)
    assert any("Difference 1 / 2" in element.value for element in at.markdown)

    at.button(key="next_difference").click().run()
    assert at.session_state["difference_index"] == 1
    assert at.button(key="next_difference").disabled
    assert not at.button(key="previous_difference").disabled
    at.button(key="previous_difference").click().run()
    assert at.session_state["difference_index"] == 0
    at.button(key="next_difference").click().run()

    at.file_uploader(key="upload_a").upload("replacement.txt", b"abc\nde\nf", "text/plain").run()
    assert not at.exception
    assert at.session_state["difference_index"] == 0
    assert at.session_state["comparison_result"].a_edus[0].text == "abc"
    assert at.button(key="previous_difference").disabled

    at.file_uploader(key="upload_b").clear().run()
    assert not at.exception
    assert at.session_state["difference_index"] == 0
    assert "comparison_result" not in at.session_state
    assert not at.button and not at.metric
    assert at.expander[0].proto.expanded


def test_uploaders_accept_one_text_file_each():
    at = AppTest.from_file(APP_PATH).run()

    assert len(at.file_uploader) == 2
    for uploader in at.file_uploader:
        assert uploader.accept_multiple_files is False
        assert uploader.allowed_type == [".txt"]
    at.file_uploader(key="upload_a").upload("a.txt", b"a", "text/plain").run()
    assert "comparison_result" not in at.session_state
    assert not at.button


@pytest.mark.parametrize(("a", "b"), [(b"ab\ncd", b"ab\ncd"), (b"", b"")])
def test_zero_difference_case(a, b):
    at = upload_pair(AppTest.from_file(APP_PATH).run(), a, b)

    assert not at.exception and not at.error
    assert not at.button and not at.selectbox
    assert any("No segmentation differences" in info.value for info in at.info)
    assert any("Comparable" in element.value for element in at.markdown)
    assert len(at.metric) == 6
    assert [e.label for e in at.expander] == [
        "Inputs", "Full annotations", "Comparison summary", "Developer diagnostics"
    ]
    assert all(not e.proto.expanded for e in at.expander)


@pytest.mark.parametrize(
    ("a", "b", "message"),
    [(b"ab", b"ac", "texts differ"), (b"a\n \nb", b"ab", "collapses distinct"),
     (b"\xff", b"a", "UTF-8")],
)
def test_failed_comparison_clears_results_and_displays_error(a, b, message):
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nb", b"ab")
    assert "comparison_result" in at.session_state
    upload_pair(at, a, b)

    assert not at.exception
    assert "comparison_result" not in at.session_state
    assert len(at.error) == 1 and message in at.error[0].value
    assert any("Not comparable" in element.value for element in at.markdown)
    assert not at.metric
    at.run()
    assert len(at.error) == 1  # Error remains accessible on later reruns.
