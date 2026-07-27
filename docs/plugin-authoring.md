# Writing a dotmaster plugin

A plugin turns configuration into files. The whole contract lives in
`dotmaster.plugins.api` — that's the only module a plugin should import from
`dotmaster.*`; everything else is internal and may change between releases.

## Minimal example

```python
from dotmaster.plugins.api import Plugin, Context, FileAction

class TerraformPlugin(Plugin):
    name = "terraform"                    # unique, namespaced for third parties: "acme.terraform"
    description = "Generates a Terraform skeleton"
    provides = ("iac.terraform",)         # capability tag — two plugins can't both provide this
    outputs = ("main.tf", "variables.tf")  # declared for `dotmaster list` and conflict detection

    def matches(self, config) -> bool:
        return config.plugins.settings.get("terraform", {}).get("enabled", False)

    def plan(self, config, ctx: Context) -> list[FileAction]:
        content = ctx.render("terraform_main.j2", project_name=config.project.name)
        return [self.file("main.tf", content)]
```

## The one rule that matters: `plan()` is pure

`plan()` may read the project directory (`ctx.read`, `ctx.exists`) and render
templates (`ctx.render`), but it must **never** write. Return `FileAction`
objects describing what you want to exist; the engine
(`dotmaster.core.engine`) decides what actually changes on disk after
comparing your request against what's already there. This is what makes
`--dry-run`, `dotmaster diff`, and rollback-on-failure possible — a plugin
that writes directly breaks all three, and fails
`tests/test_plugin_contract.py`'s purity check.

## Generating structured files: build data, not strings

For JSON, build a `dict` and call `self.json_file(...)`:

```python
def plan(self, config, ctx):
    data = {"root": True, "rules": {"no-console": "warn"}}
    return [self.json_file(".eslintrc.json", data)]
```

**Do not** hand-assemble JSON inside a Jinja template with conditional commas
— that's precisely how invalid JSON shipped in dotmaster's early history
(`{% if x %}, {% endif %}` is a missing- or trailing-comma bug waiting to
happen). If your output format has no Python serializer (YAML/TOML front
matter, INI, a bespoke DSL), render it with a template but make every
`{% if %}` / `{% for %}` tag own its whole line — `trim_blocks` +
`lstrip_blocks` are enabled, and an inline tag silently eats the
indentation or newline around it.

## Merge strategies

| Strategy | When to use | Behavior on an existing file |
|---|---|---|
| `MergeStrategy.MERGE` (default for `.json`/`.yaml`/`.toml`) | Structured config | Deep-merges; the user's existing values always win, new keys are added |
| `MergeStrategy.MANAGED_BLOCK` | Ignore files, anything append-only | Replaces only the region between dotmaster's markers; content outside is the user's and is preserved |
| `MergeStrategy.OVERWRITE` | Whole-program files (Dockerfile, CI YAML) | Full replace *only* if dotmaster still owns the file unmodified; otherwise reported as a conflict, never silently clobbered |
| `MergeStrategy.CREATE_ONLY` | Scaffolding meant to be hand-edited after generation (e.g. a migration env file) | Written once; never touched again |

`self.file(path, content)` without an explicit `strategy=` picks a sensible
default from the file's extension via `dotmaster.core.merge.default_strategy`.

## Using the network or a subprocess

Go through `ctx.fetch(url)` / `ctx.run(cmd)`, never `urllib`/`subprocess`
directly:

- `ctx.fetch` returns `None` whenever the project is configured offline
  (the default), enforcing user consent to network access in one place.
- `ctx.run` returns `None` if the command isn't on `PATH`, so you don't need
  a separate `shutil.which` check.

Always have a working fallback when `fetch`/`run` return `None` — dotmaster
must never *require* the network or an external tool to produce output.

## Registering a third-party plugin

```toml
# your package's pyproject.toml
[project.entry-points."dotmaster.plugins"]
terraform = "dotmaster_terraform:TerraformPlugin"
```

Nothing outside the built-ins loads automatically — the user opts in per
project:

```yaml
# dotmaster.yaml
plugins:
  allow: [terraform]        # or ["*"] to trust every installed plugin
  settings:
    terraform:
      enabled: true
```

## Testing your plugin

```python
def test_writes_main_tf(tmp_path):
    from dotmaster.plugins.api import Context
    plugin = TerraformPlugin()
    ctx = Context(root=tmp_path, config=my_test_config())
    actions = plugin.plan(my_test_config(), ctx)
    assert [str(a.path) for a in actions] == ["main.tf"]
```

Run it through the real engine + a parser to catch template bugs, the same
way `tests/test_artifact_validity.py` does for the built-ins:

```python
from dotmaster.core.engine import build_plan
from dotmaster.core.apply import apply_plan

plan = build_plan(config, tmp_path, [TerraformPlugin()])
apply_plan(plan, tmp_path, backup=False)
# then actually parse the file you wrote — don't just check a substring.
```
