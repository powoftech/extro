from __future__ import annotations

from typing import TYPE_CHECKING, Any

import typer
from typer.testing import CliRunner

from extro.commands.convert import convert_command
from extro.oreilly.schemas import BookMetadata
from extro.storage import database as database_module
from extro.storage.models import Book, BookSnapshot, SnapshotStatus

if TYPE_CHECKING:
    from pathlib import Path


class _FakeClient:
    def __init__(self, **_kwargs: Any) -> None:
        pass

    def fetch_metadata(self, identifier: str) -> BookMetadata:
        return BookMetadata.model_validate(
            {
                "identifier": identifier,
                "ourn": f"urn:orm:book:{identifier}",
                "title": "Example",
                "version": "1700000000000",
                "authors": [],
                "publishers": [],
            }
        )


class _SelectPrompt:
    def __init__(self, choices: list[Any]) -> None:
        self._choices = choices

    def ask(self) -> Any:
        return self._choices[0].value


def _write_snapshot(root: Path) -> Path:
    files = root / "files"
    (files / "text").mkdir(parents=True)
    (files / "stylesheet.css").write_text(
        ".hidden-note { display: none; }",
        encoding="utf-8",
    )
    (files / "text" / "ch01.html").write_text(
        """
        <div id="sbo-rt-content">
          <h1>Chapter One</h1>
          <p>Visible text</p>
          <aside class="hidden-note" aria-hidden="true">
            Hidden diagnostic sample
          </aside>
        </div>
        """,
        encoding="utf-8",
    )
    (files / "content.opf").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
          <manifest>
            <item id="css" href="stylesheet.css" media-type="text/css"/>
            <item id="chapter" href="text/ch01.html"
                  media-type="application/xhtml+xml"/>
          </manifest>
          <spine><itemref idref="chapter"/></spine>
        </package>
        """,
        encoding="utf-8",
    )
    return root


def test_convert_audit_hidden_reports_without_writing_epub(tmp_path, monkeypatch):
    db_path = tmp_path / "extro.db"
    snapshot_path = _write_snapshot(tmp_path / "snapshot")
    monkeypatch.setattr(database_module, "database_path", lambda: db_path)
    monkeypatch.setattr(
        "extro.commands.convert._require_firefox_profile",
        lambda: tmp_path,
    )
    monkeypatch.setattr("extro.commands.convert.OreillyClient", _FakeClient)
    monkeypatch.setattr(
        "extro.commands.convert.questionary.select",
        lambda _message, choices, **_kwargs: _SelectPrompt(choices),
    )

    def fail_build_epub(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("audit mode must not build an EPUB")

    def fail_export_path(*_args: Any, **_kwargs: Any) -> Path:
        raise AssertionError("audit mode must not compute an export path")

    monkeypatch.setattr("extro.commands.convert.build_epub", fail_build_epub)
    monkeypatch.setattr("extro.commands.convert.export_file_path", fail_export_path)

    database_module.upgrade_database()
    with database_module.session_scope() as session:
        book = Book(
            identifier="123",
            ourn="urn:orm:book:123",
            title="Example",
            latest_version="1700000000000",
            metadata_json={},
        )
        BookSnapshot(
            book=book,
            version="1700000000000",
            snapshot_path=str(snapshot_path),
            status=SnapshotStatus.COMPLETED,
        )
        session.add(book)

    app = typer.Typer()
    app.command(name="convert")(convert_command)
    result = CliRunner().invoke(app, ["123", "--audit-hidden"])

    assert result.exit_code == 0
    assert "Hidden Content Audit" in result.output
    assert "Hidden characters" in result.output
    assert "text/ch01.html" in result.output
    assert "Hidden diagnostic sample" in result.output
