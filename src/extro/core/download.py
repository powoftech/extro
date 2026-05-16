"""Download orchestration for O'Reilly book snapshots."""

from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol, cast

import curl_cffi
import questionary
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn
from sqlalchemy import Select, select

from extro.core.api import (
    BookMetadata,
    FilesManifest,
    FilesManifestItem,
    OreillyClient,
    normalize_book_identifier,
)
from extro.core.cookies import (
    oreilly_cookies_from_profile,
    refresh_cookies_via_firefox,
)
from extro.core.exceptions import ExtroError
from extro.core.http import make_session
from extro.core.models import (
    Book,
    BookFile,
    BookSnapshot,
    FileStatus,
    SnapshotStatus,
)
from extro.core.paths import downloads_dir, safe_snapshot_name

if TYPE_CHECKING:
    from rich.console import Console
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_AUTH_FAILURE_STATUS_CODES = {401, 403}

# Default inter-request jitter bounds (seconds)
_DELAY_MIN: float = 0.5
_DELAY_MAX: float = 1.0


# ---------------------------------------------------------------------------
# Protocols for dependency injection / testability
# ---------------------------------------------------------------------------


class CurlResponse(Protocol):
    status_code: int
    content: bytes

    def json(self) -> object: ...

    def raise_for_status(self) -> None: ...


class CurlSession(Protocol):
    def get(self, url: str) -> CurlResponse: ...


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Sleep = Callable[[float], None]
RandomDelay = Callable[[], float]


# ---------------------------------------------------------------------------
# Cookie-authenticated HTTP client
# ---------------------------------------------------------------------------


class CookieFileClient:
    """HTTP client that authenticates using Firefox cookies.

    Unlike :class:`~extro.core.api.OreillyClient`, this client attaches
    session cookies to every request.  It is used exclusively to download
    the actual book-asset files from the CDN, which require authentication.
    """

    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        self._session = self._new_session()

    def get_json(self, url: str) -> dict[str, Any]:
        response = self._get_with_refresh(url)
        data = response.json()
        if not isinstance(data, dict):
            msg = f"Expected object response from {url}"
            raise TypeError(msg)
        return data

    def get_bytes(self, url: str) -> CurlResponse:
        return self._get_with_refresh(url)

    def _get_with_refresh(self, url: str) -> CurlResponse:
        response = self._session.get(url)
        if response.status_code not in _AUTH_FAILURE_STATUS_CODES:
            response.raise_for_status()
            return response

        # Auth expired — refresh cookies via a headless Firefox session.
        logger.debug("Auth failure for %s; refreshing Firefox cookies.", url)
        refresh_cookies_via_firefox(self._profile_dir)
        self._session = self._new_session()
        response = self._session.get(url)
        response.raise_for_status()
        return response

    def _new_session(self) -> CurlSession:
        cookies = oreilly_cookies_from_profile(self._profile_dir)
        return cast(
            "CurlSession",
            make_session(cookies=cookies),
        )


# ---------------------------------------------------------------------------
# Download manager
# ---------------------------------------------------------------------------


class DownloadManager:
    """Orchestrates fetching and persisting a complete O'Reilly book snapshot."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        api_client: OreillyClient,
        session: Session,
        console: Console,
        cookie_client_factory: Callable[[Path], CookieFileClient] = CookieFileClient,
        sleep: Sleep = time.sleep,
        random_delay: RandomDelay = lambda: random.uniform(  # noqa: S311
            _DELAY_MIN, _DELAY_MAX
        ),
    ) -> None:
        self._api_client = api_client
        self._session = session
        self._console = console
        self._cookie_client_factory = cookie_client_factory
        self._sleep = sleep
        self._random_delay = random_delay

    def download(self, book_identifier: str, *, profile_dir: Path) -> Path:
        """Download (or resume) a book snapshot.

        Args:
            book_identifier: O'Reilly book identifier, URN, or URL.
            profile_dir: Path to the Firefox profile directory used for
                cookie-authenticated file downloads.

        Returns:
            The local :class:`~pathlib.Path` to the completed snapshot directory.

        Raises:
            ExtroError: On user cancellation or unsafe file paths.
        """
        identifier = normalize_book_identifier(book_identifier)

        metadata = self._api_client.fetch_metadata(identifier)
        book = self._upsert_book(metadata.model_dump(mode="json"))
        previous_completed = self._latest_completed_snapshot(book.id)
        existing_snapshot = self._snapshot_for_version(
            book.id,
            metadata.last_modified_time,
        )

        if (
            existing_snapshot is not None
            and existing_snapshot.status == SnapshotStatus.COMPLETED
        ):
            return Path(existing_snapshot.snapshot_path)

        if (
            existing_snapshot is None
            and previous_completed is not None
            and previous_completed.last_modified_time != metadata.last_modified_time
            and not self._confirm_new_version(
                previous_completed,
                metadata.last_modified_time,
            )
        ):
            msg = "Download cancelled."
            raise ExtroError(msg)

        snapshot = existing_snapshot or self._create_snapshot(
            book,
            metadata.last_modified_time,
        )
        snapshot.status = SnapshotStatus.DOWNLOADING
        self._session.commit()

        snapshot_path = Path(snapshot.snapshot_path)
        snapshot_path.mkdir(parents=True, exist_ok=True)

        manifests = self._fetch_manifests(metadata)
        self._write_manifests(snapshot_path, manifests)

        cookie_client = self._cookie_client_factory(profile_dir)
        files_manifest = FilesManifest.model_validate(manifests["files"])
        self._sync_file_rows(snapshot, files_manifest.results)
        self._download_files(cookie_client, snapshot)

        snapshot.status = SnapshotStatus.COMPLETED
        self._refresh_snapshot_progress(snapshot)
        self._session.commit()
        return snapshot_path

    # ------------------------------------------------------------------
    # Version confirmation (injectable for testing)
    # ------------------------------------------------------------------

    def _confirm_new_version(
        self,
        previous_snapshot: BookSnapshot,
        new_last_modified_time: str,
    ) -> bool:
        """Prompt the user whether to download a newer version.

        Subclasses or tests may override this method to skip the prompt.
        """
        answer = questionary.confirm(
            (
                "A newer version is available "
                f"({previous_snapshot.last_modified_time} -> "
                f"{new_last_modified_time}). "
                "Download it?"
            ),
            default=True,
        ).ask()
        return bool(answer)

    # ------------------------------------------------------------------
    # Manifest fetching and writing
    # ------------------------------------------------------------------

    def _fetch_manifests(self, metadata: BookMetadata) -> dict[str, Any]:
        return {
            "metadata": metadata.model_dump(mode="json"),
            "spine": self._api_client.fetch_spine(metadata),
            "files": self._api_client.fetch_files(metadata),
            "table_of_contents": self._api_client.fetch_table_of_contents(metadata),
            "chapters": self._api_client.fetch_chapters(metadata),
        }

    def _write_manifests(
        self,
        snapshot_path: Path,
        manifests: dict[str, Any],
    ) -> None:
        manifest_dir = snapshot_path / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in manifests.items():
            (manifest_dir / f"{name}.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _upsert_book(self, metadata: dict[str, Any]) -> Book:
        stmt: Select[tuple[Book]] = select(Book).where(
            Book.identifier == metadata["identifier"],
        )
        book = self._session.scalars(stmt).one_or_none()
        if book is None:
            book = Book(
                identifier=str(metadata["identifier"]),
                ourn=str(metadata["ourn"]),
                isbn=metadata.get("isbn"),
                title=str(metadata["title"]),
                language=metadata.get("language"),
                latest_last_modified_time=str(metadata["last_modified_time"]),
                metadata_json=metadata,
            )
            self._session.add(book)
        else:
            book.ourn = str(metadata["ourn"])
            book.isbn = metadata.get("isbn")
            book.title = str(metadata["title"])
            book.language = metadata.get("language")
            book.latest_last_modified_time = str(metadata["last_modified_time"])
            book.metadata_json = metadata
        self._session.commit()
        return book

    def _create_snapshot(self, book: Book, last_modified_time: str) -> BookSnapshot:
        snapshot_path = (
            downloads_dir() / book.identifier / safe_snapshot_name(last_modified_time)
        )
        snapshot = BookSnapshot(
            book_id=book.id,
            last_modified_time=last_modified_time,
            snapshot_path=str(snapshot_path),
            status=SnapshotStatus.PENDING,
        )
        self._session.add(snapshot)
        self._session.commit()
        return snapshot

    def _latest_completed_snapshot(self, book_id: int) -> BookSnapshot | None:
        stmt: Select[tuple[BookSnapshot]] = (
            select(BookSnapshot)
            .where(
                BookSnapshot.book_id == book_id,
                BookSnapshot.status == SnapshotStatus.COMPLETED,
            )
            .order_by(BookSnapshot.last_modified_time.desc())
        )
        return self._session.scalars(stmt).first()

    def _snapshot_for_version(
        self,
        book_id: int,
        last_modified_time: str,
    ) -> BookSnapshot | None:
        stmt: Select[tuple[BookSnapshot]] = select(BookSnapshot).where(
            BookSnapshot.book_id == book_id,
            BookSnapshot.last_modified_time == last_modified_time,
        )
        return self._session.scalars(stmt).one_or_none()

    def _sync_file_rows(
        self,
        snapshot: BookSnapshot,
        files: list[FilesManifestItem],
    ) -> None:
        existing = {file.full_path: file for file in snapshot.files}
        total_bytes = 0
        for item in files:
            local_path = snapshot_file_path(snapshot, item.full_path)
            completed = (
                item.file_size is not None
                and local_path.exists()
                and local_path.stat().st_size == item.file_size
            )
            total_bytes += item.file_size or 0
            row = existing.get(item.full_path)
            if row is None:
                row = BookFile(
                    snapshot=snapshot,
                    url=item.url,
                    full_path=item.full_path,
                    media_type=item.media_type,
                    file_size=item.file_size,
                    remote_last_modified_time=item.last_modified_time,
                    status=FileStatus.PENDING,
                    bytes_downloaded=0,
                )
                self._session.add(row)
            row.url = item.url
            row.media_type = item.media_type
            row.file_size = item.file_size
            row.remote_last_modified_time = item.last_modified_time
            if completed:
                row.status = FileStatus.COMPLETED
                row.bytes_downloaded = item.file_size or 0
                row.last_error = None
        snapshot.total_files = len(files)
        snapshot.total_bytes = total_bytes
        self._refresh_snapshot_progress(snapshot)
        self._session.commit()

    # ------------------------------------------------------------------
    # File downloading
    # ------------------------------------------------------------------

    def _download_files(
        self,
        cookie_client: CookieFileClient,
        snapshot: BookSnapshot,
    ) -> None:
        pending = [
            file for file in snapshot.files if file.status != FileStatus.COMPLETED
        ]
        if not pending:
            return

        progress = Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            console=self._console,
        )
        with progress:
            bytes_task = progress.add_task(
                "Downloading",
                total=max(snapshot.total_bytes, 1),
                completed=snapshot.downloaded_bytes,
            )
            for index, file in enumerate(pending):
                self._download_file(cookie_client, snapshot, file)
                self._refresh_snapshot_progress(snapshot)
                self._session.commit()
                progress.update(bytes_task, completed=snapshot.downloaded_bytes)
                if index < len(pending) - 1:
                    self._sleep(self._random_delay())

    def _download_file(
        self,
        cookie_client: CookieFileClient,
        snapshot: BookSnapshot,
        file: BookFile,
    ) -> None:
        target_path = snapshot_file_path(snapshot, file.full_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = cookie_client.get_bytes(file.url)
            target_path.write_bytes(response.content)
            file.status = FileStatus.COMPLETED
            file.bytes_downloaded = target_path.stat().st_size
            file.last_error = None
        except (curl_cffi.CurlError, OSError) as exc:
            error_msg = str(exc)
            logger.warning("Failed to download %s: %s", file.url, error_msg)
            file.status = FileStatus.FAILED
            file.last_error = error_msg

    def _refresh_snapshot_progress(self, snapshot: BookSnapshot) -> None:
        completed_files = 0
        downloaded_bytes = 0
        for file in snapshot.files:
            if file.status == FileStatus.COMPLETED:
                completed_files += 1
            downloaded_bytes += file.bytes_downloaded
        snapshot.completed_files = completed_files
        snapshot.downloaded_bytes = downloaded_bytes


# ---------------------------------------------------------------------------
# Path safety helper
# ---------------------------------------------------------------------------


def snapshot_file_path(snapshot: BookSnapshot, remote_full_path: str) -> Path:
    relative = PurePosixPath(remote_full_path)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        msg = f"Unsafe remote file path: {remote_full_path}"
        raise ExtroError(msg)
    root = Path(snapshot.snapshot_path) / "files"
    candidate = root.joinpath(*relative.parts).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        msg = f"Unsafe remote file path: {remote_full_path}"
        raise ExtroError(msg)
    return candidate
