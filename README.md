# mthds-std

**The standard library of methods for [MTHDS](https://mthds.ai).**

Generic, reusable AI method primitives anyone writing MTHDS pipelines can depend on. First-party, curated, evaluated against real benchmarks.

## Install a method

Any method in this library is installable by its address:

```bash
npx mthds install github.com/pipelex/mthds-std#<method-name>
```

## Methods

| Method | What it does |
|---|---|
| [`answer_from_documents`](methods/answer_from_documents/) | Given any set of documents and any question, returns a grounded answer with verbatim citations and principled abstention. |
| [`summarize`](methods/summarize/) | Produces a faithful, length-controlled summary, routing to a strategy that fits the kind of input (short text, research paper, general prose, long document). |

Each method's directory has its own README with inputs, outputs, design rationale, and limits.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the 3-apps rule, the quality bar for adding primitives, and the local development workflow.

## License

MIT. See [LICENSE](LICENSE).
