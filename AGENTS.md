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

The local Streamlit interface is a thin comparison and assessment layer. Sidebar workflows are New assessment (one A/B `.txt` or `.edus` file per side, identical parser semantics) and Load assessment (one self-contained session JSON). Compare automatically; show comparability and a subdued mode description. Keep centered Previous/Next navigation labeled Disagreement, with a zero-based index in session state. Upload replacement/removal clears old results and assessments and resets navigation. The symmetric local A/B view uses region EDU indices plus configurable context (0–10 neighbors per side, default 1); context changes must not recompute the comparison. Only selected EDUs are highlighted. Keep full annotations, summary counts, and developer diagnostics collapsed. Escape uploaded text before HTML rendering, preserve its whitespace, and label normalized canonical text as a derived representation. Show comparator/session errors without repairs.

Assessments use exactly `a_only`, `both`, `b_only`, `neither`, or `unresolved`, with optional notes. Absence is unassessed; unresolved counts as assessed. Both does not imply HLV. Anchor every record to the full canonical span and both EDU-index tuples, never just navigation order. Sessions embed exact decoded UTF-8 source contents, original filenames, and SHA-256 hashes; retain line endings in embedded sources. On import, validate schema/hashes, recompute with the existing parser/comparator, and require exact assessment identity matches. Never store or trust cached comparison results or filesystem paths for restoration. See [session schema and workflow](docs/first_slice.md#human-assessments-and-portable-sessions).

Do not add complex JavaScript interactions, raw-text/fuzzy alignment, normalization beyond the explicit whitespace fallback, token offsets, agreement/confidence scores, HLV/error diagnoses, adjudicated segmentations, guideline processing, RAG, LLM calls, databases, or persistent server storage. Future input formats must adapt into `ParsedEDU`; `.rs3` parsing is deferred.

## Layout and workflow

- `src/edu_disagreement/models.py`: typed immutable models and JSON serialization.
- `src/edu_disagreement/parsing.py`: exact line parsing and reconstruction.
- `src/edu_disagreement/comparison.py`: boundary comparison and region grouping.
- `src/edu_disagreement/__init__.py`: public Python API.
- `src/edu_disagreement/sessions.py`: Streamlit-independent assessments, source preservation, and validated portable JSON sessions; calls the unchanged parser/comparator via temporary files.
- `app/streamlit_app.py`: local comparison/assessment UI, without duplicated scientific logic.
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

For UI changes, keep comparator tests unchanged, run the full suite, and check parameterized context, highlights, navigation, errors, one-file uploads, resets, and zero-disagreement cases. Verify verdict/note persistence and JSON-only restoration, including exact sources, hashes, and region identities. Private session exports must stay outside committed fixtures/docs. Check early, middle, and late disagreements in a maximum sample. Native columns and full-annotation scroll containers do not synchronize source positions; local panels grow naturally to fit their context.

Report changed files, data flow, test results, specification ambiguities/decisions, and concrete input/output examples when completing implementation work.
