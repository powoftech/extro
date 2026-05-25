from __future__ import annotations

from typing import Any

import pytest

from extro.app.exceptions import ConfigError
from extro.oreilly.client import OreillyClient
from extro.oreilly.schemas import BookMetadata


class _FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self.url = "https://learning.oreilly.com/api/v2/example/"
        self._payload = payload
        self.raise_count = 0

    def raise_for_status(self) -> None:
        self.raise_count += 1

    def json(self) -> object:
        return self._payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
        self.requests: list[tuple[str, dict[str, str] | None]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> _FakeResponse:
        self.requests.append((url, params))
        return self._responses.pop(0)


def _metadata() -> BookMetadata:
    return BookMetadata.model_validate(
        {
            "identifier": "123",
            "ourn": "urn:orm:book:123",
            "title": "Example",
            "version": "1700000000000",
            "authors": [],
            "publishers": [],
        }
    )


def test_get_json_uses_firefox_cookie_session(tmp_path, monkeypatch):
    session = _FakeSession([_FakeResponse(200, {"ok": True})])
    make_session_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        "extro.oreilly.client.oreilly_cookies_from_profile",
        lambda profile_dir: {"sessionid": f"cookie-from-{profile_dir.name}"},
    )

    def fake_make_session(*, cookies: dict[str, str], timeout: float) -> _FakeSession:
        make_session_calls.append({"cookies": cookies, "timeout": timeout})
        return session

    monkeypatch.setattr("extro.oreilly.client.make_session", fake_make_session)

    client = OreillyClient(profile_dir=tmp_path, timeout=12.5, delay_min=0, delay_max=0)

    data = client.fetch_spine(_metadata())

    assert data == {"ok": True}
    assert make_session_calls == [
        {
            "cookies": {"sessionid": f"cookie-from-{tmp_path.name}"},
            "timeout": 12.5,
        }
    ]
    assert session.requests == [
        (
            "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:123/spine/",
            {"limit": "1000"},
        )
    ]


@pytest.mark.parametrize("status_code", [401, 403])
def test_get_json_refreshes_firefox_cookies_once_on_auth_failure(
    tmp_path,
    monkeypatch,
    status_code,
):
    first_response = _FakeResponse(status_code, {"error": "expired"})
    second_response = _FakeResponse(200, {"ok": True})
    sessions = [
        _FakeSession([first_response]),
        _FakeSession([second_response]),
    ]
    refresh_calls: list[Any] = []

    monkeypatch.setattr(
        "extro.oreilly.client.oreilly_cookies_from_profile",
        lambda profile_dir: {"sessionid": f"{profile_dir.name}-{len(sessions)}"},
    )

    def fake_make_session(*, cookies: dict[str, str], timeout: float) -> _FakeSession:
        _ = cookies, timeout
        return sessions.pop(0)

    monkeypatch.setattr("extro.oreilly.client.make_session", fake_make_session)

    def fake_refresh_cookies_via_firefox(profile_dir: Any) -> None:
        refresh_calls.append(profile_dir)

    monkeypatch.setattr(
        "extro.oreilly.client.refresh_cookies_via_firefox",
        fake_refresh_cookies_via_firefox,
    )

    client = OreillyClient(profile_dir=tmp_path, delay_min=0, delay_max=0)

    data = client.fetch_spine(_metadata())

    assert data == {"ok": True}
    assert refresh_calls == [tmp_path]
    assert first_response.raise_count == 0
    assert second_response.raise_count == 1


def test_get_json_requires_firefox_profile():
    client = OreillyClient(delay_min=0, delay_max=0)

    with pytest.raises(ConfigError, match="extro config"):
        client.fetch_spine(_metadata())
