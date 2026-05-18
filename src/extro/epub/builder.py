"""Build Send to Kindle-oriented EPUB files from downloaded snapshots."""

from __future__ import annotations

import html
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final
from urllib.parse import unquote, urldefrag, urlparse

from bs4 import BeautifulSoup
from defusedxml import ElementTree
from soupsieve.util import SelectorSyntaxError

from extro.app.exceptions import ExtroError
from extro.app.paths import safe_export_stem

if TYPE_CHECKING:
    from bs4.element import Tag

_CONTAINER_XML_TEMPLATE: Final = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{rootfile_path}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
_EPUB_MIMETYPE: Final = "application/epub+zip"
_OPF_NAMESPACE: Final = {"opf": "http://www.idpf.org/2007/opf"}
_HTML_MEDIA_TYPES: Final = {"application/xhtml+xml", "text/html"}
_CSS_MEDIA_TYPES: Final = {"text/css"}
_HTML_FILE_LIMIT: Final = 300
_HTML_SIZE_LIMIT_BYTES: Final = 30 * 1024 * 1024
_ERROR_SAMPLE_LIMIT: Final = 10
_HIDDEN_TEXT_SAMPLE_LIMIT: Final = 160
_HIDDEN_AUDIT_FINDING_LIMIT: Final = 10
KINDLE_HIDDEN_CHARACTER_LIMIT: Final = 10_000
_SAFE_FILENAME_RE: Final = re.compile(r"[^A-Za-z0-9_. -]+")
_DISPLAY_NONE_RE: Final = re.compile(
    r"display\s*:\s*none(?:\s*!important)?",
    re.IGNORECASE,
)
_DISPLAY_NONE_DECLARATION_RE: Final = re.compile(
    r"display\s*:\s*none(?P<important>\s*!important)?",
    re.IGNORECASE,
)
_CSS_COMMENT_RE: Final = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_RULE_RE: Final = re.compile(
    r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}",
    re.DOTALL,
)


@dataclass(frozen=True)
class EpubBuildResult:
    """Details about a generated EPUB file."""

    output_path: Path
    html_file_count: int
    manifest_item_count: int


@dataclass(frozen=True)
class HiddenContentFinding:
    """One generated XHTML block that Kindle may count as hidden text."""

    href: str
    source: str
    character_count: int
    sample: str


@dataclass(frozen=True)
class HiddenContentAuditResult:
    """Hidden-content summary for generated EPUB XHTML."""

    html_file_count: int
    total_hidden_characters: int
    findings: tuple[HiddenContentFinding, ...]
    hidden_character_limit: int = KINDLE_HIDDEN_CHARACTER_LIMIT

    @property
    def affected_file_count(self) -> int:
        """Number of generated XHTML files containing hidden text."""
        return len({finding.href for finding in self.findings})


@dataclass(frozen=True)
class _ManifestItem:
    href: str
    media_type: str


@dataclass(frozen=True)
class _SnapshotContext:
    files_dir: Path
    opf_path: Path
    opf_href: str
    items: list[_ManifestItem]
    html_items: list[_ManifestItem]
    css_items: list[_ManifestItem]


@dataclass(frozen=True)
class _HiddenCssRule:
    href: str
    selector: str


def safe_epub_filename(title: str, *, fallback: str) -> str:
    """Return a filesystem-safe EPUB filename for a book title."""
    cleaned = safe_export_stem(title, fallback=fallback)
    stem = cleaned or fallback
    return f"{stem}.epub"


def build_epub(
    snapshot_path: Path,
    output_path: Path,
    *,
    title: str,
) -> EpubBuildResult:
    """Build an EPUB archive from a downloaded snapshot directory."""
    context = _snapshot_context(snapshot_path)
    archive_opf_path = f"OEBPS/{context.opf_href}"
    css_hrefs = [item.href for item in context.css_items]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.name}.tmp")
    try:
        with zipfile.ZipFile(temp_path, mode="w") as archive:
            _write_mimetype(archive)
            archive.writestr(
                "META-INF/container.xml",
                _CONTAINER_XML_TEMPLATE.format(rootfile_path=archive_opf_path),
            )
            archive.write(context.opf_path, archive_opf_path)
            for item in context.items:
                source_path = _safe_source_path(context.files_dir, item.href)
                archive_path = f"OEBPS/{item.href}"
                if _is_html_item(item):
                    content = _clean_html(
                        source_path.read_text(encoding="utf-8"),
                        href=item.href,
                        title=title,
                        css_hrefs=css_hrefs,
                    )
                    _validate_html(content, item.href)
                    archive.writestr(archive_path, content)
                elif _is_css_item(item):
                    content = _rewrite_css_display_none(
                        source_path.read_text(encoding="utf-8", errors="replace")
                    )
                    archive.writestr(archive_path, content)
                else:
                    archive.write(source_path, archive_path)
            _validate_archive_manifest(archive, context.items)
        temp_path.replace(output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return EpubBuildResult(
        output_path=output_path,
        html_file_count=len(context.html_items),
        manifest_item_count=len(context.items),
    )


def audit_hidden_content(
    snapshot_path: Path,
    *,
    title: str,
) -> HiddenContentAuditResult:
    """Audit generated EPUB XHTML for hidden text counted by Kindle Previewer."""
    context = _snapshot_context(snapshot_path)
    css_hrefs = [item.href for item in context.css_items]
    css_rules = _hidden_css_rules(context.files_dir, context.css_items)

    findings: list[HiddenContentFinding] = []
    for item in context.html_items:
        source_path = _safe_source_path(context.files_dir, item.href)
        content = _clean_html(
            source_path.read_text(encoding="utf-8"),
            href=item.href,
            title=title,
            css_hrefs=css_hrefs,
        )
        _validate_html(content, item.href)
        findings.extend(_audit_html_hidden_content(content, item.href, css_rules))

    sorted_findings = tuple(
        sorted(findings, key=lambda finding: finding.character_count, reverse=True)
    )
    return HiddenContentAuditResult(
        html_file_count=len(context.html_items),
        total_hidden_characters=sum(
            finding.character_count for finding in sorted_findings
        ),
        findings=sorted_findings,
    )


def hidden_audit_finding_limit() -> int:
    """Default number of top hidden-content findings to show in CLI output."""
    return _HIDDEN_AUDIT_FINDING_LIMIT


def _snapshot_context(snapshot_path: Path) -> _SnapshotContext:
    files_dir = snapshot_path / "files"
    opf_path = _find_package_document(files_dir)
    opf_href = _source_href(files_dir, opf_path)
    items = _manifest_items(opf_path)
    html_items = [item for item in items if _is_html_item(item)]
    css_items = [item for item in items if _is_css_item(item)]

    if len(html_items) >= _HTML_FILE_LIMIT:
        msg = (
            "Send to Kindle supports fewer than "
            f"{_HTML_FILE_LIMIT} HTML files; found {len(html_items)}."
        )
        raise ExtroError(msg)

    missing = [
        item.href
        for item in items
        if not _safe_source_path(files_dir, item.href).is_file()
    ]
    if missing:
        sample = ", ".join(missing[:_ERROR_SAMPLE_LIMIT])
        suffix = "..." if len(missing) > _ERROR_SAMPLE_LIMIT else ""
        msg = f"Snapshot is incomplete; missing manifest file(s): {sample}{suffix}"
        raise ExtroError(msg)

    return _SnapshotContext(
        files_dir=files_dir,
        opf_path=opf_path,
        opf_href=opf_href,
        items=items,
        html_items=html_items,
        css_items=css_items,
    )


def _find_package_document(files_dir: Path) -> Path:
    preferred = files_dir / "content.opf"
    if preferred.is_file():
        return preferred

    candidates = sorted(files_dir.rglob("*.opf"))
    if not candidates:
        msg = f"Snapshot is missing an OPF package document: {files_dir.parent}"
        raise ExtroError(msg)
    if len(candidates) > 1:
        relative = ", ".join(str(_source_href(files_dir, path)) for path in candidates)
        msg = f"Snapshot has multiple OPF package documents: {relative}"
        raise ExtroError(msg)
    return candidates[0]


def _source_href(files_dir: Path, path: Path) -> str:
    relative = path.resolve().relative_to(files_dir.resolve())
    href = PurePosixPath(relative.as_posix()).as_posix()
    _validate_relative_href(href)
    return href


def _manifest_items(opf_path: Path) -> list[_ManifestItem]:
    try:
        root = ElementTree.parse(opf_path).getroot()
    except ElementTree.ParseError as exc:
        msg = f"Invalid OPF file: {opf_path}"
        raise ExtroError(msg) from exc
    if root is None:
        msg = f"Invalid OPF file: {opf_path}"
        raise ExtroError(msg)

    items: list[_ManifestItem] = []
    for node in root.findall(".//opf:manifest/opf:item", _OPF_NAMESPACE):
        href = node.attrib.get("href")
        media_type = node.attrib.get("media-type")
        if href is None or media_type is None:
            msg = "OPF manifest item is missing href or media-type."
            raise ExtroError(msg)
        _validate_relative_href(href)
        items.append(_ManifestItem(href=href, media_type=media_type))

    if not items:
        msg = "OPF manifest does not contain any files."
        raise ExtroError(msg)
    return items


def _is_html_item(item: _ManifestItem) -> bool:
    suffix = PurePosixPath(item.href).suffix.lower()
    return item.media_type in _HTML_MEDIA_TYPES or suffix in {".html", ".htm", ".xhtml"}


def _is_css_item(item: _ManifestItem) -> bool:
    return item.media_type in _CSS_MEDIA_TYPES or item.href.lower().endswith(".css")


def _validate_relative_href(href: str) -> None:
    relative = PurePosixPath(href)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        msg = f"Unsafe OPF manifest path: {href}"
        raise ExtroError(msg)


def _safe_source_path(root: Path, href: str) -> Path:
    relative_parts = _relative_href_parts(href)
    candidate = _safe_source_path_from_parts(root, relative_parts, href)
    if candidate.is_file():
        return candidate

    decoded_parts = _decoded_href_parts(href)
    if decoded_parts == relative_parts:
        return candidate
    return _safe_source_path_from_parts(root, decoded_parts, href)


def _relative_href_parts(href: str) -> tuple[str, ...]:
    _validate_relative_href(href)
    return PurePosixPath(href).parts


def _decoded_href_parts(href: str) -> tuple[str, ...]:
    decoded_parts = tuple(unquote(part) for part in _relative_href_parts(href))
    if any(
        part in {"", ".", ".."} or "/" in part or "\\" in part for part in decoded_parts
    ):
        msg = f"Unsafe OPF manifest path: {href}"
        raise ExtroError(msg)
    return decoded_parts


def _safe_source_path_from_parts(
    root: Path,
    relative_parts: tuple[str, ...],
    href: str,
) -> Path:
    candidate = root.joinpath(*relative_parts).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        msg = f"Unsafe OPF manifest path: {href}"
        raise ExtroError(msg)
    return candidate


def _write_mimetype(archive: zipfile.ZipFile) -> None:
    info = zipfile.ZipInfo("mimetype")
    info.compress_type = zipfile.ZIP_STORED
    archive.writestr(info, _EPUB_MIMETYPE)


def _clean_html(
    markup: str,
    *,
    href: str,
    title: str,
    css_hrefs: list[str],
) -> str:
    soup = BeautifulSoup(markup, "html.parser")
    _remove_unsafe_elements(soup)
    _rewrite_html_hidden_rendering(soup)
    _rewrite_links(soup, current_href=href)

    body_source = soup.body if soup.body is not None else soup
    body_markup = body_source.decode_contents(formatter="minimal")
    heading = _first_text(soup, "h1") or _first_text(soup, "title") or title
    css_links = "".join(
        '<link rel="stylesheet" type="text/css" '
        f'href="{html.escape(_relative_href(href, css_href))}"/>'
        for css_href in css_hrefs
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head>"
        f"<title>{html.escape(heading)}</title>"
        f"{css_links}"
        "</head>\n"
        f"<body>{body_markup}</body>\n"
        "</html>\n"
    )


def _remove_unsafe_elements(soup: BeautifulSoup) -> None:
    for tag in soup.find_all("script"):
        tag.decompose()
    for tag in soup.find_all(id="sec-overlay"):
        tag.decompose()
    for tag in soup.find_all("link"):
        if _root_absolute(str(tag.get("href", ""))):
            tag.decompose()


def _rewrite_html_hidden_rendering(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(name=True):
        style = tag.get("style")
        if isinstance(style, str):
            rewritten = _rewrite_css_display_none(style)
            if rewritten != style:
                tag["style"] = rewritten
        if tag.has_attr("hidden"):
            del tag["hidden"]
            _append_inline_style(tag, "visibility: hidden")


def _rewrite_css_display_none(css: str) -> str:
    return _DISPLAY_NONE_DECLARATION_RE.sub(
        lambda match: f"visibility: hidden{match.group('important') or ''}",
        css,
    )


def _append_inline_style(tag: Tag, declaration: str) -> None:
    style = tag.get("style")
    if isinstance(style, str) and style.strip():
        separator = "" if style.rstrip().endswith(";") else ";"
        tag["style"] = f"{style.rstrip()}{separator} {declaration}"
        return
    tag["style"] = declaration


def _hidden_css_rules(
    files_dir: Path,
    css_items: list[_ManifestItem],
) -> tuple[_HiddenCssRule, ...]:
    rules: list[_HiddenCssRule] = []
    for item in css_items:
        css_path = _safe_source_path(files_dir, item.href)
        css = _rewrite_css_display_none(
            css_path.read_text(encoding="utf-8", errors="replace")
        )
        cleaned = _CSS_COMMENT_RE.sub("", css)
        for match in _CSS_RULE_RE.finditer(cleaned):
            if _DISPLAY_NONE_RE.search(match.group("body")) is None:
                continue
            selector_group = match.group("selectors")
            for selector in selector_group.split(","):
                normalized = selector.strip()
                if normalized and not normalized.startswith("@"):
                    rules.append(_HiddenCssRule(href=item.href, selector=normalized))
    return tuple(rules)


def _audit_html_hidden_content(
    content: str,
    href: str,
    css_rules: tuple[_HiddenCssRule, ...],
) -> list[HiddenContentFinding]:
    soup = BeautifulSoup(content, "html.parser")
    hidden_by_tag: dict[Tag, str] = {}

    for tag in soup.find_all(name=True):
        source = _inline_hidden_source(tag)
        if source is not None:
            hidden_by_tag[tag] = source

    for rule in css_rules:
        try:
            matches = soup.select(rule.selector)
        except SelectorSyntaxError:
            continue
        for match in matches:
            hidden_by_tag.setdefault(
                match,
                f"css {rule.href}: {rule.selector}",
            )

    findings: list[HiddenContentFinding] = []
    counted: set[Tag] = set()
    for tag in soup.find_all(name=True):
        if tag not in hidden_by_tag:
            continue
        if any(parent in counted for parent in tag.parents):
            continue
        text = _normalized_text(tag)
        if not text:
            continue
        counted.add(tag)
        findings.append(
            HiddenContentFinding(
                href=href,
                source=hidden_by_tag[tag],
                character_count=len(text),
                sample=_sample_hidden_text(text),
            )
        )
    return findings


def _inline_hidden_source(tag: Tag) -> str | None:
    style = tag.get("style")
    if isinstance(style, str) and _DISPLAY_NONE_RE.search(style) is not None:
        return "inline style display:none"
    if tag.has_attr("hidden"):
        return "hidden attribute"
    aria_hidden = tag.get("aria-hidden")
    if isinstance(aria_hidden, str) and aria_hidden.casefold() == "true":
        return "aria-hidden=true"
    return None


def _normalized_text(tag: Tag) -> str:
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()


def _sample_hidden_text(text: str) -> str:
    if len(text) <= _HIDDEN_TEXT_SAMPLE_LIMIT:
        return text
    return f"{text[: _HIDDEN_TEXT_SAMPLE_LIMIT - 3].rstrip()}..."


def _rewrite_links(soup: BeautifulSoup, *, current_href: str) -> None:
    for tag in soup.find_all(name=True):
        for attr in ("href", "src"):
            value = tag.get(attr)
            if not isinstance(value, str):
                continue
            rewritten = _rewrite_reference(value, current_href=current_href)
            if rewritten is None:
                del tag[attr]
            else:
                tag[attr] = rewritten


def _rewrite_reference(value: str, *, current_href: str) -> str | None:
    if value.startswith("#"):
        return value
    target = _oreilly_file_href(value)
    if target is not None:
        return _relative_href(current_href, target)
    if _root_absolute(value):
        return None
    return value


def _oreilly_file_href(value: str) -> str | None:
    without_fragment, fragment = urldefrag(value)
    parsed = urlparse(without_fragment)
    path = parsed.path if parsed.scheme else without_fragment
    marker = "/files/"
    if "/api/v2/epubs/" not in path or marker not in path:
        return None

    href = path.split(marker, maxsplit=1)[1].lstrip("/")
    if not href:
        return None
    _validate_relative_href(href)
    if fragment:
        return f"{href}#{fragment}"
    return href


def _root_absolute(value: str) -> bool:
    return value.startswith("/") and not value.startswith("//")


def _relative_href(current_href: str, target_href: str) -> str:
    current_dir = posixpath.dirname(current_href) or "."
    target, fragment = urldefrag(target_href)
    relative = posixpath.relpath(target, start=current_dir)
    if relative == ".":
        relative = posixpath.basename(target)
    if fragment:
        return f"{relative}#{fragment}"
    return relative


def _first_text(soup: BeautifulSoup, selector: str) -> str | None:
    tag = soup.find(selector)
    if tag is None:
        return None
    text = tag.get_text(" ", strip=True)
    return text or None


def _validate_html(content: str, href: str) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > _HTML_SIZE_LIMIT_BYTES:
        msg = f"Send to Kindle HTML file limit exceeded: {href}"
        raise ExtroError(msg)
    try:
        ElementTree.fromstring(encoded)
    except ElementTree.ParseError as exc:
        msg = f"Generated XHTML is invalid for {href}: {exc}"
        raise ExtroError(msg) from exc
    lowered = content.lower()
    if "<script" in lowered:
        msg = f"Generated XHTML still contains script tags: {href}"
        raise ExtroError(msg)
    if 'href="/' in lowered or 'src="/' in lowered:
        msg = f"Generated XHTML still contains root-absolute links: {href}"
        raise ExtroError(msg)


def _validate_archive_manifest(
    archive: zipfile.ZipFile,
    items: list[_ManifestItem],
) -> None:
    names = set(archive.namelist())
    missing = [item.href for item in items if f"OEBPS/{item.href}" not in names]
    if missing:
        sample = ", ".join(missing[:_ERROR_SAMPLE_LIMIT])
        suffix = "..." if len(missing) > _ERROR_SAMPLE_LIMIT else ""
        msg = f"EPUB archive is missing manifest file(s): {sample}{suffix}"
        raise ExtroError(msg)
