from html.parser import HTMLParser
from pathlib import Path
import runpy

from edu_disagreement import ParsedEDU


helpers = runpy.run_path(str(Path(__file__).parents[1] / "app" / "streamlit_app.py"))


def test_upload_adapter_uses_existing_parser_and_preserves_lines():
    result = helpers["compare_uploads"](b"\r\naaa \r\n\r\nbbb\r\n", b"aaa\nbbb\n")

    assert result.canonical_source == "whitespace_normalized"
    assert result.a_edus == (ParsedEDU(0, "aaa ", 2), ParsedEDU(1, "bbb", 4))
    assert result.shared_boundaries == (3,)
    assert result.disagreement_regions == ()


def test_rendering_escapes_original_text_and_marks_only_selected_indices():
    class Rows(HTMLParser):
        def __init__(self):
            super().__init__()
            self.selected = []
            self.text = []
            self.in_text = False

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
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

    texts = ("  <script>alert('x')</script> & **text**  ", "\t ", "é🙂")
    edus = tuple(ParsedEDU(i, text, i + 1) for i, text in enumerate(texts))
    rendered = helpers["render_edus"](edus, (1, 2))
    parsed = Rows()
    parsed.feed(rendered)

    assert "<script>" not in rendered
    assert parsed.selected == [1, 2]
    assert tuple(parsed.text) == texts
