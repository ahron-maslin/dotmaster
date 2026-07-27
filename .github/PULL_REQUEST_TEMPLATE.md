## What

## Why

## Checklist

- [ ] `ruff check . && ruff format --check . && mypy dotmaster` pass
- [ ] `pytest` passes
- [ ] If this changes or adds a plugin: added a case to `tests/test_artifact_validity.py`'s `STACKS` matrix so its output is parsed, not just substring-matched
- [ ] If this changes generated output: confirmed with `dotmaster diff` on a real project that the diff is what you'd expect
