# Security Policy

## Supported versions

Only the latest released version of dotmaster receives security fixes.

## Reporting a vulnerability

Please report security issues privately via
[GitHub Security Advisories](https://github.com/ahron-maslin/dotmaster/security/advisories/new)
rather than a public issue. If that isn't available to you, open an issue
with minimal detail and ask a maintainer to reach out for a private channel.

Include, where possible:

- A description of the vulnerability and its potential impact.
- Steps to reproduce (a minimal `dotmaster.yaml` / project layout is ideal).
- The dotmaster version (`dotmaster --version`).

We aim to acknowledge reports within 5 business days.

## Scope

dotmaster writes files to your project and, only when `options.offline: false`
is explicitly set, makes a single outbound request to gitignore.io. Relevant
security properties to know about:

- **Path containment.** Every write is checked to stay inside the project
  root (`dotmaster.core.engine.safe_target`) — a crafted `dotmaster.yaml` or
  `.dotmaster/state.json` cannot direct dotmaster to write or read outside
  the project directory. If you find a way around this, that's a P0 report.
- **Template sandboxing.** Built-in templates render through a
  `jinja2.sandbox.SandboxedEnvironment`. Third-party plugin templates are
  expected to do the same via `Context.render`.
- **Plugin trust.** Third-party plugins are code that runs with your
  privileges. Nothing beyond the built-ins loads unless named in
  `plugins.allow` in `dotmaster.yaml`. Treat plugin authorship the same as
  any other dependency you'd `pip install`.
- **Network egress is opt-in.** `options.offline` defaults to `true`; no
  request leaves the machine unless a project's config explicitly disables
  it, and even then responses are size-capped and content-type checked
  before being trusted.

Vulnerabilities in a third-party plugin you've installed are that plugin's
responsibility to fix, but we're happy to help coordinate disclosure if it
affects the plugin API contract itself.
