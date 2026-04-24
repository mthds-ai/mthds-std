# Industry + practitioner notes on LLM summarization

## 1. Galileo — "Stop LLM Summarization From Failing Users"

- https://galileo.ai/blog/llm-summarization-production-guide
- **Real production failure modes catalogued**:
  - Context-window overflow → older conversation parts compressed → critical escalation signals disappear
  - Cascading summaries (summary-of-summaries) → "progressive error amplification" — each layer drifts further
  - Overgeneralization → "users are satisfied with onboarding" when raw comments show the opposite
  - Prompt sensitivity — small wording changes alter length, focus, factuality
- **Recommendations**:
  - Robust prompting: define scope precisely, specify output structure (JSON), use CoT
  - **Hierarchical compression via "chunk-and-merge"**: split → summarize each segment → combine mini-summaries (contrast: the 2024 positional-bias paper found hierarchical merging can hurt faithfulness — depends on input shape)
  - **Sliding windows** for conversation — re-summarize only recent + keep persistent memory
  - **Confidence thresholds** — if a summary scores below a threshold, use a longer-context model instead of risking user trust
  - **Transparency** — show confidence scores to users
  - **2–5% human review** sampling for catching subtle context errors

## 2. Eugene Yan — "Evaluation & Hallucination Detection for Abstractive Summaries"

- https://eugeneyan.com/writing/abstractive/
- **The faithfulness problem is worse than people realize**:
  - **30–43% hallucination rate on CNN/DailyMail**
  - **92% faithfulness-error rate on XSum** (extreme summarization)
- **Four eval dimensions** (matches SummEval):
  - Fluency → "mostly solved" by modern LLMs
  - Coherence → matters less in short summaries
  - Relevance → subjective, hard to automate
  - **Consistency/faithfulness → most objective, most automatable — focus here**
- **Escalating toolkit of techniques**:
  1. Reference-based metrics (ROUGE/METEOR/BERTScore) **if references exist**
  2. Adapt them to compare summary vs. source (not vs. reference)
  3. **NLI models** finetuned for consistency detection (SummaC, TrueTeacher)
  4. Sampling-based approaches (SelfCheckGPT — multiple summaries, check consistency)
  5. Strong LLMs as judges
  6. Trained reward models from preference data
  7. QA-based metrics (QuestEval, QAFactEval) — "last resort, complex but potentially most effective"
- **State-of-the-art reality**: best consistency detection gets **60–75% balanced accuracy** on well-studied datasets (matches the FaithJudge paper's pre-FaithJudge numbers).
- **Uncomfortable fact**: reference summaries themselves are often poor — modern LLMs outperform published references on CNN/DailyMail and XSum. Means "beat the reference" is a low bar.

## 3. CMU SEI — "Evaluating LLMs for Text Summarization: An Introduction"

- https://www.sei.cmu.edu/blog/evaluating-llms-for-text-summarization-introduction/
- **Three-category framework**: human assessment + automated metrics + AI red-teaming.
- **Five evaluation dimensions**:
  1. Accuracy (proximity to expected output)
  2. **Faithfulness** (consistency with input)
  3. **Compression** (how much shorter)
  4. **Extractiveness** (how much copied vs. rewritten)
  5. Efficiency (cost/time)
- **Recommended metrics**:
  - Accuracy → ROUGE, BLEU, METEOR, BERTScore
  - Faithfulness → SummaC, QAFactEval
  - Compression/Extractiveness → compression ratio, coverage, density
- **Strong recommendation**: NO single metric. Use a collection tailored to the use case.
- **Cautions against**:
  - Relying on reference-based metrics (references often unavailable or low-quality)
  - "Black box" LLM-based evaluation without transparency

## 4. "How to Evaluate LLM Summarization" — Tham, Medium

- https://medium.com/data-science/how-to-evaluate-llm-summarization-18a040c3905d
- **Explicitly rejects ROUGE/BLEU** for LLM-era abstractive summaries — "pre-LLM, built for extractive."
- **Rejects neural metrics** (Seahorse, Summac) for ops reasons — "several GBs, hard to run at scale."
- **Recommends LLM-as-judge via DeepEval**:
  - **Coverage (recall)** — generate *open-ended* questions from source with importance ratings, score answers 0–5
  - **Alignment (precision)** — pass the **full source** (not extracted claims) to avoid non-determinism
  - Final score = **F1** of coverage & alignment (not min)
- **Concrete targets**:
  - Entity density ~0.15 (matches Chain of Density's convergence point)
  - Coherence via sentence-to-sentence cosine similarity (nth vs n+2th sentence): ~0.45 for LLM summaries, <0.40 when sentences are randomly permuted → differential = signal
  - Repetitiveness via G-Eval criteria

## 5. HN thread: "LLMs don't summarize, they only shorten"

- https://news.ycombinator.com/item?id=44913172
- **Core claim**: true summarization requires *external* comprehension — knowing what's *important about* a text; LLMs do fluent compression.
- **Supporting view**: LLMs pattern-match to training-set summaries; fall apart on genuinely novel material.
- **Refuting view**: LLMs handle truly novel text fine, no blind-test evidence of failure.
- **Value**: philosophical grounding — "fluent compression" is a more honest descriptor than "summary," and explains many production failures (the LLM's notion of "important" ≠ the reader's).

## 6. OpenAI Cookbook — "How to evaluate a summarization task"

- https://developers.openai.com/cookbook/examples/evaluation/how_to_eval_abstractive_summarization
- **Multi-method strategy** (echoes SummEval and CMU SEI):
  1. ROUGE — legacy n-gram overlap
  2. BERTScore — semantic similarity
  3. **GPT-4-as-judge** — reference-free, rubric-based
- **Grading rubrics** (SummEval-aligned):
  - Relevance — 1–5
  - Coherence — 1–5
  - Consistency (faithfulness) — 1–5
  - Fluency — 1–3 (Poor/Fair/Good)
- **Acknowledges** potential bias in LLM-judge favoring LLM-generated text.
- **Closing recommendation**: combine human evaluation with automated metrics for most reliable results.

## 7. Reference-set variation paper (2025)

- https://arxiv.org/html/2506.14335v1
- **Critical finding for LLM era**: as output quality improves, correlation between automatic metrics and human judgment **decreases**. Post-LLM summaries have lower metric-human correlation than pre-LLM ones.
- **Meta-consequence**: the very tools we'd use to grade modern LLM summaries were calibrated on worse models. We're measuring new-era outputs with old-era rulers.
- **On reference-set size**: pre-LLM era, more references → better correlation. LLM era: more references → no improvement or slightly worse. References are less useful when outputs surpass them.

## Cross-cutting patterns

Things that appear across multiple sources:

- **Single-number evals are dangerous** — every source says don't trust one metric
- **Faithfulness is the hardest + most consequential dimension** — Eugene Yan, CMU, SummEval, Galileo, FaithJudge all agree
- **NLI + QA hybrid methods currently lead for faithfulness detection** — SummaC, QAFactEval, QuestEval keep appearing
- **Decompose to claims before scoring** — summary-wise grading loses signal compared to claim-wise
- **Reference-based metrics are a legacy tax** — ROUGE keeps showing up for baseline comparability only, not quality signal
- **Hierarchical / cascading summaries amplify errors** — Galileo warns of this; the positional-bias paper measures it
- **Entity preservation (~0.15/token) is a workable density target** — appears in Chain of Density + Medium evaluation guide independently
