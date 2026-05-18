from __future__ import annotations

import shutil
import stat
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def _make_writable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IWRITE)


def _retry_rmtree_after_chmod(
    function: Callable[..., object],
    path: str,
    excinfo: BaseException,
) -> None:
    if not isinstance(excinfo, PermissionError):
        raise excinfo

    target = Path(path)
    _make_writable(target)
    function(path)


def remove_path(path: Path) -> None:
    if not path.exists():
        return

    if path.is_dir():
        shutil.rmtree(path, onexc=_retry_rmtree_after_chmod)
        return

    try:
        path.unlink()
    except FileNotFoundError:
        return
    except PermissionError:
        _make_writable(path)
        path.unlink(missing_ok=True)
