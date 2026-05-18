from __future__ import annotations

import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path
from types import ModuleType

from typer.testing import CliRunner

import extro
import extro.app.version as app_version
from extro.app.version import UNKNOWN_VERSION, get_app_version
from extro.main import app

PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _pyproject_version() -> str:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return pyproject["project"]["version"]


def test_installed_version_matches_pyproject() -> None:
    assert distribution_version("extro") == _pyproject_version()


def test_app_version_matches_installed_distribution() -> None:
    get_app_version.cache_clear()

    assert get_app_version() == distribution_version("extro")


def test_package_version_matches_app_version() -> None:
    get_app_version.cache_clear()

    assert extro.__version__ == get_app_version()


def test_version_flag_prints_version_and_exits() -> None:
    get_app_version.cache_clear()

    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"extro {distribution_version('extro')}"


def test_app_version_uses_generated_fallback(monkeypatch) -> None:
    def missing_distribution(_name: str) -> str:
        raise PackageNotFoundError

    generated_module = ModuleType("extro._version")
    generated_module.VERSION = "1.2.3"
    monkeypatch.setattr(app_version, "distribution_version", missing_distribution)
    monkeypatch.setitem(sys.modules, "extro._version", generated_module)
    get_app_version.cache_clear()

    assert get_app_version() == "1.2.3"


def test_app_version_uses_unknown_fallback(monkeypatch) -> None:
    def missing_distribution(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(app_version, "distribution_version", missing_distribution)
    monkeypatch.delitem(sys.modules, "extro._version", raising=False)
    get_app_version.cache_clear()

    assert get_app_version() == UNKNOWN_VERSION
