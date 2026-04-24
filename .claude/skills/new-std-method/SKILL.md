---
name: new-std-method
description: |
  Scaffold a new method for `mthds-std` end-to-end: design → bundle → package → benchmark selection →
  dataset loader → scorers → eval wiring → docs → `make cc`. Does NOT run the evaluation
  (that costs LLM credits and is the user's call).

  Use when the user says: "add a method to mthds-std", "new std primitive", "create a method in mthds-std",
  "scaffold <verb> method", "add <foo> to the standard library", or asks to start a new primitive
  with its eval setup.

  Do NOT use this skill for:
    - methods that belong in `pipelex/methods` (vertical solutions) — that's a different repo
    - modifying an existing method (use `/mthds-edit` instead)
    - running existing experiments (use `make run-experiment` directly)
---

# Scaffold a new method in `mthds-std` with evaluation wired in

You are adding a primitive to **`mthds-std`** — the MTHDS standard library. Every primitive here has a stability contract (see `STABILITY.md`) and must be backed by a real benchmark (see `CONTRIBUTING.md`). Both constraints inform every phase below.

**Output of this skill**: a new `methods/<name>/` package + `methods/<name>/eval.py` + any new scorer the method needs, with `make cc` green. User runs `make push-dataset` and `make run-experiment` themselves.

---

## Phase 0 — Capture the method's purpose (gate)

Before any file-writing, confirm the method belongs in `mthds-std`. Ask the user to answer three things if not already stated:

1. **Purpose in one sentence** — e.g. "classify any text into one of N caller-provided categories".
2. **Inputs → output concept signature** — e.g. `Text + choices[]` → `Classification`.
3. **The 3-apps rule** — can the user name three *distinct, real* applications that would use this primitive as-is, in different domains? If they can't, redirect them to `pipelex/methods` (vertical solutions) and stop. `mthds-std` is under-included on purpose.

If the three facts are unclear, ask in ONE message with numbered questions. Do not proceed until the 3-apps rule is satisfied.

Also ask:
- **Method name** (snake_case, verb-first where possible: `classify_text`, `summarize`, `extract_entities`)
- **Desired package version** — usually `0.1.0` for a new primitive
- **Do you want eval wired in?** Yes/No. Some methods don't need a benchmark-backed scorecard — exploratory primitives, demo methods, or primitives whose inputs/outputs are too open-ended for benchmarks. Default: Yes, especially for anything that'll ship in `mthds-std`.

Record these; they flow into every later phase.

**Phase routing based on the eval answer**:

- **Yes, wire eval** → run all phases 1 → 9 as written
- **No eval** → skip Phase 1 (benchmark), Phase 5 (eval config), Phase 6 (scorer), Phase 7 (Langfuse judge). Run **only** Phases 2, 3, 4, 8, 9. The method still gets bundled, packaged, and documented — just without a scorecard behind it. Phase 9's handoff drops the `push-dataset` / `run-experiment` commands.

Be explicit with the user which path you're taking. If they change their mind later, adding eval is always possible: just append Phases 1, 5, 6, 7 to an existing method.

---

## Phase 1 — Find a benchmark with real ground truth

A new method is not accepted without a benchmark. You must identify one **public dataset** whose ground truth evaluates this method directly.

### Start on Hugging Face — always.

[huggingface.co/datasets](https://huggingface.co/datasets) is where essentially every public benchmark is hosted. Filter by task category (question-answering, summarization, text-classification, translation, etc.), sort by downloads, and look at the top 20 results for the primitive's task. That is almost always your candidate list.

Why HF first, not arXiv-first:
- Every seriously-used benchmark publishes there
- One API surface (`datasets` library), consistent schemas, built-in caching
- Download counts are a real signal of field adoption
- The dataset's HF page links back to the paper / GitHub / leaderboard — so you get the academic provenance anyway

Only fall back to arXiv / Papers-With-Code when:
- The task is too niche for HF's catalog (extremely rare for `mthds-std` primitives)
- You need a peer-review signal that HF metadata doesn't give you (check the dataset card — most link the paper)
- The benchmark is new and hasn't been uploaded yet (also rare)

### Per-candidate checklist

For each candidate, verify on the HF dataset card:

- **Openly downloadable** (public, no gated access)
- **Has explicit ground-truth answers** per item (check the dataset viewer)
- **Size**: ≥ 100 items for signal, ideally 500–5000
- **Official scoring methodology** documented (so we can port it as a scorer) — check the linked paper or repo
- **License** permits redistribution of scoring code if you port it

Present the top 1–3 candidates to the user with a short ranking + reasoning. Let the user pick.

### Known-good defaults by primitive class (all on HF)

| Primitive class | Benchmark candidates (HF paths) |
|---|---|
| Document QA | `yubo2333/MMLongBench-Doc`, `PatronusAI/financebench`, `THUDM/LongBench-v2` |
| Multi-hop QA | `dgslibisey/MuSiQue`, `hotpot_qa`, `dreamerdeo/2wikimultihopqa` |
| Scientific QA | `allenai/qasper` |
| Narrative QA | `deepmind/narrativeqa` |
| Classification | `ag_news`, `nyu-mll/multi_nli`, `SetFit/sst5` |
| Summarization | `cnn_dailymail`, `EdinburghNLP/xsum` |
| Entity extraction | `conll2003`, `ontonotes5` |
| Code | `openai/openai_humaneval`, `google-research-datasets/mbpp` |
| Translation | `facebook/flores`, `wmt19` |

If none fits, be explicit with the user that we'll need to compose a dataset — flag this as a scope expansion before proceeding.

**Deliverable of this phase**: the user has approved a concrete HF dataset path.

---

## Phase 2 — Build the bundle

Delegate to the `/mthds-build` skill to author the bundle. Brief it with:
- Domain code (`snake_case`, matches or relates to method name)
- Main pipe signature (inputs/outputs that align to the benchmark items)
- A short description of the internal pipeline

After `/mthds-build` runs, verify:
- `methods/<name>/bundle.mthds` exists
- `mthds-agent validate bundle methods/<name>/bundle.mthds` passes

If the build skill isn't available or the user wants you to author directly, follow `mthds-std/CONTRIBUTING.md` — singular concepts, `snake_case` pipe codes, zero deps on packages outside `native.*` + `mthds-std`.

---

## Phase 3 — Create the package manifest

Delegate to `/mthds-pkg` (or use the `mthds-agent package init` CLI directly):

```
mthds-agent package init \
  --address github.com/pipelex/mthds-std \
  --version <VERSION> \
  --description "..." \
  --authors "Evotis S.A.S" \
  --license MIT \
  --name <name> \
  --display-name "..." \
  --main-pipe <main_pipe_code> \
  -C methods/<name>
```

Then edit `methods/<name>/METHODS.toml` to add the `[exports.<domain>]` section listing every pipe the package exposes.

Verify: `mthds-agent package validate -C methods/<name>`.

---

## Phase 4 — Draft `methods/<name>/inputs.json` + `README.md`

The **method dir is the shippable package**. Only these files belong here:

```
methods/<name>/
  bundle.mthds      # Phase 2
  METHODS.toml      # Phase 3
  inputs.json       # sample inputs
  README.md         # user-facing docs
```

Do NOT put eval config, ground-truth notes, or runtime artifacts here — those live elsewhere (see Phase 5 for eval config).

- **`inputs.json`** — a single runnable sample. The **shape must match `build_bundle_inputs(...)` output from Phase 5**. Use a real URL or short inline content.
- **`README.md`** — purpose, inputs, outputs, status/confidence semantics (if applicable), model aliases used, known limits. **Prose + tables only.** No JSON / YAML / TOML code blocks or Mermaid diagrams (they don't render well in the MTHDS Hub and bloat package listings). Mirror the structure of `methods/answer_from_documents/README.md`.

---

## Phase 5 — Author `eval/configs/<name>.py` (the eval contract)

This is the **only method-specific file the eval framework needs**. It lives under `eval/configs/` — NOT in the method's package dir — so eval internals don't ship to the MTHDS Hub.

The docstring of this file doubles as the ground-truth provenance: cite the benchmark paper, HF URL, leaderboard link, license. No separate `GROUND_TRUTH.md` file.

Required template (adapt from `eval/configs/answer_from_documents.py`):

```python
"""Eval configuration for <name>."""
from __future__ import annotations
from typing import Any

from eval.scorers import ExactMatchScorer
# ... import any benchmark-specific scorer you built in Phase 6

DATASET_NAME        = "<benchmark-slug>-sample-v1"
DATASET_DESCRIPTION = "<benchmark> sample for <method>"
JUDGE_SCORE_NAMES   = ["Answer Correctness"]   # Langfuse-UI evaluators we poll for (or [])
GATE_METRIC         = "<scorer_name>"          # must match a scorer or a judge name

SCORERS = [
    ExactMatchScorer(),
    # benchmark-specific scorer (may require Phase 6),
]

def load_dataset_cases(*, n: int | None = None, all_: bool = False) -> list[dict[str, Any]]:
    """Return cases ready for Langfuse: [{input, expected_output, metadata}, ...].

    `input` MUST already be the pipe inputs payload — the exact shape
    `execute_pipeline(inputs=...)` expects. No run-time transformation layer.

    - all_=True: every row in the benchmark
    - n=N: a stratified sample of N (prefer diversity over randomness)
    - default: small sample (5–10) for smoke testing
    """
    ...
```

Implementation rules:
- **Load datasets via the `datasets` library** — `from datasets import load_dataset; ds = load_dataset("<hf_path>", split="train")`. Handles caching, schema, streaming, auth. Do NOT roll your own `urlretrieve` + pandas loader.
- **Every case dict must have** `input` (pipe-inputs payload), `expected_output` (dict with the benchmark's reference answer), `metadata` (dict). `metadata.doc_id` (or any stable item id) is used for idempotency in the seeder.
- **`input` is the pipe inputs directly** — keys match the bundle's declared inputs exactly, values are `{"concept": "...", "content": {...}}` stuffs. At run time, the framework passes `item.input` straight to `execute_pipeline(inputs=item.input)` with **zero transformation**.
- **`load_dataset_cases`** must respect both `n=<int>` and `all_=True`; if the user asks for both, `all_` wins

---

## Phase 6 — Add a scorer if a generic one doesn't fit

If the benchmark uses a **custom official scoring protocol** (e.g. MMLongBench-Doc's type-specific ANLS), port it:

1. Create `eval/scorers/<benchmark_name>_official.py`
2. Copy the upstream scoring code verbatim where possible — preserving algorithmic parity is the whole point of an "official" scorer. Add prominent attribution at the top of the file with the upstream URL.
3. Implement a class with:
   ```python
   class <BenchmarkName>OfficialScorer:
       name = "<benchmark_name>_acc"  # or similar
       def score(self, *, output, expected_output, input, metadata) -> ScoreResult: ...
   ```
4. Register it in `SCORERS` in the method's `eval.py`

Check the upstream repo's license. If it's not a permissive license, **do not copy** — instead, invoke it via subprocess or link to it.

For **standard metrics** (accuracy, F1, BLEU, ROUGE, exact match), prefer reusing what already exists in `eval/scorers/`. Add a new generic scorer only if the metric is broadly reusable across future methods.

---

## Phase 7 — Extend the existing Langfuse judge filter (one-line UI step)

The Langfuse LLM-as-judge (`Answer Correctness` or equivalent) is **already configured project-wide**. You don't create it.

What you DO need: add the new dataset name to its **filter list** so the judge runs on experiments against your dataset. In the Langfuse UI:

- **Evaluators** → open the existing judge config → **Filter**: add `<DATASET_NAME>` to the "dataset is one of" list → Save

That's it. One dropdown edit. Then judge scores will populate for this method's runs the same way they do for existing methods.

---

## Phase 8 — Validate everything locally

Run (in the `mthds-std` repo root):

```bash
make cc
```

This runs: `ruff-format` → `ruff-lint` → `plxt-format` → `plxt-lint` → `pyright` → `validate-bundles`. All must pass.

If anything fails:
- **Bundle validation errors**: open `bundle.mthds`, read the error path, fix concept/pipe reference mismatches
- **Pyright errors**: most commonly, a missing import, a dict shape mismatch, or a scorer `.name` attribute missing
- **ruff errors**: auto-fix where possible; explain any remaining rule violations

Never silence errors with broad `# type: ignore` unless the underlying issue is a third-party stub gap.

---

## Phase 9 — Smoke-test on 5 items, then hand off the full run

Run a **5-item smoke test** yourself. This is cheap (~30s of LLM time per item) and proves the full pipeline works before the user commits budget to a full benchmark run.

```bash
# 1. Seed a 5-item sample dataset
make push-dataset METHOD=<name> N=5

# 2. (User: one-time UI step — extend the judge filter to include this dataset)

# 3. Run the experiment on the 5-item sample
make run-experiment METHOD=<name> FAIL_BELOW=0.0
```

What you're proving with the smoke test:
- Pipelex executes the bundle end-to-end on real LLM calls
- The method's `eval/configs/<name>.py::load_dataset_cases` produces correctly-shaped cases
- The bundle inputs align with what `build_bundle_inputs` produces
- Langfuse dataset + experiment + trace linkage works
- Deterministic scorers (exact_match + any benchmark scorer) produce sensible numbers
- The gate mechanism fires

If the smoke test passes, the full-dataset run will work the same way. If it fails, fix before handing over.

Then produce a **final handoff message** to the user summarising:

1. What was created: new files under `methods/<name>/` and `eval/configs/<name>.py` (+ any new scorer)
2. The benchmark chosen + HF path
3. `DATASET_NAME` and expected full item count
4. **Smoke test results**: `<exact_match>`, `<benchmark scorer>`, judge availability, Langfuse experiment URL
5. The command for the full-benchmark run when they're ready:

   ```bash
   # Seed the full dataset (one-time)
   make push-dataset-all METHOD=<name>

   # Run the full benchmark. Experiment name auto-derives from
   # methods/<name>/METHODS.toml as '<package_name>@<package_version>'.
   # The runner REJECTS re-runs at the same version —
   # bump [package].version in METHODS.toml to re-run.
   make run-experiment METHOD=<name> FAIL_BELOW=<threshold>
   ```

6. What score to expect if there's a public leaderboard for the benchmark

### Versioning the eval — critical note

Every experiment run is **pinned to the package's version** (name + version from `METHODS.toml`). This ties a scorecard to a specific release:

- Run at v0.1.0 → experiment name `answer_from_documents@0.1.0`
- Change a prompt, bundle, or scorer → **bump `[package].version` in METHODS.toml** → re-run → new experiment `answer_from_documents@0.1.1`
- Attempting to re-run at the same version fails: the runner refuses to overwrite (use `RESUME=1` to append after a crash, `FORCE=1` only in emergencies).

This produces a clean, comparable history in Langfuse — one row per version, stable semantics.

---

## Principles you must follow

- **Under-commit**: `mthds-std` prefers fewer, better primitives. If the user is on the fence, redirect to `pipelex/methods`.
- **Zero deps outside `native.*` + `mthds-std`** — this is a stability-contract requirement
- **Verbatim ports for official scorers** — numeric parity with the leaderboard is the contract
- **Don't run network calls that cost money** without explicit user sign-off
- **Don't invent benchmarks** — if you can't find a real public dataset, say so and stop
- **Don't add speculative abstractions** — add a scorer / helper only when the method actually needs it

---

## Quick reference — files you touch

```
NEW (shippable MTHDS package — these go to the Hub):
  methods/<name>/bundle.mthds           # Phase 2
  methods/<name>/METHODS.toml           # Phase 3
  methods/<name>/inputs.json            # Phase 4
  methods/<name>/README.md              # Phase 4 — prose/tables only, no JSON/YAML blocks

NEW (internal eval — stays in the repo, not published):
  eval/configs/<name>.py                # Phase 5, docstring carries benchmark provenance
  [optional] eval/scorers/<x>.py        # Phase 6

MODIFY:
  mthds-std/README.md                   # add row to Quality table (optional)

DO NOT:
  - Put eval.py, GROUND_TRUTH.md, live_run.*, or *.mmd inside methods/<name>/
  - Modify eval/runner.py, eval/seeder.py, eval/common.py (generic machinery)
  - Modify any other method's files
```

## When in doubt

- Reference implementation: `methods/answer_from_documents/` (package) + `eval/configs/answer_from_documents.py` (eval config). Read both first.
- For scorer layout: read `eval/scorers/mmlongbench_official.py` to see how an upstream eval protocol is attributed and ported.
