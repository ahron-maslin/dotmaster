# Contributing to dotmaster

Thanks for considering it. This project is small enough that most
contributions are genuinely easy to land — read on for the fastest path.

## Setup

```bash
git clone https://github.com/ahron-maslin/dotmaster
cd dotmaster
pip install -e ".[dev]"
pytest
```

## The easiest contribution: a new plugin

Every generator in dotmaster is a self-contained plugin (~30–80 lines) — this
is the best-leveraged way to contribute. See
[`docs/plugin-authoring.md`](docs/plugin-authoring.md) for the full guide;
the short version:

1. Subclass `dotmaster.plugins.api.Plugin` in `dotmaster/plugins/builtin/<name>.py`.
2. Implement `matches(config)` and `plan(config, ctx)` — `plan()` must be
   pure (render content, return `FileAction`s, never touch the filesystem).
3. Register it in `dotmaster/plugins/builtin/__init__.py`.
4. Add tests in `tests/test_plugins.py` and add your plugin's active-config
   case to `tests/test_artifact_validity.py`'s `STACKS` matrix — every file a
   plugin generates must round-trip through a real parser (`yaml.safe_load`,
   `json.loads`, `tomlkit.parse`), not just a substring check. This one rule
   would have caught every template bug in dotmaster's early history.

## Before you open a PR

```bash
ruff check .
ruff format --check .
mypy dotmaster
pytest --cov=dotmaster --cov-fail-under=75
```

All four run in CI; failing any of them blocks merge.

## Guidelines

- **No comments explaining *what* code does** — name things so it's obvious.
  A comment earns its place only by explaining a non-obvious *why*.
- **`plan()` must never write to disk.** The engine (`dotmaster/core/`) is the
  only layer that touches the filesystem — that split is what makes
  `--dry-run`, `diff`, and rollback possible. A plugin that writes directly
  will fail `tests/test_plugin_contract.py`.
- **Generate structured formats from data, not string templates.** For JSON
  output, build a `dict` and call `self.json_file(...)` — don't hand-assemble
  JSON inside a Jinja template. This is how invalid JSON shipped before.
- **User edits always win.** If you're choosing a merge strategy for a new
  output file, default to `MergeStrategy.MERGE` (structured formats) or
  `MANAGED_BLOCK` (ignore-file-style content) over `OVERWRITE`, unless the
  file genuinely can't be partially merged (e.g. a Dockerfile).

## Reporting bugs

Use the issue templates — they ask for `dotmaster --version`, your
`dotmaster.yaml`, and the command you ran, which is normally enough to
reproduce a generation bug immediately.

## Security issues

Do not open a public issue — see [SECURITY.md](SECURITY.md).
