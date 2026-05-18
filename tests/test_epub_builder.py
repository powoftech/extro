from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from extro.app.exceptions import ExtroError
from extro.epub import audit_hidden_content, build_epub, safe_epub_filename


@dataclass(frozen=True)
class _SnapshotOptions:
    html_href: str = "text/ch01.html"
    include_asset: bool = True
    opf_name: str = "content.opf"
    html_markup: str | None = None
    stylesheet_css: str = "body { color: black; }"


def _write_snapshot(
    root: Path,
    options: _SnapshotOptions | None = None,
) -> Path:
    snapshot_options = options or _SnapshotOptions()
    files = root / "files"
    files.mkdir(parents=True)
    (files / "assets").mkdir()
    (files / "text").mkdir()
    (files / "stylesheet.css").write_text(
        snapshot_options.stylesheet_css,
        encoding="utf-8",
    )
    (files / "styles").mkdir()
    (files / "styles" / "page_styles.css").write_text(
        "img { max-width: 100%; }",
        encoding="utf-8",
    )
    (files / "toc.ncx").write_text("<ncx></ncx>", encoding="utf-8")
    if snapshot_options.include_asset:
        (files / "assets" / "cover.png").write_bytes(b"png")

    html_path = files.joinpath(*Path(snapshot_options.html_href).parts)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        snapshot_options.html_markup
        or """
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
    (files / snapshot_options.opf_name).write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
        <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
          <manifest>
            <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
            <item id="css" href="stylesheet.css" media-type="text/css"/>
            <item id="page-css" href="styles/page_styles.css" media-type="text/css"/>
            <item id="cover" href="assets/cover.png" media-type="image/png"/>
            <item id="chapter" href="{snapshot_options.html_href}"
                  media-type="application/xhtml+xml"/>
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
    snapshot = _write_snapshot(
        tmp_path / "snapshot",
        _SnapshotOptions(opf_name="9780321700698.opf"),
    )
    output = tmp_path / "book.epub"

    build_epub(snapshot, output, title="Example Book")

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        container = archive.read("META-INF/container.xml").decode()

    assert "OEBPS/9780321700698.opf" in names
    assert 'full-path="OEBPS/9780321700698.opf"' in container


def test_build_epub_resolves_percent_encoded_manifest_href_to_decoded_file(tmp_path):
    snapshot = _write_snapshot(tmp_path / "snapshot")
    files = snapshot / "files"
    image_dir = files / "Images"
    image_dir.mkdir()
    (image_dir / "9781836200079_(1).png").write_bytes(b"png")
    opf_path = files / "content.opf"
    opf_path.write_text(
        opf_path.read_text(encoding="utf-8").replace(
            'href="assets/cover.png"',
            'href="Images/9781836200079_%281%29.png"',
        ),
        encoding="utf-8",
    )
    output = tmp_path / "book.epub"

    build_epub(snapshot, output, title="Example Book")

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        content = archive.read("OEBPS/Images/9781836200079_%281%29.png")

    assert "OEBPS/Images/9781836200079_%281%29.png" in names
    assert content == b"png"


def test_build_epub_fails_when_manifest_file_is_missing(tmp_path):
    snapshot = _write_snapshot(
        tmp_path / "snapshot",
        _SnapshotOptions(include_asset=False),
    )

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


def test_audit_hidden_content_reports_generated_xhtml_hidden_text(tmp_path):
    hidden_text = [
        "Inline hidden text",
        "Attribute hidden text",
        "Aria hidden text",
        "Stylesheet class hidden text",
        "Stylesheet id hidden text",
    ]
    snapshot = _write_snapshot(
        tmp_path / "snapshot",
        _SnapshotOptions(
            html_markup=f"""
        <div id="sbo-rt-content">
          <h1>Chapter One</h1>
          <p>Visible reading text</p>
          <div style="display:none">{hidden_text[0]}</div>
          <p hidden>{hidden_text[1]}</p>
          <section aria-hidden="true">{hidden_text[2]}</section>
          <div class="css-hidden">{hidden_text[3]}</div>
          <div id="id-hidden">{hidden_text[4]}</div>
        </div>
        """,
            stylesheet_css="""
        .css-hidden { display: none; }
        #id-hidden { color: red; display: none !important; }
        """,
        ),
    )

    result = audit_hidden_content(snapshot, title="Example Book")

    assert result.html_file_count == 1
    assert result.affected_file_count == 1
    assert result.total_hidden_characters == len("Aria hidden text")
    assert [finding.href for finding in result.findings] == ["text/ch01.html"]
    sources = {finding.source for finding in result.findings}
    assert "aria-hidden=true" in sources
    samples = " ".join(finding.sample for finding in result.findings)
    assert "Visible reading text" not in samples


def test_build_epub_rewrites_display_none_without_deleting_text(tmp_path):
    hidden_text = [
        "Inline hidden text",
        "Attribute hidden text",
        "Stylesheet hidden text",
    ]
    snapshot = _write_snapshot(
        tmp_path / "snapshot",
        _SnapshotOptions(
            html_markup=f"""
        <div id="sbo-rt-content">
          <h1>Chapter One</h1>
          <div style="display:none">{hidden_text[0]}</div>
          <p hidden>{hidden_text[1]}</p>
          <div class="css-hidden">{hidden_text[2]}</div>
        </div>
        """,
            stylesheet_css=".css-hidden { color: red; display: none !important; }",
        ),
    )
    output = tmp_path / "book.epub"

    build_epub(snapshot, output, title="Example Book")

    source_html = (snapshot / "files" / "text" / "ch01.html").read_text(
        encoding="utf-8"
    )
    source_css = (snapshot / "files" / "stylesheet.css").read_text(encoding="utf-8")
    with zipfile.ZipFile(output) as archive:
        html_content = archive.read("OEBPS/text/ch01.html").decode()
        css_content = archive.read("OEBPS/stylesheet.css").decode()

    assert "display:none" in source_html
    assert "display: none" in source_css
    for text in hidden_text:
        assert text in html_content
    assert "display:none" not in html_content.replace(" ", "")
    assert "display:none" not in css_content.replace(" ", "")
    assert "visibility: hidden" in html_content
    assert "visibility: hidden !important" in css_content


def test_safe_epub_filename_sanitizes_title():
    assert safe_epub_filename("Bad:/Title?", fallback="book") == "bad_title.epub"
    assert safe_epub_filename("...", fallback="book") == "book.epub"


def test_safe_epub_filename_collapses_repeated_underscores():
    assert (
        safe_epub_filename(
            "The Pragmatic Programmer: your journey to mastery, "
            "20th Anniversary Edition, 2nd Edition",
            fallback="fallback__name",
        )
        == "the_pragmatic_programmer_your_journey_to_mastery_20th_"
        "anniversary_edition_2nd_edition.epub"
    )
