# dotmaster

> **Interactive dotfile generator and project configuration manager.**
>
> Answer a few questions, get a fully configured project — `.gitignore`, linting, formatting, testing, Docker, CI, and more, all in one place.

---

## Installation

```bash
# Recommended: install as a global tool via pipx
pipx install dotmaster

# Or install into your current environment
pip install dotmaster
```

---

## Quick Start

```bash
# Navigate to your project directory
cd my-new-project

# Run the guided wizard
dotmaster init
```

The wizard will ask you about your stack, and then generate all relevant dotfiles.

---

## Commands

| Command | Description |
|---|---|
| `dotmaster init` | Run the wizard and generate all dotfiles |
| `dotmaster sync` | Regenerate files from an existing `dotmaster.yaml` |
| `dotmaster add <plugin>` | Add or regenerate one plugin's files |
| `dotmaster list` | Show all available plugins |
| `dotmaster profile [name]` | Inspect or apply a preset profile |
| `dotmaster validate` | Check `dotmaster.yaml` for inconsistencies |

---

## Preset Profiles

Skip the wizard entirely with `--preset`:

```bash
dotmaster init --preset web_app      # React/Next.js + ESLint + Prettier + Docker + CI
dotmaster init --preset backend_api  # Python + FastAPI + Ruff + Docker + CI
dotmaster init --preset library      # ESLint + Jest, no Docker
dotmaster init --preset monorepo     # pnpm + ESLint + CI
```

---

## Generated Files

Depending on your answers, dotmaster can generate:

| File | Plugin |
|---|---|
| `.gitignore` | `gitignore` (via gitignore.io API or template) |
| `.eslintrc.json` + `.eslintignore` | `eslint` |
| `.prettierrc` + `.prettierignore` | `prettier` |
| `.editorconfig` | `editorconfig` |
| `Dockerfile` + `.dockerignore` | `docker` |
| `.github/workflows/ci.yml` | `github_actions` |
| `.gitlab-ci.yml` | `gitlab_ci` |
| `pyproject.toml` | `pyproject` |
| `.env.example` | `dotenv` |
| `ruff.toml` | `ruff` |

---

## dotmaster.yaml

All answers are persisted in `dotmaster.yaml` at the root of your project:

```yaml
version: "1"
project:
  name: my-app
  description: A web application
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
  env_file: true
  editorconfig: true
profile: web_app
```

Edit it directly, then run `dotmaster sync` to re-generate.

---

## Plugin System

Each tool is implemented as a **plugin** with two strategies:

1. **Delegate** — hand off to the official CLI tool if available (e.g. gitignore.io API for `.gitignore`)
2. **Generate** — fall back to a high-quality Jinja2 template

You can add custom plugins by subclassing `dotmaster.plugins.base.BasePlugin`.

---

## Development

```bash
git clone https://github.com/your-org/dotmaster
cd dotmaster
pip install -e ".[dev]"
pytest
```

---

## License

MIT
