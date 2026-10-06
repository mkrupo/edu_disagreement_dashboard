"""Local inspection UI; all scientific behavior stays in edu_disagreement."""

from hashlib import sha256
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from edu_disagreement import (
    BoundaryProjectionError,
    ComparisonResult,
    ContentMismatchError,
    ParsedEDU,
    compare_annotations,
    parse_annotation,
)


def compare_uploads(a_bytes: bytes, b_bytes: bytes) -> ComparisonResult:
    """Use the existing file parser, removing temporary uploads after parsing."""
    with TemporaryDirectory(prefix="edu-comparison-") as directory:
        a_path, b_path = Path(directory) / "a.txt", Path(directory) / "b.txt"
        a_path.write_bytes(a_bytes)
        b_path.write_bytes(b_bytes)
        return compare_annotations(parse_annotation(a_path), parse_annotation(b_path))


def render_edus(edus: tuple[ParsedEDU, ...], selected: tuple[int, ...]) -> str:
    """Escape original EDU content and mark exactly the selected EDU indices."""
    selected_indices = set(selected)
    rows = []
    for edu in edus:
        highlighted = edu.index in selected_indices
        css_class = "edu selected" if highlighted else "edu"
        marker = " · selected" if highlighted else ""
        rows.append(
            f'<div class="{css_class}" data-edu-index="{edu.index}">'
            f'<div class="edu-label">EDU {edu.index + 1} · source line '
            f'{edu.line_number}{marker}</div>'
            f'<div class="edu-text">{escape(edu.text)}</div></div>'
        )
    return '<div class="edu-list">' + "".join(rows) + "</div>"


def main() -> None:
    st.set_page_config(page_title="EDU Disagreement Dashboard", layout="wide")
    st.title("EDU Disagreement Dashboard")
    st.caption("Inspect two segmentations of the same text. Each non-empty line is one EDU.")
    st.markdown(
        """<style>
        .edu { padding: .8rem 1rem; border-bottom: 1px solid rgba(128,128,128,.25);
               border-left: 4px solid transparent; }
        .edu.selected { background: rgba(234,179,8,.15); border-left-color: #ca8a04; }
        .edu-label { font-size: .78rem; opacity: .7; margin-bottom: .3rem; }
        .edu-text { white-space: pre-wrap; overflow-wrap: anywhere; min-height: 1.5rem; }
        </style>""",
        unsafe_allow_html=True,
    )

    left_upload, right_upload = st.columns(2, gap="large")
    with left_upload:
        a_upload = st.file_uploader("Annotation A (.txt)", type=["txt"], key="upload_a")
    with right_upload:
        b_upload = st.file_uploader("Annotation B (.txt)", type=["txt"], key="upload_b")

    ready = a_upload is not None and b_upload is not None
    signature = None
    if ready:
        a_bytes, b_bytes = a_upload.getvalue(), b_upload.getvalue()
        signature = (
            a_upload.name, sha256(a_bytes).hexdigest(),
            b_upload.name, sha256(b_bytes).hexdigest(),
        )
    # Changing/removing an upload must not leave results from previous files.
    if signature != st.session_state.get("upload_signature"):
        st.session_state["upload_signature"] = signature
        st.session_state.pop("comparison_result", None)
        st.session_state.pop("selected_region", None)

    if st.button("Compare annotations", disabled=not ready, type="primary"):
        st.session_state.pop("comparison_result", None)
        st.session_state.pop("selected_region", None)
        try:
            st.session_state["comparison_result"] = compare_uploads(a_bytes, b_bytes)
        except (ContentMismatchError, BoundaryProjectionError) as error:
            st.error(str(error))
            return
        except UnicodeDecodeError:
            st.error("Both annotations must be UTF-8 encoded text files.")
            return

    result = st.session_state.get("comparison_result")
    if result is None:
        st.info("Choose Compare annotations to inspect the uploaded files." if ready
                else "Upload both annotation files, then choose Compare annotations.")
        return

    st.divider()
    for metrics in (
        (("A EDU count", len(result.a_edus)), ("B EDU count", len(result.b_edus)),
         ("Shared boundaries", len(result.shared_boundaries))),
        (("A-only boundaries", len(result.a_only_boundaries)),
         ("B-only boundaries", len(result.b_only_boundaries)),
         ("Disagreement regions", len(result.disagreement_regions))),
    ):
        for column, (label, value) in zip(st.columns(3), metrics):
            column.metric(label, value)
    st.caption(f"Comparison mode: `{result.canonical_source}`")
    if result.canonical_source == "whitespace_normalized":
        st.caption("Whitespace is ignored for comparison. Both columns show the original EDU text.")

    region = None
    if result.disagreement_regions:
        total = len(result.disagreement_regions)
        number = st.selectbox(
            "Disagreement region",
            options=range(1, total + 1),
            format_func=lambda n: f"Disagreement {n} / {total}",
            key="selected_region",
        )
        region = result.disagreement_regions[number - 1]
        st.caption("Highlighted EDUs belong to the selected disagreement region.")
    else:
        st.info("No segmentation disagreements detected.")

    left, right = st.columns(2, gap="large")
    for column, label, filename, edus, selected in (
        (left, "Annotation A", a_upload.name, result.a_edus,
         region.a_edu_indices if region else ()),
        (right, "Annotation B", b_upload.name, result.b_edus,
         region.b_edu_indices if region else ()),
    ):
        with column:
            st.subheader(label)
            st.caption(filename)
            if selected:
                st.caption("Selected EDUs: " + ", ".join(str(i + 1) for i in selected))
            with st.container(height=600, border=True):
                if edus:
                    st.markdown(render_edus(edus, selected), unsafe_allow_html=True)
                else:
                    st.caption("No non-empty EDU lines.")

    with st.expander("Comparison diagnostics", expanded=False):
        if region:
            st.caption(f"Selected canonical span: [{region.start_offset}, {region.end_offset})")
        if result.canonical_source == "whitespace_normalized":
            st.caption("Canonical text below is a whitespace-free comparison representation, "
                       "not the original source text.")
        else:
            st.caption("Canonical text below is reconstructed by concatenating the original EDUs.")
        st.code(result.canonical_text, language=None)
        st.json(result.to_dict())


if __name__ == "__main__":
    main()
