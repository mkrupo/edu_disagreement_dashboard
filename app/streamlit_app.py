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
    DisagreementRegion,
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


def local_context(
    edus: tuple[ParsedEDU, ...], selected: tuple[int, ...]
) -> tuple[ParsedEDU, ...]:
    """Return selected EDUs and one immediate neighbor on each available side."""
    if not selected:
        return ()
    positions = {edu.index: position for position, edu in enumerate(edus)}
    start = positions[selected[0]]
    end = positions[selected[-1]]
    return edus[max(0, start - 1):min(len(edus), end + 2)]


def move_difference(step: int, total: int) -> None:
    """Clamp button navigation to the existing comparison's difference range."""
    index = st.session_state.get("difference_index", 0)
    st.session_state["difference_index"] = max(0, min(index + step, total - 1))


def show_annotations(
    result: ComparisonResult,
    names: tuple[str, str],
    region: DisagreementRegion | None,
    *,
    full: bool = False,
) -> None:
    left, right = st.columns(2, gap="medium")
    for column, label, filename, edus, selected in (
        (left, "Annotation A", names[0], result.a_edus,
         region.a_edu_indices if region else ()),
        (right, "Annotation B", names[1], result.b_edus,
         region.b_edu_indices if region else ()),
    ):
        with column:
            st.subheader(label)
            st.caption(filename)
            visible = edus if full else local_context(edus, selected)
            panel = st.container(height=600, border=True) if full else st.container(border=True)
            with panel:
                if visible:
                    st.markdown(render_edus(visible, selected), unsafe_allow_html=True)
                else:
                    st.caption("No non-empty EDU lines.")


def main() -> None:
    st.set_page_config(page_title="EDU Disagreement Dashboard", layout="wide")
    st.title("EDU Disagreement Dashboard")
    st.markdown(
        """<style>
        .stMainBlockContainer { padding-top: 3rem; }
        .edu { padding: .6rem .75rem; border-bottom: 1px solid rgba(128,128,128,.25);
               border-left: 4px solid transparent; }
        .edu.selected { background: rgba(234,179,8,.15); border-left-color: #ca8a04; }
        .edu-label { font-size: .78rem; opacity: .7; margin-bottom: .3rem; }
        .edu-text { white-space: pre-wrap; overflow-wrap: anywhere; min-height: 1.5rem; }
        </style>""",
        unsafe_allow_html=True,
    )

    with st.expander("Inputs", expanded=st.session_state.get("comparison_result") is None):
        left_upload, right_upload = st.columns(2, gap="medium")
        with left_upload:
            a_upload = st.file_uploader(
                "Annotation A (.txt)", type=["txt"], accept_multiple_files=False, key="upload_a"
            )
        with right_upload:
            b_upload = st.file_uploader(
                "Annotation B (.txt)", type=["txt"], accept_multiple_files=False, key="upload_b"
            )
        st.caption("One UTF-8 file per side. Each non-empty line is one EDU.")

    ready = a_upload is not None and b_upload is not None
    a_bytes = a_upload.getvalue() if a_upload is not None else None
    b_bytes = b_upload.getvalue() if b_upload is not None else None
    signature = (
        (a_upload.name, sha256(a_bytes).hexdigest()) if a_upload is not None else None,
        (b_upload.name, sha256(b_bytes).hexdigest()) if b_upload is not None else None,
    )
    # Changing/removing an upload must not leave results from previous files.
    if signature != st.session_state.get("upload_signature", (None, None)):
        st.session_state["upload_signature"] = signature
        st.session_state.pop("comparison_result", None)
        st.session_state.pop("comparison_error", None)
        st.session_state["difference_index"] = 0
        if ready:
            try:
                st.session_state["comparison_result"] = compare_uploads(a_bytes, b_bytes)
            except (ContentMismatchError, BoundaryProjectionError) as error:
                st.session_state["comparison_error"] = str(error)
            except UnicodeDecodeError:
                st.session_state["comparison_error"] = "Both annotations must be UTF-8 encoded text files."
        # Refresh the Inputs default after success, failure, or removal.
        # The unchanged signature prevents repeating the comparison.
        st.rerun()

    result = st.session_state.get("comparison_result")
    if result is None:
        error = st.session_state.get("comparison_error")
        if error:
            st.markdown("**✗ Not comparable**")
            st.error(error)
        else:
            st.caption("Upload Annotation A and Annotation B in Inputs to begin.")
        return

    mode = ("Exact reconstruction" if result.canonical_source == "reconstructed"
            else "Whitespace-normalized")
    status, explanation = st.columns([4, 1])
    with status:
        st.markdown(f"**✓ Comparable** · :gray[{mode}]")
    with explanation:
        with st.popover("About modes"):
            st.markdown("**Exact reconstruction**")
            st.write("The two annotations reconstruct to exactly the same text after EDU line breaks are removed.")
            st.markdown("**Whitespace-normalized**")
            st.write("The annotations differ only in whitespace placement. Whitespace is ignored "
                     "for boundary comparison, but the original annotation text is preserved and displayed unchanged.")

    region = None
    if result.disagreement_regions:
        total = len(result.disagreement_regions)
        index = max(0, min(st.session_state.get("difference_index", 0), total - 1))
        st.session_state["difference_index"] = index
        previous, counter, following = st.columns([1, 2, 1])
        previous.button(
            "← Previous", disabled=index == 0, key="previous_difference",
            on_click=move_difference, args=(-1, total),
        )
        counter.markdown(f"**Difference {index + 1} / {total}**")
        following.button(
            "Next →", disabled=index == total - 1, key="next_difference",
            on_click=move_difference, args=(1, total),
        )
        region = result.disagreement_regions[index]
        show_annotations(result, (a_upload.name, b_upload.name), region)
    else:
        st.info("No segmentation differences. The full annotations are available below.")

    with st.expander("Full annotations", expanded=False):
        show_annotations(result, (a_upload.name, b_upload.name), region, full=True)

    with st.expander("Comparison summary", expanded=False):
        for metrics in (
            (("A EDU count", len(result.a_edus)), ("B EDU count", len(result.b_edus)),
             ("Shared boundaries", len(result.shared_boundaries))),
            (("A-only boundaries", len(result.a_only_boundaries)),
             ("B-only boundaries", len(result.b_only_boundaries)),
             ("Disagreement regions", len(result.disagreement_regions))),
        ):
            for column, (label, value) in zip(st.columns(3), metrics):
                column.metric(label, value)

    with st.expander("Developer diagnostics", expanded=False):
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
