# EDU disagreement dashboard

Compare two EDU segmentations of the same text, treating annotations A and B equally, with a deterministic Python core and a local Streamlit interface.

## Start here

```sh
uv sync
uv run pytest
uv run streamlit run app/streamlit_app.py
```

Use Python 3.10 or newer and [uv](https://docs.astral.sh/uv/). The comparison core uses only the standard library; the interface uses Streamlit.

In the sidebar, start with one `.txt` or `.edus` annotation per side, or load a saved session JSON. Assess disagreements with five verdicts and optional notes; exported sessions embed both sources so they can be reopened without the original files.

- [User guide](docs/user-guide.md)
- [Research and development roadmap](docs/roadmap.md)
- [Comparison contract and Python examples](docs/first_slice.md)
- [Project context and longer-term MVP](docs/EDU_disagreement_dashboard_handoff.md)
- [Agent working instructions](AGENTS.md)

Keep this README a short starting point; implementation details belong in docs and evolving development guidance belongs in `AGENTS.md`.
