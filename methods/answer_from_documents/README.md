# answer_from_documents

**The standard-library primitive for grounded document question answering.**

Given any set of documents and any question, returns a structured answer with verbatim citations, principled abstention, and an explicit status that distinguishes full answers, partial answers, and every flavor of "I don't know."

## Why this exists

Most document-QA systems fail in one of three ways: they answer confidently from world knowledge when the documents do not contain the answer, they hallucinate citations (page numbers that don't exist, quotes that paraphrase rather than quote), or they give a single-shape answer regardless of whether evidence was sufficient, partial, or absent.

`answer_from_documents` is designed to fail *visibly* and *truthfully*. Every answer is grounded in verbatim passages. When the documents can't support a confident answer, the method tells you why, with a specific status.

## What it does

Takes a list of documents, a question, and optional context. Returns a `DocumentAnswer` with a strict short-form answer, the supporting passages quoted verbatim, and a status that distinguishes confident answers from each kind of abstention.

Internally runs a five-step pipeline — one user-facing call:

1. **Extract** pages from each document in the input list.
2. **Analyze the question** — classify its type, decide whether it's answerable from documents at all, decompose compound questions into sub-questions, and generate reformulations that help retrieval find evidence when documents use different vocabulary.
3. **Retrieve passages** — a long-context pass that reads the full document set and pulls verbatim quotes for each sub-question. Returns an empty list if nothing is relevant (never pads).
4. **Verify and assess** — check coverage against every sub-question, surface contradictions across sources, and judge sufficiency (sufficient / partial / insufficient / none).
5. **Synthesize** — produce the final answer with a calibrated status, every factual claim traceable to a cited passage.

## Status enum

| Status | Meaning | `answer` field |
|---|---|---|
| `answered` | Confident full answer with sufficient evidence | populated |
| `partial_answer` | Some sub-questions answered, others explicitly declared uncovered | populated, with caveats |
| `insufficient_evidence` | Documents touch the topic but evidence is too thin | `"Not answerable"` |
| `not_in_documents` | No relevant passages found | `"Not answerable"` |
| `not_answerable_from_documents` | Question type (counterfactual, opinion, out of scope) cannot be answered from documents | `"Not answerable"` |

For any abstention, the `answer` field is the literal string `Not answerable`. The `explanation` and `caveats` fields describe why.

## Inputs

| Input | Type | Required | Purpose |
|---|---|---|---|
| `documents` | `Document[]` | yes | Any count, any format `native.Document` accepts (PDF, Word, image, web page) |
| `question` | `Text` | yes | Any question |
| `context` | `Text` | yes (may be empty) | Background information to disambiguate the question and guide synthesis |
| `answer_format` | `Text` | yes (may be empty) | Optional hint for the expected shape: `Int`, `Float`, `Str`, `List`, or `None`. Empty lets the model pick |

### About the `context` input

Context is for information that is **not a document to answer from** but that helps the method interpret the question correctly — domain-specific term definitions ("in this company, 'revenue' means GAAP net"), audience calibration ("for a CFO briefing"), temporal defaults ("'last quarter' = Q3 2024"), or scope constraints ("only the European subsidiary").

Critical contract:

- Context is **never cited**. `supporting_passages` only contains quotes from documents.
- Context is **never treated as evidence**. If the answer exists only in context and not in documents, the method returns `not_in_documents` — not `answered`.

Pass empty text to omit.

## Output

A `DocumentAnswer` with:

- `status` — one of the five values above
- `answer` — the strictest, shortest grounded answer (bare scalar, name, yes/no, or JSON array for lists). `"Not answerable"` for any abstention status. Units and symbols (`%`, `$`, `km`) preserved from the source.
- `explanation` — prose reasoning behind the answer
- `supporting_passages` — every passage used, with document identifier, page number, verbatim quote, relevance reasoning, and the sub-question it addresses
- `contradictions_noted` — conflicting claims across sources and how they were resolved
- `caveats` — what was missing or assumed; for abstentions, why
- `confidence` — `high` / `medium` / `low` / `none`

## Usage

```bash
mthds run bundle methods/answer_from_documents
```

Or programmatically via any MTHDS runtime.

## Models

The method uses three model aliases. Configure them in your runtime to control cost and quality:

| Step | Alias | Recommendation |
|---|---|---|
| Document extraction | `@default-extract-document` | Any reliable OCR / text extractor |
| Question analysis, verification | `$writing-factual` | A fast, reliable instruction-following model |
| Retrieval | `@best-gemini` | A long-context model (gemini-3.0-pro or similar). Must fit the full document set plus analysis. |
| Synthesis | `$writing-factual` | A reasoning-capable model |

## Known limits in v0.1.0

- The combined document set must fit in the retrieval model's context window. For very large corpora, a future `answer_from_corpus` variant will add a map-reduce layer.
- The method is stateless. There is no multi-turn memory or follow-up handling.
- `ambiguities[]` are returned in the internal question analysis but the method does not ask clarifying questions — callers decide whether to prompt the user before running.

## Design rationale

See the top-level `DESIGN.md` for the full design note, including why the pipeline has five steps (not three or seven), why retrieval and synthesis are separated, and which alternatives were considered and rejected.

## Stability

This method's inputs, outputs, and concept shapes are part of the `mthds-std` v0.1 stability contract. Breaking changes require a major version bump plus a deprecation window. See `STABILITY.md`.
