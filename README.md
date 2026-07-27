# dotmaster

[![CI](https://github.com/ahron-maslin/dotmaster/actions/workflows/ci.yml/badge.svg)](https://github.com/ahron-maslin/dotmaster/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dotmaster)](https://pypi.org/project/dotmaster/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> **Declarative project configuration, kept in sync.**
>
> Answer a few questions once, get `.gitignore`, linting, formatting,
> Docker, CI, and more — all generated together, recorded in one
> `dotmaster.yaml`, and continuously verifiable with `dotmaster check`.

Status: **beta.** The output-correctness and safety issues from earlier 0.2.x
releases are fixed and covered by tests (see [CHANGELOG](CHANGELOG.md)), but
the plugin API and config schema may still change before 1.0.

---

## Why dotmaster and not a scaffolder

Cookiecutter, Copier, and `create-*` tools generate a *new project*.
dotmaster generates and **maintains the configuration layer** of a project
that may already exist — and, unlike a one-shot generator, it remembers what
it wrote:

```bash
dotmaster init      # answer questions once → dotmaster.yaml + generated files
dotmaster check     # in CI: fail the build if the repo has drifted from dotmaster.yaml
dotmaster sync      # bring the repo back in line
dotmaster diff      # see what sync would change, before it changes anything
```

Edit `dotmaster.yaml` by hand, or an org-wide preset changes — either way,
`sync` converges the repo, your own edits to generated files are preserved
where they can be merged, and files you've genuinely modified are reported as
conflicts rather than silently overwritten.

---

## Installation

```bash
pipx install dotmaster
# or: uvx dotmaster init
```

## Quick start

```bash
cd my-project
dotmaster init
```

Non-interactive (CI, scripts, agents):

```bash
dotmaster init --preset backend_api --yes
dotmaster init --yes --set stack.languages=python,typescript --set infrastructure.docker=true
```

---

## Commands

| Command | Description |
|---|---|
| `dotmaster init` | Run the wizard (or `--yes`/`--set`) and generate dotfiles |
| `dotmaster sync` | Regenerate from `dotmaster.yaml`; safe to run repeatedly |
| `dotmaster diff` | Show what `sync` would change, without changing anything |
| `dotmaster check` | Exit non-zero if the project has drifted — for CI |
| `dotmaster add <plugin>` | Add or regenerate one plugin's files |
| `dotmaster remove <plugin>` | Delete a plugin's generated files |
| `dotmaster restore [--list]` | Restore files from a pre-generation backup |
| `dotmaster list` | Show available plugins (and which are active) |
| `dotmaster profile list\|show\|apply` | Inspect or apply a preset profile |
| `dotmaster validate` | Check `dotmaster.yaml` for schema and consistency errors |
| `dotmaster doctor` | Detected stack, installed tools, plugin health, drift |

Every write command supports `--dry-run`, `--force` (overwrite files you've
edited since they were generated), and `--output <dir>`.

---

## How regeneration actually works

1. Each active plugin's `plan()` describes the files it wants, as data — it
   never touches disk.
2. The engine resolves that against what's on disk and against
   `.dotmaster/state.json` (dotmaster's private record of what it last
   generated and its content hash — not meant to be committed).
3. **If you haven't touched a file, it's regenerated freely.** If you have,
   it's reported as a conflict and left alone unless you pass `--force`.
   Structured formats (JSON/YAML/TOML) merge instead of conflicting: your
   keys always win, new keys from the template are added.
4. Only then does anything get written — atomically, with a backup of
   anything about to be overwritten, and a full rollback if any write in the
   batch fails.

This is why `dotmaster sync` is safe to run on every commit or as a
pre-commit hook, and why `dotmaster check` is meaningful in CI.

---

## Preset profiles

```bash
dotmaster init --preset web_app      # React/Next.js + ESLint + Prettier + Docker + CI
dotmaster init --preset backend_api  # Python + FastAPI + Ruff + Docker + CI
dotmaster init --preset library      # ESLint + Jest, no Docker
dotmaster init --preset monorepo     # pnpm + ESLint + CI
```

A profile pre-fills the wizard (or, with `--yes`, applies directly) — nothing
is locked in, and `dotmaster profile apply <name>` merges a profile into an
existing config without overwriting anything you've already set explicitly.

---

## `dotmaster.yaml`

```yaml
version: "2"
project:
  name: my-app
  author: Jane Doe
stack:
  languages: [javascript, typescript]
  framework: nextjs
  package_manager: pnpm
quality:
  linter: eslint
  formatter: prettier
  testing: jest
infrastructure:
  docker: true
  docker_multistage: true
  ci: github_actions
options:
  offline: true      # no network calls unless you opt out
plugins:
  allow: []           # third-party plugins, opt-in by name (or ["*"])
```

Hand-editing is a first-class workflow: the file carries a
`# yaml-language-server: $schema=...` hint for editor autocomplete, and every
field is validated with a specific error (and a "did you mean" suggestion)
rather than a stack trace.

---

## Plugin system

Every generator — `.gitignore`, `Dockerfile`, `ruff.toml`, CI workflows — is a
plugin: `matches(config)` decides if it's active, `plan(config, ctx)` returns
the files it wants. Built-ins are always available; third-party plugins
register via a `dotmaster.plugins` entry point and only load if named in
`plugins.allow`.

See **[docs/plugin-authoring.md](docs/plugin-authoring.md)** for the full
guide — most plugins are 30–80 lines, and it's the easiest way to contribute.

---

## Development

```bash
git clone https://github.com/ahron-maslin/dotmaster
cd dotmaster
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check . && mypy dotmaster
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Security

`options.offline` defaults to `true` — no network call happens unless a
project explicitly opts out. All file writes are checked to stay inside the
project root. See [SECURITY.md](SECURITY.md) for the full policy and how to
report a vulnerability.

## License

[MIT](LICENSE)
