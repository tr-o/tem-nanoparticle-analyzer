#!/usr/bin/env python3
"""Require every tracked research figure to be embedded in Markdown.

Also checks local Markdown destinations and that versioned history lives only
under experiments/ rather than at repository root.
"""
from __future__ import annotations
import posixpath
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {".jpg", ".jpeg", ".png", ".svg", ".gif", ".webp", ".tif", ".tiff"}
MARKDOWN_LINK = re.compile(r"(!?\[[^\]\n]*\])\(([^)\n]+)\)")
VERSION = re.compile(r"^v[1-9]\d*$")


def list_tracked() -> list[str]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                            check=True, stdout=subprocess.PIPE)
    return [x.decode("utf8") for x in result.stdout.split(b"\0") if x]


def destinations(md: str, contents: str):
    for hit in MARKDOWN_LINK.finditer(contents):
        label, link = hit.groups()
        raw = link.strip().split(" ", 1)[0]
        if not raw or raw.startswith(("http://", "https://", "mailto:", "#", "data:", "sandbox:")):
            continue
        raw = raw.split("#", 1)[0]
        if not raw:
            continue
        if raw.startswith("/"):
            yield label.startswith("!"), "[absolute path]", raw
        else:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(md), raw))
            yield label.startswith("!"), resolved, raw


def audit():
    tracked = list_tracked()
    paths = set(tracked)
    illustrations = {p for p in paths if Path(p).suffix.lower() in IMAGES}
    markdowns = sorted(p for p in paths if p.endswith(".md"))
    embedded = set()
    missing = []
    for md in markdowns:
        file = ROOT / md
        if not file.is_file():
            missing.append((md, "(missing file)", ""))
            continue
        for is_image, path, original in destinations(md, file.read_text(encoding="utf8")):
            if path not in paths:
                missing.append((md, original, path))
            if is_image and path in illustrations:
                embedded.add(path)
    unpictured = sorted(illustrations - embedded)
    legacy_at_root = sorted(p.name for p in ROOT.iterdir()
                            if p.is_dir() and VERSION.fullmatch(p.name))
    unstructured_root = sorted(p for p in tracked if '/' not in p and Path(p).suffix in {'.py', '.joblib', '.json'})
    print(f"tracked: {len(paths)} | images: {len(illustrations)} | "
          f"embedded: {len(embedded)} | markdown: {len(markdowns)}")
    print(f"not embedded: {len(unpictured)} | broken links: {len(missing)} "
          f"| legacy dirs at root: {len(legacy_at_root)} | root code/model files: {len(unstructured_root)}")
    for p in unpictured[:50]:
        print("IMAGE_NOT_IN_MARKDOWN:", p)
    for md, url, resolved in missing[:60]:
        print("BROKEN_LINK:", md, "=>", url, "resolved:", resolved)
    for p in legacy_at_root:
        print("ROOT_LEGACY_DIRECTORY:", p)
    for p in unstructured_root:
        print("STRAY_ROOT_CODE_OR_MODEL:", p)
    if missing or unpictured or legacy_at_root or unstructured_root:
        raise SystemExit(1)
    print("OK: Every tracked image is embedded and every local Markdown link resolves.")


if __name__ == "__main__":
    audit()
