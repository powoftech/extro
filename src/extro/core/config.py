from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import platformdirs
from pydantic import BaseModel, field_validator

from extro.core.exceptions import ConfigError

_APP_NAME = "extro"
_CONFIG_FILE = "config.json"


def _config_path() -> Path:
    """Return the platform-appropriate path for extro's config file."""
    config_dir = Path(platformdirs.user_config_dir(_APP_NAME, appauthor=False))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / _CONFIG_FILE


class AppConfig(BaseModel):
    """Persisted application configuration."""

    firefox_profile_dir: Path | None = None

    @field_validator("firefox_profile_dir", mode="before")
    @classmethod
    def _coerce_path(cls, v: str | Path | None) -> Path | None:
        if v is None:
            return None
        return Path(v)

    @classmethod
    def load(cls) -> AppConfig:
        """Load config from disk. Returns a default instance if not found.

        Raises:
            ConfigError: If the file exists but cannot be parsed.
        """
        path = _config_path()
        if not path.exists():
            return cls()

        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            msg = f"Failed to read config from {path}: {exc}"
            raise ConfigError(msg) from exc

        return cls.model_validate(data)

    def save(self) -> Path:
        """Persist the current config to disk.

        Returns:
            The path where the config was written.

        Raises:
            ConfigError: If the file cannot be written.
        """
        path = _config_path()
        payload: dict[str, Any] = {}

        if self.firefox_profile_dir is not None:
            payload["firefox_profile_dir"] = str(self.firefox_profile_dir)

        try:
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            msg = f"Failed to write config to {path}: {exc}"
            raise ConfigError(msg) from exc

        return path
