# Working in this repository

## Purpose and sources of truth

Compare exactly two EDU annotations symmetrically. Neither A nor B is gold, and segmentation disagreement does not imply annotation error.

Read [the current comparison contract](docs/first_slice.md) and [the project handoff](docs/EDU_disagreement_dashboard_handoff.md) before changing scientific behavior. The original handoff is broader planning context; the current bounded task and explicit user instructions take precedence. Do not implement later milestones without a request.

## Documentation responsibilities

- Keep `README.md` minimal: purpose, setup, and links. Do not accumulate architecture, decision logs, or detailed behavior there.
- Update this file as project structure, workflows, and development constraints evolve. Keep guidance accurate and remove stale instructions.
- Put scientific contracts, examples, and durable design decisions in `docs/`; link them from here.
- Preserve the original project handoff as planning context.

## Current implemented slice

- Two UTF-8 files, one non-empty line per EDU; ignore only empty lines, retaining original one-based source line numbers.
- Preserve line content exactly, including leading/trailing spaces and whitespace-only EDUs. Remove only line terminators using ordinary Python universal-newline handling.
- Reconstruct by concatenation without separators. Prefer exact equality with `canonical_source="reconstructed"`. Only when reconstructions differ, remove characters satisfying `str.isspace()` and compare the resulting sequences with `canonical_source="whitespace_normalized"`. Raise `ContentMismatchError` if non-whitespace sequences differ.
- Preserve original parsed EDUs on both paths. In the fallback, project endpoints by counting preceding non-whitespace code points. Raise `BoundaryProjectionError` if distinct internal boundaries in either annotation collapse to the same offset, before creating boundary sets.
- Offsets are Python Unicode code-point indices, with half-open `[start, end)` spans. EDU indices are zero-based.
- Only internal EDU endpoints inside the canonical document are annotation boundaries. Document start/end are implicit region anchors. Projected endpoints at anchors are excluded from boundary decisions; whitespace-only edge EDUs remain in the parsed annotation but do not overlap canonical regions.
- Group all differences between consecutive shared anchors into one region and record ordered, overlapping EDU indices.
- Export the small JSON schema documented in `docs/first_slice.md`, with sorted boundaries and regions in document order.

The local Streamlit interface is a thin inspection layer: upload exactly one A/B `.txt` file per side in Inputs and compare automatically. Show comparability and a subdued mode description; navigate with Previous/Next buttons and a zero-based difference index in session state. Upload replacement/removal clears old results and resets navigation. The main symmetric A/B view shows the selected EDUs plus one neighbor on each side, calculated from EDU indices without canonical offsets; only selected EDUs are highlighted. Keep full annotations, summary counts, and developer diagnostics in collapsed sections. Inputs defaults to collapsed after success. Escape uploaded text before HTML rendering and preserve its whitespace. Label whitespace-normalized canonical text as a comparison representation. Show comparator errors without attempting repairs.

Do not add complex JavaScript interactions, raw-text alignment, fuzzy alignment, normalization beyond the explicit whitespace fallback, token offsets, agreement/confidence scores, disagreement labels, guideline processing, RAG, LLM calls, databases, or persistence in this slice.

## Layout and workflow

- `src/edu_disagreement/models.py`: typed immutable models and JSON serialization.
- `src/edu_disagreement/parsing.py`: exact line parsing and reconstruction.
- `src/edu_disagreement/comparison.py`: boundary comparison and region grouping.
- `src/edu_disagreement/__init__.py`: public Python API.
- `app/streamlit_app.py`: local UI and temporary-upload adapter, calling the existing file parser/comparator without duplicating scientific logic.
- `tests/`: small readable examples that verify the scientific contract.
- `pyproject.toml`: package metadata and test dependency.

Keep scientific logic importable and independent of Streamlit. The core uses only the standard library; Streamlit is the only direct UI/runtime dependency and pytest is a development dependency. Manage environments and dependencies with `uv`; commit `uv.lock` for reproducible development installs. Prefer simple functions and the existing small models over speculative abstractions or modules for future milestones.

From the repository root:

```sh
uv sync
uv run pytest
uv run streamlit run app/streamlit_app.py
git diff --check
```

For scientific logic changes, test relevant edge cases and invariants: exact whitespace, line numbers, Unicode offsets, A/B symmetry, mismatch rejection, structural anchors, region grouping, and collapsed-boundary rejection. Keep output deterministic. Do not introduce normalization beyond the documented whitespace fallback to make a failing case pass. Private `data/` is ignored by Git; both `short/` and `maximum/` samples have been deliberately validated and can be used for requested checks. Keep private content out of committed fixtures and docs.

For UI changes, keep comparator tests unchanged, run the full suite, and use Streamlit AppTest or a local browser to check local context, exact highlights, navigation endpoints, errors, one-file-per-side uploads, resets, and zero-difference cases. Check early, middle, and late differences in a maximum sample. Native columns and the optional full-annotation scroll containers do not synchronize source-text positions across A/B; local panels grow naturally to fit their context.

Report changed files, data flow, test results, specification ambiguities/decisions, and concrete input/output examples when completing implementation work.
