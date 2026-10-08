# Comparison core: exact reconstruction and whitespace fallback

This is the active comparison-core contract. The [original project handoff](EDU_disagreement_dashboard_handoff.md) describes broader milestones. A local Streamlit inspection interface is implemented; raw-text alignment remains deferred.

## Input and coordinates

- Two UTF-8 annotation files, A and B, with one non-empty line per EDU. `.txt` and `.edus` use the identical line parser.
- Ordinary Python text-file handling supports LF and CRLF line endings. Remove only line terminators, preserving all other characters. Only literally empty lines are ignored; whitespace-only lines remain EDUs.
- `ParsedEDU(index, text, line_number)` preserves zero-based EDU indices and one-based original source line numbers.
- Concatenating EDU texts without separators reconstructs each annotation's text.
- Prefer exact reconstructed-text equality; this path preserves the shared reconstruction as canonical text and reports `canonical_source: "reconstructed"`.
- Only if reconstructions differ, remove whitespace characters as defined by Python `str.isspace()`. If the resulting sequences differ, raise `ContentMismatchError`, a `ValueError` subclass, before computing disagreements. Otherwise use the shared whitespace-free sequence as canonical text and report `canonical_source: "whitespace_normalized"`.
- Original parsed EDU texts remain unchanged on both paths. All offsets are Python Unicode code-point indices in the selected canonical text and all spans are half-open `[start, end)`.
- Internal cumulative EDU endpoints are annotation boundaries. `0` and `len(text)` are structural anchors only.

## Whitespace endpoint projection

For the fallback, each EDU endpoint maps to the number of non-whitespace code points preceding it in the original annotation reconstruction. Distinct internal endpoints from one annotation must remain distinct: reject duplicate projected offsets with `BoundaryProjectionError` (also a `ValueError` subclass), even if a duplicate lies at a structural anchor. Validate before constructing boundary sets so no decisions are silently merged.

An internal endpoint projected to `0` or `len(canonical_text)` is a structural anchor and is excluded from annotation boundaries. Whitespace-only edge EDUs remain in the parsed annotations and EDU counts, but have zero canonical extent and do not overlap a disagreement region. Internal whitespace-only EDUs that collapse adjacent internal boundaries are rejected.

For example, A = `hello world\n` and B = `hello\nworld\n` reconstruct differently. The fallback uses `helloworld`, A boundaries `[]`, B boundaries `[5]`, and one region `[0, 10)` with A EDU indices `[0]` and B indices `[0, 1]`. A's original EDU text remains `hello world`.

## Data flow and result

`parse_annotation(path)` → ordered tuple of `ParsedEDU` objects → `compare_annotations(a_edus, b_edus)` → `ComparisonResult` → `to_dict()` → optional `json.dumps(...)`.

The comparator derives sorted A/B boundaries, their intersection, and each side's differences. Consecutive shared anchors, including implicit document start/end, define candidate spans. Emit exactly one `DisagreementRegion(start_offset, end_offset, a_edu_indices, b_edu_indices)` for each span whose internal boundary sets differ. Record only EDUs overlapping that span, in annotation order. A shared endpoint does not include the adjacent EDU outside the span.

`ComparisonResult` retains canonical text, provenance, and original parsed EDUs for Python callers. `to_dict()` exports the same small schema on both paths; this exact-path example is:

```json
{
  "canonical_source": "reconstructed",
  "annotations": {
    "A": {"edu_count": 2, "boundaries": [2]},
    "B": {"edu_count": 2, "boundaries": [1]}
  },
  "shared_boundaries": [],
  "a_only_boundaries": [2],
  "b_only_boundaries": [1],
  "disagreement_regions": [
    {
      "start_offset": 0,
      "end_offset": 4,
      "a_edu_indices": [0, 1],
      "b_edu_indices": [0, 1]
    }
  ],
  "warnings": []
}
```

This example comes from A = `ab\ncd\n` and B = `a\nbcd\n`; canonical text is `abcd`. Several boundary differences within the same shared anchors still form just one region.

A second example: A = `a\nbc\nd\nef\n`, B = `ab\nc\ndef\n`. Canonical text is `abcdef`; A boundaries are `[1, 3, 4]`, B boundaries `[2, 3]`, shared `[3]`, A-only `[1, 4]`, and B-only `[2]`. The two regions are:

```json
[
  {"start_offset": 0, "end_offset": 3, "a_edu_indices": [0, 1], "b_edu_indices": [0, 1]},
  {"start_offset": 3, "end_offset": 6, "a_edu_indices": [2, 3], "b_edu_indices": [2]}
]
```

## Manual use

After the README setup, use `uv run python` (or `uv run python example.py`) with the importable API and your annotation paths:

```python
import json
from edu_disagreement import (
    BoundaryProjectionError,
    ContentMismatchError,
    compare_annotations,
    parse_annotation,
)

a = parse_annotation("annotation_A.txt")
b = parse_annotation("annotation_B.txt")
try:
    result = compare_annotations(a, b)
except (ContentMismatchError, BoundaryProjectionError) as error:
    print(error)
else:
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
```

## Decisions and limits

- Two empty/empty-line-only files reconstruct to empty text and produce zero EDUs, boundaries, or regions. Empty versus text containing non-whitespace characters is a content mismatch. A whitespace-only document can compare with an empty annotation through the fallback, provided its internal boundaries do not collapse.
- Whitespace-only lines count as EDUs because trimming would alter source content.
- Unicode normalization is intentionally absent: `é` and `e` plus combining acute accent are different reconstructed texts. Combining marks and emoji each contribute their actual Python code-point lengths.
- Successful comparisons on both paths have `warnings: []`; provenance identifies the fallback without scores or taxonomies. Content mismatches and collapsed projections raise instead of returning apparent disagreements.
- The comparison core has zero runtime dependencies and lives in `src/edu_disagreement/`. The full application requires Streamlit; pytest is a development dependency.
- The Streamlit UI lives separately in `app/streamlit_app.py` and calls the existing parser/comparator. Human assessments and portable session JSON are implemented separately in `sessions.py`; the comparison contract is unchanged. No CLI, raw-text/fuzzy alignment, normalization beyond whitespace removal, scores, diagnoses, guideline processing, LLM/RAG, persistent server storage, or database is implemented.

Tests cover the original scenarios, exact whitespace and newline preservation, empty inputs, minimal JSON serialization, and exhaustive A/B symmetry and region overlap checks for all segmentations of a tiny document. Fallback tests cover trailing spaces, separators replaced by EDU newlines, multiple whitespace differences, Unicode whitespace/code-point projection, shared boundaries, A/B symmetry, retained EDU text, structural anchors, content rejection, and collapsed-boundary rejection.

## Local inspection interface

Launch with `uv run streamlit run app/streamlit_app.py`. In the sidebar, choose New assessment and upload one `.txt` or `.edus` file per side, or choose Load assessment and upload only a saved session `.json`. Comparison runs automatically. A compact comparability status and mode explanation appear above centered Previous/Next Disagreement navigation. Changing either source clears old results and assessments and resets selection to disagreement 1.

The main A-left/B-right view shows selected EDUs plus context from the sidebar setting (0–10 EDUs per side, default 1), using only region EDU indices. Context changes only rendering, not comparison. Only selected EDUs are highlighted; original text and source-line information are retained. Full annotations, comparison summary, and developer diagnostics remain collapsed, with canonical text and comparison JSON at the bottom. With no disagreements, full annotations and session export remain available without navigation or verdict controls.

## Human assessments and portable sessions

Under each local comparison, answer **Which segmentation is defensible?** with `a_only` (A defensible, B not), `both` (both defensible), `b_only` (B defensible, A not), `neither` (an alternative may be needed), or `unresolved` (inspected but cannot decide). No assessment record means unassessed; unresolved counts toward progress. Both carries no automatic HLV label. Selection saves immediately without advancing. Optional notes are enabled after choosing a verdict; Streamlit applies note edits on leaving the field or Ctrl+Enter. Revisiting a region restores its verdict and note.

Export session JSON in the sidebar saves any pending note edit and prepares a self-contained UTF-8 file. Click Download session JSON in the native dialog, then close the dialog to resume editing. This separates saving from downloading: a direct download can race the note widget's rerun and serve older bytes. The dialog contains an immutable snapshot and keeps the note editor out of reach while downloading. It embeds both original decoded sources exactly, including whitespace and line endings, original filenames, and SHA-256 of each content encoded as UTF-8. Filesystem paths are unnecessary. Session JSON contains no cached `ComparisonResult`. This valid synthetic example compares A = `a\nb` with B = `ab`:

```json
{
  "schema_version": 1,
  "sources": {
    "A": {
      "filename": "a.edus",
      "sha256": "7e18f737311b2dc3b2f269dd78396b0351f14fb66efa879f768cb23181883c78",
      "content": "a\nb"
    },
    "B": {
      "filename": "b.txt",
      "sha256": "fb8e20fc2e4c3f248c60c39bd652f3c1347298bb977b8b4d5903b85055620603",
      "content": "ab"
    }
  },
  "state": {"current_disagreement": 0, "context_edus": 1},
  "assessments": [
    {
      "start_offset": 0,
      "end_offset": 2,
      "a_edu_indices": [0, 1],
      "b_edu_indices": [0],
      "verdict": "both",
      "note": null
    }
  ]
}
```

Loading validates UTF-8 JSON, schema version 1, required source fields and hashes, then reruns the existing parser/comparator on embedded sources. Each assessment must have a supported verdict, text/null note, integer offsets and index arrays, and an exact matching recomputed region identity. Duplicate region assessments, duplicate JSON keys, hash mismatches, non-comparable sources, and unmatched identities are rejected clearly. Regions without assessments are valid. `current_disagreement` is zero-based convenience state: clamp out-of-range integers; invalid/missing positions default to zero. Valid context values 0–10 restore; invalid/missing context defaults to 1. UI state is never assessment identity.

TODO: future formats should be input adapters into `ParsedEDU`, keeping the comparator independent of file format:

```text
.txt / .edus → line parser ┐
.rs3 → future RST adapter ├→ ParsedEDU → comparator
other formats → adapter  ┘
```

Only the line parser is implemented. Sessions are downloaded/uploaded files, with no database, user accounts, or persistent server storage. Private sources and exported private sessions must not enter committed tests or documentation.
