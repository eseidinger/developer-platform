#!/usr/bin/env python3
"""Check local Markdown links in repository documentation."""

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = [
    ROOT / "README.md",
    ROOT / "docs",
    ROOT / "platform",
    ROOT / "operations",
    ROOT / "infrastructure",
    ROOT / "ansible",
    ROOT / "examples",
]
IGNORED_PARTS = {"node_modules", ".git", ".pytest_cache", ".venv", "venv"}
LINK = re.compile(
    r"!?\[[^\]]*\]\((?P<destination><[^>]+>|[^)\s]+)(?:\s+['\"][^)]*['\"])?\)"
)
EXPLICIT_ANCHOR = re.compile(
    r"<a\b[^>]*\b(?:id|name)\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE
)
HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*#*\s*$")
FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")


def markdown_files() -> list[Path]:
    files: list[Path] = []
    for item in SEARCH_ROOTS:
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            files.extend(
                path
                for path in item.rglob("*.md")
                if not IGNORED_PARTS.intersection(path.parts)
            )
    return sorted(set(files))


def slug(title: str) -> str:
    title = re.sub(r"<[^>]+>", "", title).strip().lower()
    title = re.sub(r"[^\w\- ]", "", title, flags=re.UNICODE)
    return re.sub(r"\s+", "-", title)


def anchors(path: Path) -> set[str]:
    if path.suffix.lower() != ".md":
        return set()
    result: set[str] = set()
    counts: dict[str, int] = {}
    for _, line in visible_lines(path):
        result.update(
            match.group(1).lower() for match in EXPLICIT_ANCHOR.finditer(line)
        )
        match = HEADING.match(line)
        if not match:
            continue
        base = slug(match.group("title"))
        count = counts.get(base, 0)
        counts[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    return result


def visible_lines(path: Path):
    fence_marker: str | None = None
    for number, line in enumerate(path.read_text().splitlines(), 1):
        match = FENCE.match(line)
        if fence_marker is None and match:
            fence_marker = match.group("marker")
            continue
        if fence_marker is not None:
            if (
                match
                and match.group("marker")[0] == fence_marker[0]
                and len(match.group("marker")) >= len(fence_marker)
                and not match.group("info").strip()
            ):
                fence_marker = None
            continue
        yield number, line


errors: list[str] = []
for source in markdown_files():
    for line_number, line in visible_lines(source):
        for match in LINK.finditer(line):
            destination = match.group("destination").strip("<>")
            if destination.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            file_part, separator, anchor = destination.partition("#")
            target = (
                source
                if not file_part
                else (source.parent / unquote(file_part)).resolve()
            )
            if target.is_dir():
                target = target / "README.md"
            if not target.exists():
                errors.append(
                    f"{source.relative_to(ROOT)}:{line_number}: missing {destination}"
                )
                continue
            if separator and anchor and target.suffix.lower() == ".md":
                normalized = unquote(anchor).lower()
                if normalized not in anchors(target):
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line_number}: missing anchor "
                        f"{destination}"
                    )

if errors:
    print("\n".join(errors))
    sys.exit(1)

print(f"Checked local links in {len(markdown_files())} Markdown files.")
