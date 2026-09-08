Run lightweight tests with:

```bash
uv pip install --python .venv/bin/python pytest
.venv/bin/python -m pytest -q
```

These tests do not download models or perform a full video render.
