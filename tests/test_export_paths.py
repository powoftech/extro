from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.monkeypatch import MonkeyPatch

from extro.app import paths as app_paths


def test_exports_dir_creates_sibling_directory(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(app_paths, "user_data_dir", lambda: tmp_path / "data")

    path = app_paths.exports_dir()

    assert path == tmp_path / "data" / "exports"
    assert path.is_dir()


def test_export_file_path_uses_shared_exports_root(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(app_paths, "user_data_dir", lambda: tmp_path / "data")

    path = app_paths.export_file_path(
        "Bad:/Title?",
        "1700000000000",
        extension=".epub",
        fallback="book",
    )

    assert path == tmp_path / "data" / "exports" / "bad_title-1700000000000.epub"
    assert path.parent.is_dir()


def test_export_file_path_collapses_repeated_underscores(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr(app_paths, "user_data_dir", lambda: tmp_path / "data")

    path = app_paths.export_file_path(
        "The Pragmatic Programmer: your journey to mastery, "
        "20th Anniversary Edition, 2nd Edition",
        "1700000000000",
        extension="epub",
        fallback="fallback__name",
    )

    assert path == (
        tmp_path
        / "data"
        / "exports"
        / (
            "the_pragmatic_programmer_your_journey_to_mastery_20th_"
            "anniversary_edition_2nd_edition-1700000000000.epub"
        )
    )
