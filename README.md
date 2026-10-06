# EDU disagreement dashboard

Compare two EDU segmentations of the same text, treating annotations A and B equally. The first slice is a deterministic Python comparison core.

## Start here

```sh
uv sync
uv run pytest
```

Use Python 3.10 or newer and [uv](https://docs.astral.sh/uv/). The core has no runtime dependencies.

- [Comparison contract and Python examples](docs/first_slice.md)
- [Project context and longer-term MVP](docs/EDU_disagreement_dashboard_handoff.md)
- [Agent working instructions](AGENTS.md)

Keep this README a short starting point; implementation details belong in docs and evolving development guidance belongs in `AGENTS.md`.
