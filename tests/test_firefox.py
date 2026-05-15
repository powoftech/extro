"""Tests for Firefox profile detection."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from extro.core.exceptions import FirefoxNotFoundError, NoProfilesError
from extro.core.firefox import FirefoxProfile, get_firefox_profiles

# ---------------------------------------------------------------------------
# Fake profiles.ini fixtures
# ---------------------------------------------------------------------------

_PROFILES_INI_TWO = dedent("""\
    [General]
    StartWithLastProfile=1

    [Profile0]
    Name=default-release
    IsRelative=1
    Path=Profiles/abc123.default-release
    Default=1

    [Profile1]
    Name=Work
    IsRelative=1
    Path=Profiles/xyz789.work
""")

_PROFILES_INI_ABSOLUTE = dedent("""\
    [General]
    StartWithLastProfile=1

    [Profile0]
    Name=absolute-profile
    IsRelative=0
    Path=/home/user/.mozilla/firefox/abs123.default
""")

_PROFILES_INI_EMPTY = dedent("""\
    [General]
    StartWithLastProfile=1
""")

_TWO_PROFILES = 2


def _make_ini(tmp_path: Path, content: str) -> Path:
    """Write a fake profiles.ini and return its path."""
    ini = tmp_path / "profiles.ini"
    ini.write_text(content, encoding="utf-8")
    return ini


def _create_two_profile_dirs(tmp_path: Path) -> None:
    (tmp_path / "Profiles" / "abc123.default-release").mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / "Profiles" / "xyz789.work").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetFirefoxProfiles:
    def test_raises_when_ini_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "extro.core.firefox._profiles_ini_path",
            lambda: tmp_path / "nonexistent.ini",
        )
        with pytest.raises(FirefoxNotFoundError):
            get_firefox_profiles()

    def test_raises_when_no_profiles(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ini = _make_ini(tmp_path, _PROFILES_INI_EMPTY)
        monkeypatch.setattr("extro.core.firefox._profiles_ini_path", lambda: ini)
        with pytest.raises(NoProfilesError):
            get_firefox_profiles()

    def test_returns_profiles_sorted_default_first(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ini = _make_ini(tmp_path, _PROFILES_INI_TWO)
        _create_two_profile_dirs(tmp_path)
        monkeypatch.setattr("extro.core.firefox._profiles_ini_path", lambda: ini)

        profiles = get_firefox_profiles()

        assert len(profiles) == _TWO_PROFILES
        assert profiles[0].name == "default-release"
        assert profiles[0].is_default is True
        assert profiles[1].name == "Work"
        assert profiles[1].is_default is False

    def test_relative_path_resolved_from_ini_parent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ini = _make_ini(tmp_path, _PROFILES_INI_TWO)
        _create_two_profile_dirs(tmp_path)
        monkeypatch.setattr("extro.core.firefox._profiles_ini_path", lambda: ini)

        profiles = get_firefox_profiles()
        default_profile = profiles[0]

        expected = (tmp_path / "Profiles" / "abc123.default-release").resolve()
        assert default_profile.path == expected

    def test_profile_str_includes_default_marker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ini = _make_ini(tmp_path, _PROFILES_INI_TWO)
        _create_two_profile_dirs(tmp_path)
        monkeypatch.setattr("extro.core.firefox._profiles_ini_path", lambda: ini)

        profiles = get_firefox_profiles()
        assert "[default]" in str(profiles[0])
        assert "[default]" not in str(profiles[1])

    def test_frozen_dataclass_is_hashable(self) -> None:
        profile = FirefoxProfile(name="test", path=Path("/tmp/test"), is_default=False)
        assert hash(profile) is not None
        profile_set: set[FirefoxProfile] = {profile}
        assert profile in profile_set
