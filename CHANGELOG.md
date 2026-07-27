# Changelog

All notable changes to this project are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [0.3.0] — Unreleased

A ground-up hardening pass following a full technical review. Versions prior
to this generated **syntactically invalid output** in the majority of
configurations — see below. If you ran `dotmaster init` or `dotmaster sync`
with an earlier version, re-run `dotmaster sync --force` after upgrading to
regenerate correct files.

### Fixed — critical

- **CI workflows, `docker-compose.yml`, and most `.eslintrc.json` files were
  syntactically invalid.** Jinja's `trim_blocks`/`lstrip_blocks` options
  don't tolerate `{% if %}` tags used inline as value emitters, which is how
  every affected template was written; GitHub Actions, GitLab CI and
  multi-stage Compose output had broken YAML indentation, and non-React
  ESLint configs had a missing or trailing JSON comma. All four templates
  were rewritten so every control-flow tag owns its own line, and JSON
  configs are now built from Python dicts (`json.dumps`) instead of
  hand-assembled inside templates — this class of bug is now structurally
  prevented for JSON output, and covered by
  `tests/test_artifact_validity.py`, which parses every generated file
  across a matrix of real stacks.
- **User edits to generated files could be silently destroyed.** The old
  text-merge strategy appended whole-file content after existing content on
  any change, which could leave a Dockerfile with two `FROM` stages (Docker
  builds the last one — the edit silently vanished). Merging is now
  strategy-aware per file type (`MergeStrategy.MERGE` /
  `MANAGED_BLOCK` / `OVERWRITE` / `CREATE_ONLY`), and any file dotmaster
  doesn't fully own that would require an unsafe overwrite is reported as a
  **conflict** and left untouched unless you pass `--force`.
- **Path traversal in backups.** A crafted `dotmaster.yaml`/state file could
  cause the backup step to read and copy files from outside the project
  directory. All paths are now resolved and checked for containment
  (`dotmaster.core.engine.safe_target`) before any read, write, or delete.
- **`dotmaster init` never backed up existing files** before overwriting
  them — only `sync` did. Both commands now back up through the same path.

### Changed — architecture

- **New plan → diff → apply pipeline.** Plugins no longer write to disk.
  `plugin.plan()` returns a list of `FileAction`s describing intent; the
  engine (`dotmaster.core.engine`) resolves those against the project and the
  new `.dotmaster/state.json` ledger into a `Plan`; only
  `dotmaster.core.apply` touches the filesystem, atomically and
  transactionally (any failure mid-batch rolls the whole run back). This is
  what makes `--dry-run`, `dotmaster diff`, and `dotmaster check` possible.
- **New plugin contract** (`dotmaster.plugins.api.Plugin`). The old
  `BasePlugin` (`should_run`/`delegate`/`generate`) is kept as a deprecated
  alias in `dotmaster.plugins.base` but existing third-party plugins need to
  be ported to `matches()`/`plan()` to actually run.
- **Real third-party plugin discovery.** Plugins register via the
  `dotmaster.plugins` entry-point group or `.dotmaster/plugins/*.py`, gated
  by an explicit `plugins.allow` list in `dotmaster.yaml` — previously the
  registry only ever loaded the hardcoded built-in list, so no third-party
  plugin could actually be loaded regardless of what the README said.
- **Config is now schema-validated** (pydantic). Unknown keys, wrong types,
  and misspelled enum values (`linter: eslintt`) now produce a specific error
  with a "did you mean" suggestion instead of a raw traceback or, worse,
  silent acceptance.
- **State split from intent.** `dotmaster.yaml` records what you want
  (hand-editable, meant to be committed); `.dotmaster/state.json` records
  what was actually generated and its content hash. This is what enables
  drift detection and safe regeneration, and stops the answers file from
  changing on every no-op `sync`.

### Added

- `dotmaster diff` — show what `sync` would change, without changing it.
- `dotmaster check` — exit non-zero on drift; designed for CI.
- `dotmaster restore [--list] [--at <name>]` — restore from a backup archive
  (backups were write-only before; there was no restore path).
- `dotmaster remove <plugin>` — delete a plugin's generated files (only ones
  still byte-identical to what was generated; edited files are left alone).
- `dotmaster doctor` — detected stack, installed tools, plugin health, drift.
- `--yes`, `--set key=value`, `--dry-run`, `--force`, `--offline/--online`
  flags across the write commands, and `--output` normalized everywhere.
  `dotmaster init --preset X --yes` now actually skips every prompt — before,
  `--preset` only pre-filled defaults but still asked every question, and
  there was no way to run dotmaster non-interactively at all.
- `package_json` plugin: adds the `lint`/`format`/`test` scripts the
  generated CI workflows call, when a `package.json` already exists — CI
  previously called `npm run lint` against a `package.json` with no such
  script.
- `pre_commit` plugin: generates `.pre-commit-config.yaml` from the same
  linter/formatter answers already collected.
- ESLint now generates flat config (`eslint.config.mjs`) by default — the
  format ESLint 9 uses; the legacy `.eslintrc.json` + `.eslintignore` output
  is available via `plugins.settings.eslint.legacy: true`.
- Offline by default: the gitignore.io network call (previously silent and
  undocumented) is now opt-in via `options.offline: false`, size-capped, and
  sanity-checked before being trusted for `.gitignore`.

### Fixed — other

- `ruff.toml` and `pyproject.toml`'s `[tool.ruff]` no longer both try to own
  Ruff configuration for the same project.
- `.prettierrc` no longer sets a top-level `parser`, which previously forced
  the TypeScript parser onto every file Prettier touched, including
  non-TypeScript ones.
- Generated Python Dockerfiles now copy the actual lockfile
  (`poetry.lock*`/`uv.lock*`, glob-optional) instead of assuming one exists,
  and the plain-pip path installs from `pyproject.toml` when no
  `requirements.txt` is present instead of failing the build on `COPY`.
- Log file no longer written to the project directory (or created at all) on
  `--version`/`--help`; logging now goes to the platform state directory and
  is scoped to dotmaster's own logger instead of hijacking the root logger.
- Successfully delegated files (e.g. from the gitignore.io fetch) are now
  correctly recorded and counted — previously `delegate() -> bool` discarded
  the path, so those files were invisible to backups and reporting.
- `dotmaster validate` now checks enum values, not just cross-field
  consistency — `linter: eslintt` used to pass validation silently.
- Preset profiles now actually pre-select checkbox defaults (languages,
  database engines) in the wizard; previously `default=` only moved the
  cursor and never pre-checked anything, so `--preset web_app` presented an
  empty language selection.
- Added `LICENSE` (MIT, as already declared in `pyproject.toml`); fixed the
  repository URL, which pointed at a placeholder org in both `pyproject.toml`
  and the README.

## [0.2.x] and earlier

See git history. Not recommended for use — see the "Fixed — critical"
section above.
