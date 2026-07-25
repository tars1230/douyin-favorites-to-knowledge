# Contributing

Preserve the transaction boundaries: scan does not mutate knowledge state, review requires explicit approval, and promote remains idempotent and fail-closed.

Before a pull request:

```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Use synthetic fixtures and mocked browser responses only. A PR must include expected exit codes for new failure cases and must not add credentials, personal paths, real favorite exports, browser state, or notification targets.
