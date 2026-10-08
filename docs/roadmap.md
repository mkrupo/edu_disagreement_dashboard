# Research and development roadmap

This roadmap records possibilities and decisions, not implementation commitments. **It does not authorize coding agents to implement future ideas.** New work requires an explicit, bounded request. The [original handoff](EDU_disagreement_dashboard_handoff.md) provides planning context; the [comparison contract](first_slice.md) describes current behavior and the [user guide](user-guide.md) describes current use.

## Current / completed

- Deterministic, symmetric comparison of two EDU segmentations.
- Whitespace-normalized fallback with boundary projection and explicit rejection of remaining mismatches.
- Local A/B visualization with configurable context and optional full annotations.
- Five-way human assessment with per-disagreement notes.
- Self-contained, resumable JSON sessions with embedded sources and validated assessment identities.
- Basic session workflow, progress, direct/sequential navigation, and note-consistent export.

## Near-term

- Run a small pilot assessing real disagreements.
- Establish the provenance of the annotation guidelines actually used.
- Investigate PCC annotation versions and segmentation conventions.
- Review pilot findings before expanding the assessment schema.

## Planned, not yet designed

- Optional annotation setup: a shared framework by default, or unspecified; separate A/B frameworks only when explicitly requested.
- Store framework and guideline-version provenance as session metadata.
- Design a guideline/settings interface, including verified conventions concerning attribution and same-unit.
- Prepare guidelines from PDFs/Markdown while preserving sources, examples, section/page references, and versions.
- Add an optional guideline viewer and citation-linked assessment evidence.
- Adapt `.rs3` input with validated EDU ordering. Future formats should be adapters into `ParsedEDU`, as described in the [comparison contract](first_slice.md#human-assessments-and-portable-sessions).
- Explore alternative segmentation editing and optional adjudicated `.txt`/`.edus` export.
- Scroll full annotations to the selected disagreement.
- Investigate further safe alignment strategies and optional raw-text alignment.

## Exploratory research ideas

- Structured linguistic evidence and dependency parsing.
- Guideline retrieval, RAG, or agentic LLM assistance.
- HLV diagnosis and reasons for disagreement.
- Annotator confidence and intra-annotator variability.
- Inter-annotator agreement metrics and DISRPT-style boundary evaluation.
- A single-annotator EDU segmentation interface.
- Multi-analysis representations preserving alternative valid segmentations.
- Codex or other conversational assistant integration.
- Additional corpora, corpus publication, and format harmonization.

## Principles and open decisions

“Both defensible” does not automatically imply genuine human label variation (HLV). Framework guidelines can inform defensibility assessments, but must not silently alter the deterministic comparator. The application must remain useful without framework configuration or LLM features.

The pilot should establish which guideline versions and corpus conventions apply before designing new metadata or evidence fields. PCC versions, attribution/same-unit conventions, and the scope of any later assessment-schema expansion still need investigation and human review. None of these sections is an instruction to begin implementation.
