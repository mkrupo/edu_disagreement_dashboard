"""Local inspection UI; all scientific behavior stays in edu_disagreement."""

from datetime import datetime, timezone
from hashlib import sha256
from html import escape

import streamlit as st

from edu_disagreement import (
    BoundaryProjectionError,
    ComparisonResult,
    ContentMismatchError,
    DisagreementRegion,
    ParsedEDU,
)
from edu_disagreement.sessions import (
    VERDICTS, Session, SessionValidationError, Source, compare_uploads,
    export_session, load_session, new_session,
)


VERDICT_LABELS = {
    "a_only": "A only", "both": "Both", "b_only": "B only",
    "neither": "Neither / alternative needed", "unresolved": "Unresolved",
}


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
    edus: tuple[ParsedEDU, ...], selected: tuple[int, ...], context_edus: int = 1
) -> tuple[ParsedEDU, ...]:
    """Return selected EDUs and up to N neighbors on each available side."""
    if context_edus < 0:
        raise ValueError("Context size must be non-negative.")
    if not selected:
        return ()
    positions = {edu.index: position for position, edu in enumerate(edus)}
    start = positions[selected[0]]
    end = positions[selected[-1]]
    return edus[max(0, start - context_edus):min(len(edus), end + context_edus + 1)]


def move_difference(step: int, total: int) -> None:
    """Clamp button navigation to the existing comparison's difference range."""
    index = st.session_state.get("difference_index", 0)
    st.session_state["difference_index"] = max(0, min(index + step, total - 1))
    st.session_state["disagreement_number"] = st.session_state["difference_index"] + 1


def jump_to_disagreement(total: int) -> None:
    number = st.session_state["disagreement_number"]
    index = number - 1 if type(number) is int else st.session_state["difference_index"]
    st.session_state["difference_index"] = max(0, min(index, total - 1))
    st.session_state["disagreement_number"] = st.session_state["difference_index"] + 1


def progress_counts(session: Session) -> tuple[int, int, int]:
    """Count decided, explicit unresolved, and absent assessments separately."""
    decided = unresolved = open_count = 0
    for region in session.comparison.disagreement_regions:
        assessment = session.assessments.get(region)
        if assessment is None:
            open_count += 1
        elif assessment.verdict == "unresolved":
            unresolved += 1
        else:
            decided += 1
    return decided, unresolved, open_count


def show_progress(session: Session) -> None:
    decided, unresolved, open_count = progress_counts(session)
    with st.container(horizontal_alignment="center", gap="small"):
        st.caption(f"✓ {decided} Decided · ? {unresolved} Unresolved · ○ {open_count} Open",
                   width="content")
        if session.comparison.disagreement_regions and open_count == 0:
            st.caption("All disagreements reviewed", width="content")


def show_navigation(index: int, total: int, *, bottom: bool = False) -> None:
    suffix = "_bottom" if bottom else ""
    with st.container(
        horizontal=True, horizontal_alignment="center", vertical_alignment="center", gap="small"
    ):
        st.button(
            "←", help="Previous disagreement", width="content",
            disabled=index == 0, key=f"previous_difference{suffix}",
            on_click=move_difference, args=(-1, total),
        )
        if not bottom:
            st.markdown("**Disagreement**", width="content")
            st.number_input(
                "Disagreement number", min_value=1, max_value=total, step=1,
                key="disagreement_number", width=110, label_visibility="collapsed", required=True,
                on_change=jump_to_disagreement, args=(total,),
            )
            st.markdown(f"/ {total}", width="content")
        st.button(
            "→", help="Next disagreement", width="content",
            disabled=index == total - 1, key=f"next_difference{suffix}",
            on_click=move_difference, args=(1, total),
        )


def show_annotations(
    result: ComparisonResult,
    names: tuple[str, str],
    region: DisagreementRegion | None,
    *,
    full: bool = False,
    context_edus: int = 1,
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
            visible = edus if full else local_context(edus, selected, context_edus)
            panel = st.container(height=600, border=True) if full else st.container(border=True)
            with panel:
                if visible:
                    st.markdown(render_edus(visible, selected), unsafe_allow_html=True)
                else:
                    st.caption("No non-empty EDU lines.")


def save_assessment(region: DisagreementRegion, verdict_key: str, note_key: str) -> None:
    """Widget state is temporary; judgments live in the region-keyed session."""
    st.session_state["assessment_session"].assess(
        region, st.session_state.get(verdict_key), st.session_state.get(note_key) or None
    )


def show_assessment(region: DisagreementRegion) -> tuple[str, str]:
    session = st.session_state["assessment_session"]
    assessment = session.assessments.get(region)
    identity = sha256(repr(region).encode("utf-8")).hexdigest()
    suffix = f'{st.session_state["session_generation"]}_{identity}'
    verdict_key, note_key = f"verdict_{suffix}", f"note_{suffix}"
    # Streamlit removes widgets when navigating away. Restore from durable
    # region-keyed records rather than relying on hidden widget state.
    if verdict_key not in st.session_state:
        st.session_state[verdict_key] = assessment.verdict if assessment else None
    if note_key not in st.session_state:
        st.session_state[note_key] = (assessment.note or "") if assessment else ""
    with st.container(horizontal_alignment="center"):
        st.markdown("**Which segmentation is defensible?**", width="content")
        st.segmented_control(
            "Which segmentation is defensible?", VERDICTS,
            selection_mode="single", format_func=VERDICT_LABELS.__getitem__,
            label_visibility="collapsed", width="content", key=verdict_key,
            on_change=save_assessment, args=(region, verdict_key, note_key),
        )
        st.text_area(
            "Note (optional)", key=note_key, width=650, height=100,
            disabled=st.session_state[verdict_key] is None,
            placeholder="Optional note…",
            on_change=save_assessment, args=(region, verdict_key, note_key),
        )
    return verdict_key, note_key


@st.dialog("Export session JSON", on_dismiss="rerun")
def show_export_dialog(payload: bytes, filename: str) -> None:
    """Offer an immutable export while the note editor is behind a modal."""
    st.caption("Your current note is saved in this export. Download the JSON, "
               "then close this dialog to continue editing.")
    st.download_button(
        "Download session JSON", payload, file_name=filename,
        mime="application/json", on_click="ignore",
    )


def export_filename() -> str:
    return datetime.now(timezone.utc).strftime("edu_assessment_%Y%m%d_%H%M%S_UTC.json")


def sidebar_inputs() -> None:
    """Replace the active session only when uploaded source contents change."""
    with st.sidebar:
        workflow = st.radio("Workflow", ("New assessment", "Load assessment"), key="workflow")
        if workflow == "New assessment":
            a_upload = st.file_uploader(
                "Annotation A (.txt / .edus)", type=["txt", "edus"],
                accept_multiple_files=False, key="upload_a",
            )
            b_upload = st.file_uploader(
                "Annotation B (.txt / .edus)", type=["txt", "edus"],
                accept_multiple_files=False, key="upload_b",
            )
            st.caption("One UTF-8 file per side. Each non-empty line is one EDU.")
            uploads = (a_upload, b_upload)
        else:
            uploads = (st.file_uploader(
                "Saved session (.json)", type=["json"], accept_multiple_files=False, key="upload_session"
            ),)
            st.caption("Restores both embedded annotations and their assessments.")

        signature = (workflow, tuple(
            (upload.name, sha256(upload.getvalue()).hexdigest()) if upload is not None else None
            for upload in uploads
        ))
        if signature != st.session_state.get("upload_signature"):
            st.session_state["upload_signature"] = signature
            for key in ("assessment_session", "comparison_result", "comparison_error"):
                st.session_state.pop(key, None)
            st.session_state["difference_index"] = 0
            st.session_state["disagreement_number"] = 1
            st.session_state["session_generation"] = st.session_state.get("session_generation", 0) + 1
            if all(upload is not None for upload in uploads):
                try:
                    if workflow == "New assessment":
                        session = new_session(*(Source(upload.name, upload.getvalue().decode("utf-8"))
                                                for upload in uploads))
                        session.context_edus = st.session_state.get("context_edus", 1)
                    else:
                        session = load_session(uploads[0].getvalue())
                    st.session_state["assessment_session"] = session
                    st.session_state["comparison_result"] = session.comparison
                    st.session_state["difference_index"] = session.current_disagreement
                    st.session_state["disagreement_number"] = session.current_disagreement + 1
                    st.session_state["context_edus"] = session.context_edus
                except SessionValidationError as error:
                    st.session_state["comparison_error"] = f"Session validation failed: {error}"
                except (ContentMismatchError, BoundaryProjectionError) as error:
                    st.session_state["comparison_error"] = str(error)
                except UnicodeDecodeError:
                    st.session_state["comparison_error"] = "Both annotations must be UTF-8 encoded text files."

        st.session_state.setdefault("context_edus", 1)
        st.number_input("Context EDUs: ± N", min_value=0, max_value=10, step=1, key="context_edus")


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

    sidebar_inputs()

    result = st.session_state.get("comparison_result")
    if result is None:
        error = st.session_state.get("comparison_error")
        if error:
            st.markdown("**✗ Not comparable**")
            st.error(error)
        else:
            st.caption("Upload Annotation A and Annotation B, or load a saved session, in the sidebar.")
        return

    session = st.session_state["assessment_session"]
    session.context_edus = st.session_state["context_edus"]
    names = (session.a_source.filename, session.b_source.filename)

    mode = ("Exact reconstruction" if result.canonical_source == "reconstructed"
            else "Whitespace-normalized")
    st.markdown(
        f"**✓ Comparable** · :gray[{mode}]",
        width="content",
        help=(
            "**Exact reconstruction**\n\n"
            "The two annotations reconstruct to exactly the same text after EDU line breaks are removed.\n\n"
            "**Whitespace-normalized**\n\n"
            "The annotations differ only in whitespace placement. Whitespace is ignored for boundary "
            "comparison, while original EDU text is preserved unchanged."
        ),
    )

    region = None
    assessment_widgets = None
    show_progress(session)
    if result.disagreement_regions:
        total = len(result.disagreement_regions)
        index = max(0, min(st.session_state.get("difference_index", 0), total - 1))
        st.session_state["difference_index"] = index
        # Synchronize before creating the numeric widget, including after upload
        # replacement or session restoration. Callbacks run before this script.
        st.session_state["disagreement_number"] = index + 1
        show_navigation(index, total)
        region = result.disagreement_regions[index]
        show_annotations(result, names, region, context_edus=session.context_edus)
        assessment_widgets = show_assessment(region)
        show_navigation(index, total, bottom=True)
    else:
        st.info("No segmentation differences. The full annotations are available below.")

    session.current_disagreement = st.session_state["difference_index"]
    with st.sidebar:
        if st.button("Export session JSON", key="export_session"):
            # A normal button rerun receives pending note edits before creating
            # download bytes. A direct download starts before that rerun ends.
            if region is not None:
                save_assessment(region, *assessment_widgets)
            show_export_dialog(export_session(session).encode("utf-8"), export_filename())
        st.caption("Export JSON to keep your work.")

    with st.expander("Full annotations", expanded=False):
        show_annotations(result, names, region, full=True)

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
