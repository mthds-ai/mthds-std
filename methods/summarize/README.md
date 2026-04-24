# summarize

**Faithful, length-controlled summarization of a single text.**

Given any text, this primitive profiles what kind of input it is, routes to a strategy that fits its kind, drafts a summary grounded in the source, and verifies every claim against the original before returning. The output is a structured `Summary` with explicit accountability for what was preserved and what was omitted.

## Why this exists

Summarization looks simple and is not. Every LLM application that has tried to ship a "summarize" feature since GPT-3 has bumped into the same wall: summaries that are fluent but quietly wrong, or thorough but disproportionately long, or short but missing the point. The LLM alone is not the solution — the pipeline around it is.

This method is an attempt to encode what the research literature and production engineering teams have learned about that pipeline. It is not novel; it is opinionated and rigorous about a problem that keeps being treated casually.

## The problem

Recent research gives a sobering picture of where LLM summarization actually stands:

- **Hallucination is the dominant failure mode, and it is widespread.** Eugene Yan's 2024 [review of abstractive summary evaluation](https://eugeneyan.com/writing/abstractive/) cites 30–43% hallucination rates on CNN/DailyMail and a staggering 92% faithfulness-error rate on XSum. Even in well-instrumented clinical pipelines, a [Nature 2025 study](https://www.nature.com/articles/s41746-025-01670-7) measured a 1.47% hallucination rate plus a 3.45% omission rate — meaning roughly one in 20 medical summaries contains a factual error or a critical omission.
- **Our measurement tools are decaying.** A 2025 paper on [reference-set variation](https://arxiv.org/html/2506.14335v1) finds that the correlation between automatic metrics (ROUGE, BLEU, BERTScore) and human judgment is dropping as models improve. We are grading better outputs with worse rulers.
- **Even LLM-as-judge is noisy.** The [FaithJudge benchmark (2025)](https://arxiv.org/html/2505.04847v2) shows zero-shot GPT-4-class judges hitting around 65% balanced accuracy on faithfulness detection — barely better than a biased coin. The same paper shows that few-shot judging with hand-labeled hallucination examples jumps accuracy to 84%, but no one ships that by default.
- **Long inputs have a structural bias nobody fixes.** Liu et al.'s [Lost in the Middle (TACL 2024)](https://arxiv.org/abs/2307.03172) demonstrates a U-shaped attention curve: LLMs systematically under-weight content in the middle of their context. This is a property of rotary positional embeddings, not a prompt problem, so it affects every current model. A follow-up [2024 paper on positional bias in faithfulness evaluation](https://arxiv.org/html/2410.23609v1) shows the *evaluators themselves* inherit this bias — compounding the problem when we try to score long-input summaries.
- **The philosophical problem.** A widely-discussed [Hacker News thread](https://news.ycombinator.com/item?id=44913172) argued that LLMs do not summarize; they only shorten. Genuine summarization requires understanding what is important about a text — and that depends on who is reading and why. An LLM's notion of "important" is a statistical average over its training corpus, not necessarily what your reader needs.

Practitioner writeups tell the same story in concrete terms. [Galileo's production guide](https://galileo.ai/blog/llm-summarization-production-guide) catalogs real failures: critical escalation signals lost to context-window overflow, cascading summary-of-summary pipelines amplifying errors, and confidence-less outputs that degrade downstream decisions. [CMU SEI's evaluation framework](https://www.sei.cmu.edu/blog/evaluating-llms-for-text-summarization-introduction/) warns against single-metric reliance and pushes for a collection approach spanning accuracy, faithfulness, compression, extractiveness, and efficiency.

## Why it's complicated

Summarization has at least seven axes of variation that make a single prompt inadequate:

| Dimension | Variants |
|---|---|
| **Length** | one sentence / one paragraph / one page / "as long as needed" |
| **Format** | prose / bullets / sections / TL;DR + details |
| **Fidelity** | extractive (copy from source) / abstractive (rewrite) |
| **Audience** | executive / technical / layperson / child |
| **Purpose** | overview / decision / learning / search indexing |
| **Input shape** | single doc / multi-doc / transcript / code / data |
| **Temporal** | one-shot / running / delta-since-last |

Cross-multiplied, that is hundreds of meaningfully distinct variants. A primitive that promises to handle all of them in one prompt will, predictably, handle none of them well.

On top of that, two compounding structural problems force architectural (not prompt-engineering) solutions:

1. **The coverage vs. faithfulness tradeoff.** The [Adams et al. 2023 meta-evaluation](https://proceedings.mlr.press/v219/adams23a/adams23a.pdf) of faithfulness metrics for long-form summarization makes this explicit: making summaries more faithful tends to make them shallower, while making them thorough tends to introduce hallucinations. You cannot max both; you have to pick a gate.
2. **Naive hierarchical merging makes things worse.** Intuitively, you split a long document, summarize each chunk, then summarize the summaries. Research shows this cascade amplifies hallucinations — each layer drifts further from the source. The fix is to re-ground every merge step in the original text, not in prior summaries (see ["Context-Aware Hierarchical Merging", 2025](https://arxiv.org/abs/2502.00977)).

## How this method addresses the problem

The design decisions flow directly from the research:

- **Routing, not one-size-fits-all.** A profile step classifies the input (research paper, news article, blog post, report, book chapter, legal document, slides, code) and picks one of four internal strategies. A research paper with an existing abstract gets treated differently from a 500-word memo, which gets treated differently from a 50-page report.
- **Extract-then-write, not compress-in-one-shot.** For the general medium-length case, we extract key facts (entities, numbers, dates, claims) deterministically first, then draft the summary grounded in those facts. This is the industry-consensus pattern — AWS, Arize, Galileo, Mozilla, and OpenAI's cookbook all converge on it — because it isolates "what matters" from "how to phrase it."
- **Verify after writing.** The faithfulness step checks every claim in the draft against the source, flags unsupported claims and critical omissions, and recommends a status adjustment. This is what the research calls claim-level judging; it consistently outperforms whole-summary judging because one hallucinated claim and one correct claim do not usefully average.
- **Source-grounded merge for long input.** When the chunk-map-reduce strategy fires, the merge step reads the original source alongside the chunk summaries — not just the summaries. This is the specific fix the hierarchical-merging research prescribes.
- **Faithfulness is the primary gate, coverage is secondary.** Given the tradeoff is real, we pick: we would rather produce a shorter summary that is honest than a longer one that lies.
- **Explicit uncovered aspects.** The output includes a field naming what the method chose to omit. Transparency about omission is a design requirement, not a nice-to-have. You can audit coverage without running a judge.
- **Preserved entities as a cheap faithfulness anchor.** The output lists every entity from the source that survived into the summary, with its type. This is a deterministic, judge-free check that catches the "drops key names/numbers" failure mode without an LLM call.

## What it does

Internally, a four-step pipeline:

1. **Profile the input** — classify the kind of text, estimate length, detect a pre-existing summary section if any, flag hazards.
2. **Route to a strategy** — four available:
   - `single_shot` for short general text (one LLM call, no pre-extraction)
   - `promote_preexisting` for research papers and whitepapers that already contain an abstract (use it as the spine, enrich with key results the abstract elides)
   - `extract_then_write` for general medium-length text (extract key facts first, draft grounded in those facts)
   - `chunk_map_reduce` for long documents (chunk, summarize each chunk, merge with source-grounding)
3. **Verify faithfulness** — decompose the draft into claims, check each against the source, flag unsupported claims and missing key points.
4. **Finalize** — apply the verification report: remove unsupported claims, adjust status and confidence, populate preserved entities and uncovered aspects, honor the caller's format.

## Status enum

| Status | Meaning |
|---|---|
| `summarized` | Full confident summary. Every claim traces to the source. |
| `partial` | Summary produced, but with unsupported claims removed or critical omissions flagged. |
| `unsafe_to_summarize` | The source was adversarial, self-contradicting, or the verifier caught fabrications that could mislead. The summary field contains a minimal neutral statement explaining the problem. |

## Inputs

| Input | Type | Required | Purpose |
|---|---|---|---|
| `text` | `Text` | yes | The source text to summarize. |
| `length` | `Text` | yes (may be empty) | `short` (~50 words), `medium` (~150), `long` (~400), or an explicit `<N> words`. Empty defaults to medium. |
| `format` | `Text` | yes (may be empty) | `prose`, `bullets`, or `sections`. Empty defaults to prose. |
| `audience` | `Text` | yes (may be empty) | Free-text audience hint (e.g., `for a CFO briefing`, `for a lay reader`). Adjusts register but not content. Empty means no adjustment. |

## Output

A `Summary` with:

- `status` — one of the three values above
- `answer` — the summary text itself, in the requested format. Named `answer` for consistency with other `mthds-std` methods and with the shared Langfuse LLM-judge configuration.
- `key_points` — 3 to 7 distilled takeaways, always populated regardless of format
- `preserved_entities` — entities from the source that appear in the summary, each with a type category (person, organization, location, date, number, other). The cheap faithfulness anchor callers can audit without running a judge.
- `uncovered_aspects` — parts of the source NOT covered by this summary. Explicit honesty about omission; this field is populated when the summary trades coverage for length.
- `length_words` — actual word count of the summary
- `confidence` — high / medium / low / none, grounded in the verification step, not in the model's prior
- `strategy_used` — which internal strategy produced this summary, for traceability

## Usage

```bash
mthds run bundle methods/summarize
```

Or programmatically via any MTHDS runtime.

## Models

The method uses a single model alias throughout. Configure it in your runtime to control cost and quality.

| Step | Alias | Recommendation |
|---|---|---|
| Profile, extraction, drafting, verification, finalization | `$writing-factual` | A reliable instruction-following model. For production-grade faithfulness checks, upgrade the verification step to a reasoning-class model. |
| Chunk summarization (when `chunk_map_reduce` is active) | `$writing-factual` | Runs in parallel across chunks via PipeBatch. |

## Known limits in v0.1.0

- **Single-text input only.** For summarizing multiple related documents, compose with `answer_from_documents` or wait for a future `summarize_corpus` sibling primitive.
- **No conversation / meeting / email specialization.** Those inputs have genuinely different output shapes (speakers, action items, decisions) and belong in a sibling primitive.
- **No image, audio, or code-semantic input.** Text only. For audio, chain with a transcription step upstream.
- **Chunking uses an LLM pass**, not deterministic byte-count splitting. Slow on very long inputs; acceptable for v0.1 where correctness beats speed.
- **Faithfulness verification is zero-shot** in v0.1. Research shows few-shot verification with hand-labeled hallucination examples nearly doubles detection accuracy. Upgrade planned for v0.2.
- **Lost-in-the-middle is not solved.** LLMs under-attend to the middle of long inputs architecturally. We degrade transparently (lower confidence, populated `uncovered_aspects`) rather than silently.

## References and further reading

The sources behind each design decision are cataloged in the repo under `research/summarization/`. The most influential ones in one place:

- Liu et al., [Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172). TACL 2024. The positional-bias paper.
- Adams et al., [A Meta-Evaluation of Faithfulness Metrics for Long-Form Summarization](https://proceedings.mlr.press/v219/adams23a/adams23a.pdf). 2023.
- Adams et al., [From Sparse to Dense: GPT-4 Summarization with Chain of Density Prompting](https://arxiv.org/abs/2309.04269). 2023.
- Fabbri et al., [SummEval: Re-evaluating Summarization Evaluation](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00373/). TACL 2020. Still the canonical meta-evaluation.
- Narayan et al., [Don't Give Me the Details, Just the Summary!: Topic-Aware Convolutional Neural Networks for Extreme Summarization (XSum)](https://aclanthology.org/D18-1206/). EMNLP 2018. The benchmark this method is evaluated against.
- [A Comprehensive Survey of Hallucination in Large Language Models](https://arxiv.org/html/2510.06265v2). 2025. The taxonomy of failure modes.
- [Benchmarking LLM Faithfulness in RAG with Evolving Leaderboards (FaithJudge)](https://arxiv.org/html/2505.04847v2). 2025. Current state of the art for faithfulness judging.
- [On Positional Bias of Faithfulness for Long-form Summarization](https://arxiv.org/html/2410.23609v1). 2024. Bias in the metrics themselves.
- [Context-Aware Hierarchical Merging for Long Document Summarization](https://arxiv.org/abs/2502.00977). 2025.
- Eugene Yan, [Evaluation & Hallucination Detection for Abstractive Summaries](https://eugeneyan.com/writing/abstractive/). Practitioner goldmine.
- CMU SEI, [Evaluating LLMs for Text Summarization: An Introduction](https://www.sei.cmu.edu/blog/evaluating-llms-for-text-summarization-introduction/).
- Galileo, [Stop LLM Summarization From Failing Users](https://galileo.ai/blog/llm-summarization-production-guide).
- OpenAI Cookbook, [How to evaluate a summarization task](https://developers.openai.com/cookbook/examples/evaluation/how_to_eval_abstractive_summarization).
- Hacker News discussion, [LLMs don't summarize, only shorten](https://news.ycombinator.com/item?id=44913172).

## Stability

This method's inputs, outputs, and concept shapes are part of the `mthds-std` v0.1 stability contract. Breaking changes require a major version bump plus a deprecation window. See `STABILITY.md`.
