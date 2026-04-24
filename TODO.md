# TODO

## Scale eval execution via Temporal (pipelex-api)

Running the pipe locally on every dataset item doesn't scale: rate limits are
the hard wall, not CPU or wall time. The framework already abstracts the task
function, so moving it behind `pipelex-api` (Temporal-backed, server-side
rate-limited, horizontally scalable) is the natural next step.

The philosophy:

- **Local** stays responsible for what's cheap and stateful: dataset selection,
  experiment identity (name@version), scoring, gating, reporting.
- **Pipelex-api** becomes responsible for what's expensive and stateless:
  executing the pipe on each item with proper rate-limit + retry behaviour.
- The eval framework becomes a **coordinator**, not an executor. It submits
  work, waits (or returns a handle), reconciles results, posts scores, gates.
- No new eval features until this is in. Every feature designed around the
  current in-process `PipelexRunner` will become legacy the moment we move.

## Public benchmark scorecard (Hugging Face Space)

Langfuse can't publish datasets or experiment runs as public URLs — only
individual traces. That's a problem for open-benchmark visibility: we want
anyone on the internet to see `mthds-std`'s scores against MMLongBench-Doc
etc. without handing them Langfuse access.

The philosophy:

- Results belong to the **public**, not to a project dashboard.
- Scorecards must be **durable and citable** — a URL that works next year,
  not a trace that could be deleted.
- The eval infrastructure stays internal (Langfuse + pipelex-api); the
  **publication layer** is separate.

Shape: a Hugging Face Space with a lightweight UI that pulls from the
Langfuse API using server-side credentials, rendering a leaderboard per
method: columns for version, benchmark, headline metric, date. Per-item
drill-downs link to public Langfuse traces where available. Source of truth
for numbers stays in Langfuse; the Space is a read-only window.

