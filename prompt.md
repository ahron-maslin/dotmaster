Build a CLI tool called "dotmaster" that interactively generates and manages project dotfiles.

Core idea:
The tool asks the user a series of questions about their project, then generates all necessary config files (dotfiles) or delegates to the official tools when possible.

Flow:
1. Run `dotmaster init`
2. CLI asks structured questions (Q&A style)

Questions should include:
- What language(s)? (JS, Python, Go, etc.)
- Framework? (React, Next.js, Django, etc.)
- Package manager? (npm, yarn, pnpm, pip, poetry)
- Linting? (ESLint, Ruff, none)
- Formatting? (Prettier, Black, none)
- Testing? (Jest, Pytest, none)
- Containerization? (Docker yes/no)
- CI/CD? (GitHub Actions, GitLab CI, none)
- Environment config? (.env needed?)
- Editor config? (.editorconfig yes/no)

Behavior:
- Based on answers, generate appropriate dotfiles:
  (.gitignore, .eslintrc, .prettierrc, pyproject.toml, Dockerfile, etc.)
- When possible, call official generators:
  (e.g., `eslint --init`, `create-next-app`, `poetry init`)
- Otherwise, use high-quality templates

Advanced features:
- Store answers in a single `dotmaster.yaml`
- Allow regeneration (`dotmaster sync`)
- Allow partial updates
- Plugin system for new tools
- Preset profiles (web app, library, backend API, etc.)

Output:
- Clean project structure
- All relevant dotfiles generated
- Minimal duplication
- Clear comments inside generated files

Goal:
Make project setup fast, consistent, and centralized via guided Q&A.
