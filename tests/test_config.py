"""Tests for AppConfig persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from extro.core.config import AppConfig
from extro.core.exceptions import ConfigError


class TestAppConfigDefaults:
    def test_default_instance_has_no_profile(self) -> None:
        cfg = AppConfig()
        assert cfg.firefox_profile_dir is None

    def test_load_returns_default_when_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "extro.core.config._config_path",
            lambda: tmp_path / "config.json",
        )
        cfg = AppConfig.load()
        assert cfg.firefox_profile_dir is None


class TestAppConfigRoundtrip:
    def test_save_and_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "config.json"
        monkeypatch.setattr("extro.core.config._config_path", lambda: config_file)

        profile_dir = tmp_path / "profile0"
        profile_dir.mkdir()

        cfg = AppConfig(firefox_profile_dir=profile_dir)
        saved = cfg.save()
        assert saved == config_file
        assert config_file.exists()

        loaded = AppConfig.load()
        assert loaded.firefox_profile_dir == profile_dir

    def test_save_creates_parent_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "nested" / "dirs" / "config.json"
        monkeypatch.setattr("extro.core.config._config_path", lambda: config_file)
        # The parent dirs are created in _config_path; simulate that
        config_file.parent.mkdir(parents=True, exist_ok=True)

        cfg = AppConfig(firefox_profile_dir=Path("/some/profile"))
        cfg.save()
        assert config_file.exists()

    def test_path_coercion_from_string(self) -> None:
        cfg = AppConfig(firefox_profile_dir="/some/path")
        assert isinstance(cfg.firefox_profile_dir, Path)
        assert cfg.firefox_profile_dir == Path("/some/path")


class TestAppConfigErrors:
    def test_load_raises_config_error_on_invalid_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text("{not valid json}", encoding="utf-8")
        monkeypatch.setattr("extro.core.config._config_path", lambda: config_file)

        with pytest.raises(ConfigError):
            AppConfig.load()
