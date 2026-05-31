"""Read and write bellman-state.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from bellman.update.paths import state_read_path, state_write_path


@dataclass
class BellmanState:
    last_update_check: datetime | None = None
    installed_version: str | None = None
    installed_asset_id: int | None = None

    @classmethod
    def load(cls) -> BellmanState:
        path = state_read_path()
        if path is None:
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        last_check = raw.get("last_update_check")
        parsed_check: datetime | None = None
        if isinstance(last_check, str):
            try:
                parsed_check = datetime.fromisoformat(last_check)
                if parsed_check.tzinfo is None:
                    parsed_check = parsed_check.replace(tzinfo=UTC)
            except ValueError:
                parsed_check = None
        asset_id = raw.get("installed_asset_id")
        return cls(
            last_update_check=parsed_check,
            installed_version=raw.get("installed_version"),
            installed_asset_id=int(asset_id) if asset_id is not None else None,
        )

    def save(self) -> None:
        path = state_write_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {}
        if self.last_update_check is not None:
            payload["last_update_check"] = self.last_update_check.astimezone(
                UTC
            ).isoformat()
        if self.installed_version is not None:
            payload["installed_version"] = self.installed_version
        if self.installed_asset_id is not None:
            payload["installed_asset_id"] = self.installed_asset_id
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def touch_check_time(self) -> None:
        self.last_update_check = datetime.now(UTC)
        self.save()
