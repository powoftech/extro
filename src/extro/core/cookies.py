from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING, cast

import browsercookie  # type: ignore[import-untyped]
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from extro.core.exceptions import ConfigError

if TYPE_CHECKING:
    from http.cookiejar import CookieJar
    from pathlib import Path

OREILLY_HOME_URL = "https://learning.oreilly.com/home2/"


def firefox_cookie_files(profile_dir: Path) -> list[str]:
    candidates = [
        profile_dir / "sessionstore-backups" / "recovery.js",
        profile_dir / "sessionstore-backups" / "recovery.json",
        profile_dir / "sessionstore-backups" / "recovery.jsonlz4",
        profile_dir / "sessionstore.js",
        profile_dir / "sessionstore.json",
        profile_dir / "sessionstore.jsonlz4",
        profile_dir / "cookies.sqlite",
    ]
    return [str(path) for path in candidates if path.exists()]


def oreilly_cookies_from_profile(profile_dir: Path) -> dict[str, str]:
    cookie_files = firefox_cookie_files(profile_dir)
    if not cookie_files:
        msg = f"No Firefox cookies found in selected profile: {profile_dir}"
        raise ConfigError(msg)

    cookiejar = cast("CookieJar", browsercookie.firefox(cookie_files=cookie_files))
    cookies: dict[str, str] = {}
    for cookie in cookiejar:
        if "oreilly" in cookie.domain.lower() and cookie.value is not None:
            cookies[str(cookie.name)] = str(cookie.value)
    return cookies


def is_firefox_running() -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq firefox.exe", "/NH"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        return any(
            line.lower().startswith("firefox.exe")
            for line in result.stdout.splitlines()
        )
    result = subprocess.run(
        ["pgrep", "-x", "firefox"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def refresh_cookies_via_firefox(profile_dir: Path) -> None:
    if is_firefox_running():
        msg = (
            "Firefox is already running. Close all Firefox windows before refreshing "
            "cookies with the selected profile."
        )
        raise ConfigError(msg)

    options = Options()
    options.add_argument("-profile")
    options.add_argument(str(profile_dir))
    options.add_argument("--headless")

    driver = webdriver.Firefox(options=options)
    try:
        driver.get(OREILLY_HOME_URL)
        WebDriverWait(driver, 30).until(
            expected_conditions.presence_of_element_located((By.ID, "history")),
        )
        time.sleep(5)
    finally:
        driver.quit()
