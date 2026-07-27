"""
tests/test_schema.py
Keeps schema/dotmaster.schema.json (referenced by the $schema hint every
generated dotmaster.yaml carries, for editor autocomplete) from silently
drifting out of sync with the actual config model.
"""

from __future__ import annotations

import json
from pathlib import Path

from dotmaster.config import DotmasterConfig

SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "dotmaster.schema.json"


def test_schema_file_matches_current_model():
    on_disk = json.loads(SCHEMA_PATH.read_text())
    current = DotmasterConfig.model_json_schema()
    current["$schema"] = "http://json-schema.org/draft-07/schema#"
    current["title"] = "dotmaster.yaml"
    assert on_disk == current, (
        "schema/dotmaster.schema.json is stale — regenerate it:\n"
        '  python -c "import json; from dotmaster.config import DotmasterConfig; '
        "s = DotmasterConfig.model_json_schema(); "
        "s['$schema'] = 'http://json-schema.org/draft-07/schema#'; s['title'] = 'dotmaster.yaml'; "
        "json.dump(s, open('schema/dotmaster.schema.json', 'w'), indent=2)\""
    )
