# Input-aware summarization: design thinking

Not yet implemented. This is the architecture sketch for a `summarize` primitive
that adapts its strategy to the kind of text it's given.

> **Note on Pipelex pipes**: the architecture below uses `PipeSequence` everywhere,
> `PipeCondition` for the routing step, and sometimes `PipeBatch` for per-chunk
> work. That's what the problem calls for. If a step is simpler as a single
> `PipeLLM`, it stays a single `PipeLLM` — we don't add `PipeParallel` or
> recursion just because the toolkit supports them. Using every pipe type is not
> a design goal; solving the routing problem cleanly is.

The user's pushback that forced this doc:

> "The summary method ALSO NEEDS TO adapt to the KIND OF text. For example,
> IF ITS A RESEARCH PAPER, MAYBE it should output JUST the abstract? If its a
> small text, its NOT the same strategy as a Large text. Or a bunch of text.
> Its OF COURSE AN AI WORKFLOW, so it NEEDS TO HAVE MANY STEPS, parallel,
> condition etc, anyway use the full power of pipelex."

---

## The real insight: "summarize" is a routing problem, not a prompt problem

One prompt, one model, one strategy → will always be mediocre across input types.
The research (`10_papers.md`, `20_industry.md`, `30_techniques.md`) is unanimous
that different input types need different strategies. Chain of Density works
great on news but wastes cycles on a 500-word memo. Hierarchical merging
amplifies errors on short text but is necessary for long text. News articles
have a lead bias that RoPE happens to handle well; research papers front-load
abstracts that are already summaries.

**A principled `summarize` primitive detects what it's given, picks a strategy,
executes it, and verifies.** That's what Pipelex's controller pipes exist for.

---

## The two axes that determine strategy

After reading the research, there are really only two dimensions that need
to drive the routing:

### Axis 1 — input shape

| Shape | Typical length | Has intrinsic structure? | Pre-existing summary? |
|---|---|---|---|
| trivial | <200 words | no | n/a |
| short general | 200–2k | varies | no |
| research paper | 3k–15k | yes (abstract, intro, method, results) | **yes (abstract)** |
| news article | 300–2k | inverted pyramid | effectively (lead) |
| blog post | 500–5k | headings common | rarely |
| report / whitepaper | 3k–30k | yes (exec summary, sections) | often (exec summary) |
| book chapter | 5k–30k | narrative flow | no |
| meeting transcript | 2k–20k | turn-based, speaker-attributed | no |
| email thread | 500–10k | turn-based, chronological | no |
| chat / conversation | 500–∞ (streaming) | turn-based | no |
| legal document | 2k–50k | numbered clauses | rarely |
| slides / deck | 200–3k | bullet-heavy, already condensed | effectively |
| code | 100–5k | syntactic | no |
| multi-document bundle | 5k–500k total | depends | per-doc varies |

### Axis 2 — purpose / output shape

| Purpose | Output shape | Optimizes for |
|---|---|---|
| TL;DR / gist | 1–3 sentences | fluency, recency |
| briefing | 100–300 words | faithfulness, coverage |
| structured report | sections + bullets | scannability |
| searchable index | keywords + entities | retrievability, density |
| continuation input | structured JSON | downstream parsability |

---

## Proposed architecture

```
summarize (MAIN_PIPE, PipeSequence)
  │
  1. profile_input ─────────────────────────► InputProfile
  │     PipeLLM, small/fast model
  │     text (+ optional caller hints) → {
  │        input_type,              # one of the categories above
  │        length_category,         # trivial | short | medium | long | very_long
  │        has_structure,           # headings / sections / clear hierarchy
  │        has_preexisting_summary, # abstract / exec summary / lead
  │        preexisting_summary_span, # if any, where it is
  │        language,
  │        word_count,
  │        entity_density_source,   # cheap signal
  │        detected_hazards,        # contradictions, redactions, markup noise
  │     }
  │
  2. select_strategy ───────────────────────► strategy_code (string)
  │     PipeCondition driven by InputProfile + caller hints
  │     outputs one of:
  │       "return_as_is"         (trivial / already short enough)
  │       "promote_preexisting"  (research paper, whitepaper — use the abstract,
  │                               enhance with key results)
  │       "single_shot"          (short general text)
  │       "extract_then_write"   (medium text — our 3-step validated pattern)
  │       "conversation"         (chat / meeting / email — turn-aware)
  │       "chunk_map_reduce"     (long — split, summarize each, merge with grounding)
  │       "hierarchical_tree"    (very long — recursive tree summary)
  │       "multi_doc_synthesis"  (multiple docs — cross-doc synthesis)
  │
  3. execute ────────────────────────────────► Summary (draft)
  │     PipeCondition dispatches to sub-pipelines below.
  │     Each sub-pipeline returns a draft Summary.
  │
  4. verify_faithfulness ───────────────────► FaithfulnessReport
  │     PipeLLM, claim-level
  │     draft + source + extracted_facts → {
  │        unsupported_claims[],
  │        missing_key_points[],
  │        status_adjustment,   # may downgrade confidence or force "partial"
  │     }
  │
  5. format_output ─────────────────────────► final Summary
        PipeLLM or PipeCompose (template)
        applies caller's requested `format` (prose/bullets/sections)
        applies caller's `length` hint
        populates the final Summary shape
```

---

## Sub-pipeline specs (one per strategy)

### 1. `return_as_is` — trivial input

Input is already a summary. Don't summarize a summary.

```
return_as_is (PipeSequence)
  1. return_trimmed              PipeFunc (or PipeLLM minimal)
     text → Summary {
       summary: text,
       status: "already_summary",
       confidence: "high",
       key_points: [first_sentence],
     }
```

Triggers: `length_category == "trivial"` OR word count < caller's requested length.

---

### 2. `promote_preexisting` — research paper / whitepaper

The document already contains a summary (abstract, exec summary, lead). Use it
as the spine and enrich.

```
promote_preexisting (PipeSequence)
  1. extract_preexisting          PipeLLM
     text + preexisting_summary_span → clean_abstract
  
  2. parallel:                    PipeParallel
     ├─ extract_key_results       PipeLLM
     │    full text → {numerical_findings, named_contributions, limitations}
     └─ extract_key_quotes        PipeLLM
          full text → {headline_quotes[]}
  
  3. enhance_abstract             PipeLLM
     clean_abstract + results + quotes → enriched summary
     (keeps the author's own framing; adds what the abstract elides)
```

Research paper-specific insight: the abstract is usually written by the author
and is already optimized for faithfulness. Rewriting it loses information;
enhancing it adds what abstracts chronically miss (specific numbers, methodology
deltas, limitations).

---

### 3. `single_shot` — short general text

```
single_shot (PipeSequence)
  1. summarize_direct             PipeLLM
     text + length + format + audience → Summary draft
```

One LLM call. For text < 2k words where extract-then-write is overkill.
The cost/quality tradeoff tips in favor of simplicity here.

---

### 4. `extract_then_write` — the validated default

This is what we sketched in `40_synthesis.md`. Applies to general medium-length
input (2k–15k words).

```
extract_then_write (PipeSequence)
  1. extract_key_facts            PipeLLM
     text → {entities, numbers, dates, claims, key_points}
  
  2. draft_summary                PipeLLM
     text + extracted_facts + length + format + audience
     → Summary draft with claim_citations
```

---

### 5. `conversation` — chat / meeting / email

Turn-based, speaker-aware. Very different failure modes from document
summarization.

```
conversation (PipeSequence)
  1. extract_structure            PipeLLM
     text → {turns[], speakers[], timestamps_if_any}
  
  2. parallel:                    PipeParallel
     ├─ extract_decisions          PipeLLM
     │    turns + speakers → decisions[]
     ├─ extract_action_items       PipeLLM
     │    turns + speakers → action_items[] (with owner + deadline if stated)
     ├─ extract_topics             PipeLLM
     │    turns → topics_discussed[]
     └─ extract_unresolved         PipeLLM
          turns → open_questions[]
  
  3. compose_structured_summary   PipeCompose (deterministic template)
     decisions + actions + topics + unresolved + audience → Summary
```

Key design point: the output shape for conversations is genuinely different
(has `decisions`, `action_items` as first-class fields). This suggests maybe
we should actually have a **sibling primitive** `summarize_conversation`, not
a branch. TBD.

---

### 6. `chunk_map_reduce` — long input

For 15k–100k words that fit in a long-context model but benefit from explicit
chunking.

```
chunk_map_reduce (PipeSequence)
  1. chunk_document               PipeFunc or PipeLLM
     text → chunks[] (semantically bounded, not fixed-length)
  
  2. summarize_each_chunk         PipeBatch
     chunks[] → chunk_summaries[] (parallel, fast)
     Each chunk also outputs its own extracted_facts
  
  3. merge_with_source_grounding  PipeLLM
     chunk_summaries[] + original text (as grounding context)
     → merged Summary
     KEY: the 2024 positional-bias paper's finding — merge step must
     re-ground against SOURCE, not just against prior summaries.
     Cascade-only merging amplifies hallucinations.
```

---

### 7. `hierarchical_tree` — very long input

For 100k+ words, or when chunk count > some threshold where flat map-reduce
produces too many chunks to merge in one LLM call.

```
hierarchical_tree (PipeSequence)
  1. chunk_at_leaves              PipeFunc
     text → leaf_chunks[]
  
  2. summarize_leaves             PipeBatch (parallel)
     leaf_chunks[] → leaf_summaries[]
  
  3. group_level_1                PipeFunc
     leaf_summaries → groups_level1[] (N per group)
  
  4. summarize_level_1            PipeBatch (parallel)
     For each group: LLM with access to SOURCE for that group's leaf ranges
     → level1_summaries[]
  
  5. repeat until one summary     PipeCondition loop
     if count > 1: group → summarize → back to step 5
     if count == 1: done
  
  6. final_ground_to_source       PipeLLM
     final summary + full source (long-context) → verified final
     Last-chance faithfulness check against the original, not summaries of summaries
```

This is exactly the pattern AdmTree and context-aware hierarchical merging
papers describe. NOT the naive cascade that Galileo warns about.

---

### 8. `multi_doc_synthesis` — several related documents

Not a single text. Multiple texts that need cross-document synthesis.

```
multi_doc_synthesis (PipeSequence)
  1. per_doc_profile_and_summarize PipeBatch
     documents[] → per_doc_summaries[] (each ran through its own
                                        input-aware summarize sub-pipeline!)
     (this is recursive: each doc gets profiled + routed + summarized via our
      main primitive. The primitive calls itself on each document.)
  
  2. parallel:                    PipeParallel
     ├─ identify_common_themes   PipeLLM
     │    per_doc_summaries → themes[]
     ├─ identify_contradictions  PipeLLM
     │    per_doc_summaries → contradictions[]
     └─ identify_unique_insights PipeLLM
          per_doc_summaries → per_doc_unique[]
  
  3. compose_synthesis            PipeLLM
     themes + contradictions + unique + per_doc_summaries
     → cross-doc Summary
```

Arguably this should also be its own sibling primitive `summarize_corpus`,
not a branch inside `summarize`. Multi-doc changes the output shape
(introduces `cross_doc_contradictions`, `themes`, etc.).

---

## What to do about caller overrides

The profiler can be wrong. A caller who KNOWS their input is a research paper
should be able to skip the profile step.

```
summarize(
  text,
  length = "medium",
  format = "prose",
  audience = "",
  input_type_hint = "",    # OPTIONAL — "research_paper", "meeting", etc.
                            # When provided, skips profile_input and routes directly.
  strategy_override = "",   # OPTIONAL — for debugging or advanced callers
)
```

Defaults auto-detect; callers opt in to control.

---

## The open design question I can't resolve without more thought

**Is this one primitive with 8 strategies, or 3–4 sibling primitives?**

Arguments for **one primitive**:
- Single callable for every use case
- Caller doesn't have to know which to pick
- Pipelex composition (`PipeCondition`) is made for this

Arguments for **siblings**:
- Output shapes genuinely differ (`summarize` of a meeting has `action_items`
  as a first-class field; `summarize` of an article doesn't)
- Trying to unify all shapes produces a bloated `Summary` type with many
  optional fields
- Matches how `mthds-std` already splits concerns (we didn't force
  `answer_from_documents` to handle both short-form QA and long-doc QA)

**My hunch** (for later debate):
- `summarize` — single doc, non-conversational (strategies 1–7 minus conversation)
- `summarize_conversation` — sibling primitive, turn-based
- `summarize_corpus` — sibling primitive, multi-doc synthesis

Three primitives, each with a clean contract, each with its own `eval/configs/`.
`summarize` is the one we'd build first because it's the most universal AND
the benchmark (XSum) targets it directly.

---

## The benchmark complication

Our research picked **XSum** (extreme news summarization) as the anchor
benchmark. But if `summarize` routes by input type, XSum only exercises ONE
route (news article → single_shot or extract_then_write). We'd be gating on
a slice of the method's behavior.

Options:
1. **Accept this** — XSum is the leaderboard we need anyway. Other strategies
   get eval'd as they're used, through their own small benchmarks.
2. **Add per-strategy benchmarks** over time:
   - Research papers → ScisummNet or arxiv-cs-summarization
   - Meetings → MeetingBank
   - Long docs → GovReport or LongBench-summarization
   - Multi-doc → MultiNews
3. **Weight the gate** — 50% XSum (news), 50% a diverse sample from other
   HF benchmarks

Option 2 is the right long-term answer. v0.1 ships with just XSum and we
acknowledge the other routes are eval'd by human review only. v0.2 adds
MeetingBank etc. as separate datasets.

---

## The big questions to resolve BEFORE writing code

1. **Single primitive vs. 3 siblings?** — the biggest architectural fork.
2. **Is `profile_input` robust enough to trust?** — what fraction of inputs
   does it misclassify, and what's the failure mode when it does?
3. **Do we expose `strategy_override`?** — debugging aid or attack surface?
4. **How many benchmarks for v0.1?** — ship with one (XSum), or commit to 2–3
   (XSum + MeetingBank + ScisummNet) before we call it ready?
5. **What's the minimum strategy for v0.1?** — all 7, or start with 3
   (single_shot, extract_then_write, chunk_map_reduce) and add more over time?

Discuss these before implementation.

---

## What this design gets right

- **Routing solves the real problem** — one strategy cannot serve 14 input types; a profile + condition step is the minimal way to adapt
- **Each strategy is testable in isolation** — can validate `promote_preexisting` on arxiv papers without running anything else
- **Verify step is shared** — all strategies converge into the same faithfulness check, keeping the contract uniform
- **Recursive self-use makes multi-doc free** — `multi_doc_synthesis` calls the main primitive per document; the routing logic applies at every level without new code
- **Honest profile output** — `detected_hazards` lets the profiler flag "this input looks adversarial" early, before LLM cost is spent

## What this design risks

- **Profiler misclassification** — a report that looks like a research paper
  but isn't, or a transcript mistaken for prose, routes to the wrong sub-pipeline
- **Strategy count creeps** — 7 strategies is a lot; each one is its own
  maintenance burden
- **The "general" strategy carries too much weight** — if `extract_then_write`
  becomes the catch-all for anything the profiler isn't sure about, it needs
  to be really good
- **Benchmark coverage is uneven** — XSum only tests one route

---

## Status

Design thinking only. Do NOT implement yet. This file is the working memo
the user wanted me to write before we build.

When we're ready to build, the questions under "big questions to resolve"
get answered first, then we do Phase 0 of the `new-std-method` skill with
this design in hand.
