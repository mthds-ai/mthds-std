"""Eval configuration for `answer_from_documents`.

Benchmark: MMLongBench-Doc (NeurIPS 2024 Datasets & Benchmarks Track)
  - Paper:       https://arxiv.org/abs/2407.01523
  - Code/data:   https://github.com/mayubo2333/MMLongBench-Doc
  - Hugging Face: https://huggingface.co/datasets/yubo2333/MMLongBench-Doc
  - Content:     135 long PDFs (avg 47.5 pages), 1091 expert-annotated QA pairs
  - Leaderboard: https://huggingface.co/spaces/OpenIXCLab/mmlongbench-doc
                 (best published: ~61.9% at time of writing)

Every evaluated method supplies this module with a fixed interface:

  DATASET_NAME           str       Langfuse dataset to push/read
  DATASET_DESCRIPTION    str       Shown in the Langfuse UI
  JUDGE_SCORE_NAMES      list[str] Langfuse-UI evaluators we poll for (async)
  GATE_METRIC            str       Name of the score used by --fail-below
  SCORERS                list      Deterministic scorers (run sync during experiment)

  def load_dataset_cases(*, n, all_) -> list[case]

Each case is `{"input": <pipe-inputs-payload>, "expected_output": {...}, "metadata": {...}}`.
The `input` is handed directly to `execute_pipeline(inputs=...)` at run time —
no transformation layer.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from eval.scorers import ExactMatchScorer, MMLongBenchOfficialScorer

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

DATASET_NAME = "mmlongbench-sample-v1"
DATASET_DESCRIPTION = "MMLongBench-Doc sample for answer_from_documents."

# Langfuse-UI evaluators we poll for after the experiment finishes
JUDGE_SCORE_NAMES = ["Answer Correctness"]

# Name of the metric used by `--fail-below` (must match a scorer or judge name)
GATE_METRIC = "mmlongbench_acc"

# Deterministic scorers, run synchronously against every item
SCORERS = [
    ExactMatchScorer(),
    MMLongBenchOfficialScorer(),
]

# ---------------------------------------------------------------------------
# Dataset source: MMLongBench-Doc (Hugging Face parquet)
# ---------------------------------------------------------------------------

_MMLB_PARQUET_URL = (
    "https://huggingface.co/datasets/yubo2333/MMLongBench-Doc/resolve/main/data/train-00000-of-00001.parquet"
)
_MMLB_PDF_BASE = "https://huggingface.co/datasets/yubo2333/MMLongBench-Doc/resolve/main/documents/"


def _ensure_parquet_cached() -> Path:
    cache = Path.home() / ".cache" / "mthds-std-eval" / "mmlongbench.parquet"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        print(f"Fetching MMLongBench-Doc parquet → {cache}")
        urlretrieve(_MMLB_PARQUET_URL, cache)  # noqa: S310
    return cache


def _load_all_rows() -> list[dict[str, Any]]:
    """Load the full MMLongBench-Doc parquet as a list of dict rows."""
    import pandas as pd  # local import so `pandas` is only needed for the loader

    df = pd.read_parquet(_ensure_parquet_cached())
    df["pages"] = df["evidence_pages"].apply(ast.literal_eval)
    raw: list[Any] = df.to_dict("records")
    return [{str(k): v for k, v in row.items()} for row in raw]


def _row_to_case(row: dict[str, Any]) -> dict[str, Any]:
    """One row of the benchmark → one Langfuse dataset item.

    `input` is the **pipe inputs payload directly** — `execute_pipeline(inputs=item.input)`
    works with zero transformation at run time.
    """
    return {
        "input": {
            "documents": {
                "concept": "native.Document",
                "content": [{"url": _MMLB_PDF_BASE + row["doc_id"]}],
            },
            "question": {"concept": "native.Text", "content": {"text": row["question"]}},
            "context": {"concept": "native.Text", "content": {"text": ""}},
            "answer_format": {"concept": "native.Text", "content": {"text": row["answer_format"]}},
        },
        "expected_output": {"answer": _normalize_expected(row["answer"])},
        "metadata": {
            "benchmark": "MMLongBench-Doc",
            "doc_id": row["doc_id"],
            "answer_format": row["answer_format"],  # read by MMLongBenchOfficialScorer
            "evidence_pages": list(row["pages"]),
        },
    }


def _normalize_expected(value: Any) -> str:
    import json as _json

    if isinstance(value, list):
        return _json.dumps(list(value))
    return str(value)


def load_dataset_cases(*, n: int | None = None, all_: bool = False) -> list[dict[str, Any]]:
    """Return cases ready for `seeder.push_dataset`.

    - `all_`=True: every answerable + unanswerable row in MMLongBench-Doc (~1091).
    - `n`=N: a stratified sample of N rows across answer_format types, preferring
      cross-page answerable cases for fidelity.
    - default: 5 (one per answer_format: Int, Str, Float, List, None).
    """
    rows = _load_all_rows()

    if all_:
        return [_row_to_case(row) for row in rows]

    sample_n = n or 5

    # Minimum viable diversity: at least one of each answer_format
    picks: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    def _take(fmt: str, pred=None, limit: int = 1) -> None:
        count = 0
        for row in rows:
            if row["answer_format"] != fmt:
                continue
            if pred is not None and not pred(row):
                continue
            if row["doc_id"] + row["question"] in used_ids:
                continue
            picks.append(_row_to_case(row))
            used_ids.add(row["doc_id"] + row["question"])
            count += 1
            if count >= limit:
                return

    _take("Int", lambda r: len(r["pages"]) >= 3 and str(r["answer"]).lower() != "not answerable")
    _take("Str", lambda r: len(r["pages"]) >= 2 and str(r["answer"]).lower() != "not answerable")
    _take("Float", lambda r: len(r["pages"]) >= 2 and str(r["answer"]).lower() != "not answerable")
    _take("List", lambda r: len(r["pages"]) >= 2)
    _take("None")  # unanswerable

    # Top up to sample_n with diverse extras
    if len(picks) < sample_n:
        for row in rows:
            if row["doc_id"] + row["question"] in used_ids:
                continue
            picks.append(_row_to_case(row))
            used_ids.add(row["doc_id"] + row["question"])
            if len(picks) >= sample_n:
                break

    return picks[:sample_n]
