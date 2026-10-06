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
- Reconstruct by concatenation without separators. Compare only identical reconstructed texts. Raise `ContentMismatchError` before computing disagreements otherwise.
- Offsets are Python Unicode code-point indices, with half-open `[start, end)` spans. EDU indices are zero-based.
- Only internal EDU endpoints are annotation boundaries. Document start/end are implicit region anchors.
- Group all differences between consecutive shared anchors into one region and record ordered, overlapping EDU indices.
- Export the small JSON schema documented in `docs/first_slice.md`, with sorted boundaries and regions in document order.

Do not add UI/Streamlit, HTML/JavaScript, raw-text fallback, fuzzy alignment, normalization, token offsets, agreement/confidence scores, disagreement labels, guideline processing, RAG, LLM calls, databases, or persistence in this slice.

## Layout and workflow

- `src/edu_disagreement/models.py`: typed immutable models and JSON serialization.
- `src/edu_disagreement/parsing.py`: exact line parsing and reconstruction.
- `src/edu_disagreement/comparison.py`: boundary comparison and region grouping.
- `src/edu_disagreement/__init__.py`: public Python API.
- `tests/`: small readable examples that verify the scientific contract.
- `pyproject.toml`: package metadata and test dependency.

Keep scientific logic importable and independent of any eventual UI. Use the standard library at runtime; pytest is a development dependency. Manage environments and dependencies with `uv`; commit `uv.lock` for reproducible development installs. Prefer simple functions and the existing small models over speculative abstractions or modules for future milestones.

From the repository root:

```sh
uv sync
uv run pytest
git diff --check
```

For scientific logic changes, test relevant edge cases and invariants: exact whitespace, line numbers, Unicode offsets, A/B symmetry, mismatch rejection, structural anchors, and region grouping. Keep output deterministic. Do not silently normalize input to make a failing case pass.

Report changed files, data flow, test results, specification ambiguities/decisions, and concrete input/output examples when completing implementation work.
