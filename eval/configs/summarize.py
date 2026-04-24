"""Eval configuration for `summarize`.

Benchmark: XSum (Extreme Summarization, Narayan et al. EMNLP 2018)
  - Paper:      https://aclanthology.org/D18-1206/
  - HF:         https://huggingface.co/datasets/EdinburghNLP/xsum
  - Content:    204k BBC News articles, each with a 1-sentence professional summary.
                Targets abstractive extreme summarization — makes hallucination surface sharply.
  - Leaderboard context: a widely-cited benchmark; published ROUGE-L baselines span
                roughly 0.20–0.40 depending on model and epoch. Research (Yan) reports
                ~92% faithfulness-error rate on XSum across the field — XSum is a
                hallucination stress test more than a quality ceiling.

We use XSum as a v0.1 anchor because extreme 1-sentence summaries reveal the failure
mode that matters most (hallucination in dense compression). Adequate performance on
XSum implies the method can handle most "summarize this short article" use cases.

Deferred to v0.2+: MeetingBank (conversation shape), SciTLDR (research abstracts),
GovReport (long-document summarization).

Every evaluated method supplies this module with a fixed interface:

  DATASET_NAME           str       Langfuse dataset to push/read
  DATASET_DESCRIPTION    str       Shown in the Langfuse UI
  JUDGE_SCORE_NAMES      list[str] Langfuse-UI evaluators we poll for (async)
  GATE_METRIC            str       Name of the score used by --fail-below
  SCORERS                list      Deterministic scorers (run sync during experiment)

  def load_dataset_cases(*, n, all_) -> list[case]
"""

from __future__ import annotations

from typing import Any, cast

from eval.scorers import EntityPreservationScorer, LengthHitScorer

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

DATASET_NAME = "xsum-sample-v1"
DATASET_DESCRIPTION = "XSum extreme-summarization sample for the summarize primitive."

# Langfuse-UI LLM-judge evaluators to poll for after the experiment.
# For summarize, we want a faithfulness judge; extend the existing project-wide
# judge's dataset filter to include DATASET_NAME so this works.
JUDGE_SCORE_NAMES = ["Summary Faithfulness"]

# Primary gate metric. For a noisy-but-signal scorer, entity_preservation_rate is
# the best deterministic anchor. If Summary Faithfulness is configured and scoring,
# switch GATE_METRIC to it for stricter gating.
GATE_METRIC = "entity_preservation_rate"

# Deterministic scorers run synchronously on every item.
SCORERS = [
    LengthHitScorer(tolerance=0.5),  # XSum summaries are single-sentence, ~20-30 words;
    # our 'short' target of 50 is generous. Tolerance wide.
    EntityPreservationScorer(),
]

# ---------------------------------------------------------------------------
# Dataset loading via HF datasets library
# ---------------------------------------------------------------------------

_HF_DATASET_PATH = "EdinburghNLP/xsum"


def _row_to_case(row: dict[str, Any]) -> dict[str, Any]:
    """One XSum row → one Langfuse dataset item.

    `input` is the pipe inputs payload directly — handed to `execute_pipeline(inputs=...)`
    at run time with zero transformation.
    """
    article = str(row.get("document", ""))
    reference = str(row.get("summary", ""))
    doc_id = str(row.get("id", ""))
    return {
        "input": {
            "text": {"concept": "native.Text", "content": {"text": article}},
            "length": {"concept": "native.Text", "content": {"text": "short"}},
            "format": {"concept": "native.Text", "content": {"text": "prose"}},
            "audience": {"concept": "native.Text", "content": {"text": ""}},
        },
        "expected_output": {"summary": reference},
        "metadata": {
            "benchmark": "XSum",
            "doc_id": doc_id,
            "length": "short",
            "source_text": article,  # read by EntityPreservationScorer fallback path
        },
    }


def load_dataset_cases(*, n: int | None = None, all_: bool = False) -> list[dict[str, Any]]:
    """Return cases ready for the Langfuse seeder.

    - `all_=True`  → every row of the XSum test split (~11,334 items).
    - `n=N`        → N rows taken from the start of the test split (deterministic sample).
    - default      → 10-row smoke-test sample.
    """
    from datasets import load_dataset

    split_size = n or (None if all_ else 10)
    split_spec = "test" if all_ or split_size is None else f"test[:{split_size}]"

    ds = load_dataset(_HF_DATASET_PATH, split=split_spec)
    cases: list[dict[str, Any]] = []
    for row in ds:
        cases.append(_row_to_case(cast(dict[str, Any], row)))
        if not all_ and split_size is not None and len(cases) >= split_size:
            break
    return cases
