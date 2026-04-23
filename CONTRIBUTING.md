# Contributing to mthds-std

`mthds-std` is the standard library of the MTHDS ecosystem. Its job is to provide the small set of primitives that every MTHDS app can depend on, with a stability contract that makes that dependency safe.

Because downstream packages build on top of it, the bar for additions and changes is high — higher than for `pipelex/methods` (which is for vertical solutions) or application code.

## Before you propose a new primitive

Ask these questions. If any answer is "no" or "not sure," the primitive probably does not belong here.

### 1. The "3 apps" rule

**Can you name three distinct real applications that would use this primitive as-is, without wrapping it?**

The three applications must be in different domains. "Three customer support bots" does not pass. "A customer support bot, a legal research tool, and an internal knowledge base" does.

If you cannot name three, the primitive is probably a solution, not a base — and it belongs in `pipelex/methods` or your own package.

### 2. Stability

Once a primitive ships in `mthds-std`, its input/output contract is load-bearing. Are you prepared to keep that contract stable?

See `STABILITY.md` for what counts as a breaking change and what does not.

### 3. Zero external deps

Methods in `mthds-std` use only `native.*` concepts or concepts defined inside `mthds-std`. Does your primitive respect that?

If your primitive needs a concept from another package, it either belongs in that package, or the concept should be lifted into `mthds-std` — which is itself a v0.1 contract change.

### 4. Is it already covered?

Could your goal be achieved by:
- Composing existing `mthds-std` primitives?
- Passing a different prompt or question to an existing primitive (e.g., `answer_from_documents`)?

If yes, no new primitive is needed. Compose, don't accrete.

## How to propose a primitive

1. Open an issue titled `Proposal: <primitive_name>`.
2. Include:
   - One-line purpose
   - Input/output contract (concepts and multiplicity)
   - The 3-apps argument — three real applications named specifically
   - Why existing `mthds-std` primitives cannot compose to cover it
   - Suggested prompt or pipeline sketch
3. Wait for maintainer sign-off before implementing. The 3-apps rule is applied strictly, and primitives are deliberately under-included — most proposals will be redirected to `pipelex/methods` or a separate package.

## How to propose a change to an existing primitive

- **Prompt tweaks** (no shape change): open a PR with before/after examples showing the improvement. These are patch releases.
- **Adding an optional field or enum value**: open a PR. Minor release.
- **Anything that changes an existing shape, name, or meaning**: open an RFC issue first. Breaking changes require a deprecation window and a major release. Be prepared for a slow and deliberate review.

## Quality bar for implementation

Every method in `mthds-std` must:

- Pass `mthds-agent validate bundle`
- Pass `mthds-agent package validate`
- Have a complete `inputs.json` that the method can run against (mock URLs are fine for testing infrastructure; real small samples are better where feasible)
- Have a `README.md` that describes: what it does, inputs, outputs, model aliases used, known limits
- Use only `native.*` concepts or concepts defined inside `mthds-std`
- Respect MTHDS conventions: concepts singular, pipe codes snake_case, domain codes snake_case
- Be reviewed by at least one other maintainer before merge

## Style

- Be concise in prompts. Every instruction in a system prompt is load-bearing; every word you can cut is a word the model has more capacity for.
- Name precisely. `summarize` is better than `do_summary`; `answer_from_documents` is better than `grounded_qa`.
- Prefer verb-first method names: `extract_*`, `answer_*`, `classify_*`, `compare_*`.
- Keep descriptions under one paragraph. If more is needed, put it in the package README.
