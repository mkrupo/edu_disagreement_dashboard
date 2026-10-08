from html.parser import HTMLParser
import datetime
from pathlib import Path
import re
import runpy

import pytest
import streamlit as st
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


def assert_progress(at, decided, unresolved, open_count):
    expected = f"✓ {decided} Decided · ? {unresolved} Unresolved · ○ {open_count} Open"
    assert any(c.value == expected for c in at.caption)
    assert at.main.caption[0].value == expected  # Above annotation labels and note/navigation below.
    assert decided + unresolved + open_count == len(at.session_state["comparison_result"].disagreement_regions)
    assert not any(c.value.startswith("Assessed ") for c in at.caption)


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
    assert at.number_input(key="disagreement_number").value == 1
    assert at.number_input(key="disagreement_number").min == 1
    assert at.number_input(key="disagreement_number").max == 2

    at.button(key="next_difference").click().run()
    assert at.session_state["difference_index"] == 1
    assert at.number_input(key="disagreement_number").value == 2
    assert at.button(key="next_difference").disabled
    assert not at.button(key="previous_difference").disabled
    at.button(key="previous_difference").click().run()
    assert at.session_state["difference_index"] == 0
    assert at.number_input(key="disagreement_number").value == 1
    at.button(key="next_difference").click().run()

    at.file_uploader(key="upload_a").upload("replacement.txt", b"abc\nde\nf", "text/plain").run()
    assert not at.exception
    assert at.session_state["difference_index"] == 0
    assert at.session_state["comparison_result"].a_edus[0].text == "abc"
    assert at.number_input(key="disagreement_number").value == 1
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


def test_session_labels_keep_existing_workflow_state_and_remove_redundant_captions():
    at = AppTest.from_file(APP_PATH).run()
    assert at.radio(key="workflow").label == "Session"
    assert at.radio(key="workflow").options == ["New session", "Load session"]
    assert at.session_state["workflow"] == "New assessment"
    assert [uploader.label for uploader in at.file_uploader] == ["Annotation A", "Annotation B"]
    assert not at.sidebar.caption
    at.radio(key="workflow").set_value("Load assessment").run()
    assert not at.exception
    assert at.session_state["workflow"] == "Load assessment"
    assert at.file_uploader[0].label == "Session JSON"
    assert at.file_uploader[0].allowed_type == [".json"]
    assert at.file_uploader[0].accept_multiple_files is False
    assert not at.sidebar.caption


@pytest.mark.parametrize(("a", "b"), [(b"ab\ncd", b"ab\ncd"), (b"", b"")])
def test_zero_difference_case(a, b):
    at = upload_pair(AppTest.from_file(APP_PATH).run(), a, b)

    assert not at.exception and not at.error
    assert [button.key for button in at.button] == ["export_session"]
    assert not at.selectbox
    assert any("No segmentation differences" in info.value for info in at.info)
    assert any("Comparable" in element.value for element in at.markdown)
    assert len(at.metric) == 6
    assert [e.label for e in at.expander] == [
        "Full annotations", "Comparison summary", "Developer diagnostics"
    ]
    assert all(not e.proto.expanded for e in at.expander)
    assert not at.segmented_control
    assert_progress(at, 0, 0, 0)
    assert [widget.key for widget in at.number_input] == ["context_edus"]
    assert not any(c.value == "All disagreements reviewed" for c in at.caption)
    assert not at.get("download_button")
    at.button(key="export_session").click().run()
    assert not at.exception
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
    assert_progress(at, int(verdict != "unresolved"), int(verdict == "unresolved"), 1)
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
    assert_progress(at, 1, 1, 0)
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
    assert restored.number_input(key="disagreement_number").value == 2
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
    assert_progress(at, 0, 0, 1)


def test_upload_replacement_discards_previous_assessments_only_after_continue():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef", b"ab\nc\ndef")
    at.segmented_control[0].set_value("a_only").run()
    at.text_area[0].set_value("Previous source").run()
    at.file_uploader(key="upload_a").upload("replacement.edus", b"abc\nde\nf", "text/plain").run()
    assert at.get("dialog")
    assert at.session_state["assessment_session"].a_source.filename == "a.txt"
    at.button(key="continue_replacement").click().run()
    assert not at.exception
    assert at.session_state["difference_index"] == 0
    assert not at.session_state["assessment_session"].assessments
    assert at.segmented_control[0].value is None
    assert at.text_area[0].value == ""


def assessed_pair():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef", b"ab\nc\ndef")
    at.segmented_control[0].set_value("both").run()
    at.text_area[0].set_value("Independent first note").run()
    at.button(key="next_difference").click().run()
    at.segmented_control[0].set_value("unresolved").run()
    at.text_area[0].set_value("Original second note").run()
    at.number_input(key="context_edus").set_value(3).run()
    return at


def assert_replacement_warning(at):
    assert not at.exception
    assert at.get("dialog")[0].proto.dialog.title == "Replace current session?"
    assert any(element.value == (
        "Your current assessments may be lost. Export your session JSON before continuing."
    ) for element in at.markdown)
    assert at.button(key="cancel_replacement").label == "Cancel"
    assert at.button(key="continue_replacement").label == "Continue"


@pytest.mark.parametrize("side", ["a", "b"])
@pytest.mark.parametrize("remove", [False, True], ids=["replace", "remove"])
@pytest.mark.parametrize("decision", ["cancel", "continue"])
def test_assessed_annotation_changes_require_confirmation(side, remove, decision):
    at = assessed_pair()
    session = at.session_state["assessment_session"]
    comparison = session.comparison
    first, second = comparison.disagreement_regions
    other_assessment = session.assessments[first]
    generation = at.session_state["session_generation"]
    at.text_area[0].set_value("Pending edit before changing files")
    uploader = at.file_uploader(key="upload_" + side)
    if remove:
        uploader.clear().run()
    else:
        uploader.upload("replacement.edus", b"abc\ndef", "text/plain").run()
    assert_replacement_warning(at)
    assert at.session_state["assessment_session"] is session
    assert session.assessments[second].note == "Pending edit before changing files"
    assert session.assessments[first] == other_assessment
    assert_navigation(at, 2, 2)
    at.button(key=decision + "_replacement").click().run()
    assert not at.exception and not at.get("dialog")
    if decision == "cancel":
        assert at.session_state["assessment_session"] is session
        assert at.session_state["comparison_result"] is comparison
        assert at.session_state["session_generation"] == generation
        assert at.text_area[0].value == "Pending edit before changing files"
        assert at.segmented_control[0].value == "unresolved"
        assert_navigation(at, 2, 2)
        at.number_input(key="context_edus").set_value(4).run()
        at.button(key="previous_difference_bottom").click().run()
        assert not at.get("dialog")  # Unchanged canceled inputs never apply on later reruns.
        assert at.session_state["assessment_session"] is session
        assert at.text_area[0].value == "Independent first note"
    elif remove:
        assert "assessment_session" not in at.session_state
        assert "comparison_result" not in at.session_state
        assert at.session_state["difference_index"] == 0
    else:
        replacement = at.session_state["assessment_session"]
        assert replacement is not session
        assert not replacement.assessments
        assert getattr(replacement, side + "_source").filename == "replacement.edus"
        assert at.session_state["difference_index"] == 0
        assert at.text_area[0].value == ""


@pytest.mark.parametrize("loaded", [False, True], ids=["new-to-load", "load-to-new"])
@pytest.mark.parametrize("decision", ["cancel", "continue"])
def test_workflow_switch_keeps_current_inputs_until_confirmed(loaded, decision):
    at = assessed_pair()
    if loaded:
        payload = export_session(at.session_state["assessment_session"]).encode("utf-8")
        at = AppTest.from_file(APP_PATH).run()
        at.radio(key="workflow").set_value("Load assessment").run()
        at.file_uploader(key="upload_session").upload("saved.json", payload, "application/json").run()
    session = at.session_state["assessment_session"]
    workflow = at.session_state["workflow"]
    input_names = [uploader.value.name for uploader in at.file_uploader]
    at.text_area[0].set_value("Pending note before switching workflows")
    target = "New assessment" if loaded else "Load assessment"
    at.radio(key="workflow").set_value(target).run()
    assert_replacement_warning(at)
    assert at.radio(key="workflow").value == workflow
    assert [uploader.value.name for uploader in at.file_uploader] == input_names
    assert at.session_state["assessment_session"] is session
    assert at.text_area[0].value == "Pending note before switching workflows"
    at.button(key=decision + "_replacement").click().run()
    assert not at.exception and not at.get("dialog")
    if decision == "cancel":
        assert at.radio(key="workflow").value == workflow
        assert [uploader.value.name for uploader in at.file_uploader] == input_names
        assert at.session_state["assessment_session"] is session
        assert at.text_area[0].value == "Pending note before switching workflows"
        assert_navigation(at, 2, 2)
        at.run()
        assert not at.get("dialog")
    else:
        assert at.radio(key="workflow").value == target
        assert "assessment_session" not in at.session_state
        assert "comparison_result" not in at.session_state
        assert at.session_state["difference_index"] == 0
        assert len(at.file_uploader) == (2 if loaded else 1)


@pytest.mark.parametrize("payload_kind", ["valid", "invalid", "removed"])
@pytest.mark.parametrize("decision", ["cancel", "continue"])
def test_loading_different_json_requires_confirmation(payload_kind, decision):
    from edu_disagreement.sessions import Source, new_session

    original = assessed_pair().session_state["assessment_session"]
    replacement = new_session(Source("new-a.edus", "a\nb\nc"), Source("new-b.txt", "abc"))
    replacement.assess(replacement.comparison.disagreement_regions[0], "b_only", "Replacement note")
    replacement.context_edus = 5
    at = AppTest.from_file(APP_PATH).run()
    at.radio(key="workflow").set_value("Load assessment").run()
    at.file_uploader(key="upload_session").upload(
        "original.json", export_session(original).encode("utf-8"), "application/json"
    ).run()
    session = at.session_state["assessment_session"]
    at.text_area[0].set_value("Pending loaded note")
    uploader = at.file_uploader(key="upload_session")
    if payload_kind == "removed":
        uploader.clear().run()
    else:
        payload = export_session(replacement).encode("utf-8") if payload_kind == "valid" else b"{"
        uploader.upload("replacement.json", payload, "application/json").run()
    assert_replacement_warning(at)
    assert at.session_state["assessment_session"] is session
    assert at.text_area[0].value == "Pending loaded note"
    at.button(key=decision + "_replacement").click().run()
    assert not at.exception and not at.get("dialog")
    if decision == "cancel":
        assert at.session_state["assessment_session"] is session
        assert not at.error
        assert_navigation(at, 2, 2)
        at.run()
        assert at.text_area[0].value == "Pending loaded note"
    elif payload_kind == "valid":
        assert at.session_state["assessment_session"] == replacement
        assert at.text_area[0].value == "Replacement note"
        assert at.segmented_control[0].value == "b_only"
        assert at.number_input(key="context_edus").value == 5
        assert_navigation(at, 1, 1)
    else:
        assert "assessment_session" not in at.session_state
        assert "comparison_result" not in at.session_state
        if payload_kind == "invalid":
            assert "Session validation failed" in at.error[0].value


def test_cancel_preserves_latest_note_in_export_and_new_changes_prompt_again(download_payloads):
    from edu_disagreement.sessions import load_session

    at = assessed_pair()
    session = at.session_state["assessment_session"]
    at.text_area[0].set_value("Note pending before canceled removal")
    at.file_uploader(key="upload_a").clear().run()
    assert_replacement_warning(at)
    at.button(key="cancel_replacement").click().run()
    at.button(key="export_session").click().run()
    restored = load_session(download_payloads[-1])
    assert restored == session
    at.run()  # Close the export dialog.
    at.file_uploader(key="upload_a").upload("different.txt", b"abc\ndef", "text/plain").run()
    assert_replacement_warning(at)  # Cancel is not permission for future changes.


def test_unchanged_sources_and_cleared_assessments_do_not_warn():
    at = assessed_pair()
    session = at.session_state["assessment_session"]
    upload_pair(at, b"a\nbc\nd\nef", b"ab\nc\ndef")
    assert not at.exception and not at.get("dialog")
    assert at.session_state["assessment_session"] is session
    at.segmented_control[0].set_value(None).run()
    at.button(key="previous_difference").click().run()
    at.segmented_control[0].set_value(None).run()
    assert not session.assessments
    at.radio(key="workflow").set_value("Load assessment").run()
    assert not at.get("dialog")
    assert "assessment_session" not in at.session_state


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


@pytest.fixture
def download_payloads(monkeypatch):
    """Capture the actual bytes offered to Streamlit, retaining native controls."""
    payloads = []
    native_download = st.download_button

    def download(label, data, **kwargs):
        payloads.append(data)
        return native_download(label, data, **kwargs)

    monkeypatch.setattr(st, "download_button", download)
    return payloads


def test_export_commits_pending_note_before_offering_download(download_payloads):
    from edu_disagreement.sessions import load_session

    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef", b"ab\nc\ndef")
    at.segmented_control[0].set_value("both").run()
    at.text_area[0].set_value("original note").run()
    at.button(key="next_difference").click().run()
    at.segmented_control[0].set_value("unresolved").run()
    at.text_area[0].set_value("independent other note").run()
    at.button(key="previous_difference").click().run()
    session = at.session_state["assessment_session"]
    first, second = session.comparison.disagreement_regions
    other = session.assessments[second]
    comparison = session.comparison
    assert not download_payloads and not at.get("download_button")

    # Pending note and Export arrive in one interaction, with no prior .run().
    at.text_area[0].set_value("latest edit: é🙂\n  preserved whitespace  ")
    at.button(key="export_session").click().run()

    assert not at.exception
    assert session.assessments[first].note == "latest edit: é🙂\n  preserved whitespace  "
    loaded = load_session(download_payloads[-1])
    assert loaded.assessments == session.assessments
    assert loaded.assessments[second] == other
    assert session.comparison is comparison
    assert at.session_state["difference_index"] == 0
    assert_progress(at, 1, 1, 0)
    assert at.get("dialog")
    assert at.get("download_button")[0].label == "Download session JSON"
    assert at.get("download_button")[0].proto.ignore_rerun
    assert at.text_area[0].proto.help == ""
    assert at.text_area[0].proto.placeholder == "Optional note…"
    assert at.text_area[0].label == "Note (optional)"
    assert at.text_area[0].proto.label_visibility.value == 2  # Native collapsed label, still accessible.
    at.get("download_button")[0].click().run()
    assert session.assessments == loaded.assessments  # Download changes no judgments.


def test_pending_note_survives_navigation_without_separate_submission():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef", b"ab\nc\ndef")
    at.segmented_control[0].set_value("both").run()
    at.text_area[0].set_value("edited just before navigating")
    at.button(key="next_difference").click().run()
    assert not at.exception
    at.button(key="previous_difference").click().run()
    assert at.text_area[0].value == "edited just before navigating"
    assert at.segmented_control[0].value == "both"


def test_loaded_assessment_pending_edit_and_repeated_export(download_payloads):
    from edu_disagreement.sessions import Source, load_session, new_session

    original = new_session(Source("a.edus", "a\nbc\nd\nef"), Source("b.txt", "ab\nc\ndef"))
    first, second = original.comparison.disagreement_regions
    original.assess(first, "both", "loaded first note")
    original.assess(second, "b_only", "other assessment")
    at = AppTest.from_file(APP_PATH).run()
    at.radio(key="workflow").set_value("Load assessment").run()
    at.file_uploader(key="upload_session").upload(
        "session.json", export_session(original).encode("utf-8"), "application/json"
    ).run()
    at.segmented_control[0].set_value("a_only")
    at.text_area[0].set_value("loaded note edited immediately before export")
    at.button(key="export_session").click().run()
    assert not at.exception
    loaded = load_session(download_payloads[-1])
    assert loaded.assessments[first].verdict == "a_only"
    assert loaded.assessments[first].note == "loaded note edited immediately before export"
    assert loaded.assessments[second] == original.assessments[second]
    assert (loaded.a_source, loaded.b_source) == (original.a_source, original.b_source)

    # A full rerun closes the dialog and removes the previous download control.
    at.run()
    assert not at.get("download_button")
    at.text_area[0].set_value("")
    at.button(key="export_session").click().run()
    assert not at.exception
    latest = load_session(download_payloads[-1])
    assert latest.assessments[first].note is None
    assert latest.assessments[second] == original.assessments[second]


def test_progress_counts_all_verdicts_and_an_open_disagreement():
    from edu_disagreement.sessions import Source, new_session

    session = new_session(Source("a.txt", "a\nbc\n" * 6), Source("b.txt", "ab\nc\n" * 6))
    assert helpers["progress_counts"](session) == (0, 0, 6)
    for region, verdict in zip(session.comparison.disagreement_regions, VERDICTS):
        session.assess(region, verdict)
    assert helpers["progress_counts"](session) == (4, 1, 1)
    session.assess(session.comparison.disagreement_regions[-1], "unresolved")
    assert helpers["progress_counts"](session) == (4, 2, 0)


@pytest.mark.parametrize(("verdicts", "counts"), [
    (("both", "neither"), (2, 0, 0)),
    (("a_only", "unresolved"), (1, 1, 0)),
    (("unresolved", "unresolved"), (0, 2, 0)),
])
def test_all_reviewed_status_includes_explicit_unresolved(verdicts, counts):
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef", b"ab\nc\ndef")
    assert not any(c.value == "All disagreements reviewed" for c in at.caption)
    at.segmented_control[0].set_value(verdicts[0]).run()
    at.button(key="next_difference_bottom").click().run()
    at.segmented_control[0].set_value(verdicts[1]).run()
    assert_progress(at, *counts)
    assert any(c.value == "All disagreements reviewed" for c in at.caption)
    assert not any("fully resolved" in c.value.lower() or "adjudicated" in c.value.lower() for c in at.caption)
    assert at.button(key="export_session")
    at.segmented_control[0].set_value(None).run()
    assert not any(c.value == "All disagreements reviewed" for c in at.caption)


def assert_navigation(at, number, total):
    assert not at.exception
    assert at.session_state["difference_index"] == number - 1
    assert at.number_input(key="disagreement_number").value == number
    assert at.session_state["assessment_session"].current_disagreement == number - 1
    for suffix in ("", "_bottom"):
        assert at.button(key="previous_difference" + suffix).disabled == (number == 1)
        assert at.button(key="next_difference" + suffix).disabled == (number == total)


def test_numeric_navigation_and_both_arrow_pairs_stay_synchronized():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef\ng\nhi", b"ab\nc\nde\nf\nghi")
    comparison = at.session_state["comparison_result"]
    assert_navigation(at, 1, 3)
    at.number_input(key="disagreement_number").set_value(2).run()
    assert_navigation(at, 2, 3)
    at.button(key="next_difference_bottom").click().run()
    assert_navigation(at, 3, 3)
    at.button(key="previous_difference").click().run()
    assert_navigation(at, 2, 3)
    at.button(key="previous_difference_bottom").click().run()
    assert_navigation(at, 1, 3)
    at.button(key="next_difference").click().run()
    assert_navigation(at, 2, 3)
    at.number_input(key="disagreement_number").set_value(3).run()
    assert_navigation(at, 3, 3)
    assert at.session_state["comparison_result"] is comparison


@pytest.mark.parametrize("control", ["next_difference", "next_difference_bottom", "disagreement_number"])
def test_all_navigation_controls_preserve_pending_notes(control):
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef", b"ab\nc\ndef")
    at.segmented_control[0].set_value("both").run()
    at.text_area[0].set_value("pending note before " + control)
    if control == "disagreement_number":
        at.number_input(key=control).set_value(2).run()
    else:
        at.button(key=control).click().run()
    assert_navigation(at, 2, 2)
    assert at.segmented_control[0].value is None
    at.button(key="previous_difference_bottom").click().run()
    assert_navigation(at, 1, 2)
    assert at.text_area[0].value == "pending note before " + control
    assert at.segmented_control[0].value == "both"


def test_direct_navigation_restores_on_load_and_resets_with_smaller_upload():
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nbc\nd\nef\ng\nhi", b"ab\nc\nde\nf\nghi")
    at.number_input(key="disagreement_number").set_value(3).run()
    payload = export_session(at.session_state["assessment_session"]).encode("utf-8")
    restored = AppTest.from_file(APP_PATH).run()
    restored.radio(key="workflow").set_value("Load assessment").run()
    restored.file_uploader(key="upload_session").upload("session.json", payload, "application/json").run()
    assert_navigation(restored, 3, 3)
    upload_pair(at, b"abc\ndef\nghi", b"abcdefghi")
    assert_navigation(at, 1, 1)
    assert at.number_input(key="disagreement_number").min == 1
    assert at.number_input(key="disagreement_number").max == 1


def test_export_filename_is_utc_and_stable_for_each_snapshot(monkeypatch):
    real_datetime = datetime.datetime

    class Clock(real_datetime):
        instant = real_datetime(2026, 10, 8, 18, 2, 3, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))

        @classmethod
        def now(cls, tz=None):
            return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)

    monkeypatch.setattr(datetime, "datetime", Clock)
    snapshots = []
    native_download = st.download_button

    def download(label, data, **kwargs):
        snapshots.append((data, kwargs["file_name"]))
        return native_download(label, data, **kwargs)

    monkeypatch.setattr(st, "download_button", download)
    at = upload_pair(AppTest.from_file(APP_PATH).run(), b"a\nb", b"ab")
    at.segmented_control[0].set_value("both").run()
    at.button(key="export_session").click().run()
    assert not at.exception
    snapshot = snapshots[-1]
    assert snapshot[1] == "edu_assessment_20261008_160203_UTC.json"
    assert re.fullmatch(r"edu_assessment_\d{8}_\d{6}_UTC\.json", snapshot[1])
    Clock.instant += datetime.timedelta(seconds=10)
    at.get("download_button")[0].click().run()
    assert snapshots[-1] == snapshot
    at.run()
    at.button(key="export_session").click().run()
    assert not at.exception
    assert snapshots[-1][1] == "edu_assessment_20261008_160213_UTC.json"
    assert snapshots[-1][0] == snapshot[0]  # Timestamp is outside the JSON schema.
