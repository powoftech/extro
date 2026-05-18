from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import typer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from extro.commands.reset import reset_command
from extro.downloads.integrity import make_read_only
from extro.storage.models import Base, Book, BookFile, BookSnapshot

if TYPE_CHECKING:
    from pathlib import Path


class _Prompt:
    def __init__(self, answer: str) -> None:
        self._answer = answer

    def ask(self) -> str:
        return self._answer


def _session(db_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)()


def _seed_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(db_path))) as connection:
        connection.executescript(
            """
            CREATE TABLE books (id INTEGER PRIMARY KEY);
            CREATE TABLE book_snapshots (id INTEGER PRIMARY KEY);
            CREATE TABLE book_files (id INTEGER PRIMARY KEY);
            """
        )
        connection.execute("INSERT INTO books DEFAULT VALUES")
        connection.execute("INSERT INTO book_snapshots DEFAULT VALUES")
        connection.execute("INSERT INTO book_files DEFAULT VALUES")


def test_reset_command_recreates_database_and_removes_downloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "data"
    downloads_root = data_root / "downloads"
    exports_root = data_root / "exports"
    db_path = data_root / "extro.db"
    monkeypatch.setattr(
        "extro.commands.reset.app_paths.user_data_dir_path",
        lambda: data_root,
    )
    monkeypatch.setattr(
        "extro.commands.reset.questionary.text",
        lambda *_args, **_kwargs: _Prompt("  ExtRo  "),
    )

    _seed_database(db_path)

    download_file = (
        downloads_root / "123" / "1700000000000" / "files" / "text" / "file.txt"
    )
    download_file.parent.mkdir(parents=True, exist_ok=True)
    download_file.write_bytes(b"data")
    make_read_only(download_file)

    export_file = exports_root / "example-1700000000000.epub"
    export_file.parent.mkdir(parents=True, exist_ok=True)
    export_file.write_bytes(b"epub")

    app = typer.Typer()
    app.command(name="reset")(reset_command)
    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    assert not downloads_root.exists()
    assert db_path.exists()
    assert export_file.exists()

    with _session(db_path) as session:
        assert session.query(Book).count() == 0
        assert session.query(BookSnapshot).count() == 0
        assert session.query(BookFile).count() == 0

    assert "Reset Complete" in result.output


def test_reset_command_aborts_when_confirmation_does_not_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "data"
    downloads_root = data_root / "downloads"
    db_path = data_root / "extro.db"
    monkeypatch.setattr(
        "extro.commands.reset.app_paths.user_data_dir_path",
        lambda: data_root,
    )
    monkeypatch.setattr(
        "extro.commands.reset.questionary.text",
        lambda *_args, **_kwargs: _Prompt("wrong"),
    )

    _seed_database(db_path)
    downloads_root.mkdir(parents=True, exist_ok=True)

    app = typer.Typer()
    app.command(name="reset")(reset_command)
    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    assert downloads_root.exists()
    assert db_path.exists()
    assert "Aborted" in result.output
