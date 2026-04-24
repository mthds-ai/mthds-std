# Academic research on LLM summarization (digested notes)

## 1. Lost in the Middle — Liu et al., TACL 2024

- **arXiv**: https://arxiv.org/abs/2307.03172
- **Core finding**: U-shaped performance curve. LLMs attend strongest to the **beginning (primacy)** and **end (recency)** of their context; middle content is systematically under-used.
- **Root cause**: Rotary Position Embedding (RoPE) introduces long-term decay. Architectural, not prompt-fixable.
- **Mitigation that works**: Placing the most important content at the start or end of the prompt, not the middle.
- **Direct implication for summarization**: When the input is long, summaries will disproportionately reflect front + back, under-weighting middle content. This is an architectural property of current LLMs — no summarizer on top of a long-context model fully escapes it.

## 2. Positional Bias of Faithfulness for Long-Form Summarization (2024)

- **arXiv**: https://arxiv.org/html/2410.23609v1
- **Key novelty**: the **faithfulness metrics themselves** have positional bias — not only the generators.
- **Specific numbers**:
  - 7.8% difference in balanced accuracy when documents are reordered (MultiNews)
  - Highest sensitivity when important docs are placed in the middle (avg 3.1% variation)
  - Lead bias confirmed in the metrics: they score highest when important content is up front
- **Remedy that works**: Evaluate each source document individually and take the **maximum faithfulness score** across per-document evaluations. Outperforms full-context scoring.
- **Surprising negative result**: Hierarchical merging and incremental updating **reduced** faithfulness. Simple prompting ("focus on the middle documents") beat sophisticated methods.
- **Direct implication for our eval**: if we use LLM-as-judge for faithfulness on long inputs, we must score per-chunk + max-pool, not full-context.

## 3. Benchmarking LLM Faithfulness in RAG with Evolving Leaderboards (2025)

- **arXiv**: https://arxiv.org/html/2505.04847v2
- **Introduces FaithJudge**: LLM-as-judge framework that uses human-annotated hallucination examples in-context (few-shot) rather than zero-shot prompting.
- **Benchmarks used**: FaithBench (hardest), AggreFact, RAGTruth, TofuEval-MeetingBank.
- **Reality check on existing methods**:
  - Existing hallucination detectors (HHEM, AlignScore, MiniCheck) → ~**50% accuracy on FaithBench** = essentially random
  - Zero-shot GPT-4o → 65.9% balanced accuracy
  - Zero-shot o3-mini-high → 68.8% balanced accuracy
  - **FaithJudge (o3-mini-high + annotated examples) → 84% balanced accuracy, 82.1% F1-macro**
- **Takeaway**: the BEST published faithfulness detector, using few-shot with gold examples, gets 84%. Anything without calibration examples lives in the 50–65% range = random to weak.
- **Implication**: a naive LLM-as-judge for faithfulness is unreliable. Either use few-shot with hand-labeled examples, or accept the score is noisy.

## 4. Chain of Density (CoD) — Adams et al., 2023

- **arXiv**: https://arxiv.org/abs/2309.04269
- **ACL**: https://aclanthology.org/2023.newsum-1.7/
- **Technique**: Iterative densification. Start with a short entity-sparse summary (~80 words). In each round, identify 1–3 missing salient entities and rewrite the summary **keeping the same length** but adding them. 5 rounds by default.
- **Findings**:
  - Summaries become more **abstractive**, exhibit more **fusion**, less **lead bias** than vanilla GPT-4 prompts
  - Entity density goes from low → converges around 0.15 (entities per token)
  - Explicit **informativeness vs. readability tradeoff** — denser = harder to read
- **Instructor impl** (https://python.useinstructor.com/blog/2023/11/05/chain-of-density/):
  - 3 iterations instead of 5
  - Fine-tuned GPT-3.5 (20 examples) hits CoD's entity density of 0.15 at **20–40× faster / 72× cheaper** than GPT-4-CoD
  - Key constraint in prompt: "use the exact same number of words for each summary"

## 5. SummEval — Fabbri et al. TACL 2020 (still the canonical meta-eval)

- https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00373/
- **Re-evaluates 14 automatic metrics** against expert + crowd-sourced human annotation on 100 CNN/DailyMail articles × 16 model outputs.
- **The four dimensions** (now standard vocabulary):
  - **Coherence**: structure / organization across sentences
  - **Consistency**: factual alignment with source (= faithfulness, no hallucinations)
  - **Fluency**: sentence-level quality
  - **Relevance**: inclusion of important content
- **Finding**: automatic metrics poorly correlate with human judgment. Different metrics disagree. No metric captures all four dimensions.
- **Takeaway**: if you're going to use metrics, use a **collection** spanning the four dimensions, not a single number.

## 6. LLM Hallucination Survey (2025)

- **arXiv**: https://arxiv.org/html/2510.06265v2
- **Taxonomy**:
  - **Factuality hallucinations** — output contradicts real-world facts
  - **Faithfulness hallucinations** — output drifts from input/context; subcategorized into instruction / context / logical
  - **Intrinsic** — contradicts source ("Mona Lisa painted in 17th century")
  - **Extrinsic** — adds unsupported content
- **Clinical data point**: medical text summarization showed **1.47% hallucination rate + 3.45% omission rate** even with SOTA. That's 1-in-70 summaries hallucinating in a clinical setting, and 1-in-29 missing something important.

## 7. LLM-as-judge biases to know about (composite from multiple papers)

- **Verbosity bias**: judges prefer longer answers regardless of quality
- **Positional bias**: in pairwise, prefer second answer
- **Non-determinism**: different scores on repeat runs with same input
- **Shorter-answer bias in single-answer grading**: opposite of verbosity bias — depends on task framing
- **Overestimates faithfulness** as a class: judges are too generous about hallucinations

**Mitigation patterns from the literature**:
- Pairwise comparison + swap + average
- Multi-run + average to handle non-determinism
- Few-shot with gold examples (FaithJudge's finding)
- Decompose to claim-level judgments (claim-wise beats summary-wise in most benchmarks)
