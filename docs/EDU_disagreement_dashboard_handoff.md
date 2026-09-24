# EDU Disagreement Dashboard — Project Handoff

**Purpose of this file:** preserve the useful project-planning context from a temporary ChatGPT conversation so the work can continue in a normal chat/project.  
**Scope deliberately excluded:** the earlier discussion about ChatGPT Sites, Sites privacy/terms, and Prism.  
**Status at handoff:** concept and scope have been clarified; implementation should begin with a small deterministic MVP before adding guideline retrieval or LLM analysis.

---

## 1. Core idea

Build a **discourse segmentation disagreement dashboard** for comparing two competing EDU segmentations of the same underlying text.

The tool should not assume that either annotation is "gold." The two inputs are simply:

- **Annotation A**
- **Annotation B**

The human user decides what those represent. Examples:

- human annotator A vs. human annotator B
- human annotation vs. model output
- model X vs. model Y
- old annotation vs. revised annotation
- corpus reference vs. a competing analysis

The software must not assign epistemic privilege to either side.

The broader research motivation is **Human Label Variation (HLV)** in discourse segmentation: observed differences between annotations should not automatically be treated as annotation errors. Some may reflect differences induced by annotation schemes, some may be genuine mistakes, some may arise because guidelines are underspecified or conflicting, and some may represent genuinely defensible alternative segmentations.

The tool should help a human inspect and reason about these cases rather than automatically "adjudicating" them.

---

## 2. Research framing from the ESSLLI 2026 talk

The project grows out of the talk:

> *What Counts as a Discourse Unit? Towards Drawing the Boundary between Annotation Error and Human Label Variation*

The initial conceptual diagnosis tree was:

```text
                    observed boundary difference
                              |
                    same annotation setup?
                 guidelines: EDU definition,
                    structural options
                       /             \
                      /               \
          no — rules explain it?       yes
                  |                     |
        scheme-induced boundary     are both analyses
              difference             defensible?
                                      /       \
                                     no       yes
                                     |         |
                              annotation      HLV
                                 error
```

Two notes from the original slide:

- prerequisite: independently double-annotated data
- research goal: automate/model this process

### Refinement for the software

The dashboard should preserve that conceptual structure but avoid forcing a binary verdict.

A safer working form is:

```text
                    observed boundary difference
                              |
                    same annotation setup?
                       /               \
                     no                 yes
                     |                   |
            can differing rules      are both analyses
            explain difference?        defensible?
                /       \               /      \
              yes        no            no      yes
               |          |             |        |
          scheme-      unresolved /   likely   HLV
          induced      inspect         error  candidate
```

Use cautious labels:

- **scheme-induced**
- **likely annotation error**
- **HLV candidate**
- **unresolved / insufficient evidence**

The LLM should generate hypotheses/evidence for human inspection, not declare ground truth.

A separate non-theoretical category is necessary:

- **alignment/content mismatch**

This covers typos, deletions, paraphrases, duplicated text, model-generated textual alterations, or failed matching. These are preprocessing/alignment issues and must not silently become segmentation disagreements.

---

## 3. Important project decision: no "gold" concept

Earlier brainstorming briefly considered displaying a gold/reference annotation. This was explicitly rejected.

The tool should compare **exactly two segmentations** symmetrically.

If a researcher wants to compare an annotator to a gold/reference segmentation, they simply upload that reference as A or B.

Default UI labels can be `A` and `B`, with optional human-readable names such as:

- Annotator 1
- Annotator 2
- PCC reference
- GPT-6 output
- revised annotation

This keeps the tool general and methodologically neutral.

---

## 4. Inputs envisioned

Minimal initial input:

```text
raw.txt
annotation_A.txt
annotation_B.txt
```

### `raw.txt`

Canonical untouched source text.

Strongly recommended because it provides a stable coordinate system against which both annotations can be aligned.

### Annotation files

Simplest initial format:

```text
This is EDU one.
This is EDU two.
This is EDU three.
```

**One non-empty line = one EDU.**

This format is intentionally boring and transparent.

Later formats (CSV, RST corpora, model outputs, etc.) can be adapters into the same internal representation rather than complicating the MVP.

---

## 5. The first real technical problem: robust text alignment

The core deterministic problem should be solved **before** adding LLMs, PDFs, RAG, or databases.

Do **not** align annotation B directly against annotation A if a canonical raw source exists.

Instead:

```text
                annotation A
                    ↗
canonical raw text
                    ↘
                annotation B
```

Each annotation is independently projected onto the raw text.

### Internal strategy

For each annotation:

1. concatenate the EDU strings
2. preserve the EDU endpoint positions in the concatenated annotation text
3. align the concatenated annotation text to the canonical raw document
4. map every EDU endpoint to a character/token position in the raw text

Then both segmentations reduce to sets of source positions:

```text
raw text:
0123456789.....................................

A boundaries = {47, 119, 181, 227, ...}
B boundaries = {47, 103, 181, 227, ...}
```

Comparison then becomes deterministic.

### Preserve source text exactly

Maintain two representations:

1. **display/source text** — untouched
2. **normalized matching representation** — only for alignment

Reasonable normalization may include:

- Unicode normalization
- non-breaking space ↔ ordinary space
- repeated whitespace normalization
- smart quote ↔ straight quote normalization
- typographic dash variants

Avoid aggressive transformations initially.

Lowercasing, punctuation removal, or similar lossy normalization should be fallback strategies only if clearly justified.

### Typos and imperfect text

Example:

Raw:

```text
The experiment was successful, although some problems remained.
```

Annotation:

```text
The experiment was succesful, although some problems remained.
```

A sequence alignment should still map the EDU boundaries around the typo to the corresponding source positions.

### Alignment confidence is mandatory

The alignment process should not simply output mapped boundaries. It should provide diagnostics such as:

```text
document alignment: 99.4%

boundary 1 -> exact
boundary 2 -> exact
boundary 3 -> inferred across one-character deletion
boundary 4 -> ambiguous
```

Crucial rule:

> **An uncertain alignment must never silently become a segmentation disagreement.**

The UI should explicitly flag uncertain spans:

```text
⚠ Could not confidently align this annotation span.
Review source-text mismatch before interpreting the boundary difference.
```

This is especially important for model outputs, which may delete, duplicate, normalize, or paraphrase text.

Those cases should be represented as **content alterations/alignment problems**, not HLV.

---

## 6. Boundary differences vs. disagreement regions

Do not assume that every differing boundary is an independent disagreement.

Example:

```text
A: | aaa bbb | ccc     | ddd eee |
B: | aaa     | bbb ccc | ddd eee |
```

This technically contains multiple differing boundary positions, but they jointly express one alternative segmentation of the same span.

Therefore distinguish:

```text
boundary difference
       ↓
disagreement region
```

A useful first heuristic:

> Use the nearest shared boundaries on the left and right as anchors. Everything between them is one disagreement region.

Example:

```text
        ┌──── disagreement region ────┐

A:  | aaa bbb | ccc       | ddd eee |
B:  | aaa     | bbb ccc   | ddd eee |
     ↑                            ↑
   shared                       shared
```

The LLM should eventually reason over the **whole disagreement region**, not receive two isolated boundary questions.

---

## 7. MVP philosophy

The most important scoping decision:

> **The LLM is not the project. The disagreement representation is the project; the LLM is an optional reasoning layer on top.**

The project must become useful *before* any generative model is connected.

### MVP 0.1 should do only this

```text
Upload:
- raw.txt
- annotation_A.txt
- annotation_B.txt

        ↓

parse annotations

        ↓

align A and B independently to raw text

        ↓

project EDU boundaries to canonical coordinates

        ↓

identify:
- shared boundaries
- differing boundaries
- disagreement regions
- alignment/content warnings

        ↓

visualize and inspect
```

No API.

No PDF parsing.

No vector database.

No RAG.

No authentication.

No persistent cloud database.

No automatic error/HLV judgment.

This alone should be a complete and useful research tool.

---

## 8. Minimal visualization envisioned

A first upload screen could be:

```text
┌─────────────────────────────────────────────────────┐
│ Upload                                              │
│                                                     │
│ Original text      [ raw.txt              ]         │
│ Annotation A       [ annotator_a.txt      ]         │
│ Annotation B       [ annotator_b.txt      ]         │
│                                                     │
│                         [ Compare ]                 │
└─────────────────────────────────────────────────────┘
```

Then a document view:

```text
Document 001
Agreement: ...
7 disagreement regions
2 alignment warnings

─────────────────────────────────────────────

[rendered source text with A/B boundary overlays]
```

Selecting a disagreement region should show something like:

```text
Disagreement 4 / 7

SOURCE
although the evidence remained limited because ...

A
[although the evidence remained limited]
[because ...]

B
[although the evidence remained limited because ...]

Alignment confidence: high
```

Exact visual design is deliberately *not* fixed yet. First prove that the internal representation supports the necessary views.

Questions for later UI design include:

- how to render the untouched raw text
- how to superimpose two boundary sets without visual clutter
- how to indicate shared vs. A-only vs. B-only boundaries
- how to show disagreement regions
- how to visualize alignment warnings
- whether to support token-level or character-level highlighting
- whether to provide a side-by-side EDU view in addition to raw-text overlays

---

## 9. Guideline support: later milestone

After the deterministic comparator works, allow the user to supply segmentation manuals/guidelines.

A major requirement is **traceability**, not merely text extraction.

For a guideline manual, preserve:

```text
section title / identifier
source PDF
page range
original extracted text
examples/exceptions where possible
retrieval representation
```

Example:

```text
§ 4.2 Subordinate clauses
source: guidelines.pdf
pages: 17–18

[original guideline text]
```

LLM-generated summaries/tags may be added later, but must never replace the authoritative source text.

When the model later cites a guideline in its reasoning, the dashboard should be able to expose the exact source passage.

### Same vs. different annotation setup

This should normally be supplied by the human, not inferred by the model.

Possible future upload UI:

```text
Annotation setup

○ Same annotation guidelines
○ Different annotation guidelines
```

If same:

```text
Guidelines
[ upload one PDF ]
```

If different:

```text
Guidelines A
[ upload ]

Guidelines B
[ upload ]
```

This directly supplies the branch of the ESSLLI diagnosis tree.

---

## 10. Guideline extraction is a substantial subproblem

Segmentation guidelines may be long PDFs (~40 pages), with:

- definitions
- structural rules
- exceptions
- edge cases
- examples
- tables
- headings/subheadings
- framework-specific terminology
- possibly poor PDF extraction quality

Do not solve this in the initial MVP.

For born-digital PDFs, the later goal is a structured Markdown-like representation with page/section provenance.

Possible later pipeline:

```text
PDF
 ↓
layout-aware extraction
 ↓
section reconstruction
 ↓
clean guideline document
 ↓
chunking by meaningful sections
 ↓
retrieval index
```

Scanned documents or pathological layouts can be treated as later edge cases instead of driving the initial architecture.

---

## 11. LLM analysis: eventual role

Once a disagreement region and relevant guideline passages can be produced reliably, the model receives a **bounded case**, not the entire corpus.

Conceptually:

```text
CASE
────────────────────────────
Original context:
previous context ...
[disagreement region]
following context ...

Segmentation A:
[...]

Segmentation B:
[...]

Annotation setup:
same guidelines

Relevant guideline passages:
§3.1 ...
§4.7 ...
§8.2 ...
```

The model should not be asked:

> Which annotation is correct?

Instead ask it to reason symmetrically:

```text
Explain a plausible rationale that could lead to A.

Explain a plausible rationale that could lead to B.

For each interpretation, identify supporting or
contradicting guideline passages.

Determine whether:
- one analysis appears to violate an explicit rule;
- both appear compatible with the guidelines;
- the guidelines are ambiguous, silent, or conflicting;
- there is insufficient evidence.

Do not infer annotator intent beyond what the text
and guidelines support.
```

The result should be structured and evidence-linked.

The model is an **analysis assistant**, not an automated adjudicator.

---

## 12. Proposed disagreement representation

Do not immediately hard-code a large taxonomy.

Maintain at least two dimensions.

### Primary diagnosis

Potential working values:

```text
scheme-induced
likely annotation error
HLV candidate
unresolved
```

These should be treated as hypotheses/candidates for human review.

### Guideline evidence status

Potential values:

```text
explicitly licensed
explicitly prohibited
underspecified
conflicting
silent
uncertain retrieval
```

This is preferable to turning "underspecified guidelines" into a top-level diagnosis from the beginning.

For example, the project might later empirically show that many HLV candidates correlate with underspecified guideline regions. That result is more informative if it was not baked into the classification system in advance.

---

## 13. Follow-up interaction

A later version can support case-specific follow-up questions such as:

- Why do you think A is defensible?
- Doesn't §4.6 explicitly prohibit that?
- What would have to be true for B to count as an error?
- Show the exact guideline passage.
- Is there another plausible reading of this construction?

For follow-ups, provide only:

```text
current disagreement region
local source context
A segmentation
B segmentation
retrieved guideline sections
initial model analysis
follow-up conversation for this case
```

Do not resend the entire corpus or full 40-page guideline manual.

This keeps reasoning focused and reduces inference cost.

---

## 14. Batch analysis and caching

The initial analysis of every disagreement does not need to run live.

Preferred later architecture:

```text
annotations
     ↓
deterministic disagreement detection
     ↓
guideline retrieval
     ↓
batch LLM analysis
     ↓
cached structured results
     ↓
dashboard
```

The dashboard can display precomputed analyses almost for free.

Live API calls are then needed mainly for:

- explicit "re-analyse" actions
- follow-up questions
- changed prompts/models/guidelines

### Reproducible cache key

An analysis cache entry should eventually depend on something like:

```text
case text
+ A segmentation
+ B segmentation
+ annotation setup
+ guideline file/version hash
+ retrieved guideline passages
+ system prompt version
+ model
+ reasoning setting
```

Unchanged inputs → reuse prior result.

Changed guideline/prompt/model → produce a new analysis version rather than silently overwriting provenance.

This is both a cost optimization and a research reproducibility feature.

---

## 15. Suggested implementation architecture

Do not design the project around ChatGPT Sites.

Prefer a normal local codebase with Git.

Conceptual structure:

```text
edu-disagreement-dashboard/
├── README.md
├── pyproject.toml
├── src/
│   └── edu_disagreement/
│       ├── parsing/
│       ├── alignment/
│       ├── comparison/
│       ├── guidelines/        # later
│       ├── llm/               # later
│       └── models.py
├── app/
├── tests/
├── sample_data/
└── docs/
```

Early commits should be small and legible, e.g.:

```text
feat: parse line-separated EDU files
test: add whitespace and typo alignment cases
feat: map EDU boundaries to canonical text
feat: identify disagreement regions
feat: add minimal comparison UI
```

The scientifically important logic should live in a reusable Python package, not inside UI callbacks.

---

## 16. UI stack: intentionally boring first

Initial suggestion: use a Python-native local UI, with **Streamlit** as a plausible first candidate because it can cheaply handle:

- file uploads
- app state
- tables
- controls
- lightweight HTML/text visualization

Architecture:

```text
               edu_disagreement
                 Python package
                      │
          ┌───────────┴───────────┐
          │                       │
     Streamlit UI            later UI/API
      first MVP             if needed
```

If visualization eventually requires richer interaction, replace the frontend while preserving the core alignment/comparison package.

Do **not** begin with a large web stack such as React + TypeScript + FastAPI + Postgres + Redis + OAuth + vector DB unless the MVP proves those are actually needed.

---

## 17. Explicit project stop points

These stop points are essential to avoid turning this into an open-ended annotation-platform project.

### Milestone 1 — Core comparator

Input:

- raw text
- A line-separated EDU file
- B line-separated EDU file

Output:

- robust alignment to canonical text
- boundary coordinate sets
- shared/differing boundaries
- disagreement regions
- alignment/content warnings

Requirements:

- deterministic
- unit-tested
- usable from Python/CLI
- no LLM

This is the **first implementation milestone**.

### Milestone 2 — Minimal visual dashboard

Add:

- upload interface
- rendered source text
- A/B segmentation visualization
- clickable/listed disagreement regions
- alignment warnings

At this point the project should already count as a complete useful MVP.

### Milestone 3 — Guidelines

Add:

- one/two manual upload
- reliable source-preserving extraction
- section/page provenance
- relevant-passage retrieval

No generative diagnosis is strictly required yet.

### Milestone 4 — LLM diagnosis

Add:

- structured case construction
- symmetric reasoning over A and B
- evidence-linked guideline citations
- cautious diagnosis categories
- offline/batch processing
- cache/provenance

### Milestone 5 — Interactive analysis

Only if useful:

- case-specific follow-up questions
- human adjudication/notes
- corpus-level statistics
- filters/search
- export
- prompt/model/version comparison

Everything after Milestone 2 is optional enhancement.

---

## 18. Important scope rules

1. **Do not build the LLM layer before deterministic alignment/comparison works.**
2. **Do not turn uncertain text alignment into apparent segmentation disagreement.**
3. **Do not privilege A or B.**
4. **Do not automatically equate disagreement with error.**
5. **Do not force an HLV/error classification when evidence is insufficient.**
6. **Do not solve every corpus/file format in the MVP. Start with one-EDU-per-line text files.**
7. **Do not solve pathological PDF extraction in the MVP.**
8. **Do not build cloud infrastructure before a local tool is useful.**
9. **Keep the underlying analysis package independent of the UI.**
10. **Treat LLM outputs as inspectable, provenance-tracked hypotheses rather than ground truth.**

---

## 19. Division of labor envisioned

### Main ChatGPT project conversation

Use for:

- conceptual reasoning
- research framing
- protecting scope
- defining milestones
- deciding data structures
- discussing alignment choices
- designing evaluation
- guideline/RAG methodology
- LLM prompt/schema design
- reviewing implementation outcomes
- deciding what should happen next

The chat should remain the project's **decision/discussion log**, not become an implementation transcript containing every changed line of code.

### Local Codex + Git

Use for:

- repository inspection
- implementation
- tests
- running sample cases
- refactors
- debugging
- generating concrete audit reports
- bounded implementation tasks

Codex should receive narrowly scoped tasks derived from decisions made in the planning chat.

It can also be asked to inspect the current implementation and report options/tradeoffs back before changes are made.

### Subagents

Potentially useful later for isolated, parallelizable tasks such as:

- evaluate candidate sequence-alignment libraries/algorithms
- design adversarial alignment test cases
- inspect one PDF extraction approach
- review UI visualization alternatives
- create unit-test fixtures

Avoid delegating core architecture decisions to several agents simultaneously at the beginning; this risks contradictory abstractions and unnecessary scope growth.

---

## 20. Immediate next question

Do **not** begin with UI design, RAG, or LLM prompting.

The next planning task should be:

> **Define the canonical internal representation for raw text, EDU annotations, aligned EDU spans/boundaries, alignment confidence/issues, and disagreement regions.**

Only after that representation is agreed should Codex implement the parser/alignment MVP.

Questions to resolve in that step include:

- Are coordinates character offsets, token offsets, or both?
- How is a boundary represented?
- How do we preserve exact EDU text while also storing normalized/aligned text?
- How are insertions/deletions/substitutions represented?
- What counts as a shared boundary under imperfect alignment?
- How is alignment confidence represented?
- How are disagreement regions formed from shared anchors?
- What should the first machine-readable output look like?

This is the recommended point at which to resume the project.

---

## 21. Suggested kickoff message for the new ChatGPT project conversation

Copy/paste this after attaching this handoff file:

> This Markdown file is the handoff from a temporary brainstorming conversation about my EDU segmentation disagreement dashboard. Treat it as the current project context and decision log. I want to keep the project deliberately scoped: deterministic MVP first, then visualization, and only later guidelines/LLM analysis if useful. We should proceed one decision at a time rather than designing the whole system at once. The next task is Milestone 1 planning: define the minimal canonical internal representation needed for parsing, alignment, boundary comparison, alignment warnings, and disagreement regions. Do not start implementation yet; first help me settle that representation in a way I can hand to local Codex as a bounded task.

