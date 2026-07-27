"""
tests/test_schema.py
Keeps schema/dotmaster.schema.json (referenced by the $schema hint every
generated dotmaster.yaml carries, for editor autocomplete) from silently
drifting out of sync with the actual config model.

This intentionally does NOT assert byte-for-byte equality against a freshly
generated schema: pydantic's JSON Schema *shape* (ref styles, anyOf nesting,
$defs naming) legitimately differs between pydantic versions, so an exact
comparison flakes on every routine pydantic bump — Dependabot is configured
to propose those weekly. What must never drift is the set of fields the
schema actually documents.
"""

from __future__ import annotations

import json
from pathlib import Path

from dotmaster.config import DotmasterConfig

SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "dotmaster.schema.json"

REGENERATE_HINT = (
    'python -c "import json; from dotmaster.config import DotmasterConfig; '
    "s = DotmasterConfig.model_json_schema(); "
    "s['$schema'] = 'http://json-schema.org/draft-07/schema#'; s['title'] = 'dotmaster.yaml'; "
    "json.dump(s, open('schema/dotmaster.schema.json', 'w'), indent=2)\""
)


def _field_names(model) -> set[str]:
    names = set(model.model_fields)
    for field in model.model_fields.values():
        nested = getattr(field.annotation, "model_fields", None)
        if nested:
            names |= set(nested)
    return names


def test_schema_file_is_valid_json():
    json.loads(SCHEMA_PATH.read_text())


def test_schema_file_covers_every_current_field():
    on_disk_text = SCHEMA_PATH.read_text()
    missing = [name for name in _field_names(DotmasterConfig) if name not in on_disk_text]
    assert not missing, (
        f"schema/dotmaster.schema.json is missing field(s) {missing} — regenerate it:\n  {REGENERATE_HINT}"
    )


def test_schema_file_has_no_stale_fields():
    on_disk = json.loads(SCHEMA_PATH.read_text())
    documented = set(on_disk.get("properties", {}))
    current = set(DotmasterConfig.model_fields)
    stale = documented - current
    assert not stale, (
        f"schema/dotmaster.schema.json documents removed field(s) {stale} — regenerate it:\n  {REGENERATE_HINT}"
    )
