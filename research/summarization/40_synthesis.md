# Synthesis: how research informs our `summarize` primitive

## What the research says, boiled down

### 1. Hallucination is the real problem (not coherence, not length)

- **30–43% hallucination rates on CNN/DailyMail**, **92% on XSum** (Eugene Yan)
- Even SOTA clinical pipelines: **1.47% hallucination + 3.45% omission** (Nature 2025)
- Best automatic detectors: **84% balanced accuracy** (FaithJudge, few-shot) vs. **~50% for anything zero-shot**

**→ Our gate metric must be faithfulness. Not length-hit, not ROUGE.**

### 2. "Lost in the middle" is architectural — we can't beat it, only work around it

- LLMs systematically under-attend to the middle of their context (TACL 2024)
- The problem shows up in both the **generator** and the **faithfulness evaluator** (2024 positional-bias paper)
- No prompt fully fixes it; "focus on middle" instructions help a little

**→ For long inputs, we degrade transparently (low confidence + caveats), we don't pretend to produce a balanced summary.**

### 3. Single metrics mislead — use a collection

- SummEval, CMU SEI, Eugene Yan all converge on this
- ROUGE keeps showing up but poorly correlates with human judgment post-LLM era
- Reference-based metrics are a legacy comparability tax; include but don't gate on them

**→ Report many scores; gate on one or two well-chosen ones.**

### 4. Evaluation-level positional bias is real

- Faithfulness scorers score higher when important content is at the start
- Remedy: per-document evaluation + max-pooling
- Hierarchical merging (multiple compression rounds) can **reduce** faithfulness

**→ Our judging strategy has to be careful. Prefer claim-wise over summary-wise. Prefer few-shot over zero-shot when hand-labeled examples exist.**

### 5. Entity preservation is the cheap faithfulness proxy

- CoD converges to 0.15 entities/token independently measured by practitioners
- Deterministic, no LLM-as-judge call needed
- Catches the "drops important names/numbers" failure mode without a judge

**→ Ship an `entity_preservation_rate` scorer as one of our deterministic metrics.**

### 6. Extract-then-write + verify is the pattern that works

- Galileo's production recommendation
- Our own `answer_from_documents` design
- Isolates "what matters" from "how to phrase it"
- Each step has a narrow failure mode, verifiable independently

**→ Three-step internal pipeline: extract_key_facts → draft_summary → verify_faithfulness. Same rigor as `answer_from_documents`.**

### 7. Chain of Density is a real, operationalizable technique — but with a knob

- Iterative densification converges to useful entity density
- But **denser ≠ better for all readers** — informativeness-vs-readability tradeoff
- Offering it as a style option is more honest than forcing it

**→ Expose `style = "prose" | "bullets" | "dense"` where "dense" uses CoD internally. Not the default (readability-hostile).**

## Concrete design for `summarize@0.1.0`

### Inputs

```
summarize(
    text,                   # the substrate
    length = "medium",      # "short" | "medium" | "long" | "<N> words"
    format = "prose",       # "prose" | "bullets" | "sections"
    style = "standard",     # "standard" | "dense" (CoD)  | "factual-only"
    audience = ""           # free-text hint; not enum (audience variety is infinite)
) → Summary
```

### Outputs (revised from first sketch, research-informed)

```
Summary {
    status: "summarized" | "partial" | "unsafe_to_summarize"
    summary: Text
    key_points: List[Text]                    # always populated, regardless of format
    preserved_entities: List[Entity]          # CHEAP DETERMINISTIC FAITHFULNESS SIGNAL
    claim_citations: List[ClaimTrace]         # each claim → span in source (claim-level auditability)
    faithfulness_self_assessed: Boolean       # the model's own assessment
    uncovered_aspects: List[Text]             # explicit: what was NOT included from source
    length_words: Integer
    confidence: "high" | "medium" | "low" | "none"
}
```

Key additions informed by research:
- **`claim_citations`**: from FaithJudge / QAFactEval / claim-wise judging — every claim must trace back. Downstream callers can audit without running a judge themselves.
- **`uncovered_aspects`**: explicit acknowledgment of what was dropped. The CMU "coverage" dimension, made inspectable.
- **`preserved_entities`**: deterministic faithfulness proxy per CoD + Medium guide.
- **`status`** enum: inherited from `answer_from_documents`; includes `unsafe_to_summarize` for cases where the input is adversarial (contradicts itself, too sparse, etc.)

### Internal pipeline (3 LLM calls, not 5)

```
summarize (PipeSequence, main_pipe)
  1. extract_key_facts        PipeLLM (fast)
        text → {named_entities, numbers, dates, claims[], key_points[]}

  2. draft_summary             PipeLLM (reasoning-class, optional CoD loop for "dense" style)
        text + extracted_facts + length + format + style + audience
        → Summary draft with claim_citations

  3. verify_faithfulness       PipeLLM (fast; could later swap for FaithJudge with few-shot)
        draft + extracted_facts + source_text
        → {faithful, unsupported_claims[], missing_key_points[]}
        → populates faithfulness_self_assessed, uncovered_aspects
        If unsupported_claims is non-empty: downgrade confidence
        If > K unsupported: force status = "partial"
```

### Scorers

**Deterministic (run per experiment, always):**
- `length_hit` — within ±20% of target length
- `entity_preservation_rate` — fraction of source entities appearing in summary; target > 0.70
- `compression_ratio` — source tokens / summary tokens (informational)
- `rouge_l` — baseline comparability, **informational only**

**LLM-as-judge (async, configured in Langfuse):**
- `Summary Faithfulness (claim-wise)` — decompose summary into claims, grade each vs. source. Optional: few-shot with hand-labeled FaithBench examples → approaches FaithJudge quality
- `Summary Coverage` — open-ended questions from source, grade summary-derived answers
- `Summary Fluency/Coherence` — lightweight, de-prioritized (mostly solved per Yan)

**Gate metric**: `Summary Faithfulness`. Threshold: 0.85 for v0.1 (aggressive — we'll miss on first release).

### Benchmark choice: XSum + (stretch: SummEval)

- **Primary**: `EdinburghNLP/xsum` on HF — 204k articles × 1-sentence abstractive summaries. Extreme summarization surfaces hallucination sharply. Baseline hallucination reported: **92% on XSum** (Yan) → our threshold should be "substantially better than baseline."
- **Stretch (v0.2)**: SummEval — human-rated scores across 4 dimensions, great for calibrating our judge against humans.

### What we're NOT promising (say it in the README)

- We won't fix lost-in-the-middle architectural biases
- We won't beat hierarchical merging's error amplification — single-doc only in v0.1
- We won't silently produce biased summaries on long input — degrade with `confidence: low`
- Coverage < faithfulness — we prioritize not-lying over not-missing-anything
- No single number is the full story; we report ~5 scores per run

## Pipeline rigor rules (inherited from `answer_from_documents`)

- Verbatim entity preservation (don't paraphrase names, numbers, dates in the summary)
- Explicit abstention path (`unsafe_to_summarize`) when the source is adversarial
- Confidence tied to evidence assessment, not to model prior
- `uncovered_aspects` is populated — we name what's missing, don't hide it

## Known risks / open questions

1. **CoD is slow** (49s for GPT-4 vs. 2s for fine-tuned GPT-3.5). Our "dense" style might need careful latency budgeting. Maybe only 2 rounds by default instead of 5.
2. **Judge cost** at benchmark scale — 1000 XSum items × 2 judges each = 2000 judge calls per run. Not trivial.
3. **FaithJudge-quality judging requires labeled examples** we don't have. Our first pass will use zero-shot → expect ~65% judge accuracy → our reported faithfulness has noise floor around 15–20 points. Should acknowledge this in the scorecard.
4. **XSum has 92% hallucination rate in the literature** — means our "summarized" status with high confidence will be a genuinely hard bar. A reasonable v0.1 might score 0.60–0.75 on Faithfulness. That's still publishable if we're honest about baselines.

## Late additions from further research

### 8. The meta-problem: metrics get worse as models get better

- 2025 reference-set variation paper: correlation between automatic metrics and human judgment **decreases** post-LLM era
- More references do not help for LLM outputs (unlike pre-LLM era)
- **Implication**: we cannot fully trust any automatic metric to track v0.1 → v0.2 quality improvements. We need **human spot-checks** periodically to confirm automatic scores reflect reality.
- **Practical**: schedule a 20-item human eval on the same dataset slice every major version bump. Compare our auto-scores to human ratings. Detect drift.

### 9. Extract-then-write is industry consensus, not a unique insight

- AWS, Arize, Galileo, Mozilla, OpenAI Cookbook all converge on two-stage hybrid
- Our `extract_key_facts → draft → verify` pipeline is *validated*, not original
- **Don't over-claim innovation** in the method README. Say: "implements the community-consensus extract-then-rewrite pattern with explicit verification."

### 10. Citation-based evaluation is a thing

- "Ask, Retrieve, Summarize" 2025 — introduces **Reference F1** for citation accuracy
- Measures whether summary citations resolve to correct source spans
- Our `claim_citations` field makes this computable
- **Possible new scorer**: `citation_resolvability_rate` — fraction of `claim_citations` that actually resolve to a valid source span. Deterministic, cheap, catches the "invented citation" failure mode.

## Revised recommendations (final)

### Must-haves for v0.1

1. **Pipeline**: 3-step extract → draft → verify (validated by industry consensus)
2. **Deterministic scorers**:
   - `length_hit` (±20%)
   - `entity_preservation_rate` (target 0.70, entity density target 0.15)
   - `citation_resolvability_rate` (new — checks claim_citations resolve)
   - `rouge_l` (informational only, for baseline comparability)
3. **LLM-as-judge scorers (Langfuse UI)**:
   - `Summary Faithfulness` (claim-wise) — primary gate
   - `Summary Coverage` (QA-based from source) — secondary
4. **Gate**: Faithfulness >= 0.85, but **acknowledge the noise floor** (zero-shot judge is ~65% accurate; our reported score has real uncertainty).
5. **Benchmark**: `EdinburghNLP/xsum`, 500-item sample first. Full 11k test in v0.2.
6. **Scorecard honesty**: publish baselines, noise floor, and the 4 SummEval dimensions. Do NOT claim "solved."

### Nice-to-haves for v0.2+

- FaithJudge-style few-shot with hand-labeled FaithBench examples → gets judging from ~65% to ~84% accuracy
- Human eval cadence (20 items per major version) — anchor the drift
- Chain of Density as a `style="dense"` option — not the default
- Position-robustness check: shuffle source paragraphs, re-summarize, compare consistency
- Multi-doc summarization: separate primitive `summarize_corpus` (NOT a knob on `summarize`)

### Explicit non-goals for v0.1

- No claim of solving "lost in the middle" — architectural
- No multi-doc (deferred)
- No running / temporal summaries (different problem shape)
- No code / audio / image inputs (compose upstream)
- No guarantee coverage ≥ faithfulness — we trade coverage for honesty

## TL;DR on the design

`summarize@0.1.0` is a **3-step faithful-compression pipeline** with **entity preservation** as the cheap deterministic anchor and **claim-wise judging** as the primary gate. Research says coverage and faithfulness trade off; we optimize for faithfulness and surface what was dropped. We benchmark on XSum (where hallucination bites hardest) and publish a calibrated scorecard that's honest about the noise floor.

Everything above is traceable to a cited paper or practitioner source — see `10_papers.md`, `20_industry.md`, `30_techniques.md`.
