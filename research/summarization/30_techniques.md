# Named techniques (with pointers)

## Generation techniques

### Chain of Density (CoD)
- Adams et al. 2023 — https://arxiv.org/abs/2309.04269
- Iterative densification: start sparse, add 1–3 missing entities per round, keep same length
- Default: 5 rounds; Instructor's impl uses 3
- Converges to entity density ~0.15 (entities/token)
- Tradeoff: denser = less readable
- Best candidate for **"hit a target density"** as a knob

### Extract-then-write
- Galileo + our own `answer_from_documents` design
- Step 1: extract key facts (entities, numbers, dates, claims)
- Step 2: write summary constrained to those facts
- Step 3: verify each claim in summary traces to source
- The pattern we already use in `answer_from_documents` — carries over cleanly

### Chunk-and-merge (hierarchical)
- Galileo production guide
- Split input into chunks → summarize each → combine summaries
- **Warning from positional-bias paper**: can amplify hallucinations; simple "focus on middle" prompts often beat this
- Useful when input > context, but not free lunch

### Sliding window (for conversation / running streams)
- Galileo
- Re-summarize only recent N turns + keep persistent long-term memory
- Different problem shape than single-shot doc summarization — different primitive

### Context-aware hierarchical merging
- https://arxiv.org/abs/2502.00977 (2025)
- Re-ground each merge step in the original source, not just in prior summaries
- Targeted fix for hierarchical merging's error amplification

## Evaluation techniques (faithfulness)

### SummaC (NLI-based, sentence-level)
- Applies Natural Language Inference at sentence granularity
- Strong performer; referenced by Eugene Yan + CMU SEI

### QAFactEval (QA + NLI hybrid)
- Generate questions from source → check summary answers them correctly
- Combines with NLI signals
- "Last resort but potentially most effective" — Eugene Yan

### FaithJudge (few-shot LLM-as-judge)
- https://arxiv.org/html/2505.04847v2 (2025)
- Use human-annotated hallucination examples as in-context demonstrations
- 84% balanced accuracy on FaithBench vs. ~50% for zero-shot methods
- **Current SOTA for faithfulness judging**

### SelfCheckGPT (sampling-based)
- Generate multiple summaries, compare for consistency
- "Simpler unigram models surprisingly outperform complex methods" — Yan
- Works without a reference or source document

### TrueTeacher (distilled NLI)
- NLI model distilled using synthetic labels from LLM-annotated summaries
- 87.8% ROC-AUC
- Smaller model, cheaper inference than LLM-as-judge

### Per-document max-pooling
- Positional bias paper's recommendation
- Score each source document individually, take max faithfulness score
- Mitigates lost-in-the-middle in the **evaluator**, not just the generator

## Evaluation techniques (coverage + content selection)

### Open-ended question generation (coverage metric)
- Medium guide (Tham)
- Generate QA pairs from source with importance rating
- Grade summary-derived answers 0–5 vs. reference answers
- Avoids the yes/no binary trap

### Entity density target ~0.15
- Appears in CoD + Medium eval independently
- Simple deterministic metric: distinct entities / token count
- Good content-richness proxy

### Sentence-to-sentence cosine (coherence)
- Adjacent and n+2 sentence pairs
- ~0.45 for LLM summaries, <0.40 when permuted → differential = signal
- Deterministic, cheap, ignores content quality

## Prompting patterns

### "Focus on middle documents" (anti-position-bias)
- Positional bias paper
- Just adding this instruction outperforms hierarchical merging
- Cheap; works because RoPE bias is a tendency not a hard wall

### Claim-wise vs. summary-wise judging
- FaithJudge paper
- Decompose summary into claims → judge each vs. source → aggregate
- Consistently beats whole-summary judging

### Structured output enforcement
- Galileo + practitioner consensus
- Force JSON / typed schema → prevents length drift, aids downstream parsing
- Reduces prompt-sensitivity problem

### CoT + explicit reasoning field
- Galileo
- Make the model narrate its reasoning before writing the summary
- Useful for verification step (can be checked vs. source); cost: latency + tokens

## Benchmarks worth knowing

| Benchmark | What it tests | Why it matters |
|---|---|---|
| **CNN/DailyMail** | Extractive-friendly news summaries | Legacy; easy but models cheat by copying leads |
| **XSum** | 1-sentence abstractive from ~300-word news | Hard; hallucination surfaces immediately; **92% faithfulness errors reported** |
| **SummEval** | 16 models × 100 articles × 4 human-rated dims | The meta-eval of metrics; calibration reference |
| **FaithBench** | Hardest faithfulness detection | SOTA methods get 84% balanced accuracy here |
| **AggreFact** | Aggregated factuality benchmarks | Cross-dataset |
| **RAGTruth** | RAG-specific faithfulness | Different distribution than news |
| **TofuEval-MeetingBank** | Meeting transcript summarization | Dialogue / conversation shape |
| **MultiNews** | Multi-document news | Multi-doc shape, heavier; used in positional-bias paper |
| **SAMSum** | Dialogue summarization | Conversation-specific |

## Hybrid extractive-then-abstractive (the dominant production pattern)

- **Widespread industry convergence** — AWS, Arize, Galileo, Mozilla blog all recommend a two-stage pipeline
- **Stage 1 (extractive)**: deterministic pick of key sentences/entities from source — zero hallucination risk
- **Stage 2 (abstractive)**: LLM rewrites the extracted material for fluency, fusion, readability
- **Use cases where hybrid wins**:
  - Legal, medical, scientific, compliance — where exact phrasing matters
  - Any context where "did this come from the source" must be inspectable
- **Use cases where pure abstractive is fine**:
  - News, blog posts, exec summaries — where readability dominates
- **Our primitive**: our 3-step pipeline (extract_key_facts → draft → verify) IS this pattern. The research confirms it — extract-then-write is the industry default for faithful summaries, not an innovation but a validated choice.

## Commercial / open toolkits

- **DeepEval** (https://github.com/confident-ai/deepeval) — LLM-as-judge framework, referenced by Medium guide
- **G-Eval** (part of DeepEval) — single-framework LLM judging with criteria
- **SummEval toolkit** (https://github.com/Yale-LILY/SummEval) — 14 metrics unified API
- **HHEM, AlignScore, MiniCheck** — fine-tuned faithfulness detectors (the ~50% accuracy set)
- **Ragas** — RAG-focused evaluator suite (what we already use in Langfuse)
