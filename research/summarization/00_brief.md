# Research brief: why LLM summarization fails, and how to do it well

## The question

If we build `summarize` as a primitive in `mthds-std`, what does the published research (2023–2026) say about:

1. **Why current LLM summarization is bad** — concrete failure modes, not vibes
2. **What specific techniques actually work** — not "prompt it better" but named methods
3. **How to evaluate it meaningfully** — because bad evals hide bad summaries
4. **What we should NOT promise** — the limits of the state of the art

## Scope

- Academic papers (arXiv, TACL, ACL, EMNLP) — the research record
- Industry engineering writeups — what ships vs. what's published
- HN / practitioner threads — the unglamorous truth
- Benchmark papers — so we know what "good" is measured against

## Working method

- Fetch sources, digest each into notes with page references where available
- Flag specific techniques that are named and actionable
- End with a synthesized design for our primitive that takes the research into account
- Be honest about what we're NOT solving

## Files in this folder

- `00_brief.md` — this file
- `10_papers.md` — digested notes from academic papers
- `20_industry.md` — industry writeups + practitioner lessons
- `30_techniques.md` — specific named techniques that improve summarization
- `40_synthesis.md` — how research informs our `summarize` primitive design
