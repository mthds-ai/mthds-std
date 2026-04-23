# Evaluation

This directory contains the eval harness for `mthds-std` methods, wired to [Langfuse](https://langfuse.com).

## What it does

1. Seeds a Langfuse **Dataset** with benchmark cases (defaults to MMLongBench-Doc)
2. Runs an **Experiment** by executing a bundle against each dataset item
3. Posts deterministic scores (`exact_match`, `answer_status`, `run_status`)
4. Lets you configure **LLM-as-judge** evaluators in the Langfuse UI to score semantic equivalence automatically

## One-time setup

### 1. Install Python deps

```bash
make install    # creates .venv via uv, installs eval + dev extras from pyproject.toml
```

### 2. Wire Langfuse into Pipelex

Add to `~/.pipelex/telemetry.toml`:

```toml
[langfuse]
enabled    = true
public_key = "${LANGFUSE_PUBLIC_KEY}"
secret_key = "${LANGFUSE_SECRET_KEY}"
endpoint   = "https://cloud.langfuse.com"
```

Set env vars (either export or a `.env`):

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com
```

Every Pipelex run will now auto-trace to Langfuse.

### 3. Seed the dataset (once per benchmark version)

```bash
make push-dataset                              # defaults: DATASET=mmlongbench-sample-v1, N=5
make push-dataset DATASET=my-ds N=20           # override defaults
```

This samples 5 diverse cases from MMLongBench-Doc (Int, Str, Float, List, None-answerable) and creates them as Langfuse dataset items. Idempotent — re-runs skip existing items.

### 4. Configure the LLM-as-judge evaluator in Langfuse UI

One-time UI setup:

1. Go to Langfuse UI → **Evaluators** → New
2. Judge model: Claude or GPT-5 class (must support structured output)
3. Prompt (template):
   ```
   Compare the model's answer to the expected answer.
   Ignore formatting differences: quote style, case, trailing whitespace.

   Question: {{input.question}}
   Expected: {{expected_output.answer}}
   Got: {{output.answer}}

   Return 1.0 if semantically equivalent, 0.0 otherwise.
   Provide a one-line reason.
   ```
4. Variable mapping:
   - `input` → dataset item input
   - `output` → trace output
   - `expected_output` → dataset item expected_output
5. Scope: **Experiments** only (keeps production traces free)
6. Filter: dataset = `mmlongbench-sample-v1`

After this is active, every experiment run is scored by the judge automatically — no code changes.

## Running an experiment

```bash
make run-experiment EXPERIMENT=v0.1.0-baseline
# or override anything:
make run-experiment \
  BUNDLE=methods/answer_from_documents \
  DATASET=mmlongbench-sample-v1 \
  EXPERIMENT=v0.1.0-baseline \
  FAIL_BELOW=0.80

# Seed + run in one shot:
make eval EXPERIMENT=v0.1.0-baseline
```

Output:

```
Experiment 'v0.1.0-baseline' on dataset 'mmlongbench-sample-v1' (5 items)
Bundle: /…/methods/answer_from_documents

[1/5] fdac8d1e9ef56519371df7e6532df27d.pdf
    ✅ got='19'
[2/5] PH_2016.06.08_Economy-Final.pdf
    ✅ got='8'
…

============================================================
  exact_match: 4/5 = 80.0%
  runs errored (excluded from score): 0
  experiment URL: Langfuse UI → Datasets → mmlongbench-sample-v1 → Runs → v0.1.0-baseline
============================================================
```

Exit code is non-zero if `--fail-below` is set and the score is below the threshold — CI gate.

## What's in Langfuse after a run

- **Dataset view** shows all items with their `expected_output`
- **Experiment view** shows the run, per-item scores, aggregate
- **Trace view** shows the full Pipelex pipeline execution per item — every pipe, every LLM call, prompts, completions, tokens, latency
- **Comparison view** diffs runs side-by-side — `v0.1.0-baseline` vs `v0.1.1-prompt-tweak`

## Adding a new benchmark

1. Create a `cases.json` in the shape `push_dataset.py` expects (see `--cases-json` flag)
2. Run `push_dataset.py --name <new-name> --cases-json <path>`
3. Configure a judge evaluator scoped to that dataset
4. Run `run_experiment.py --dataset <new-name>`

## Adding to CI

See `.github/workflows/eval.yml` (at the repo root) for the PR gate that runs the experiment automatically and blocks merges below the threshold.
