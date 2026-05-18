from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from extro.commands.delete import delete_snapshots
from extro.storage.models import Base, Book, BookSnapshot, SnapshotStatus

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)()


def test_delete_snapshots_removes_all_matching_export_formats(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
):
    downloads_root = tmp_path / "downloads"
    exports_root = tmp_path / "exports"
    monkeypatch.setattr("extro.commands.delete.downloads_dir", lambda: downloads_root)
    monkeypatch.setattr("extro.commands.delete.exports_dir", lambda: exports_root)

    session = _session(tmp_path)
    book = Book(
        identifier="123",
        ourn="urn:orm:book:123",
        title="Example Book",
        latest_version="1700000000000",
        metadata_json={},
    )
    snapshot = BookSnapshot(
        book=book,
        version="1700000000000",
        snapshot_path=str(downloads_root / "123" / "1700000000000"),
        status=SnapshotStatus.COMPLETED,
    )
    session.add(book)
    session.flush()

    snapshot_path = Path(snapshot.snapshot_path)
    snapshot_path.mkdir(parents=True)
    epub_path = exports_root / "example_book-1700000000000.epub"
    pdf_path = exports_root / "example_book-1700000000000.pdf"
    epub_path.parent.mkdir(parents=True, exist_ok=True)
    epub_path.write_bytes(b"epub")
    pdf_path.write_bytes(b"pdf")

    result = delete_snapshots(
        session,
        book,
        {snapshot.id},
        remove_exports=True,
    )

    expected_removed_exports = 2
    expected_removed_directories = 1

    assert result.removed_exports == expected_removed_exports
    assert result.removed_directories == expected_removed_directories
    assert result.deleted_book is True
    assert not epub_path.exists()
    assert not pdf_path.exists()
    assert not snapshot_path.exists()
