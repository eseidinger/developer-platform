# Developer Platform API

The Developer Platform API and hosted-application access gateway are a uv-managed
Python project. Source is under `src/app`; unit and integration tests are under
`tests`.

```bash
uv sync
uv run python -m unittest discover -s tests -v
```
