"""Typer CLI for the eval framework. Parses args, calls `eval.core` functions, prints."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.core import (  # noqa: E402
    EvalConfigError,
    ExperimentAlreadyExists,
    PushReport,
    RunReport,
    push_dataset,
    run_experiment,
)

app = typer.Typer(add_completion=False, help=__doc__)


@app.command()
def push(
    method: str = typer.Option(..., help="Method name under methods/"),
    n: int | None = typer.Option(None, help="Number of cases (default: method's default)"),
    all_: bool = typer.Option(False, "--all", help="Push every available case"),
    dataset: str | None = typer.Option(None, "--dataset", help="Override dataset name"),
) -> None:
    """Seed a Langfuse dataset."""
    try:
        report: PushReport = push_dataset(method=method, n=n, all_=all_, dataset_override=dataset)
    except EvalConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"dataset='{report.dataset}'  added={report.added}  skipped={report.skipped}")


@app.command()
def run(
    method: str = typer.Option(..., help="Method name under methods/"),
    experiment: str | None = typer.Option(None, help="Override experiment name"),
    dataset: str | None = typer.Option(None, help="Override dataset name"),
    fail_below: float = typer.Option(0.0, help="Fail if gate metric is below this. 0 disables."),
    gate_metric: str | None = typer.Option(None, help="Override gate metric name"),
    concurrency: int = typer.Option(1, help="Parallel task runs"),
    judge_wait_seconds: int = typer.Option(180, help="Max seconds to wait for async judge scores"),
    resume: bool = typer.Option(False, help="Append to an existing run (e.g. resume after crash)"),
    force: bool = typer.Option(False, help="Overwrite a completed run at this version"),
) -> None:
    """Run an experiment for one method, print a report, gate on the configured metric."""
    try:
        report: RunReport = run_experiment(
            method=method,
            experiment_override=experiment,
            dataset_override=dataset,
            gate_metric_override=gate_metric,
            concurrency=concurrency,
            judge_wait_seconds=judge_wait_seconds,
            resume=resume,
            force=force,
            on_judge_progress=_print_judge_progress,
        )
    except EvalConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except ExperimentAlreadyExists as exc:
        typer.echo(f"\n❌ {exc}", err=True)
        raise typer.Exit(code=2) from exc

    _print_report(report)
    _apply_gate(report, fail_below)


# ---------------------------------------------------------------------------
# Pretty-printing (CLI concern, not library)
# ---------------------------------------------------------------------------


def _print_judge_progress(scored: int, expected: int) -> None:
    typer.echo(f"  {scored}/{expected} judge scores ready...")


def _print_report(report: RunReport) -> None:
    typer.echo("\n" + "=" * 78)
    typer.echo(f"  method              : {report.method}")
    typer.echo(f"  experiment          : {report.experiment}")
    typer.echo(f"  dataset             : {report.dataset}")
    for name, (passes, attempted) in report.per_scorer.items():
        rate = (passes / attempted) if attempted else 0.0
        typer.echo(f"  {name:20}: {passes}/{attempted} = {rate:.1%}")
    for name, (mean_val, scored, expected_count) in report.judge_summary.items():
        if scored:
            typer.echo(f"  {name:20}: mean={mean_val:.2f}  over {scored}/{expected_count} items")
        else:
            typer.echo(f"  {name:20}: (not available — judge may still be running)")
    typer.echo(f"  runs errored        : {report.errors}")
    typer.echo(f"  experiment URL      : {report.experiment_url}")
    typer.echo("=" * 78)


def _apply_gate(report: RunReport, fail_below: float) -> None:
    if report.gate_value is None:
        typer.echo(f"\n⚠️  gate metric '{report.gate_metric}' not found — skipping gate", err=True)
        return
    if fail_below and report.gate_value < fail_below:
        typer.echo(
            f"\n❌ {report.gate_metric}={report.gate_value:.1%} below threshold {fail_below:.1%}",
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo(f"\n✅ {report.gate_metric}={report.gate_value:.1%} (threshold {fail_below:.1%})")


if __name__ == "__main__":
    app()
