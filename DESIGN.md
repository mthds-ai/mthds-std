# mthds-std — Design

The standard library of MTHDS. Generic, reusable primitives that every MTHDS app can depend on.

## Principles

1. **Generic over specific.** A primitive earns its place in `mthds-std` only if it is useful across multiple unrelated domains. Vertical solutions belong in `pipelex/methods`, not here.
2. **Zero external deps.** Every method in `mthds-std` uses only `native.*` concepts or concepts defined within `mthds-std` itself. Std sits at the bottom of the stack.
3. **Stability is a promise.** Inputs, outputs, and concept shapes are load-bearing contracts. Breaking changes require a major version bump and a deprecation window. See `STABILITY.md`.
4. **Under-commit.** It is easier to add primitives later than to change or remove them. v0.1.0 ships with a single, high-impact primitive. New additions go through a 3-apps rule (below).

## The "3 apps" rule

A candidate is accepted into `mthds-std` only if we can name **three distinct real applications** that would use it as-is, without wrapping it. If we can't, it is a solution, not a primitive — and it belongs in `pipelex/methods`.

---

## v0.1.0 surface

One primitive, shipped deliberately.

### `answer_from_documents`

**Purpose.** Given any set of documents and any question, produce a grounded answer with verbatim citations and principled abstention.

**3-apps test.**
- Customer support bot answering from product docs
- Internal knowledge base QA for onboarding
- Legal research assistant answering from case files

All three are distinct domains with different document types, different question types, and different users. The primitive works in all three with no changes.

**Pipeline.** Five steps:

1. `extract_one_document` (PipeExtract, batched over the input list) — any document format → `Page[]`
2. `analyze_question` (PipeLLM) — classify question type, detect unanswerable questions (counterfactual, opinion, out-of-scope), decompose compound questions, generate reformulations to help retrieval find evidence under different vocabulary
3. `retrieve_passages` (PipeLLM, long-context) — read all pages, extract verbatim passages for each sub-question, cite by document and page. Empty list when nothing is relevant.
4. `verify_and_assess` (PipeLLM) — coverage check against every sub-question, contradiction detection across sources, sufficiency judgment
5. `synthesize_answer` (PipeLLM) — produce final answer with a calibrated status enum that distinguishes full answers, partial answers, and each flavor of abstention

**Why these five steps (not three, not seven).** Each step has a narrow, independently-verifiable job:

- Dropping `analyze_question` lets compound questions silently fail and terminology mismatches cause retrieval misses.
- Dropping `verify_and_assess` removes the only mechanism that catches hallucinated citations and silent contradictions.
- Merging `retrieve_passages` and `synthesize_answer` into one call lets the model invent citations.
- Adding a `catalog_documents` step duplicates work that `retrieve_passages` already does.
- Adding iterative gap-filling (loop retrieval for uncovered sub-questions) is valuable but expensive — deferred to a future `answer_from_documents_deep` variant.
- Adding a post-synthesis critique step is weaker than pre-synthesis assessment: the synthesis model is less likely to drift when it sees the critique *before* writing.

**Concepts introduced.** `QuestionAnalysis`, `DocumentPassage`, `EvidenceAssessment`, `DocumentAnswer` — plus the enums `QuestionType` (10 values) and `AnswerStatus` (5 values).

**Status enum — the abstention contract.**

| Status | Trigger |
|---|---|
| `answered` | Every sub-question has evidence, synthesis produced a confident answer |
| `partial_answer` | Some sub-questions have evidence, others do not; caveats name the uncovered ones explicitly |
| `insufficient_evidence` | Passages touch the topic but evidence is too thin |
| `not_in_documents` | No relevant passages found |
| `not_answerable_from_documents` | Question type (counterfactual, opinion, out-of-scope) cannot be answered from documents regardless of content |

The five statuses map to five genuinely distinct real-world outcomes. A 4-status or 3-status enum collapses at least one important distinction.

---

## Deferred candidates

These passed the 3-apps rule in an earlier design round but are **deferred** to keep v0.1.0 focused on shipping one excellent primitive:

| Primitive | Reason for deferral |
|---|---|
| `summarize` | Deferred to v0.2.0. Useful but `answer_from_documents` with "summarize this" as the question covers most cases. |
| `extract_entities` | Deferred to v0.2.0. Well-served by `pipelex/methods/entity_extractor` today. |
| `classify_text` | Deferred. |
| `chunk_document` | Deferred. |
| `extract_tables` | Deferred. |
| `compare_texts` | Deferred. |
| `translate` | Deferred. |
| `describe_image`, `transcribe_audio`, `generate_image` | Deferred. Add when the generic primitive shape stabilizes. |
| `embed_text`, `rerank` | Deferred. Depends on how embedding provider abstraction lands in the runtime. |

Each deferred primitive can be added in a minor version bump (v0.2.0, v0.3.0, etc.) without breaking anything.

---

## Explicitly excluded — never in `mthds-std`

These are solutions, not primitives. They belong in `pipelex/methods` or third-party packages:

- `write_report`, `generate_email` — too template-dependent
- `analyze_cv`, `qualify_rfp`, `due_diligence`, `compliance_checker` — verticals
- `code_review`, `generate_code` — a domain of its own
- `plan_task`, `decompose_goal` — agent helpers, not primitives
