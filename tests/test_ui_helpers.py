from html.parser import HTMLParser
from pathlib import Path
import runpy

import pytest
from streamlit.testing.v1 import AppTest

from edu_disagreement import ParsedEDU
from edu_disagreement.sessions import VERDICTS, export_session


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
    assert at.button(key="previous_difference").label == "←"
    assert at.button(key="next_difference").label == "→"
    assert at.button(key="previous_difference").proto.help == "Previous disagreement"
    assert at.button(key="next_difference").proto.help == "Next disagreement"
    assert not at.selectbox
    assert all(not expander.proto.expanded for expander in at.expander)
    assert any("Disagreement 1 / 2" in element.value for element in at.markdown)

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
    assert not at.expander


@pytest.mark.parametrize(
    ("a", "b", "mode"),
    [(b"a\nb", b"ab", "Exact reconstruction"),
     (b"a \nb", b"ab", "Whitespace-normalized")],
)
def test_comparison_mode_explanation_is_accessible_in_status_help(a, b, mode):
    at = upload_pair(AppTest.from_file(APP_PATH).run(), a, b)
    status = next(element for element in at.markdown if element.value.startswith("**✓ Comparable**"))

    assert mode in status.value
    assert "**Exact reconstruction**" in status.proto.help
    assert "exactly the same text after EDU line breaks are removed" in status.proto.help
    assert "**Whitespace-normalized**" in status.proto.help
    assert "Whitespace is ignored for boundary comparison" in status.proto.help
    assert "original EDU text is preserved unchanged" in status.proto.help


def test_uploaders_accept_one_text_file_each():
    at = AppTest.from_file(APP_PATH).run()

    assert len(at.file_uploader) == 2
    for uploader in at.file_uploader:
        assert uploader.accept_multiple_files is False
        assert uploader.allowed_type == [".txt", ".edus"]
    assert len(at.sidebar.file_uploader) == 2
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
        "Full annotations", "Comparison summary", "Developer diagnostics"
    ]
    assert all(not e.proto.expanded for e in at.expander)
    assert not at.segmented_control
    assert any(c.value == "Assessed 0 / 0" for c in at.caption)
    assert len(at.get("download_button")) == 1


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


@pytest.mark.parametrize(("size", "expected"), [(0, (3,)), (1, (2, 3, 4)), (3, tuple(range(7))),
                                                 (10, tuple(range(7)))])
def test_parameterized_context(size, expected):
    edus = tuple(ParsedEDU(i, str(i), i + 1) for i in range(7))
    assert helpers["local_context"](edus, (3,), size) == tuple(edus[i] for i in expected)


@pytest.mark.parametrize("verdict", VERDICTS)
def test_each_verdict_is_saved_immediately_without_advancing(verdict):
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef", b"ab\nc\ndef")
    session = at.session_state["assessment_session"]
    region = session.comparison.disagreement_regions[0]
    assert region not in session.assessments
    assert at.segmented_control[0].value is None
    assert at.text_area[0].disabled

    at.segmented_control[0].set_value(verdict).run()
    assert not at.exception
    assert session.assessments[region].verdict == verdict
    assert at.session_state["difference_index"] == 0
    assert any(c.value == "Assessed 1 / 2" for c in at.caption)
    assert not at.text_area[0].disabled


def test_assessments_and_independent_notes_survive_navigation_and_json_only_reload():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef", b"ab\nc\ndef")
    at.segmented_control[0].set_value("both").run()
    at.text_area[0].set_value("First note: é\nsecond line").run()
    at.button(key="next_difference").click().run()
    assert at.segmented_control[0].value is None
    assert at.text_area[0].value == ""
    at.segmented_control[0].set_value("unresolved").run()
    at.text_area[0].set_value("Independent second note").run()
    at.number_input(key="context_edus").set_value(3).run()
    original_comparison = at.session_state["comparison_result"]
    at.number_input(key="context_edus").set_value(4).run()
    assert at.session_state["comparison_result"] is original_comparison
    at.button(key="previous_difference").click().run()
    assert at.segmented_control[0].value == "both"
    assert at.text_area[0].value == "First note: é\nsecond line"
    at.button(key="next_difference").click().run()
    assert at.segmented_control[0].value == "unresolved"
    assert at.text_area[0].value == "Independent second note"
    assert any(c.value == "Assessed 2 / 2" for c in at.caption)
    payload = export_session(at.session_state["assessment_session"]).encode("utf-8")

    restored = AppTest.from_file(APP_PATH).run()
    restored.radio(key="workflow").set_value("Load assessment").run()
    assert len(restored.file_uploader) == 1
    assert restored.file_uploader[0].accept_multiple_files is False
    assert restored.file_uploader[0].allowed_type == [".json"]
    restored.file_uploader(key="upload_session").upload("session.json", payload, "application/json").run()
    assert not restored.exception and not restored.error
    assert len(restored.file_uploader) == 1  # No separate A/B uploads.
    assert restored.session_state["comparison_result"] == original_comparison
    assert restored.session_state["comparison_result"] is not original_comparison
    assert restored.session_state["difference_index"] == 1
    assert restored.number_input(key="context_edus").value == 4
    assert restored.segmented_control[0].value == "unresolved"
    assert restored.text_area[0].value == "Independent second note"
    restored.button(key="previous_difference").click().run()
    assert restored.segmented_control[0].value == "both"
    assert restored.text_area[0].value == "First note: é\nsecond line"


def test_deselecting_verdict_means_unassessed():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nb", b"ab")
    at.segmented_control[0].set_value("unresolved").run()
    assert len(at.session_state["assessment_session"].assessments) == 1
    at.segmented_control[0].set_value(None).run()
    assert not at.exception
    assert not at.session_state["assessment_session"].assessments
    assert any(c.value == "Assessed 0 / 1" for c in at.caption)


def test_upload_replacement_discards_previous_assessments():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef", b"ab\nc\ndef")
    at.segmented_control[0].set_value("a_only").run()
    at.text_area[0].set_value("Previous source").run()
    at.file_uploader(key="upload_a").upload("replacement.edus", b"abc\nde\nf", "text/plain").run()
    assert not at.exception
    assert at.session_state["difference_index"] == 0
    assert not at.session_state["assessment_session"].assessments
    assert at.segmented_control[0].value is None
    assert at.text_area[0].value == ""


def test_edus_extension_uses_identical_parser():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a \r\nb", b"ab")
    comparison = at.session_state["comparison_result"]
    at.file_uploader(key="upload_a").upload("a.edus", b"a \r\nb", "text/plain")
    at.file_uploader(key="upload_b").upload("b.edus", b"ab", "text/plain").run()
    assert at.session_state["comparison_result"] == comparison
    assert at.session_state["assessment_session"].a_source.content == "a \r\nb"


def test_invalid_loaded_session_clears_previous_comparison_and_shows_error():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nb", b"ab")
    at.radio(key="workflow").set_value("Load assessment").run()
    at.file_uploader(key="upload_session").upload("bad.json", b"{", "application/json").run()
    assert not at.exception
    assert "comparison_result" not in at.session_state
    assert "assessment_session" not in at.session_state
    assert "Session validation failed" in at.error[0].value
    assert not at.get("download_button")
