from __future__ import annotations

from functools import cache
from importlib import import_module
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from typing import Final

APP_NAME: Final = "extro"
DISTRIBUTION_NAME: Final = "extro"
UNKNOWN_VERSION: Final = "0+unknown"


def _installed_distribution_version() -> str | None:
    try:
        return distribution_version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return None


def _generated_version() -> str | None:
    try:
        module = import_module("extro._version")
    except ModuleNotFoundError as exc:
        if exc.name != "extro._version":
            raise
        return None

    version = getattr(module, "VERSION", None)
    if isinstance(version, str):
        return version
    return None


@cache
def get_app_version() -> str:
    return _installed_distribution_version() or _generated_version() or UNKNOWN_VERSION
