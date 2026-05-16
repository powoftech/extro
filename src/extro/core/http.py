"""Shared HTTP helpers for extro.

All outbound requests impersonate a real Chrome browser.  Rather than
copy-pasting the same 15-line headers dict everywhere, build a single
``curl_cffi.Session`` through :func:`make_session` and reuse it.
"""

from __future__ import annotations

import curl_cffi

# ---------------------------------------------------------------------------
# Browser-spoof headers shared by every outbound request
# ---------------------------------------------------------------------------

BROWSER_HEADERS: dict[str, str] = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;"
        "q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Gpc": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": ('"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"'),
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "Windows",
}


def make_session(
    *,
    cookies: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> curl_cffi.Session:
    """Return a ``curl_cffi.Session`` configured with browser-spoof headers.

    Args:
        cookies: Optional cookie dict to attach to every request.
        timeout: Request timeout in seconds.

    Returns:
        A ready-to-use :class:`curl_cffi.Session`.
    """
    return curl_cffi.Session(
        headers=BROWSER_HEADERS,
        cookies=cookies,
        http_version="v2",
        allow_redirects=True,
        verify=True,
        timeout=timeout,
        impersonate="chrome146"
    )
