# DotMaster — Technical Due Diligence & Blueprint

**Reviewer:** incoming lead maintainer
**Date:** 2026-07-26
**Commit reviewed:** `e2c1299` (main, clean tree)
**Scope:** entire repository — 2,272 LOC source, 1,146 LOC tests, 18 templates, 13 plugins, 4 profiles

> **Headline:** the architecture is sound and the ergonomics are unusually good for a v0.2.
> But **every GitHub Actions workflow, every GitLab CI file, every multi-stage
> `docker-compose.yml`, and most `.eslintrc.json` files this tool generates are
> syntactically invalid** and cannot be consumed by the tools they target. This is
> verified, reproducible, and affects the default happy path. Nothing else in this
> document matters until §3.1 is fixed.

---

## Table of contents

1. [Phase 1 — What DotMaster is](#1-phase-1--what-dotmaster-is)
2. [Phase 2 — Code review](#2-phase-2--code-review)
3. [Phase 3 — Bug hunt](#3-phase-3--bug-hunt)
4. [Phase 4 — Security review](#4-phase-4--security-review)
5. [Phase 5 — Production readiness](#5-phase-5--production-readiness)
6. [Phase 6 — Plugin system](#6-phase-6--plugin-system)
7. [Phase 7 — CLI UX](#7-phase-7--cli-ux)
8. [Phase 8 — Competitive analysis](#8-phase-8--competitive-analysis)
9. [Phase 9 — Missing features](#9-phase-9--missing-features)
10. [Phase 10 — Open source health](#10-phase-10--open-source-health)
11. [Phase 11 — Growth & integrations](#11-phase-11--growth--integrations)
12. [Phase 12 — Scalability architecture](#12-phase-12--scalability-architecture)
13. [Phase 13 — Roadmap](#13-phase-13--roadmap)
14. [Phase 14 — CTO report](#14-phase-14--cto-report)

---

# 1. Phase 1 — What DotMaster is

## 1.1 Problem statement

Every new repository requires the same 10–15 configuration files (`.gitignore`,
linter, formatter, editor config, container, CI, env template, DB scaffold). Today
developers either copy-paste from a previous project, run five separate `init`
commands with five different UX conventions, or hand it to an AI. DotMaster
collapses that into one Q&A and — critically — **persists the answers** so the
configuration can be regenerated later.

## 1.2 Target user

Primary: the individual developer starting a project, or a small team standardising
across repos. Secondary (currently unserved, see §8.4): platform/DevEx teams who
want to enforce one configuration baseline across an org's repositories.

## 1.3 Current feature set

| Capability | Status |
|---|---|
| Interactive wizard (`init`) | Works, TTY-only |
| Persisted answers (`dotmaster.yaml`) | Works |
| Regeneration (`sync`) | Works, output is invalid (§3.1) |
| Single-plugin regeneration (`add`) | Works |
| Plugin listing (`list`) | Works |
| Preset profiles (4) | Partially broken (§3.11) |
| Config validation (`validate`) | Cosmetic only (§3.13) |
| Smart merging (JSON/YAML/TOML/text) | Works for JSON/YAML; text merge is destructive (§3.5) |
| Pre-generation backup | Works for `sync`, silently skipped for `init` (§3.7) |
| Third-party plugins | **Does not exist** (§6.1) |
| Non-interactive / CI mode | **Does not exist** (§3.12) |
| Dry-run / diff | **Does not exist** |
| Restore from backup | **Does not exist** |

## 1.4 Architecture

```
                    ┌──────────────┐
   user ───────────▶│  cli.py      │  typer app: init/sync/add/list/profile/validate
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     ┌────────────────┐        ┌──────────────────┐
     │  wizard.py     │        │  config.py       │  dataclasses ⇄ dotmaster.yaml
     │  (InquirerPy)  │───────▶│  DotmasterConfig │
     └────────────────┘        └────────┬─────────┘
              ▲                         │
              │                         ▼
       ┌──────┴───────┐        ┌──────────────────┐
       │ profiles/    │        │ plugins/registry │  name → class, .active(config)
       │ (4 dicts)    │        └────────┬─────────┘
       └──────────────┘                 │  should_run(config)
                                        ▼
                            ┌───────────────────────┐
                            │ BasePlugin.run()      │
                            │   delegate() → bool   │──▶ runner.py (subprocess)
                            │   generate() → [Path] │──▶ renderer.py ──▶ templates/*.j2
                            └───────────┬───────────┘        │
                                        │                    ▼
                                        │             merger.py (json/yaml/toml/text)
                                        ▼
                            ┌───────────────────────┐
                            │ cli._run_generation   │──▶ backup.py (zip) 
                            │  records paths in cfg │──▶ save_config()
                            └───────────────────────┘
```

**Core modules**

| Module | LOC | Responsibility | Verdict |
|---|---|---|---|
| `cli.py` | 521 | Command definitions + the generation loop | Loop belongs in an engine module |
| `wizard.py` | 508 | Interactive Q&A | 0% test coverage, untestable by design |
| `config.py` | 185 | Schema + YAML I/O | No validation; crashes on bad input |
| `plugins/base.py` | 149 | Plugin contract | Good shape, one design flaw (§6.2) |
| `merger.py` | 121 | Format-aware merge | JSON/YAML fine, text merge unsafe |
| `renderer.py` | 78 | Jinja2 | Env config is the root cause of §3.1 |
| `backup.py` | 68 | Pre-generation zip | Write-only; no restore |
| `runner.py` | 56 | subprocess wrapper | Safe (`shell=False`), underused |
| `plugins/registry` | 56 | Registry | No third-party discovery |

## 1.5 How the plugin system works

```python
class BasePlugin(ABC):
    name: str; description: str; triggers: list[str]; version: str = "1.0.0"

    def should_run(config) -> bool          # any trigger "key:value" matches config
    def delegate(config, out) -> bool       # optional: hand off to official CLI
    def generate(config, out) -> list[Path] # required: render templates, WRITE FILES
    def run(config, out) -> list[Path]      # delegate() or generate(), wraps exceptions
    def post_run(config, out) -> None       # after-all hook
```

Activation is a flat `"key:value"` string DSL evaluated against a hardcoded mapping
in `base.py:67-83`. Registration is a module-level singleton seeded from
`BUILTIN_PLUGINS`.

## 1.6 Configuration flow

```
wizard answers ─┐
profile defaults─┼─▶ DotmasterConfig ─▶ registry.active() ─▶ plugin.generate()
existing yaml ──┘         │                                        │
                          │                                        ▼
                          └────── record_generated(path) ◀── written files
                                        │
                                        ▼
                                  dotmaster.yaml
```

## 1.7 Design patterns in use

Strategy (delegate vs generate), Registry, Template Method (`run()` orchestrating
`delegate`/`generate`), Data Transfer Object (dataclass config), Plugin.
All appropriate. No over-engineering — this is a genuine strength.

## 1.8 Areas that are visibly unfinished

- Third-party plugin loading (documented in README, not implemented)
- `post_run` hook (defined, never overridden, no documented use)
- `BasePlugin.version` (declared "for future compatibility checks", unused)
- Backup restore path (backups created, never readable by the tool)
- `CONFIG_VERSION` migration path (constant exists, no migration code)
- `syrupy` in dev-deps (snapshot testing installed, zero snapshot tests)
- `tree.yml`, `prompt.md` — design scratch files committed to the repo root

---

# 2. Phase 2 — Code review

## 2.1 What is genuinely good

- **Clean layering.** `config` → `plugins` → `renderer` → `templates` with no cycles.
  A new contributor can add a plugin in 20 lines and it works.
- **Lazy imports in CLI commands** (`cli.py:104`, `198`, `242`…) keep `--help` fast.
- **Templates are high quality as prose** — healthchecks, non-root users, distroless
  Go runtime, comments explaining the *why*. Someone thought about these.
- **`runner.py` uses `shell=False` with list args everywhere.** No injection surface.
- **Test hygiene is above average for the size** — 63 tests, arrange/act/assert,
  a regression test with an explanatory docstring (`test_cli.py:16-22`).

## 2.2 Architecture issues

### A1 — Plugins do I/O inside `generate()`; there is no plan phase (**Critical, architectural**)

Every plugin calls `render_to_file(...)` which writes to disk immediately
(`renderer.py:77`). This single decision makes the following *impossible* without a
rewrite: `--dry-run`, diff preview, conflict detection, transactional rollback,
per-file overwrite prompts, drift detection, and parallel plugin execution.

**Fix — separate planning from application.** This is the highest-leverage refactor
in the codebase and everything in the roadmap depends on it:

```python
# dotmaster/core/plan.py
@dataclass(frozen=True)
class FileAction:
    path: Path                  # relative to project root
    content: str
    plugin: str
    strategy: MergeStrategy = MergeStrategy.MERGE   # MERGE | OVERWRITE | SKIP_IF_EXISTS
    mode: int | None = None
    reason: str = ""            # shown in --dry-run / diff output

@dataclass
class Plan:
    actions: list[FileAction]
    conflicts: list[Conflict]   # user-modified files we would clobber

# plugin contract becomes pure:
def generate(self, config, ctx: Context) -> list[FileAction]: ...
```

Then `apply(plan, root, *, dry_run: bool)` is the only code in the project that
touches the filesystem: it can render a diff, prompt, write atomically
(`tmp` + `os.replace`), and roll back on failure. Plugins become pure functions and
therefore trivially testable.

### A2 — The generation engine lives in the CLI (`cli.py:97-163`)

`_run_generation` does backup + orchestration + progress rendering + config
persistence + post-hooks. It is 66 lines, untested, and unreachable from any API
other than argv. Move to `dotmaster/core/engine.py`, return a structured result, and
let `cli.py` do nothing but parse args and render.

### A3 — The trigger DSL does not scale (`base.py:56-89`)

`should_run` is `any(trigger matches)` over a `key:value` string list, evaluated
against a **hardcoded** dict of config fields. Consequences:

- No `AND` (a plugin needing "python **and** docker" cannot express it).
- No negation, no comparison, no version constraints.
- A third-party plugin cannot introduce a new trigger key — `mapping` in
  `_eval_trigger` is closed. This alone blocks the plugin ecosystem.
- `RuffPlugin` (`ruff.py:18-22`) already had to override `should_run` to express
  what its own `triggers = ["linter:ruff", "formatter:ruff"]` should have covered —
  the override is redundant with the base `any()` semantics, which is a smell that
  the author didn't trust the DSL.
- The valid-key list is duplicated in three places: `base.py:67-83`,
  the docstring at `base.py:41-45`, and `test_plugin_contract.py:17-21`.

**Fix:** replace the string DSL with a predicate, keeping a declarative helper for
the common case.

```python
class BasePlugin:
    def should_run(self, config: DotmasterConfig) -> bool:
        return self.matches(config)          # override with plain Python

class RuffPlugin(BasePlugin):
    def matches(self, c): return "ruff" in (c.quality.linter, c.quality.formatter)
```

Plain Python is *more* discoverable than a bespoke mini-language, is type-checked,
supports AND/OR/NOT for free, and removes the closed mapping. Keep `triggers` only
as **display metadata** for `dotmaster list`.

### A4 — `delegate()`'s contract loses information (`base.py:118-136`)

`run()` returns `[]` when `delegate()` succeeds, so successfully delegated files are
invisible to the engine — not counted, not recorded, never backed up. See §3.6.
`delegate()` should return `list[Path] | None`, not `bool`.

### A5 — Config has no validation layer

`DotmasterConfig.from_dict` (`config.py:110-127`) splats untrusted YAML straight into
dataclass constructors. Any unknown key, null section, or wrong type raises a raw
`TypeError` (verified, §3.8). For a tool whose entire premise is "the YAML is the
source of truth", the YAML must be schema-validated. Given `typer`/`rich` are already
dependencies, adding `pydantic` is a small cost for a large win: field validation,
enum constraints, clear error messages, and a generated JSON Schema for editor
autocomplete (`# yaml-language-server: $schema=...`).

## 2.3 Duplication

**D1 — Plugin context dicts (10 near-identical blocks).** `has_python` / `has_node` /
`has_go` are recomputed in `docker.py:25-31`, `dotenv.py:22-26`,
`github_actions.py:28-33`, `gitlab_ci.py:28-33`, `database.py:43-46`. Put them on
the config object:

```python
@dataclass
class DotmasterConfig:
    @property
    def has_node(self) -> bool: return self.has_any_language("javascript", "typescript")
    @property
    def has_python(self) -> bool: return self.has_language("python")
```

…and pass the config object itself into templates (`render(name, {"cfg": config})`),
which deletes ~80 lines of context plumbing and removes the class of bug where a
template variable is renamed in one plugin but not another.

**D2 — `github_ci.j2` and `gitlab_ci.j2` duplicate the entire package-manager
matrix** (`pnpm`/`yarn`/`npm` → install command, run command, lockfile name) six
times each. Extract a Jinja macro file or, better, a `PackageManager` value object in
Python: `pm.install_cmd`, `pm.run_cmd`, `pm.lockfile`, `pm.cache_key`.

**D3 — Ruff config exists twice** — `ruff_toml.j2` and the `[tool.ruff]` section of
`pyproject_toml.j2`. Both are emitted for a Python+ruff project, producing **two
competing configs** (`ruff.toml` wins, silently shadowing the pyproject block). This
is a functional bug as well as duplication: `RuffPlugin` and `PyprojectPlugin` both
fire for `_cfg(languages=["python"], linter="ruff")`.

**D4 — `.eslintignore` / `.prettierignore` / `.dockerignore` / `.gitignore`** share
80% of their entries with no shared source.

## 2.4 Code smells

| Location | Smell |
|---|---|
| `base.py:148-149` | `from typing import Any` **after** the class body, with a comment apologising for it. Move to the top; `from __future__ import annotations` is already on line 5, so the annotation was never evaluated at runtime anyway. |
| `base.py:132` | `if not isinstance(result, list)` — runtime type-checking a contract that `mypy` should enforce. Keep it, but add mypy to CI so it's a belt-and-braces check rather than the only check. |
| `cli.py:104-106, 198-199, 242, 278, 299, 353, 381, 393, 449` | Nine function-local import blocks. Fine as a startup-latency tactic, but it hides the dependency graph. Consolidate into one lazy `_engine()` accessor. |
| `wizard.py:460` | `raise SystemExit(0)` inside a library function; everywhere else the codebase uses `typer.Exit`. The wizard should return `None`/raise a domain exception and let the CLI decide the exit code. |
| `cli.py:402-426` | 25 lines of hand-rolled "merge profile into config" with the same three-line pattern repeated nine times, and it silently omits the `database` section. Replace with a generic `merge_defaults(config, profile_dict)` walking the dataclass fields. |
| `cli.py:457-499` | `validate` hardcodes six rules as an if-ladder. Should be a list of `Rule` objects (`id`, `severity`, `check`, `message`, `fix_hint`) so rules are testable, listable (`dotmaster validate --list-rules`), and suppressible. |
| `config.py:139-144` | `record_generated` mints a fresh timestamp on every regeneration → `dotmaster.yaml` shows a dirty diff after every `sync` even when nothing changed (§3.31). |
| `merger.py:110` | `file_path.name.endswith("rc")` — matches `.eslintrc`, but also `.babelrc`, `.npmrc` (INI!), and any file ending in the letters "rc" such as `webpack.config.src`. Use an explicit registry of filename → format. |
| Templates | Emoji and box-drawing characters (`──`, `✓`) are emitted into generated files and console output with no `--no-unicode` fallback. |

## 2.5 Typing, logging, error handling

- **Typing:** annotations are present and mostly accurate, but `config` parameters in
  every plugin are untyped (`def generate(self, config, output_dir: Path)`), and
  `PluginRegistry.active(self, config)` is untyped. `mypy` is not in CI and there is
  no `[tool.mypy]` section despite a `.mypy_cache/` in the tree — someone ran it once
  and never wired it up.
- **Logging:** `logging.basicConfig()` in the root callback (`cli.py:74-80`)
  configures the **root logger**, so any library that logs will write into the user's
  project directory. The log file is created on *every* invocation including
  `--version` and `--help` (verified). It writes to `Path.cwd()`, not `--output`, and
  it is not in the generated `.gitignore`. See §3.14.
- **Error handling:** the per-plugin `except Exception` in `cli.py:142-146` is the
  right instinct (one bad plugin shouldn't abort the run) but it leaves the project in
  a half-generated state with no rollback, and `save_config` runs anyway at line 147 —
  recording partial success as complete. Typer's pretty-traceback is left on, so
  genuine user errors (malformed YAML) produce a 30-line traceback panel (verified,
  §3.8). Set `pretty_exceptions_enable=False` and catch domain errors explicitly.

## 2.6 Testability

`wizard.py` is 508 lines at **0% coverage** because `inquirer.*` calls are made
directly at module scope inside one 280-line function. Extract a `Prompter`
protocol:

```python
class Prompter(Protocol):
    def text(self, msg: str, default: str = "") -> str: ...
    def select(self, msg: str, choices: list[Choice], default: str) -> str: ...
    def checkbox(self, msg: str, choices, default) -> list[str]: ...
    def confirm(self, msg: str, default: bool) -> bool: ...

def run_wizard(prompter: Prompter, *, preset=None, output_dir=None) -> DotmasterConfig
```

`InquirerPrompter` for production, `ScriptedPrompter([...])` for tests, and — for
free — a `NonInteractivePrompter` that reads `--set key=value` flags, which solves
the CI/headless gap (§3.12) with the same abstraction.

---

# 3. Phase 3 — Bug hunt

Every finding below was **reproduced against `e2c1299`**; commands are given.

## 3.1 CRITICAL — All generated CI files and multi-stage compose files are invalid

**Severity:** Critical (flagship output is unusable)
**Files:** `dotmaster/renderer.py:23-25`, `templates/github_ci.j2`, `templates/gitlab_ci.j2`, `templates/docker_compose.j2`

**Root cause.** The Jinja environment sets both `trim_blocks=True` and
`lstrip_blocks=True` (`renderer.py:24-25`). Those options assume block tags occupy
whole lines. All three templates use block tags **inline**, as value emitters:

- `lstrip_blocks` deletes the indentation preceding an inline `{% if %}`/`{% raw %}`
- `trim_blocks` eats the newline following a tag that ends a line

**Reproduction & evidence:**

```bash
mkdir /tmp/dm && cd /tmp/dm
python - <<'EOF'
from dotmaster.config import *
save_config(DotmasterConfig(
  project=ProjectConfig(name='demo'),
  stack=StackConfig(languages=['typescript'], framework='nextjs', package_manager='pnpm'),
  quality=QualityConfig(linter='eslint', formatter='prettier', testing='jest'),
  infrastructure=InfraConfig(docker=True, docker_multistage=True, ci='github_actions'),
  database=DatabaseConfig(enabled=True, engines=['postgresql'], orm='prisma')), Path('dotmaster.yaml'))
EOF
dotmaster sync
python -c "import yaml;yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Produced output (`github_ci.j2:13-16` → `ci.yml:13-15`):

```yaml
concurrency:
group: ${{ github.workflow }}-${{ github.ref }}     # ← indentation destroyed
  cancel-in-progress: true
```

```yaml
        with:
node-version: ${{ matrix.node-version }}            # ← same, under `with:`
cache: pnpm
```

`docker_compose.j2:15` → `docker-compose.yml:13-14`:

```yaml
    build:
      context: .
target: runtime    restart: unless-stopped          # ← indent lost AND newline eaten
```

`gitlab_ci.j2:29` → `.gitlab-ci.yml`:

```yaml
      files:
        - package-lock.json    paths:               # ← newline eaten
```

**Measured blast radius** across six representative stacks:

| Stack | Broken artifacts |
|---|---|
| Next.js + pnpm + Docker(multistage) + GH Actions + Prisma | `ci.yml`, `docker-compose.yml`, `.eslintrc.json`, `.prettierrc` |
| TS + Express + npm + GitLab CI + MySQL | `.gitlab-ci.yml`, `.eslintrc.json`, `.prettierrc` |
| Python + FastAPI + Poetry + Docker + GH Actions + Alembic | `ci.yml`, `docker-compose.yml` |
| Go + Gin + Docker + GH Actions | `ci.yml` |
| Python + TS mixed + GitLab CI + Mongo | `.gitlab-ci.yml`, `docker-compose.yml`, `.prettierrc` |
| Python, no docker/CI/db (minimal) | *(none — all valid)* |

Only the most trivial configuration produces fully valid output.

**Fix.** Two parts.

1. *Immediate* — put `{% raw %}`/`{% endraw %}` and `{% if %}` on their own lines,
   and convert inline conditionals to expressions:

```jinja
{# github_ci.j2 — before #}
concurrency:
  {% raw %}group: ${{ github.workflow }}-${{ github.ref }}{% endraw %}
  cancel-in-progress: true

{# after #}
{% raw %}
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
{% endraw %}
```

```jinja
{# docker_compose.j2 — before #}
      {% if multistage %}target: runtime{% endif %}
{# after #}
{% if multistage %}
      target: runtime
{% endif %}
```

```jinja
{# gitlab_ci.j2 / github_ci.j2 — before #}
          {% if package_manager == 'pnpm' %}cache: pnpm{% elif ... %}{% endif %}
{# after #}
          cache: {{ 'pnpm' if package_manager == 'pnpm' else 'yarn' if package_manager == 'yarn' else 'npm' }}
```

2. *Systemic* — **a parser test over a config matrix**, which is what should have
   caught this on day one. `syrupy` is already a dev dependency:

```python
# tests/test_generated_artifacts.py
@pytest.mark.parametrize("cfg", ALL_STACK_COMBINATIONS, ids=lambda c: c.id)
def test_every_generated_file_parses(cfg, tmp_path):
    for plugin in registry.active(cfg):
        for path in plugin.generate(cfg, tmp_path):
            assert_parses(path)     # yaml.safe_load / json.loads / tomlkit.parse / configparser
```

Add `actionlint` (GitHub) and `docker compose config` to CI as a second gate.

## 3.2 CRITICAL — `.eslintrc.json` is invalid whenever the framework isn't React

**Severity:** Critical · **File:** `templates/eslintrc.j2:16-22, 33-52`

Two independent JSON defects:

1. **Missing comma in `plugins`** — the comma after `"@typescript-eslint"` is emitted
   only `{% if has_react %}`, so a TypeScript + Jest + Express project renders
   `["@typescript-eslint" "jest"]`.
2. **Trailing comma in `rules`** — the last real entry in both the base block and the
   TypeScript block ends with `,`, and the closing entry is inside
   `{% if has_react %}`.

**Reproduce:**

```bash
python -c "
from dotmaster.renderer import render
print(render('eslintrc.j2',{'framework':'express','has_typescript':True,'has_react':False,'testing':'jest','package_manager':'npm'}))" > /tmp/e.json
node -e "JSON.parse(require('fs').readFileSync('/tmp/e.json','utf8').replace(/^\s*\/\/.*$/gm,''))"
# SyntaxError: Expected ',' or ']' after array element in JSON at position 251
```

ESLint strips `//` comments but does **not** accept trailing commas or missing
delimiters, so `eslint` exits with a config-parse error and the project has no
linting at all.

**Fix.** Stop hand-assembling JSON in Jinja. Build a `dict` in the plugin and
`json.dumps(..., indent=2)`:

```python
def generate(self, config, ctx):
    cfg = {"root": True, "env": {...}, "plugins": [...], "extends": [...], "rules": {...}}
    if config.has_typescript: cfg["plugins"].append("@typescript-eslint"); ...
    return [FileAction(Path(".eslintrc.json"), json.dumps(cfg, indent=2) + "\n", ...)]
```

This makes syntactically invalid output *unrepresentable* — the correct structural
fix, and it applies equally to `.prettierrc`.

## 3.3 HIGH — `.prettierrc` sets a global `parser`, breaking Prettier for non-TS files

**Severity:** High · **File:** `templates/prettierrc.j2:12-13`

`"parser": "typescript"` at the top level forces the TypeScript parser onto *every*
file Prettier touches — `.json`, `.md`, `.css`, `.yaml` — all of which then fail to
format. Prettier's own docs mark top-level `parser` as discouraged; it belongs in
`overrides`. Since the file extension already selects the parser, the correct fix is
to **delete the key entirely**.

## 3.4 HIGH — Generated ESLint config uses the format ESLint removed

**Severity:** High (obsolescence) · **Files:** `eslint.py`, `eslintrc.j2`, `eslintignore.j2`

ESLint 9 (2024) made flat config (`eslint.config.js`) the default and **dropped
`.eslintignore` support entirely**. A 2026 tool emitting `.eslintrc.json` +
`.eslintignore` produces configuration that modern ESLint ignores. Generate
`eslint.config.mjs` by default with an `--eslint-legacy` escape hatch, and move the
ignore list into the flat config's `ignores` key.

## 3.5 HIGH — `merge_text` corrupts every non-structured file the user has edited

**Severity:** High (data corruption) · **File:** `merger.py:73-79`, reached from `renderer.py:74-75`

`render_to_file` defaults to `merge=True`, and `merge_content` falls through to
`merge_text` for anything that isn't `.json`/`.yaml`/`.toml` — i.e. `Dockerfile`,
`.gitignore`, `.env.example`, `.dockerignore`, `.editorconfig`. `merge_text` appends
the **entire** newly rendered file after a marker unless the new content appears
verbatim in the old.

**Reproduce:**

```bash
python - <<'EOF'
from pathlib import Path; import tempfile
from dotmaster.renderer import render_to_file
d = Path(tempfile.mkdtemp()); ctx = {...}   # python/fastapi/single-stage
p = d/'Dockerfile'; render_to_file('dockerfile.j2', ctx, p)      # 21 lines
p.write_text(p.read_text().replace('3.12-slim','3.11-slim'))     # user edits base image
render_to_file('dockerfile.j2', ctx, p)                          # dotmaster sync
print(len(p.read_text().splitlines()), p.read_text().count('FROM '))
EOF
# 42 2
```

The result is a Dockerfile with **two `FROM` stages**: Docker builds the last one,
so the user's edit is silently reverted while appearing to still be in the file. The
same mechanism doubles `.gitignore` and `.env.example` on every content change.

**Fix.** Text files have no generic merge. Options, in order of preference:
1. **Managed-region markers** — write generated content between
   `# >>> dotmaster managed >>>` / `# <<< dotmaster managed <<<` and replace only
   that region, preserving everything else. Correct for `.gitignore`, `.editorconfig`.
2. **Line-set union** for pure ignore-lists (`.gitignore`, `.dockerignore`).
3. **Never merge** whole-program files (`Dockerfile`): detect drift by hash, and
   prompt `overwrite / keep / show diff`.

## 3.6 HIGH — Successfully delegated files are invisible to the engine

**Severity:** High · **Files:** `base.py:127-129`, `cli.py:135-141`

`run()` returns `[]` when `delegate()` succeeds. Consequences for the *default* path
(gitignore.io is reachable):

- `.gitignore` is written but never printed with a `✓`
- it is never added to `config.generated`
- therefore it is **never backed up** on subsequent runs (`backup.py:29`)
- the summary undercounts: "Generated 11 file(s)" when 12 were written

**Verified live** — in an end-to-end `sync`, the `gitignore` plugin line printed with
no file beneath it and `.gitignore` was absent from the `generated:` list in
`dotmaster.yaml` while present on disk.

**Fix:** `def delegate(...) -> list[Path] | None` — `None` means "not applicable, fall
through", a list means "handled, here's what I wrote".

## 3.7 HIGH — `dotmaster init` on an existing project takes no backup

**Severity:** High (data loss) · **File:** `cli.py:203-221` + `backup.py:23-25`

`backup_managed_files` returns early when `config.generated` is empty. On `init` the
config comes fresh from the wizard, so `generated` is *always* empty — meaning the
one command most likely to be run against an already-configured directory is the one
with no safety net. The user even confirms "Overwrite settings? y" and reasonably
assumes the tool knows what it's doing.

**Fix:** on `init`, load the pre-existing `dotmaster.yaml` (if any) and carry its
`generated` list into the backup step before overwriting; additionally back up any
file the plan is about to touch, whether or not dotmaster claims to own it.

## 3.8 HIGH — Malformed `dotmaster.yaml` produces a raw traceback

**Severity:** High (UX/robustness) · **File:** `config.py:110-127, 152-163`

```python
DotmasterConfig.from_dict({"project": {"name":"x","license":"MIT"}})
# TypeError: ProjectConfig.__init__() got an unexpected keyword argument 'license'
DotmasterConfig.from_dict({"project": None})
# TypeError: ProjectConfig() argument after ** must be a mapping, not NoneType
DotmasterConfig.from_dict({"stack": "python"})
# TypeError: StackConfig() argument after ** must be a mapping, not str
```

And a syntactically broken YAML file:

```bash
printf 'project: [1,2\n' > dotmaster.yaml && dotmaster validate
# → 30-line rich traceback ending in yaml.parser.ParserError
```

Both are *expected* user states — hand-editing `dotmaster.yaml` is a documented
workflow (README line 107). **Fix:** schema-validate on load (pydantic), catch
`yaml.YAMLError`, and report `dotmaster.yaml:12  unknown key 'license' in section
'project'` with `pretty_exceptions_enable=False`.

## 3.9 MEDIUM — `merge_toml` lets generated defaults clobber user values

**Severity:** Medium (data loss) · **File:** `merger.py:50-57`

```python
else:
    existing_table[key] = value    # new (generated) wins
```

A user bumps `version = "2.1.0"` in `pyproject.toml`; the next `sync` silently resets
it to the template's `0.1.0`. Note the *opposite* convention is used in
`cli.py:406-425` (`profile --apply`), where existing values win. Pick one rule —
"user edits always win, generated content only fills gaps" — and apply it in both
places. Anything else needs a 3-way merge against the previously generated content
(which requires storing it; see §12.3).

## 3.10 MEDIUM — `RuffPlugin` and `PyprojectPlugin` emit competing configs

**Severity:** Medium · **Files:** `ruff.py`, `pyproject.py`, `pyproject_toml.j2:79-101`

For `languages=["python"], linter="ruff"` both plugins are active and both write ruff
settings, to `ruff.toml` and `[tool.ruff]` respectively. Ruff resolves `ruff.toml`
first, so the pyproject block is dead config that will drift and confuse. Decide one
home (recommend `[tool.ruff]` in `pyproject.toml` when that file exists, else
`ruff.toml`) and add a **conflict-detection pass** to the engine: two plugins
claiming overlapping configuration for the same tool should be an error, not a race.

## 3.11 MEDIUM — Preset profiles never pre-select languages or DB engines

**Severity:** Medium · **File:** `wizard.py:279-293, 350-363`

```python
languages = inquirer.checkbox(choices=[...], default=pd("stack","languages",[]), ...)
```

InquirerPy's `checkbox` uses `default` **only to position the cursor** — pre-selection
comes from `Choice(..., enabled=True)`. Verified in
`InquirerPy.base.control.InquirerPyUIListControl._get_choices`: `enabled` is taken
from the `Choice` dataclass and `default` only ever sets `selected_choice_index`
(and only when a choice's *value* equals it — here `default` is a *list*, so it never
matches anything).

Result: `dotmaster init --preset web_app` shows an **empty** language checkbox and
forces the user to re-pick, defeating the profile. Same for database engines.

**Fix:**

```python
prechecked = set(pd("stack", "languages", []))
choices = [Choice(v, label, enabled=v in prechecked) for v, label in LANGUAGES]
```

## 3.12 MEDIUM — No non-interactive mode; `--preset` does not skip the wizard

**Severity:** Medium (blocks all automation) · **Files:** `cli.py:184-190`, `wizard.py:180`

README line 50 says "Skip the wizard entirely with `--preset`", but
`run_wizard(preset_profile=preset)` only pre-fills defaults — every question is still
asked. In a non-TTY the run dies:

```bash
dotmaster init --preset web_app < /dev/null
# Warning: Input is not a terminal (fd=0).
# Aborted.
```

This makes DotMaster unusable in CI, Docker builds, `npx`-style one-liners, dotfile
bootstrap scripts, and from any AI agent — i.e. every automated adoption path.

**Fix:** `--yes/-y` to accept all defaults, `--set stack.framework=nextjs` for
overrides, `--from <file>` to supply answers, and auto-detect non-TTY → require `-y`
or fail with a clear message and non-zero exit.

## 3.13 MEDIUM — `validate` accepts arbitrary invalid values

**Severity:** Medium · **File:** `cli.py:435-513`

```bash
printf 'stack:\n  languages: [pythn]\nquality:\n  linter: eslintt\n' > dotmaster.yaml
dotmaster validate
#   ✓ dotmaster.yaml is valid!
```

The command checks six cross-field consistency rules but never validates that values
are members of their enums. A user with a typo gets a green check and then silently
loses every plugin that depended on that field. Enum validation must come first;
"did you mean `eslint`?" via `difflib.get_close_matches` is a two-line addition.

## 3.14 MEDIUM — Log file pollution and root-logger hijack

**Severity:** Medium · **File:** `cli.py:71-80`

- `.dotmaster.log` is created in `Path.cwd()` on **every** invocation, including
  `dotmaster --version` and `--help` (verified: an empty dir contains only
  `.dotmaster.log` after `--version`).
- It uses `Path.cwd()`, not `--output`.
- `logging.basicConfig` configures the **root** logger at INFO, so every third-party
  library's log lands in the user's project.
- The generated `.gitignore` does not exclude `.dotmaster.log` or `.dotmaster/`, so
  users will commit the tool's droppings.
- If cwd is read-only, the CLI crashes before doing anything.

**Fix:** log to the platform state dir (`platformdirs.user_state_dir("dotmaster")`),
attach the handler to the `dotmaster` logger only (`propagate=False`), create it
lazily on first record, add `--log-file` to override, and add `.dotmaster/` +
`.dotmaster.log` to the generated `.gitignore`.

## 3.15 MEDIUM — Generated Python Dockerfiles cannot build

**Severity:** Medium · **File:** `templates/dockerfile.j2:14-30, 66-79`

- Poetry path: `COPY pyproject.toml ./` then `poetry install --only main`. Without
  `poetry.lock` the build is non-reproducible, and `poetry install` fails outright if
  the project is package-mode and `README.md`/the package dir aren't copied.
- uv path: `RUN pip install uv && uv sync --no-dev` — `uv sync` requires `uv.lock`,
  which is never copied.
- pip path: `COPY requirements*.txt ./` in a project where DotMaster just generated a
  `pyproject.toml` and no `requirements.txt` → `COPY` fails, build aborts.

Node multi-stage has the same class of problem: the Next.js branch copies
`.next/standalone`, which only exists if `next.config.js` sets
`output: 'standalone'` — a file DotMaster does not generate.

**Fix:** generate lockfile-aware Dockerfiles, emit the companion files the Dockerfile
assumes (or detect their absence and choose a different branch), and add a CI job
that actually `docker build`s a sample of generated projects.

## 3.16 MEDIUM — Generated CI calls npm scripts that don't exist

**Severity:** Medium · **Files:** `github_ci.j2:47-62`, `gitlab_ci.j2:38-50`

The workflows run `npm run lint`, `npm run format:check`, `npm test`. DotMaster never
generates or modifies `package.json`, so on the first push CI fails with
`Missing script: "lint"`. Either add a `package.json` plugin that injects the scripts
(the natural counterpart to the existing `pyproject` plugin), or make CI call the
tools directly (`npx eslint .`, `npx prettier --check .`).

## 3.17 MEDIUM — No rollback despite backups; partial failure is recorded as success

**Severity:** Medium · **File:** `cli.py:131-147`

If plugin #4 of 9 throws, plugins 1–3 have already written, 5–9 continue, and
`save_config` at line 147 persists the run as if complete. A backup zip exists but
**there is no command to restore it** — the user must find `.dotmaster/backups/`,
unzip manually, and figure out which files to revert. Add `dotmaster restore [--list]
[--at <timestamp>]`, and once §2.2/A1 lands, make apply transactional.

## 3.18 LOW — `dotmaster.yaml` churns on every sync

**Severity:** Low (but constant friction) · **File:** `config.py:66-69, 139-144`

`GeneratedEntry.at` is regenerated with `datetime.now()` on every `record_generated`,
so `git diff` after a no-op `sync` shows 11 changed timestamps. Either drop `at`, or
preserve the original timestamp when the content is unchanged and store a content
hash instead (which you need anyway for drift detection, §12.3).

## 3.19 LOW — Backups grow without bound and are not ignored by git

**Severity:** Low · **File:** `backup.py:38-64`

Every `sync` writes a new zip into `.dotmaster/backups/` with no retention policy and
no entry in the generated `.gitignore`. Add `--keep-backups N` (default 10) and
pruning; add `.dotmaster/` to the generated ignore file.

## 3.20 LOW — Windows path separators are persisted into `dotmaster.yaml`

**Severity:** Low (cross-platform) · **File:** `config.py:141-144`

`str(path)` yields `.github\workflows\ci.yml` on Windows. That file is committed and
then read on Linux/macOS, where the path never resolves — backups silently skip the
file and `add`-style targeting misses. Always store POSIX form:
`rel = PurePosixPath(path.as_posix())`.

## 3.21 LOW — `pyproject` plugin silently no-ops when the file exists

**Severity:** Low · **File:** `pyproject.py:28-30`

```python
if existing.exists():
    return True     # "delegation succeeded" — nothing happened
```

Returning `True` means "handled", so `generate()` is skipped and no path is reported.
For a Poetry user, `dotmaster add pyproject` prints success and does nothing.

## 3.22 LOW — `add <plugin>` bypasses `should_run` without telling the user

**Severity:** Low · **File:** `cli.py:110-117`

`dotmaster add eslint` in a pure-Python project happily writes `.eslintrc.json`.
Defensible as an escape hatch, but it should warn: *"eslint is not active for this
configuration (no javascript/typescript language). Generate anyway? [y/N]"*.

## 3.23 LOW — Unicode output has no fallback

`✓`, `→`, `⚠`, `──`, and emoji are printed unconditionally and written into
generated files. On a legacy Windows console (cp1252) or a CI log with `LANG=C`, Rich
will substitute or mangle these. Add `--no-unicode` / honour `NO_COLOR` and
`TERM=dumb`.

## 3.24 LOW — `--verbose` only works before the subcommand

`-v` is on the root callback, so `dotmaster init -v` errors while `dotmaster -v init`
works. Users will type the former. Add the flag to each command or use a shared
callback parameter.

---

# 4. Phase 4 — Security review

**Overall:** no critical vulnerabilities. `subprocess` usage is correct, there is no
`eval`/`exec`, no deserialization of untrusted pickles, and `yaml.safe_load` is used
throughout. The issues are (a) one path-traversal write primitive, (b) an
undisclosed network call, and (c) latent risks that will become real the moment
third-party plugins and user templates ship.

## 4.1 MEDIUM — Path traversal in the backup routine → arbitrary file copy

**File:** `backup.py:50-53`

```python
rel = f.relative_to(output_dir)     # PURELY LEXICAL — does not resolve ".."
dest = staging_dir / rel
dest.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(f, dest)
```

`Path.relative_to` is a lexical operation: `Path("/proj/../secret").relative_to("/proj")`
returns `../secret` rather than raising. A crafted `dotmaster.yaml` therefore causes
DotMaster to read a file outside the project and write a copy of it outside the
staging directory.

**Reproduced:**

```python
cfg.generated = [GeneratedEntry(path="../secret.txt", plugin="evil")]
backup_managed_files(cfg, proj)
# → proj/.dotmaster/secret.txt now contains the contents of ../secret.txt
```

With more `../` segments the write lands anywhere the process can write. **Threat
model is realistic**: `dotmaster sync` in a freshly cloned repository is the intended
workflow, and `dotmaster.yaml` is attacker-controlled content in that scenario.

**Fix:**

```python
root = output_dir.resolve()
target = (output_dir / entry.path).resolve()
if not target.is_relative_to(root):        # 3.9+
    logger.warning("skipping out-of-tree managed path: %s", entry.path)
    continue
if target.is_symlink(): continue           # also refuse symlinks
```

Apply the same containment check in `render_to_file` — today nothing prevents a
plugin (including a future third-party one) from writing to `~/.ssh/authorized_keys`.

## 4.2 MEDIUM — Undisclosed network egress on every `init`/`sync`

**File:** `plugins/builtin/gitignore.py:45-71`

Every run POSTs the project's language and framework list to
`https://www.toptal.com/developers/gitignore/api/...` and writes the **raw response
body straight to `.gitignore`** with:

- no `Content-Type` check
- no response size limit (a hostile/compromised endpoint can fill the disk)
- no integrity check
- no opt-out flag
- no mention in the README

Two distinct problems. **Privacy:** the user's stack fingerprint leaves the machine
without consent — unacceptable in air-gapped, regulated, and enterprise settings.
**Integrity:** the contents of a security-relevant file (`.gitignore` is what stops
`.env` and `*.pem` being committed) are supplied by a third party over the wire. A
tampered response that quietly drops `.env` from the ignore list is a plausible and
high-impact supply-chain attack.

**Fix:** make the network path **opt-in** (`--online` / `network: false` in config),
default to the bundled template, cap the response at e.g. 256 KiB, verify
`Content-Type: text/plain`, sanity-check that the payload looks like a gitignore, and
document the behaviour prominently.

## 4.3 MEDIUM — Template rendering is unsandboxed (latent)

**File:** `renderer.py:19-27`

`Environment(loader=FileSystemLoader(TEMPLATES_DIR))` with no `SandboxedEnvironment`.
Safe today because templates ship inside the wheel. The moment user-supplied or
community templates are supported — which every roadmap item points toward — this
becomes **remote code execution**: Jinja2 template injection via
`{{ ''.__class__.__mro__[1].__subclasses__() }}` is a well-trodden path. Switch to
`jinja2.sandbox.SandboxedEnvironment` **now**, before the feature exists; the cost is
one import and it closes the door permanently.

## 4.4 MEDIUM — No plugin trust model (latent but imminent)

The README advertises custom plugins, and §12 recommends entry-point discovery. A
Python entry point executes arbitrary code at import time, with the user's
privileges, in their project directory. Before shipping plugin discovery, decide:

- an explicit `plugins:` allowlist in `dotmaster.yaml` (nothing loads unless named)
- a lockfile pinning plugin name → version → hash
- `dotmaster plugins list --untrusted` showing what would execute
- a capability declaration in the plugin manifest (`writes: [".github/**"]`,
  `network: false`, `subprocess: false`) enforced by the apply layer

Without this, "install a dotmaster plugin" becomes "run arbitrary code", and a
popular plugin registry becomes a high-value supply-chain target.

## 4.5 LOW — Weak default credentials and 0.0.0.0 port binding in generated compose

**File:** `templates/docker_compose.j2:56-160`

`POSTGRES_PASSWORD:-postgres`, `MYSQL_ROOT_PASSWORD:-rootpassword`,
`MONGO_PASSWORD:-password`, and `- "${POSTGRES_PORT:-5432}:5432"` binds to all
interfaces. Fine on a laptop, dangerous on a shared/cloud dev box or a coffee-shop
network. Bind to `127.0.0.1:5432:5432` by default and emit a
`# ⚠ development credentials — do not use in production` banner. Optionally generate
a random password into `.env` at creation time.

## 4.6 LOW — `.env.example` guidance is good but incomplete

The template correctly says "NEVER commit the real .env", and the generated
`.gitignore` does cover `.env`. Consider also generating a
`git config --local core.hooksPath`-installable pre-commit hook that blocks `.env`
and private keys — a natural, high-value extension of the tool's remit.

## 4.7 Dependency & supply chain

- Dependencies are mainstream and pinned only by lower bound (`typer>=0.12`,
  `jinja2>=3.1`, …). No upper bounds, no lockfile, no `pip-audit` in CI.
- `typer[all]` is a **deprecated extra** (Typer ≥0.12 folds Rich/shellingham into the
  base package); it currently resolves but will break.
- Release workflow (`.github/workflows/release.yml`) uses PyPI Trusted Publishing —
  correct and modern. But it **does not run the test suite before publishing** and
  does not verify that the git tag matches the built version. Add both, plus
  `--attestations` / Sigstore provenance.
- No `SECURITY.md`, no advisory contact, no CVE process.
- `dependabot.yml` absent.

## 4.8 Confirmed non-issues (for the record)

- `runner.run()` uses list-form args with `shell=False` — no shell injection.
- `poetry init` arguments come from config but are passed as argv, not interpolated.
- gitignore.io URL terms are mapped through closed dicts (`_LANG_MAP`, `_FW_MAP`), so
  no URL injection from config values.
- `yaml.safe_load` everywhere; no `yaml.load`.
- Generated Dockerfiles create non-root users and use distroless for Go — good.

---

# 5. Phase 5 — Production readiness

## 5.1 Testing

| Module | Coverage | Assessment |
|---|---|---|
| `wizard.py` (508 LOC) | **0%** | The primary UX, entirely untested |
| `cli.py` (521 LOC) | 36% | Only `profile --apply` is covered |
| `runner.py` | 44% | Subprocess paths untested |
| `gitignore.py` | 50% | The network path is untested |
| `merger.py` | 75% | Failure paths untested |
| plugins/templates | ~100% *statements* | But **no test asserts the output is valid** |
| **Total** | **59%** | 63 tests, all passing, 2.85 s |

The coverage number flatters the suite. The plugin tests assert
`"postgres" in content` — a substring check that passes on completely malformed YAML.
That's exactly how §3.1 shipped.

**Required before 1.0:**
1. Parse-validity tests over a stack matrix (§3.1) — *this is the single most
   valuable test to write*.
2. Snapshot tests with `syrupy` (already a dependency) for all 18 templates.
3. Wizard tests via an injected `Prompter` (§2.6).
4. Full CLI integration tests for all six commands, including failure exit codes.
5. Idempotency property test: `sync; sync` must produce a byte-identical tree.
6. Round-trip property test: `wizard answers → yaml → load → same config`.
7. External validators in CI: `actionlint`, `docker compose config`, `eslint
   --print-config`, `ruff check --config`, `prettier --check`.
8. Cross-platform matrix: Windows + macOS, not just `ubuntu-latest`.

## 5.2 CI/CD

Current CI (`.github/workflows/ci.yml`): one job, Ubuntu only, Python 3.10–3.12,
`hatch run dev:pytest`. Missing:

- lint (`ruff check`) and format (`ruff format --check`) — ironic for this project
- type checking (`mypy` / `pyright`) — a `.mypy_cache/` exists but nothing runs it
- coverage reporting + a floor (`--cov-fail-under=80`)
- Windows and macOS runners
- Python 3.13 (released 2024) — `requires-python = ">=3.10"` claims support that is
  untested
- `pip-audit` / `dependabot`
- build-and-smoke-install job (`pipx install ./dist/*.whl && dotmaster --version`)
- generated-artifact validation (see above)

## 5.3 Release process & versioning

`hatch-vcs` derives the version from git tags — good. Gaps:

- Release publishes **without running tests**.
- No `CHANGELOG.md` and no release notes automation.
- No documented SemVer policy. For this tool the contract that matters is not just
  the Python API but **the generated output**: changing a template changes users'
  files. Define it explicitly:
  - *patch* — bug fixes in generated content that keep the same shape
  - *minor* — new plugins, new options, additive template content
  - *major* — changed default output, removed plugin, `dotmaster.yaml` schema change
- No pre-release channel (`0.x.0rc1`) for template changes to be validated in the wild.

## 5.4 Migrations & backward compatibility

`CONFIG_VERSION = "1"` exists and `from_dict` reads `version` but **never checks it**.
A v2 schema would silently mis-parse v1 files. Needed:

```python
MIGRATIONS = {"1": migrate_1_to_2, "2": migrate_2_to_3}
def load_config(path):
    data = _read(path)
    v = str(data.get("version", "1"))
    while v != CONFIG_VERSION:
        data = MIGRATIONS[v](data); v = str(data["version"])
```

Plus `dotmaster migrate` as an explicit command, and a refusal (not a crash) when the
file's version is *newer* than the installed tool: *"dotmaster.yaml was written by a
newer version (3). Upgrade with `pipx upgrade dotmaster`."*

## 5.5 Observability, telemetry, crash reporting

- Logging: see §3.14. Once fixed, add `--log-level` and structured (JSON) logs behind
  a flag for CI consumption.
- Telemetry: **opt-in only**, or not at all. This is a developer-tools audience with
  strong feelings; an opt-out tracker would be a launch-day controversy. If you want
  usage data, ship `dotmaster --version --json` and let people volunteer it, or
  instrument only the documentation site.
- Crash reporting: print a short error plus *"re-run with `--verbose` and attach
  `<logfile>` to a bug report"*, with a pre-filled GitHub issue URL. No automatic
  upload.

## 5.6 Documentation

README is well-written but **describes features that don't exist or don't work**:
custom plugins (§6.1), `--preset` skipping the wizard (§3.12), and a `sync` whose
output doesn't parse. Fixing the docs/reality gap is a release blocker in itself.
Missing entirely: CONTRIBUTING, CHANGELOG, LICENSE file (!), plugin authoring guide,
`dotmaster.yaml` schema reference, examples directory, troubleshooting.

## 5.7 Production-readiness scorecard

| Area | Score | Blocker for 1.0? |
|---|---|---|
| Core correctness | 2/10 | **Yes** — §3.1, §3.2 |
| Data safety | 4/10 | **Yes** — §3.5, §3.7 |
| Testing | 4/10 | **Yes** |
| CI/CD | 4/10 | Yes |
| Security | 6/10 | Yes — §4.1, §4.2 |
| Extensibility | 2/10 | Yes — §6.1 |
| CLI UX | 6/10 | Partly |
| Docs / OSS hygiene | 3/10 | **Yes** — no LICENSE |
| Architecture | 7/10 | No |
| **Overall** | **4/10** | Roughly 8–12 weeks of focused work from 1.0 |

---

# 6. Phase 6 — Plugin system

## 6.1 The headline finding: there is no plugin system

README line 118: *"You can add custom plugins by subclassing
`dotmaster.plugins.base.BasePlugin`."*

There is **no discovery mechanism**. `PluginRegistry.__init__` (`plugins/__init__.py:19-24`)
seeds itself from the hardcoded `BUILTIN_PLUGINS` list, and the module-level
singleton is constructed at import time. A third party can subclass `BasePlugin` all
they like; nothing will ever load it. The only way to register is to import
`dotmaster.plugins.registry` and call `register()` from inside a process you control
— which a CLI user does not have.

For a project whose central thesis is extensibility, this is the most important gap
in the repository after §3.1.

## 6.2 Contract design review

**Good:** small surface (4 methods), clear lifecycle docstring, `run()` as a template
method, exceptions wrapped with plugin identity (`base.py:136`).

**Problems:**

| # | Issue | Impact |
|---|---|---|
| 1 | `generate()` performs I/O | Blocks dry-run, diff, rollback, conflict detection (§2.2/A1) |
| 2 | `delegate() -> bool` loses the file list | §3.6 |
| 3 | Trigger DSL is closed and can't express AND | §2.3/A3 |
| 4 | `version` declared but never checked | No compatibility story |
| 5 | No API version on the *contract* itself | A `BasePlugin` change silently breaks every third-party plugin |
| 6 | No declared outputs | Can't detect two plugins writing the same file (§3.10) |
| 7 | No config schema contribution | A plugin can't add its own questions or `dotmaster.yaml` keys |
| 8 | `post_run` has no ordering or dependency model | Hooks fire in registration order, always |
| 9 | No plugin-scoped settings | Every knob must be added to the core `DotmasterConfig` |
| 10 | Exceptions collapse to `RuntimeError` | Callers can't distinguish "template missing" from "network down" |

## 6.3 Proposed plugin API v1

```python
# dotmaster/plugins/api.py — the ONLY module third parties import
from dotmaster.plugins.api import Plugin, FileAction, Context, Question, api_version

API_VERSION = 1     # bumped only on breaking changes; loader refuses mismatches

class Plugin(Protocol):
    id: str                       # "eslint"            — stable, namespaced for 3rd party: "acme.terraform"
    version: str                  # "2.1.0"             — the plugin's own semver
    requires_api: int             # 1                   — checked at load time
    summary: str
    provides: tuple[str, ...]     # ("lint.javascript",) — capability tags, enables conflict detection
    outputs: tuple[str, ...]      # (".eslintrc.json",)  — declared, verified after apply

    def questions(self, ctx: Context) -> list[Question]: ...   # contributes to the wizard
    def matches(self, cfg: Config) -> bool: ...                # replaces the trigger DSL
    def plan(self, cfg: Config, ctx: Context) -> list[FileAction]: ...   # PURE — no I/O
    def post_apply(self, cfg: Config, ctx: Context) -> None: ...         # opt-in side effects
```

`Context` carries the injected services a plugin is allowed to use — and nothing
else. That's both DX and the enforcement point for the capability model in §4.4:

```python
@dataclass(frozen=True)
class Context:
    root: Path
    render: Callable[[str, dict], str]   # sandboxed Jinja bound to the plugin's template dir
    run: CommandRunner                   # subprocess, only if the manifest declares subprocess: true
    http: HttpClient | None              # None unless network: true AND user allowed it
    log: Logger
    settings: Mapping[str, Any]          # this plugin's section of dotmaster.yaml
```

## 6.4 Discovery

```python
# dotmaster/plugins/loader.py
def discover() -> list[LoadedPlugin]:
    found = list(_builtins())
    for ep in entry_points(group="dotmaster.plugins"):        # pip-installed
        found.append(_load_entry_point(ep))
    for path in (Path.cwd()/".dotmaster"/"plugins").glob("*.py"):   # project-local
        found.append(_load_path(path))
    return _filter_by_allowlist(found, config.plugins.allow)  # §4.4 trust model
```

Third-party registration then costs one line in *their* `pyproject.toml`:

```toml
[project.entry-points."dotmaster.plugins"]
terraform = "dotmaster_terraform:TerraformPlugin"
```

## 6.5 Plugin developer experience

Today, authoring a plugin means reading the source of an existing one. Ship instead:

1. **`dotmaster plugin new <name>`** — scaffolds a plugin package with tests, a
   template dir, and a working `pyproject.toml`. (DotMaster scaffolding DotMaster
   plugins is also excellent marketing.)
2. **`dotmaster.testing`** — a public pytest fixture package:
   ```python
   def test_writes_eslintrc(plugin_harness):
       result = plugin_harness.run(MyPlugin(), stack="typescript+react")
       result.assert_generated(".eslintrc.json")
       result.assert_valid_json(".eslintrc.json")
       result.assert_idempotent()
   ```
3. **A conformance suite** third-party authors run in their own CI:
   `pytest --dotmaster-conformance` asserts purity of `plan()`, declared-vs-actual
   outputs, idempotency, and no writes outside `root`.
4. **A plugin authoring guide** with a complete worked example (Terraform or
   pre-commit are good candidates — genuinely useful and not yet built in).
5. **`dotmaster plugin doctor`** — validates a plugin's manifest, API version,
   declared outputs, and trigger correctness before publishing.

## 6.6 Version compatibility

```
dotmaster core 1.4.0
      ├── plugin API v1  ──▶ plugin declares requires_api = 1   → load
      └── plugin API v2  ──▶ plugin declares requires_api = 1   → load in compat shim, warn
                        ──▶ plugin declares requires_api = 3   → refuse, tell user to upgrade
```

Rules to publish and hold to: the API version increments only on breaking contract
changes; core supports N and N-1 for at least two minor releases; `dotmaster doctor`
reports every loaded plugin's API version and health.

---

# 7. Phase 7 — CLI UX

## 7.1 First-run experience

Good: the Rich banner, phase headers with icons, the summary table before
confirmation, and the per-file `✓` progress list are genuinely pleasant — better than
Cookiecutter and on par with `create-vite`.

Problems on first contact:

1. `dotmaster` with no args prints help but **also creates `.dotmaster.log`** in the
   user's directory. First impression: "this tool littered in my repo before I ran
   anything."
2. No `dotmaster doctor` to tell the user what's installed and detected.
3. No detection of the *existing* project. Running in a repo that already has
   `package.json`, `tsconfig.json`, and `.git` should pre-answer half the wizard —
   see §9.5.
4. The wizard asks 12–15 questions with no progress indicator ("Step 3 of 6") and no
   way to go back.

## 7.2 Command surface

| Command | Assessment |
|---|---|
| `init` | Good name. Needs `--yes`, `--set`, `--dry-run`, `--force`. |
| `sync` | Good. Should default to showing a diff and asking, not silently writing. |
| `add <plugin>` | Good. Needs a `remove` counterpart. |
| `list` | Fine, but should show **active/inactive for the current project**, not just a static catalogue. |
| `profile` | Overloaded: `profile`, `profile <name>`, `profile <name> --apply` are three different operations. Split into `profile list` / `profile show <name>` / `profile apply <name>`. |
| `validate` | Misleading (§3.13). |
| **missing** | `diff`, `check` (CI mode, exit 1 on drift), `restore`, `remove`, `doctor`, `explain <file>`, `plugin new`, `completion` |

## 7.3 Flags and defaults

Missing across the board, in rough priority order:

- `--dry-run` — table-stakes for any tool that writes files. Currently impossible
  (§2.2/A1).
- `--yes / -y` — non-interactive confirm.
- `--force / --overwrite` — the merge/overwrite decision is hardcoded in every
  plugin call (`render_to_file(overwrite=False, merge=True)`); the **user has no way
  to influence it at all**.
- `--only <plugin,...>` / `--skip <plugin,...>` — partial sync.
- `--offline` — disable the gitignore.io call (§4.2).
- `--json` — machine-readable output for scripts and agents.
- `--quiet` — suppress everything but errors.
- `NO_COLOR` / `--no-color` — respected by Rich only partially.

Inconsistent option definitions today: `init --output` declares
`file_okay=False, dir_okay=True, writable=True`; `sync`/`add` declare only
`file_okay=False, dir_okay=True`; `profile`/`validate` declare neither. Extract one
shared `OutputDir` annotated type.

## 7.4 Error messages

Current:

```
Unknown plugin: 'eslnt'
```

Better:

```
Error: unknown plugin 'eslnt'

  Did you mean: eslint?

  Run `dotmaster list` to see all 13 available plugins.
```

Apply the same pattern (`difflib.get_close_matches`) to profiles and config enum
values. Every error should answer: what happened, why, and what to do next.

## 7.5 Confirmation & safety

- `init` asks one blunt question about overwriting *settings*, then rewrites files
  with no per-file confirmation and (per §3.7) no backup.
- The intended flow is: **plan → show diff → confirm → apply**.

```
$ dotmaster sync
  Analyzing 9 plugins…

  Files to create (3)
    + .github/workflows/ci.yml
    + docker-compose.yml
    + prisma/schema.prisma

  Files to update (2)
    ~ .gitignore          +4 lines
    ~ .eslintrc.json      merged: 2 new rules, your overrides preserved

  Conflicts (1)
    ! Dockerfile          modified since dotmaster generated it
                          [k]eep mine  [o]verwrite  [d]iff  [s]kip

  Proceed? [Y/n]
```

## 7.6 Discoverability

- Shell completion is enabled (`add_completion=True`) but not documented.
- No `--help` examples. Typer supports epilogs; every command should show one:
  ```
  Examples:
    dotmaster init --preset backend_api --yes
    dotmaster sync --dry-run
    dotmaster add docker --output ./services/api
  ```
- No man page, no `dotmaster docs` to open the website.

---

# 8. Phase 8 — Competitive analysis

## 8.1 The landscape

| Tool | Category | Scope | Update story | Language |
|---|---|---|---|---|
| **Cookiecutter** | Scaffolder | Whole project | None (one-shot) | Python |
| **Copier** | Scaffolder | Whole project | **Yes** — 3-way merge from `.copier-answers.yml` | Python |
| **Yeoman** | Scaffolder | Whole project | Weak | Node |
| **cargo-generate** | Scaffolder | Whole project | None | Rust |
| **Hygen** | Code generator | Files within a project | N/A | Node |
| **create-next-app / vite / t3** | Bootstrapper | Whole project, one stack | None | Node |
| **DotMaster** | **Config manager** | **Config layer of an existing project** | **Partial** (`sync`) | Python |

## 8.2 What DotMaster already does better than anyone

1. **Persisted, editable answers as the source of truth.** Only Copier shares this,
   and Copier's answers file is template-scoped; DotMaster's is *project*-scoped and
   human-authorable. `dotmaster.yaml` is a genuinely good idea.
2. **Multi-tool composition.** `create-next-app` gives you Next.js config; `eslint
   --init` gives you ESLint. Nobody composes linter + formatter + container + CI +
   DB + migrations from one coherent answer set.
3. **Works on *existing* projects.** Every scaffolder assumes an empty directory.
   That's the majority of real-world need — most repos already exist.
4. **Delegate-or-generate.** Preferring the official tool when present, with a
   template fallback, is the right instinct and nobody else does it systematically.
5. **CLI polish.** The wizard is nicer than Cookiecutter's flat prompt list.

## 8.3 What competitors have that DotMaster lacks

| Feature | Who has it | Priority for DotMaster |
|---|---|---|
| Remote/community templates (`gh:user/repo`) | Cookiecutter, Copier, cargo-generate | **High** |
| Update with 3-way merge + conflict markers | Copier | **High** |
| Conditional file inclusion in templates | All scaffolders | Medium |
| Post-generation hooks | Cookiecutter, Copier | Medium (`post_run` exists, undocumented) |
| Template versioning/pinning | Copier (`--vcs-ref`) | **High** |
| Non-interactive/data-file mode | All of them | **Critical** (§3.12) |
| Rich ecosystem of published templates | Cookiecutter (thousands) | Long-term |
| `--dry-run` / `--pretend` | Copier, Yeoman | **Critical** |
| Composability of sub-generators | Yeoman | Medium |
| Idempotency guarantees | Copier | **High** |

## 8.4 The differentiation thesis

DotMaster should stop competing with scaffolders and claim a category no one owns:

> **Declarative project configuration with drift detection.**
> `dotmaster.yaml` describes the intended configuration; `dotmaster sync` converges
> the repo to it; `dotmaster check` fails CI when the repo has drifted.
> *Terraform for your dotfiles.*

Three moves follow from that positioning, none of which any competitor is placed to
make:

1. **`dotmaster check` in CI.** Exit non-zero when generated config has drifted from
   `dotmaster.yaml`. Turns a one-shot generator into a continuously-enforced policy —
   and gets DotMaster into every PR of every adopting repo.
2. **Org profiles as installable packages.** A platform team publishes
   `acme-dotmaster-profile`; every repo does `dotmaster init --profile acme/backend`
   and stays in sync as the standard evolves. This is the enterprise wedge, and it is
   completely unserved today.
3. **Fleet upgrades.** When ESLint 9 changes config formats, DotMaster ships a
   migration and 10,000 repos run `dotmaster sync`. Cookiecutter can't do this
   structurally — it has no memory of what it generated.

## 8.5 Features to deliberately *not* build

- **Full project scaffolding** (source files, app structure). Cookiecutter/Copier own
  it, `create-*` tools own it per-framework, and it dilutes the "config layer"
  identity that makes DotMaster explicable in one sentence.
- **A DSL/scripting language for templates.** Cookiecutter's hooks and Yeoman's
  composability became their maintenance burden. Keep logic in Python plugins.
- **A GUI/web builder.** High effort, low retention for this audience.
- **Opt-out telemetry.** See §5.5.

---

# 9. Phase 9 — Missing features

## 9.1 Small wins (each ≤ 1 day)

| Feature | Why |
|---|---|
| `--dry-run` on all write commands | Table stakes (needs §2.2/A1) |
| `--yes`, `--force`, `--offline`, `--quiet`, `--json` | Automation & consent |
| `dotmaster remove <plugin>` | Deletes the plugin's files and its `generated` entries |
| "Did you mean…?" suggestions | §7.4 |
| `--help` examples on every command | §7.6 |
| Add `.dotmaster/` + `.dotmaster.log` to generated `.gitignore` | Stop littering |
| Backup retention (`--keep-backups`) | §3.19 |
| `dotmaster list` marks active plugins for the current project | §7.2 |
| Progress "Step 3 of 6" in the wizard | Perceived speed |
| `dotmaster --version --json` | Bug reports, agent use |

## 9.2 Medium features (2–5 days each)

| Feature | Notes |
|---|---|
| **`dotmaster diff`** | Show what `sync` would change. The confidence-builder. |
| **`dotmaster check`** | CI mode; exit 1 on drift. The strategic feature (§8.4). |
| **`dotmaster restore`** | Makes the existing backup system actually useful (§3.17). |
| **`dotmaster doctor`** | Detected stack, installed tools, plugin health, config problems. |
| **Stack auto-detection** | Read `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, lockfiles, `.git` to pre-answer the wizard. Turns 15 questions into 3. |
| **`package.json` plugin** | Injects `lint`/`format`/`test` scripts — fixes §3.16 and closes the biggest gap in the Node story. |
| **Non-interactive mode** | `--yes` + `--set` + `--from answers.yml` (§3.12). |
| **Pre-commit plugin** | `.pre-commit-config.yaml` generated from the same linter/formatter answers — very high value, trivially derived from data already collected. |
| **VS Code plugin** | `.vscode/settings.json` + `extensions.json` matching the chosen linter/formatter. Extremely popular, near-zero risk. |
| **Config JSON Schema** | Publish it; add the `yaml-language-server` modeline to generated files → autocomplete and validation in every editor. |

## 9.3 Major features (1–3 weeks each)

| Feature | Notes |
|---|---|
| **Plan/apply architecture** | §2.2/A1. Prerequisite for half of §9.1–9.2. |
| **Real plugin system** | §6.4. Prerequisite for community growth. |
| **Remote profiles & template packs** | `dotmaster init --profile gh:acme/standards@v2`, with pinning and hash verification. |
| **3-way merge with drift detection** | Store a hash (and optionally the content) of what was generated; on `sync`, compare disk vs. last-generated vs. new-generated. Preserve user edits, surface real conflicts. This is the hardest and most valuable engineering problem in the project. |
| **Monorepo support** | Per-workspace `dotmaster.yaml` with inheritance from the root; `dotmaster sync --recursive`. The current model assumes exactly one project per directory. |
| **Language-agnostic profile packs** | Ruby, PHP, Java/Kotlin, .NET, Rust plugins. Each is small; together they multiply the addressable audience. |

## 9.4 "Wow" features

1. **`dotmaster check` as a GitHub Action.** One YAML block in any repo:
   ```yaml
   - uses: dotmaster/check-action@v1     # fails the PR if config drifted
   ```
   Every adopting repo advertises DotMaster on every PR. This is the growth loop.
2. **`dotmaster explain <file>`** — "why does this file exist, which plugin owns it,
   which answer caused it, and what happens if I change it?" Nobody else can do this,
   because nobody else retains the provenance. Genuinely delightful.
3. **`dotmaster upgrade`** — "ESLint 9 changed its config format. DotMaster can
   migrate `.eslintrc.json` → `eslint.config.mjs`. Preview? [Y/n]". Turns DotMaster
   from a one-time generator into a subscription-grade utility.
4. **`dotmaster init --from-repo github.com/vercel/next.js`** — learn a configuration
   from a repository you admire and apply the equivalent to yours.
5. **Shareable config links.** `dotmaster init --from dm.sh/abc123` — a
   one-line-shareable stack, perfect for blog posts, tutorials, and conference talks.
6. **Time-travel:** `dotmaster history` / `dotmaster rollback` over the backup
   archives, with diffs. The backups already exist; only the UI is missing.

## 9.5 AI-powered features

Ordered by (value ÷ risk). The guiding principle: **AI proposes, deterministic code
disposes** — never let a model write files directly; have it emit a `dotmaster.yaml`
patch that goes through the normal plan → diff → confirm pipeline. That keeps output
reviewable and reproducible, and it is a genuine differentiator over "just ask an
assistant to write my config".

| Feature | Description | Risk |
|---|---|---|
| **Stack detection** (no LLM needed) | Deterministic file/lockfile analysis → pre-filled wizard. Do this first; it captures most of the value with none of the risk. | None |
| **`dotmaster explain --ai <file>`** | Natural-language explanation of a generated config, grounded in the file + the answers that produced it. Read-only. | Low |
| **`dotmaster suggest`** | Analyse the repo → "you have TypeScript but no linter; 87% of similar projects use ESLint. Add it?" Emits a config patch, not files. | Low |
| **`dotmaster init --describe "Next.js app with Postgres and Stripe"`** | NL → `dotmaster.yaml`, shown for confirmation before anything is written. Best possible onboarding demo. | Medium |
| **Migration assistant** | "Your ESLint config is legacy; here's the flat-config equivalent" — model drafts, deterministic validators (`eslint --print-config`) verify before offering. | Medium |
| **Modernization audit** | "Your Dockerfile installs as root, has no healthcheck, and pins no digest" — rule-based first, LLM only for prose. | Medium |
| **Conflict resolution assistant** | On a 3-way merge conflict, propose a resolution with reasoning. Always shows a diff. | Medium |
| ~~Freeform AI file generation~~ | Unreviewable, unreproducible, and abandons the whole value proposition. **Don't.** | High |

Implementation notes: keep AI **optional and pluggable** (`dotmaster-ai` as a
separate installable package), BYO-key, never on by default, never sending file
contents without explicit consent, and always with a non-AI fallback path.

---

# 10. Phase 10 — Open source health

## 10.1 Blocking gaps

| Item | Status | Severity |
|---|---|---|
| **`LICENSE` file** | **Missing** — `pyproject.toml` and README both claim MIT, but there is no license file in the repo | **Blocker.** Without it the code is legally "all rights reserved" for redistribution purposes. Fix today. |
| `CONTRIBUTING.md` | Missing | High |
| `CODE_OF_CONDUCT.md` | Missing | Medium |
| `SECURITY.md` | Missing | High (the tool writes files and makes network calls) |
| `CHANGELOG.md` | Missing | High |
| Issue templates | Missing | Medium |
| PR template | Missing | Medium |
| `dependabot.yml` | Missing | Medium |
| Repo URLs | **Wrong** — `pyproject.toml:37` points to `github.com/dotmaster/dotmaster`, README:125 says `your-org/dotmaster`; the real repo is `ahron-maslin/dotmaster` | High (broken links on PyPI) |
| `docs/` | Missing | High |
| `examples/` | Missing | High |
| Repo scratch files | `prompt.md` (the original AI build prompt) and `tree.yml` are committed at the repo root | Medium — delete or move to `docs/design/` |

## 10.2 README

Strengths: clear one-liner, quick start above the fold, tables, honest scope.

Fixes needed:
1. Remove/qualify claims that aren't true yet (custom plugins, `--preset` skipping
   the wizard).
2. Add a **demo GIF or asciinema** at the top — for a CLI this is the single highest
   converting element.
3. Add badges: CI, PyPI version, Python versions, license, downloads.
4. Add "Why not Cookiecutter/Copier?" — comparison tables drive adoption decisions.
5. Add a **disclosure of the gitignore.io network call** (§4.2).
6. Add "Status: beta — expect breaking changes before 1.0".

## 10.3 Contribution ramp

The plugin architecture is a gift for community contribution: each plugin is ~30
lines and independently testable. Exploit it deliberately:

- Label 15–20 "add a plugin for X" issues as `good first issue` with a checklist
  (Terraform, pre-commit, commitlint, husky, renovate, .nvmrc, Makefile,
  devcontainer, EditorConfig for more languages, Kubernetes manifests, Helm,
  golangci-lint, rustfmt/clippy, PHP-CS-Fixer, RuboCop, Checkstyle…).
- Publish a plugin authoring guide with a complete worked example (§6.5).
- Add a `plugins/CONTRIBUTING.md` checklist: tests, snapshot, docs row, `list` entry.
- Set up an "adopters" file and a plugin gallery page early — social proof compounds.

## 10.4 Branding & website

- The name is good: memorable, descriptive, available.
- Needs a logo/wordmark and a single hero line. Suggestion:
  **"One file. Every config. Always in sync."**
- Docs site: MkDocs Material or Docusaurus on GitHub Pages, with a live
  "configure your stack" playground that emits a `dotmaster.yaml` and previews the
  generated files in-browser (WASM Python or a small serverless renderer). That
  playground is also the best possible marketing asset.

---

# 11. Phase 11 — Growth & integrations

## 11.1 What users will ask for, in the order they'll ask

1. "Why doesn't it work in CI?" (§3.12)
2. "It overwrote my Dockerfile." (§3.5)
3. "Can it detect my existing stack?" (§9.2)
4. "Can I add my company's standards?" (org profiles, §8.4)
5. "Where's the plugin for `<my tool>`?" (§6.4)
6. "Can it update configs when tools release breaking changes?" (§9.4)
7. "Does it work in a monorepo?" (§9.3)
8. "Can I preview before it writes?" (§9.1)

## 11.2 Integration priority

| Integration | Effort | Impact | Notes |
|---|---|---|---|
| **GitHub Action (`dotmaster check`)** | S | **Very high** | The growth loop (§9.4). Do this first. |
| **pre-commit hook** | S | High | `repos: - repo: github.com/…/dotmaster` — puts DotMaster in the inner loop. |
| **VS Code extension** | M | High | Status bar drift indicator, "sync now", YAML schema, plugin catalogue browser. |
| **Claude Code / Cursor / Copilot skills** | S | High | Ship an MCP server or skill definition exposing `plan`, `diff`, `apply`. Agents are a fast-growing consumer of CLI tools and DotMaster's structured plan output is ideal for them — but only once non-interactive mode exists. |
| **GitLab CI component / Bitbucket pipe** | S | Medium | Parity with the GH Action. |
| **JetBrains plugin** | L | Medium | After VS Code proves demand. |
| **Homebrew / Scoop / winget / `uvx`** | S | High | Distribution beyond `pipx` is the #1 install friction. `uvx dotmaster init` should work today — document it. |
| **Renovate/Dependabot integration** | M | Medium | Auto-PR when a DotMaster template updates. Very sticky. |
| **Docker image** | S | Medium | `docker run -v $PWD:/app dotmaster/dotmaster init -y` for zero-install trials. |
| **Cloud providers (AWS/GCP/Azure scaffolds)** | L | Medium | Natural plugin territory; let the community own it. |

## 11.3 Distribution & adoption tactics

- `uvx dotmaster` / `pipx run dotmaster` in the README hero — zero-install trial.
- Submit plugins for popular stacks to the relevant awesome-lists.
- Write the "we standardised config across 200 repos" case study once one exists.
- The GitHub Action creates a public badge in adopters' READMEs — free distribution.

---

# 12. Phase 12 — Scalability architecture

## 12.1 Does the current architecture survive hundreds of plugins?

No. Specific breakages, in order of when they'd bite:

| Constraint | Breaks at | Why |
|---|---|---|
| `BUILTIN_PLUGINS` hardcoded list | ~1 third-party plugin | No discovery (§6.1) |
| Trigger DSL's closed `mapping` | ~20 plugins | Plugins can't introduce new config dimensions (§2.3/A3) |
| All plugins instantiated eagerly (`registry.all()`) | ~200 plugins | `dotmaster list` imports every plugin module → slow startup |
| Single flat `DotmasterConfig` | ~30 plugins | Every plugin knob must be added to the core schema |
| No output ownership | ~15 overlapping plugins | Silent clobbering (already happening, §3.10) |
| No execution order/dependency graph | ~10 interdependent plugins | `post_run` fires in registration order |
| Templates in one flat directory | ~100 templates | Name collisions between plugins |
| No plugin versioning enforcement | first breaking API change | Ecosystem-wide breakage |
| No caching of remote templates | first marketplace | Network per run |

## 12.2 Target architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ INTERFACES        cli/  ·  github-action  ·  vscode-ext  ·  mcp-server    │
├──────────────────────────────────────────────────────────────────────────┤
│ APPLICATION       commands: init · sync · diff · check · restore · plugin │
│                   ui/: Prompter protocol (interactive | scripted | flags) │
├──────────────────────────────────────────────────────────────────────────┤
│ CORE  (pure, no I/O — 100% unit-testable)                                 │
│   model/     Config (pydantic) · Schema registry · migrations             │
│   engine/    resolve(plugins, config) ─▶ Plan                             │
│               • dependency/topological ordering                           │
│               • output-ownership conflict detection                       │
│               • capability resolution ("lint.javascript" provided once)   │
│   merge/     strategies: json · yaml · toml · ini · markers · union       │
│   diff/      Plan ─▶ human diff / machine JSON                            │
├──────────────────────────────────────────────────────────────────────────┤
│ APPLY  (the ONLY layer that touches the filesystem)                       │
│   • snapshot → atomic writes (tmp + os.replace) → verify → commit         │
│   • rollback on any failure                                               │
│   • path containment enforcement (§4.1)                                   │
│   • state/lockfile update                                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ PLUGINS                                                                   │
│   api.py (versioned Protocol) · loader (entry points + local + remote)    │
│   sandbox: capability grants (fs scope · network · subprocess)            │
│   builtin/  ·  community (pip)  ·  project-local (.dotmaster/plugins/)    │
├──────────────────────────────────────────────────────────────────────────┤
│ REGISTRY (remote, optional)                                               │
│   index of plugins & profiles · semver · hashes · signatures · cache      │
└──────────────────────────────────────────────────────────────────────────┘
```

**Key changes vs today**

1. **Plan/apply split** (§2.2/A1) — the foundation for everything.
2. **Lazy plugin loading** — the registry reads entry-point *metadata* (name,
   summary, triggers) without importing the module; import happens only for plugins
   that match. Keeps `dotmaster list` instant at 1,000 plugins.
3. **Namespaced plugin ids and template dirs** — `acme.terraform` owns
   `templates/acme.terraform/*`; no global namespace.
4. **Plugin-scoped config sections** — plugins declare a schema fragment; the core
   schema stays small:
   ```yaml
   plugins:
     acme.terraform:
       backend: s3
       region: eu-west-1
   ```
5. **Capability-based conflict resolution** — plugins declare `provides =
   ("lint.python",)`; the engine errors if two active plugins provide the same
   capability, with a clear "choose one" message. Fixes §3.10 structurally.
6. **State file separate from answers.** `dotmaster.yaml` = intent (hand-editable,
   committed). `.dotmaster/state.json` = facts (generated-file inventory, content
   hashes, plugin versions, template version). This split enables drift detection and
   3-way merge, and stops §3.18's diff churn.

## 12.3 The state file — the enabler for everything

```json
{
  "schema": 1,
  "dotmaster_version": "1.0.0",
  "applied_at": "2026-07-26T10:00:00Z",
  "files": {
    ".github/workflows/ci.yml": {
      "plugin": "github_actions", "plugin_version": "2.1.0",
      "generated_sha256": "abc123…",     // what WE wrote
      "observed_sha256":  "abc123…",     // what's on disk now
      "strategy": "managed"
    }
  }
}
```

With `generated` vs `observed` hashes you get, essentially for free:

- **drift detection** → `dotmaster check` (the strategic feature, §8.4)
- **safe overwrite** → untouched files can be replaced silently; modified ones prompt
- **3-way merge** → base = last generated, ours = disk, theirs = new generation
- **`dotmaster remove`** → delete only files we own and the user hasn't changed
- **honest `sync` reporting** → "3 created, 2 updated, 1 unchanged, 1 conflict"

## 12.4 Marketplace considerations

- **Index, don't host.** Point at PyPI; the registry is a curated index with metadata,
  ratings, and verification badges. Far less operational burden and no artifact
  storage.
- **Lockfile.** `dotmaster.lock` pinning plugin name → version → sha256, so a team's
  configuration is reproducible and a compromised plugin release can't silently roll
  out.
- **Verification tiers.** `official` / `verified` / `community`, surfaced in
  `dotmaster plugin search`, with the trust model of §4.4 enforced at load time.
- **Conformance CI.** Plugins must pass the public conformance suite (§6.5) to be
  listed — keeps quality high as the ecosystem grows.

---

# 13. Phase 13 — Roadmap

Effort key: **S** ≤1 day · **M** 2–5 days · **L** 1–3 weeks · **XL** 1 month+

## 13.1 Critical fixes — this week (~2 weeks total)

| # | Item | Effort | Ref |
|---|---|---|---|
| 1 | Fix Jinja whitespace bugs in `github_ci.j2`, `gitlab_ci.j2`, `docker_compose.j2` | M | §3.1 |
| 2 | Add parse-validity tests over a stack matrix (the regression net) | M | §3.1 |
| 3 | Build `.eslintrc.json` / `.prettierrc` from Python dicts via `json.dumps` | S | §3.2 |
| 4 | Remove the global `parser` key from `.prettierrc` | S | §3.3 |
| 5 | **Add a `LICENSE` file**; fix repo URLs in `pyproject.toml` + README | S | §10.1 |
| 6 | Stop `merge_text` from duplicating whole files; markers or skip | M | §3.5 |
| 7 | Path containment check in `backup.py` and `render_to_file` | S | §4.1 |
| 8 | `delegate()` returns paths; record and report delegated files | S | §3.6 |
| 9 | Back up existing files on `init`, not just `sync` | S | §3.7 |
| 10 | Fix log-file pollution; scope logging to the `dotmaster` logger | S | §3.14 |
| 11 | Pre-select profile values in checkbox prompts | S | §3.11 |
| 12 | Make the gitignore.io call opt-in; document it | S | §4.2 |

## 13.2 Before v1.0 (~8–10 weeks)

| # | Item | Effort | Ref |
|---|---|---|---|
| 13 | **Plan/apply refactor** — `generate()` returns `FileAction`s | L | §2.2/A1 |
| 14 | `--dry-run` + `dotmaster diff` | M | §9.1, §9.2 |
| 15 | Non-interactive mode: `--yes`, `--set`, `--from` | M | §3.12 |
| 16 | Schema validation with pydantic + friendly config errors | M | §3.8, §3.13 |
| 17 | **Real plugin loading** via entry points + `plugins/api.py` | L | §6.4 |
| 18 | State file with content hashes; drift detection | L | §12.3 |
| 19 | `dotmaster check` (CI mode) | M | §8.4 |
| 20 | `dotmaster restore` + transactional apply/rollback | M | §3.17 |
| 21 | Replace the trigger DSL with `matches()` predicates | M | §2.3/A3 |
| 22 | Wizard `Prompter` protocol + wizard tests to ≥80% | M | §2.6 |
| 23 | Flat-config ESLint output; `package.json` scripts plugin | M | §3.4, §3.16 |
| 24 | Fix generated Dockerfiles (lockfiles, missing companion files) | M | §3.15 |
| 25 | CI: ruff + mypy + coverage floor + Windows/macOS + 3.13 | M | §5.2 |
| 26 | Config migrations (`version` handling + `dotmaster migrate`) | M | §5.4 |
| 27 | Docs site, CONTRIBUTING, SECURITY, CHANGELOG, examples | M | §10 |
| 28 | Plugin authoring guide + `dotmaster plugin new` + test harness | M | §6.5 |
| 29 | Stack auto-detection to pre-answer the wizard | M | §9.2 |
| 30 | Command surface cleanup (`profile` subcommands, `remove`, `doctor`) | M | §7.2 |

## 13.3 Nice to have (post-1.0, ~2 months)

| # | Item | Effort |
|---|---|---|
| 31 | GitHub Action wrapper for `dotmaster check` | S |
| 32 | pre-commit hook integration | S |
| 33 | VS Code extension (schema + drift indicator + sync) | L |
| 34 | Remote/org profiles with pinning and hash verification | L |
| 35 | 3-way merge with conflict UI | L |
| 36 | `dotmaster explain <file>` | M |
| 37 | Homebrew/Scoop/winget, Docker image | M |
| 38 | New plugins: pre-commit, VS Code settings, devcontainer, Terraform, renovate, commitlint, Makefile | M each |
| 39 | Monorepo / recursive sync | L |
| 40 | `dotmaster upgrade` (tool-format migrations) | L |

## 13.4 Future vision (6–18 months)

| # | Item | Effort |
|---|---|---|
| 41 | Plugin registry & marketplace with verification tiers | XL |
| 42 | `dotmaster.lock` reproducible configuration | L |
| 43 | AI layer as an optional package (`suggest`, `--describe`, migration assist) | XL |
| 44 | Web playground / shareable config links | L |
| 45 | Enterprise: policy enforcement, org dashboards, compliance reports | XL |
| 46 | Language coverage: Ruby, PHP, Java/Kotlin, .NET, Rust | XL |
| 47 | JetBrains plugin | L |

---

# 14. Phase 14 — CTO report

## Biggest strength

**The concept and the config model.** `dotmaster.yaml` as a durable, hand-editable
record of configuration intent — with the tool converging the repo toward it — is a
genuinely good idea that nobody in this category has executed on. Combined with a
plugin architecture where a new tool costs 30 lines, and a CLI that is already more
pleasant than Cookiecutter's, the foundations are in place. Most projects at this
stage have the opposite problem: polish without a thesis. This one has the thesis.

## Biggest weakness

**The product does not currently work.** Not in a subtle way: the GitHub Actions
workflow, GitLab CI file, multi-stage Compose file, and most ESLint configs it
generates are syntactically invalid and rejected by the tools they target. A user's
first `dotmaster init` on a realistic stack produces a repo where CI won't start.
That is a trust-destroying first impression, and no amount of roadmap fixes a
reputation for producing broken files.

The second-order weakness is *why* it shipped: **the test suite asserts substrings,
never validity.** 63 green tests and 59% coverage gave false confidence. The fix
(§3.1, item 2) is more important than the bug fix itself.

## Highest-risk technical debt

**Plugins perform I/O inside `generate()`.** Everything users will demand next —
dry-run, diff, drift detection, rollback, conflict resolution, CI checking — is
blocked behind this one decision, and it gets more expensive with every plugin
written against the current contract. Every week it's deferred, the migration cost
grows. Do it before the plugin API is published, because publishing it freezes the
contract for third parties.

Runner-up: the **README promises a plugin system that doesn't exist**. That is a
credibility liability the moment anyone tries it.

## Most impactful feature to build next

After the critical fixes: **`dotmaster check` — CI drift detection.** It converts a
one-shot generator into continuously-enforced policy, which is the difference between
a tool someone uses once and a tool an organisation depends on. It is also the growth
loop: a GitHub Action running in adopters' repos is free, credible distribution. It
depends on the state file (§12.3), which is also the prerequisite for safe merging —
so the same work unblocks the #1 data-safety concern *and* the #1 strategic feature.

## What should be removed

- `prompt.md` and `tree.yml` — build scratch, not source.
- The `triggers` string DSL as an *evaluation* mechanism (keep it as display metadata).
- `[tool.ruff]` from `pyproject_toml.j2` (duplicate of `ruff.toml`, §3.10).
- The `merge_text` strategy in its current form — it is worse than not merging.
- `typer[all]` — deprecated extra.
- The bottom-of-file `from typing import Any` in `base.py`.
- `dist/` artifacts from the working tree.

## What should be simplified

1. **Context construction** — pass the config object to templates instead of
   hand-building 10 near-identical dicts (~80 lines deleted, §2.3/D1).
2. **`profile --apply`** — replace 25 lines of repeated if-statements with one
   generic dataclass-walking merge.
3. **`validate`** — replace the if-ladder with a declarative rule list.
4. **Package-manager branching** — one `PackageManager` value object replaces ~12
   Jinja branches across two CI templates.
5. **`should_run`** — plain Python predicates instead of a mini-language.

## What should be refactored first

In strict order:

1. **Templates → validity** (§3.1, §3.2). Nothing else matters while output is broken.
2. **Test harness → parse every generated artifact.** Prevents recurrence.
3. **Plan/apply split** (§2.2/A1). Unblocks the roadmap.
4. **Config → pydantic.** Makes the "hand-edit the YAML" workflow safe.
5. **Plugin API v1 + entry-point loading.** Only after 3 and 4, so the published
   contract is the right one.

## Would I personally adopt this tool?

**Not today** — I'd generate a broken CI workflow on my first project and stop. But I
want it to exist, and I'd adopt it the day §13.1 ships. The `sync`-from-a-committed-
answers-file model solves a real problem I currently solve by copy-pasting from my
last repo.

## Would I recommend it to my engineering team?

Not at v0.2. At v1.0 with `check` and org profiles — **yes, enthusiastically**, and
for a specific reason: standardising configuration across dozens of repositories is a
recurring platform-engineering cost with no good off-the-shelf answer. That's a
budget line, not a nice-to-have.

## Could it become the standard tool for bootstrapping project configuration?

**Yes, with an important caveat about positioning.** As "another scaffolder" it
competes with Cookiecutter's thousand templates and every framework's `create-*`
command, and loses. As **"declarative project configuration with drift detection —
Terraform for your dotfiles"**, it competes with nothing, because that category is
empty. The technical distance between here and there is about 8–12 focused weeks; the
harder question is discipline about scope — resisting the pull toward full project
scaffolding, which would make the tool explicable in a paragraph instead of a
sentence.

The realistic ceiling: the default configuration layer for polyglot teams and
platform orgs, with a plugin ecosystem in the low hundreds. That is a very good
outcome for an OSS developer tool.

## My 6-month plan as maintainer

**Month 1 — Make it true.**
Ship §13.1 in the first two weeks; every claim in the README either works or leaves
the README. Add the artifact-validity test matrix, ruff + mypy + coverage floor +
Windows/macOS to CI. Add the LICENSE. Cut `v0.3.0` and say plainly in the release
notes that prior versions generated invalid CI files — owning it early costs far less
than being found out later.

**Month 2 — Make it safe.**
Plan/apply refactor. `--dry-run`, `dotmaster diff`, transactional apply, `restore`.
State file with content hashes. Non-interactive mode (`--yes`/`--set`), which
simultaneously unblocks CI use, agent use, and wizard testability. Cut `v0.4.0`.

**Month 3 — Make it extensible.**
Publish plugin API v1: `plugins/api.py`, entry-point discovery, capability
declarations, the trust/allowlist model, `dotmaster plugin new`, the test harness, and
the authoring guide. Seed 15 `good first issue` plugin requests. Cut `v0.5.0` and
start recruiting contributors in earnest — this is the month community growth either
starts or doesn't.

**Month 4 — Make it strategic.**
`dotmaster check` + the GitHub Action + the pre-commit hook. Stack auto-detection.
Remote/org profiles with pinning. This is the month DotMaster stops being a generator
and becomes infrastructure. Publish the "Terraform for your dotfiles" positioning
piece alongside it.

**Month 5 — Make it trustworthy.**
3-way merge with a real conflict UI. Config migrations. Docs site with the interactive
playground. Security review of the plugin sandbox before the ecosystem grows. Beta
program with 5–10 teams running `check` in CI, and fix whatever they hit.

**Month 6 — Ship 1.0.**
Freeze the plugin API and the `dotmaster.yaml` schema, publish the SemVer and
deprecation policy, Homebrew/Scoop/Docker distribution, VS Code extension, launch
post. Then immediately start the AI layer as a *separate optional package* — valuable,
but never on the critical path of the core tool's correctness.

**Throughout:** a hard rule that no template change merges without a parse-validity
test, and no feature merges that makes `plan()` impure. Those two rules would have
prevented every critical finding in this report.
