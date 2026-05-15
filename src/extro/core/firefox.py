from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from extro.core.exceptions import FirefoxNotFoundError, NoProfilesError


@dataclass(frozen=True)
class FirefoxProfile:
    """Represents a single Firefox user profile."""

    name: str
    path: Path
    is_default: bool

    def __str__(self) -> str:
        marker = " [default]" if self.is_default else ""
        return f"{self.name}{marker}"


def _profiles_ini_path() -> Path:
    """Return the platform-specific path to Firefox's profiles.ini."""
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if not appdata:
            msg = "APPDATA environment variable is not set."
            raise FirefoxNotFoundError(msg)
        return Path(appdata) / "Mozilla" / "Firefox" / "profiles.ini"

    if sys.platform == "darwin":
        return (
            Path.home() / "Library" / "Application Support" / "Firefox" / "profiles.ini"
        )

    # Linux / BSD / other POSIX
    return Path.home() / ".mozilla" / "firefox" / "profiles.ini"


def get_firefox_profiles() -> list[FirefoxProfile]:
    """Parse Firefox's profiles.ini and return all available profiles.

    Returns:
        A list of :class:`FirefoxProfile` instances, default profile first.

    Raises:
        FirefoxNotFoundError: If profiles.ini cannot be found.
        NoProfilesError: If the file contains no readable profiles.
    """
    ini_path = _profiles_ini_path()

    if not ini_path.exists():
        msg = (
            f"Firefox profiles.ini not found at: {ini_path}\n"
            "Please make sure Firefox is installed and has been launched at least once."
        )
        raise FirefoxNotFoundError(msg)

    config = configparser.ConfigParser(strict=False)
    config.read(ini_path, encoding="utf-8")

    profiles: list[FirefoxProfile] = []

    for section in config.sections():
        if not section.lower().startswith("profile"):
            continue

        name = config.get(section, "Name", fallback=None)
        raw_path = config.get(section, "Path", fallback=None)

        if name is None or raw_path is None:
            continue

        is_relative = config.getint(section, "IsRelative", fallback=1)
        is_default = config.getboolean(section, "Default", fallback=False)

        profile_path = ini_path.parent / raw_path if is_relative else Path(raw_path)

        profiles.append(
            FirefoxProfile(
                name=name,
                path=profile_path.resolve(),
                is_default=is_default,
            )
        )

    if not profiles:
        msg = (
            "No Firefox profiles found in profiles.ini. "
            "Launch Firefox and create a profile first."
        )
        raise NoProfilesError(msg)

    # Sort: default profile first, then alphabetically
    profiles.sort(key=lambda p: (not p.is_default, p.name.lower()))

    return profiles
