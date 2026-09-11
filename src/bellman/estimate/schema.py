"""Load the shipped project-estimate JSON Schema."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from bellman.estimate.simulate import SCHEMA_VERSION


def load_estimate_schema() -> dict[str, Any]:
    """Return the JSON Schema for ``bellman estimate --json`` output.

    Returns:
        Parsed JSON Schema document whose ``x-schema-version`` matches
        :data:`bellman.estimate.simulate.SCHEMA_VERSION`.

    Raises:
        FileNotFoundError: When the schema resource is missing from the
            package.
        ValueError: When the schema file is not valid JSON.
    """
    path = files("bellman.estimate.schemas").joinpath(
        f"project_estimate-{SCHEMA_VERSION}.json"
    )
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        msg = f"estimate schema {SCHEMA_VERSION} is not installed"
        raise FileNotFoundError(msg) from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"estimate schema {SCHEMA_VERSION} is not valid JSON"
        raise ValueError(msg) from exc
    if not isinstance(document, dict):
        msg = f"estimate schema {SCHEMA_VERSION} must be a JSON object"
        raise ValueError(msg)
    return document
