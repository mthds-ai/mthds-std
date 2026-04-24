"""Library functions for eval: push datasets + run experiments.

Pure Python API. No argparse, no Typer, no prints except for progress.
The CLI layer (`eval/cli.py`) handles all user-facing concerns.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from langfuse import Langfuse
from langfuse.experiment import Evaluation, EvaluatorFunction
from langfuse.types import ExperimentScoreType
from mthds.package.manifest.parser import parse_methods_toml
from pipelex.pipelex import Pipelex
from pipelex.pipeline.runner import PipelexRunner

from eval.scorers import Scorer, ScoreResult

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EvalConfigError(RuntimeError):
    """Raised for any misconfiguration: missing env var, missing bundle, bad manifest."""


class ExperimentAlreadyExists(RuntimeError):
    """Raised when a run at the current version already exists and resume/force isn't set."""


# ---------------------------------------------------------------------------
# Reports (structured results returned to the caller)
# ---------------------------------------------------------------------------


@dataclass
class PushReport:
    dataset: str
    added: int
    skipped: int


@dataclass
class RunReport:
    method: str
    experiment: str
    dataset: str
    experiment_url: str
    per_scorer: dict[str, tuple[int, int]] = field(default_factory=dict)  # name -> (passes, attempted)
    errors: int = 0
    judge_summary: dict[str, tuple[float, int, int]] = field(default_factory=dict)  # name -> (mean, scored, expected)
    gate_metric: str = ""
    gate_value: float | None = None


# ---------------------------------------------------------------------------
# Environment + client setup
# ---------------------------------------------------------------------------


def read_env(name: str) -> str:
    """Read env var, stripping surrounding quotes Make's `include .env` leaves behind."""
    return (os.environ.get(name) or "").strip().strip('"').strip("'")


def build_langfuse_client() -> tuple[Langfuse, str]:
    public_key, secret_key = read_env("LANGFUSE_PUBLIC_KEY"), read_env("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        raise EvalConfigError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")
    base_url = (read_env("LANGFUSE_BASE_URL") or read_env("LANGFUSE_HOST") or "https://cloud.langfuse.com").rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise EvalConfigError(f"LANGFUSE_BASE_URL='{base_url}' is missing a scheme")
    return Langfuse(base_url=base_url, public_key=public_key, secret_key=secret_key), base_url


# ---------------------------------------------------------------------------
# Method loading
# ---------------------------------------------------------------------------


def load_method_config(method: str) -> tuple[ModuleType, Path]:
    """Import eval/configs/<method>.py and return (module, bundle_dir)."""
    bundle_dir = Path("methods") / method
    if not (bundle_dir / "bundle.mthds").exists():
        raise EvalConfigError(f"no bundle at {bundle_dir}/bundle.mthds")
    config_path = Path("eval") / "configs" / f"{method}.py"
    if not config_path.exists():
        raise EvalConfigError(f"{config_path} not found (see eval/configs/answer_from_documents.py for reference)")
    spec = importlib.util.spec_from_file_location(f"mthds_eval_{method}", config_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, bundle_dir.resolve()


def read_manifest(bundle_dir: Path):
    manifest_path = bundle_dir / "METHODS.toml"
    if not manifest_path.exists():
        raise EvalConfigError(f"{manifest_path} not found. Package the method first.")
    manifest = parse_methods_toml(manifest_path.read_text())
    if not manifest.name or not manifest.main_pipe:
        raise EvalConfigError(f"{manifest_path} must declare [package].name and [package].main_pipe")
    return manifest


# ---------------------------------------------------------------------------
# Pipelex task + scorer adapter
# ---------------------------------------------------------------------------


def make_task(main_pipe: str, bundle_text: str):
    """Build an async task for langfuse.run_experiment — runs the bundle via PipelexRunner.

    The dataset item's `input` field IS the pipe inputs payload; no transformation needed.
    Task is async because Langfuse's experiment runner iterates tasks inside an event loop.
    """
    runner = PipelexRunner()

    async def task(*, item: Any, **_kwargs: Any) -> dict[str, Any]:
        response = await runner.execute_pipeline(pipe_code=main_pipe, mthds_contents=[bundle_text], inputs=item.input)
        content = response.pipe_output.main_stuff.content
        if hasattr(content, "model_dump"):
            return cast(dict[str, Any], content.model_dump())
        return {"answer": str(content)}

    return task


def scorer_to_evaluator(scorer: Scorer) -> EvaluatorFunction:
    def _eval(
        *,
        input: Any = None,  # noqa: A002
        output: Any = None,
        expected_output: Any = None,
        metadata: Any = None,
        **_kwargs: Any,
    ) -> Evaluation:
        result: ScoreResult = scorer.score(
            output=output or {}, expected_output=expected_output or {}, input=input or {}, metadata=metadata or {}
        )
        return Evaluation(
            name=result.name,
            value=result.value,
            comment=result.comment,
            data_type=cast("ExperimentScoreType", result.data_type),
        )

    _eval.__name__ = f"evaluator_{scorer.name}"
    return cast("EvaluatorFunction", _eval)


# ---------------------------------------------------------------------------
# Judge polling
# ---------------------------------------------------------------------------


def _find_existing_runs(*, langfuse: Langfuse, run_name: str) -> list[tuple[str, int]]:
    """Return a list of (dataset_name, item_count) for every dataset in the project
    that already has a dataset_run with the given name.

    Project-wide uniqueness check — a method version is identified by its run_name,
    so the same name appearing on any dataset means the method was already evaluated.
    """
    matches: list[tuple[str, int]] = []
    try:
        resp = langfuse.api.datasets.list()
    except Exception:
        return matches
    for ds in getattr(resp, "data", []) or []:
        ds_name = getattr(ds, "name", None)
        if not ds_name:
            continue
        try:
            existing = langfuse.get_dataset_run(dataset_name=ds_name, run_name=run_name)
        except Exception:
            continue
        items = getattr(existing, "dataset_run_items", None) or []
        if items:
            matches.append((ds_name, len(items)))
    return matches


def wait_for_judge_scores(
    *,
    langfuse: Langfuse,
    dataset: str,
    run_name: str,
    judge: str,
    timeout_s: int,
    poll_interval_s: int = 6,
    on_progress: Any = None,
) -> tuple[list[float], int]:
    """Poll until all traces in the run have the judge score, or timeout."""
    try:
        run = langfuse.get_dataset_run(dataset_name=dataset, run_name=run_name)
    except Exception:
        return [], 0
    trace_ids = [it.trace_id for it in run.dataset_run_items if getattr(it, "trace_id", None)]
    if not trace_ids:
        return [], 0

    def _collect() -> list[float]:
        values: list[float] = []
        for trace_id in trace_ids:
            try:
                resp = langfuse.api.scores.get_many(trace_id=trace_id, name=judge, limit=10)
            except Exception:
                continue
            for score in resp.data or []:
                value = getattr(score, "value", None)
                if isinstance(value, (int, float)):
                    values.append(float(value))
        return values

    deadline, last = time.time() + timeout_s, -1
    vals: list[float] = []
    while time.time() < deadline:
        vals = _collect()
        if len(vals) != last and on_progress is not None:
            on_progress(len(vals), len(trace_ids))
            last = len(vals)
        if len(vals) >= len(trace_ids):
            break
        time.sleep(poll_interval_s)
    return vals, len(trace_ids)


# ---------------------------------------------------------------------------
# Public API: push_dataset
# ---------------------------------------------------------------------------


def push_dataset(
    *,
    method: str,
    n: int | None = None,
    all_: bool = False,
    dataset_override: str | None = None,
) -> PushReport:
    """Seed a Langfuse dataset from the method's configured source."""
    config, _ = load_method_config(method)
    dataset_name = dataset_override or config.DATASET_NAME
    description = getattr(config, "DATASET_DESCRIPTION", f"Eval dataset for {method}")

    kwargs: dict = {"all_": True} if all_ else ({"n": n} if n is not None else {})
    cases = config.load_dataset_cases(**kwargs)

    langfuse, _ = build_langfuse_client()
    langfuse.create_dataset(name=dataset_name, description=description)

    existing_keys: set[tuple[str, str]] = set()
    try:
        existing = langfuse.get_dataset(dataset_name)
        for item in existing.items:
            meta = item.metadata or {}
            inp = item.input if isinstance(item.input, dict) else {}
            existing_keys.add((str(meta.get("doc_id", "")), str(inp.get("question", ""))))
    except Exception:
        pass

    added = skipped = 0
    for case in cases:
        meta = case.get("metadata") or {}
        inp = case.get("input") or {}
        key = (str(meta.get("doc_id", "")), str(inp.get("question", "")))
        if key in existing_keys:
            skipped += 1
            continue
        langfuse.create_dataset_item(
            dataset_name=dataset_name,
            input=case["input"],
            expected_output=case.get("expected_output"),
            metadata=meta,
        )
        added += 1
    langfuse.flush()

    return PushReport(dataset=dataset_name, added=added, skipped=skipped)


# ---------------------------------------------------------------------------
# Public API: run_experiment
# ---------------------------------------------------------------------------


def run_experiment(
    *,
    method: str,
    experiment_override: str | None = None,
    dataset_override: str | None = None,
    gate_metric_override: str | None = None,
    concurrency: int = 1,
    judge_wait_seconds: int = 180,
    resume: bool = False,
    force: bool = False,
    on_judge_progress: Any = None,
) -> RunReport:
    """Run an experiment for one method. Returns a structured RunReport; does not gate or print."""
    config, bundle_dir = load_method_config(method)
    manifest = read_manifest(bundle_dir)
    assert manifest.main_pipe is not None  # validated in read_manifest

    dataset_name = dataset_override or config.DATASET_NAME
    scorers: list[Scorer] = list(config.SCORERS)
    judge_names: list[str] = list(getattr(config, "JUDGE_SCORE_NAMES", []))
    gate_name = gate_metric_override or getattr(
        config, "GATE_METRIC", judge_names[0] if judge_names else scorers[0].name
    )
    exp_name = experiment_override or f"{manifest.name}@{manifest.version}"

    langfuse, base_url = build_langfuse_client()
    ds = langfuse.get_dataset(dataset_name)

    # Version-uniqueness gate — project-wide, not just this dataset.
    # A method version identifies a specific state of the code; the same version must
    # not run twice anywhere in the project (on any dataset). Force a version bump for
    # any re-run, even across datasets.
    if not resume and not force:
        prior_datasets = _find_existing_runs(langfuse=langfuse, run_name=exp_name)
        # If the only prior run is on THIS dataset, that's the normal "already ran here" case.
        # If there's also a run on any OTHER dataset at this version, that's the cross-dataset case.
        if prior_datasets:
            other_datasets = [name for name, _ in prior_datasets if name != dataset_name]
            same_dataset = next(((n, c) for n, c in prior_datasets if n == dataset_name), None)
            parts: list[str] = []
            if same_dataset is not None:
                parts.append(f"already ran on '{same_dataset[0]}' ({same_dataset[1]} items)")
            if other_datasets:
                parts.append(f"already ran on: {', '.join(other_datasets)}")
            raise ExperimentAlreadyExists(
                f"{exp_name} " + "; ".join(parts) + ". "
                f"Any change that would produce a different score requires a version bump — "
                f"edit [package].version in methods/{method}/METHODS.toml. "
                f"Pass --resume to append items to the existing run, or --force to overwrite."
            )

    evaluators: list[EvaluatorFunction] = [scorer_to_evaluator(s) for s in scorers]
    bundle_text = (bundle_dir / "bundle.mthds").read_text()

    # Pipelex.make() initializes the runtime singleton (config, hubs, telemetry).
    # Required before any PipelexRunner call.
    with Pipelex.make():
        result = langfuse.run_experiment(
            name=exp_name,
            run_name=exp_name,
            description=f"Run of {method} on {dataset_name}",
            data=ds.items,
            task=make_task(manifest.main_pipe, bundle_text),
            evaluators=evaluators,
            max_concurrency=concurrency,
            metadata={"method": method, "experiment_name": exp_name},
        )
    langfuse.flush()

    # Aggregate deterministic scores
    scorer_names = [s.name for s in scorers]
    per_scorer: dict[str, tuple[int, int]] = {name: (0, 0) for name in scorer_names}
    errors = 0
    for item_result in result.item_results:
        output = item_result.output or {}
        if isinstance(output, dict) and output.get("status") in {"run_error", "parse_error"}:
            errors += 1
            continue
        for name in scorer_names:
            ev = next((e for e in (item_result.evaluations or []) if e.name == name), None)
            passes, attempted = per_scorer[name]
            attempted += 1
            if ev is not None and isinstance(ev.value, (int, float)) and cast(float, ev.value) >= 1.0:
                passes += 1
            per_scorer[name] = (passes, attempted)

    # Async judges
    judge_summary: dict[str, tuple[float, int, int]] = {}
    for judge_name in judge_names:
        values, expected_count = wait_for_judge_scores(
            langfuse=langfuse,
            dataset=dataset_name,
            run_name=exp_name,
            judge=judge_name,
            timeout_s=judge_wait_seconds,
            on_progress=on_judge_progress,
        )
        mean_val = sum(values) / len(values) if values else 0.0
        judge_summary[judge_name] = (mean_val, len(values), expected_count)

    # Resolve gate
    gate_value: float | None = None
    if gate_name in per_scorer:
        passes, attempted = per_scorer[gate_name]
        gate_value = (passes / attempted) if attempted else 0.0
    elif gate_name in judge_summary:
        mean_val, scored, _ = judge_summary[gate_name]
        gate_value = mean_val if scored else None

    return RunReport(
        method=method,
        experiment=exp_name,
        dataset=dataset_name,
        experiment_url=f"{base_url}/datasets/{dataset_name}/experiments/{exp_name}",
        per_scorer=per_scorer,
        errors=errors,
        judge_summary=judge_summary,
        gate_metric=gate_name,
        gate_value=gate_value,
    )
