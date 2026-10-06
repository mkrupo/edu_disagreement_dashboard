# Comparison core: exact reconstruction and whitespace fallback

This is the active implementation contract. The [original project handoff](EDU_disagreement_dashboard_handoff.md) describes broader milestones; raw-text alignment and visualization are deferred.

## Input and coordinates

- Two UTF-8 annotation files, A and B, with one non-empty line per EDU.
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
- Runtime dependencies are zero; pytest is a development dependency. Scientific logic lives in `src/edu_disagreement/`.
- No UI, CLI, raw-text alignment, fuzzy alignment, normalization beyond whitespace removal, scores, diagnoses, guideline processing, LLM/RAG, persistence, or database is part of this slice.

Tests cover the original scenarios, exact whitespace and newline preservation, empty inputs, minimal JSON serialization, and exhaustive A/B symmetry and region overlap checks for all segmentations of a tiny document. Fallback tests cover trailing spaces, separators replaced by EDU newlines, multiple whitespace differences, Unicode whitespace/code-point projection, shared boundaries, A/B symmetry, retained EDU text, structural anchors, content rejection, and collapsed-boundary rejection.
