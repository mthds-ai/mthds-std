# mthds-std

**The standard library of MTHDS.**

Generic, reusable primitives that every MTHDS app can depend on — with a stability contract.

This is to MTHDS what `numpy` is to Python: first-party, curated, and effectively part of the platform, distributed through the same package system as everything else.

## Install

```bash
mthds install mthds-std
```

Or, with Pipelex:

```bash
pip install 'pipelex[std]'
```

Packages follow the [MTHDS package layout](https://mthds.ai/packages/structure/).

## What's in v0.1.0

One primitive, shipped deliberately:

| Method | Purpose |
|---|---|
| [`answer_from_documents`](methods/answer_from_documents/) | Grounded document question answering with verbatim citations and principled abstention |

See [`DESIGN.md`](DESIGN.md) for why v0.1.0 ships with a single primitive and what is deferred.

## Philosophy

Every primitive in `mthds-std`:

- **Is generic.** Useful across multiple unrelated domains. No vertical-specific logic.
- **Has zero external deps.** Uses only `native.*` concepts or concepts defined inside `mthds-std`.
- **Has a stability promise.** Breaking changes require a major version bump and a 3-month deprecation window. See [`STABILITY.md`](STABILITY.md).
- **Passes the "3 apps" rule.** A new primitive is accepted only if three distinct real applications would use it as-is. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

The ecosystem it sits in:

| Repo | Role |
|---|---|
| **`mthds-std`** (this repo) | Standard library — generic primitives, stability contract |
| `pipelex/methods` | Vertical solutions — CV analysis, RFP qualification, due diligence |
| `pipelex-cookbook` | Tutorials and worked examples |
| `awesome-mthds` | Curated community list |

## Quality

Every method in `mthds-std` is evaluated against a real benchmark with real ground truth.

| Method | Benchmark | Dataset | Latest score | Gate |
|---|---|---|---|---|
| [`answer_from_documents`](methods/answer_from_documents/) | [MMLongBench-Doc](https://github.com/mayubo2333/MMLongBench-Doc) (NeurIPS 2024) | `mmlongbench-sample-v1` (5 items, growing) | — *run CI once to populate* | exact_match ≥ 80% |

- **CI-gated**: every PR runs the eval; PRs below threshold are blocked. See [`.github/workflows/eval.yml`](.github/workflows/eval.yml).
- **Public scorecard**: experiment runs are visible in Langfuse with per-item drill-down, token cost, and LLM-as-judge semantic scoring.
- **Reproducible**: see [`eval/README.md`](eval/README.md) to run the eval locally against your own Langfuse project.

## License

MIT. See [`LICENSE`](LICENSE).
