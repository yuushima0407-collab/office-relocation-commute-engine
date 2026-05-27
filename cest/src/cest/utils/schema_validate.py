from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from jsonschema import Draft202012Validator

_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "schemas"

_RESPONSE_VALIDATOR: Optional[Draft202012Validator] = None


def _get_response_validator() -> Draft202012Validator:
    global _RESPONSE_VALIDATOR
    if _RESPONSE_VALIDATOR is not None:
        return _RESPONSE_VALIDATOR

    schema_path = _SCHEMA_DIR / "evaluation_report_v0.3.3.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    _RESPONSE_VALIDATOR = Draft202012Validator(schema)
    return _RESPONSE_VALIDATOR


def validate_response(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    """Validate response against v0.3.3 schema. Returns list of errors."""
    v = _get_response_validator()
    errors = sorted(v.iter_errors(payload), key=lambda e: list(e.path))

    items = []
    for e in errors[:20]:
        path = ".".join(str(x) for x in e.path) if e.path else "$"
        items.append({"path": path, "message": e.message})

    return items
