from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from extro.app.exceptions import ExtroError
from extro.epub import build_epub, safe_epub_filename


def _write_snapshot(
    root: Path,
    *,
    html_href: str = "text/ch01.html",
    include_asset: bool = True,
    opf_name: str = "content.opf",
) -> Path:
    files = root / "files"
    files.mkdir(parents=True)
    (files / "assets").mkdir()
    (files / "text").mkdir()
    (files / "stylesheet.css").write_text("body { color: black; }", encoding="utf-8")
    (files / "styles").mkdir()
    (files / "styles" / "page_styles.css").write_text(
        "img { max-width: 100%; }",
        encoding="utf-8",
    )
    (files / "toc.ncx").write_text("<ncx></ncx>", encoding="utf-8")
    if include_asset:
        (files / "assets" / "cover.png").write_bytes(b"png")

    html_path = files.joinpath(*Path(html_href).parts)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        """
        <div id="sbo-rt-content">
          <h1>Chapter One</h1>
          <img src="/api/v2/epubs/urn:orm:book:123/files/assets/cover.png">
          <a href="https://example.com/reference">external</a>
          <a href="/tracking">tracking</a>
          <script>alert("no")</script>
          <div id="sec-overlay"><div id="sec-container"></div></div>
        </div>
        """,
        encoding="utf-8",
    )
    (files / opf_name).write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
        <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
          <manifest>
            <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
            <item id="css" href="stylesheet.css" media-type="text/css"/>
            <item id="page-css" href="styles/page_styles.css" media-type="text/css"/>
            <item id="cover" href="assets/cover.png" media-type="image/png"/>
            <item id="chapter" href="{html_href}" media-type="application/xhtml+xml"/>
          </manifest>
          <spine><itemref idref="chapter"/></spine>
        </package>
        """,
        encoding="utf-8",
    )
    return root


def test_build_epub_packages_and_sanitizes_html(tmp_path):
    snapshot = _write_snapshot(tmp_path / "snapshot")
    output = tmp_path / "book.epub"

    result = build_epub(snapshot, output, title="Example Book")

    assert result.output_path == output
    assert result.html_file_count == 1
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist()[0] == "mimetype"
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert "META-INF/container.xml" in archive.namelist()
        assert "OEBPS/content.opf" in archive.namelist()
        html_content = archive.read("OEBPS/text/ch01.html").decode()

    ET.fromstring(html_content.encode())
    assert 'src="../assets/cover.png"' in html_content
    assert 'href="https://example.com/reference"' in html_content
    assert 'href="/tracking"' not in html_content
    assert "<script" not in html_content
    assert "sec-overlay" not in html_content
    assert 'href="../stylesheet.css"' in html_content
    assert 'href="../styles/page_styles.css"' in html_content


def test_build_epub_uses_nonstandard_package_document_name(tmp_path):
    snapshot = _write_snapshot(tmp_path / "snapshot", opf_name="9780321700698.opf")
    output = tmp_path / "book.epub"

    build_epub(snapshot, output, title="Example Book")

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        container = archive.read("META-INF/container.xml").decode()

    assert "OEBPS/9780321700698.opf" in names
    assert 'full-path="OEBPS/9780321700698.opf"' in container


def test_build_epub_fails_when_manifest_file_is_missing(tmp_path):
    snapshot = _write_snapshot(tmp_path / "snapshot", include_asset=False)

    with pytest.raises(ExtroError, match="missing manifest file"):
        build_epub(snapshot, tmp_path / "book.epub", title="Example Book")


def test_build_epub_rejects_unsafe_manifest_paths(tmp_path):
    snapshot = _write_snapshot(tmp_path / "snapshot")
    opf_path = snapshot / "files" / "content.opf"
    opf_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
          <manifest>
            <item id="bad" href="../secret.txt" media-type="text/plain"/>
          </manifest>
        </package>
        """,
        encoding="utf-8",
    )

    with pytest.raises(ExtroError, match="Unsafe OPF manifest path"):
        build_epub(snapshot, tmp_path / "book.epub", title="Example Book")


def test_safe_epub_filename_sanitizes_title():
    assert safe_epub_filename("Bad:/Title?", fallback="book") == "Bad_Title.epub"
    assert safe_epub_filename("...", fallback="book") == "book.epub"
