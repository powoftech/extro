from __future__ import annotations

import hashlib
import stat
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
import typer
from rich.console import Console
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from extro.commands.verify import verify_command
from extro.downloads.integrity import (
    IntegrityState,
    hash_file,
    is_read_only,
    make_read_only,
    verify_file,
)
from extro.downloads.manager import DownloadManager
from extro.oreilly.schemas import BookMetadata
from extro.storage import database as database_module
from extro.storage.models import Base, Book, BookFile, BookSnapshot, SnapshotStatus


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content


class _FakeCookieClient:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def get_bytes(self, url: str) -> _FakeResponse:
        _ = url
        return _FakeResponse(self._content)


class _FakeApiClient:
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

    def fetch_spine(self, metadata: Any) -> dict[str, Any]:
        _ = metadata
        return {}

    def fetch_table_of_contents(self, metadata: Any) -> dict[str, Any]:
        _ = metadata
        return {}

    def fetch_chapters(self, metadata: Any) -> dict[str, Any]:
        _ = metadata
        return {}

    def fetch_files(self, metadata: Any) -> dict[str, Any]:
        _ = metadata
        return {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "url": "https://example.invalid/file.txt",
                    "full_path": "text/file.txt",
                    "media_type": "text/plain",
                    "file_size": 7,
                    "last_modified_time": "1700000000000",
                }
            ],
        }


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)()


def _book_file(
    tmp_path: Path,
    *,
    data: bytes | None,
    stored_hash: str | None,
    read_only: bool,
) -> tuple[BookSnapshot, BookFile]:
    snapshot = BookSnapshot(
        book_id=1,
        version="1700000000000",
        snapshot_path=str(tmp_path / "snapshot"),
        status=SnapshotStatus.COMPLETED,
    )
    file = BookFile(
        snapshot=snapshot,
        url="https://example.invalid/file.txt",
        full_path="text/file.txt",
        media_type="text/plain",
        file_size=len(data) if data is not None else None,
        remote_last_modified_time=None,
        status="completed",
        bytes_downloaded=len(data) if data is not None else 0,
        content_sha256=stored_hash,
    )
    path = Path(snapshot.snapshot_path) / "files" / "text" / "file.txt"
    if data is not None:
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        if read_only:
            make_read_only(path)
        else:
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
    return snapshot, file


def test_download_stores_sha256_and_marks_file_read_only(tmp_path, monkeypatch):
    content = b"content"
    downloads_root = tmp_path / "downloads"
    session = _session(tmp_path)
    monkeypatch.setattr(
        "extro.downloads.manager.downloads_dir",
        lambda: downloads_root,
    )

    def cookie_client_factory(profile_dir: Path) -> _FakeCookieClient:
        _ = profile_dir
        return _FakeCookieClient(content)

    manager = DownloadManager(
        api_client=_FakeApiClient(),
        session=session,
        console=Console(file=StringIO()),
        cookie_client_factory=cookie_client_factory,
        random_delay=lambda: 0,
    )

    snapshot_path = manager.download("123", profile_dir=tmp_path)

    book_file = session.query(BookFile).one()
    file_path = snapshot_path / "files" / "text" / "file.txt"
    assert file_path.read_bytes() == content
    assert book_file.content_sha256 == hashlib.sha256(content).hexdigest()
    assert is_read_only(file_path)


@pytest.mark.parametrize(
    ("data", "stored_hash", "read_only", "expected"),
    [
        (b"same", hashlib.sha256(b"same").hexdigest(), True, IntegrityState.OK),
        (
            b"changed",
            hashlib.sha256(b"original").hexdigest(),
            True,
            IntegrityState.CHANGED,
        ),
        (None, hashlib.sha256(b"missing").hexdigest(), True, IntegrityState.MISSING),
        (
            b"writable",
            hashlib.sha256(b"writable").hexdigest(),
            False,
            IntegrityState.WRITABLE,
        ),
        (b"unknown", None, True, IntegrityState.UNVERIFIED),
    ],
)
def test_verify_file_reports_expected_state(
    tmp_path,
    data,
    stored_hash,
    read_only,
    expected,
):
    snapshot, file = _book_file(
        tmp_path,
        data=data,
        stored_hash=stored_hash,
        read_only=read_only,
    )

    assert verify_file(snapshot, file).state == expected


def test_verify_command_reports_failure_and_exit_code(tmp_path, monkeypatch):
    db_path = tmp_path / "extro.db"
    monkeypatch.setattr(database_module, "database_path", lambda: db_path)
    database_module.upgrade_database()
    snapshot_path = tmp_path / "snapshot"
    file_path = snapshot_path / "files" / "text" / "file.txt"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"changed")
    make_read_only(file_path)
    with database_module.session_scope() as session:
        book = Book(
            identifier="123",
            ourn="urn:orm:book:123",
            title="Example",
            latest_version="1700000000000",
            metadata_json={},
        )
        snapshot = BookSnapshot(
            book=book,
            version="1700000000000",
            snapshot_path=str(snapshot_path),
            status=SnapshotStatus.COMPLETED,
        )
        BookFile(
            snapshot=snapshot,
            url="https://example.invalid/file.txt",
            full_path="text/file.txt",
            media_type="text/plain",
            file_size=7,
            remote_last_modified_time=None,
            status="completed",
            bytes_downloaded=7,
            content_sha256=hashlib.sha256(b"original").hexdigest(),
        )
        session.add(book)

    app = typer.Typer()
    app.command()(verify_command)
    result = CliRunner().invoke(app, ["123"])

    assert result.exit_code == 1
    assert "changed" in result.output
    assert "text/file.txt" in result.output


def test_verify_command_reports_success(tmp_path, monkeypatch):
    db_path = tmp_path / "extro.db"
    monkeypatch.setattr(database_module, "database_path", lambda: db_path)
    database_module.upgrade_database()
    snapshot_path = tmp_path / "snapshot"
    file_path = snapshot_path / "files" / "text" / "file.txt"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"same")
    make_read_only(file_path)
    with database_module.session_scope() as session:
        book = Book(
            identifier="123",
            ourn="urn:orm:book:123",
            title="Example",
            latest_version="1700000000000",
            metadata_json={},
        )
        snapshot = BookSnapshot(
            book=book,
            version="1700000000000",
            snapshot_path=str(snapshot_path),
            status=SnapshotStatus.COMPLETED,
        )
        BookFile(
            snapshot=snapshot,
            url="https://example.invalid/file.txt",
            full_path="text/file.txt",
            media_type="text/plain",
            file_size=4,
            remote_last_modified_time=None,
            status="completed",
            bytes_downloaded=4,
            content_sha256=hash_file(file_path),
        )
        session.add(book)

    app = typer.Typer()
    app.command()(verify_command)
    result = CliRunner().invoke(app, ["123"])

    assert result.exit_code == 0
    assert "Verified files: 1" in result.output


def test_migration_adds_nullable_content_sha256(tmp_path, monkeypatch):
    db_path = tmp_path / "extro.db"
    monkeypatch.setattr(database_module, "database_path", lambda: db_path)

    database_module.upgrade_database()

    engine = database_module.create_db_engine()
    columns = {
        column["name"]: column for column in inspect(engine).get_columns("book_files")
    }
    assert "content_sha256" in columns
    assert columns["content_sha256"]["nullable"] is True
