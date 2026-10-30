#!/usr/bin/env python3
"""One-time, idempotent repository refactor, preserving every tracked figure.

Run at repository root: python scripts/refactor_repository.py
Migrates v* directories to experiments/, rewrites cross-references and scripts,
then builds theme-based Markdown figure atlases. No research data is deleted.
"""
from __future__ import annotations
import os
import re
import posixpath
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = re.compile(r"^v(?:[1-9]\d*)$")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".tif", ".tiff"}
MARKDOWN_LINK = re.compile(r"(!?\[[^\]\n]*\]\()([^\)\n]+)(\))")


def relocate(path: str) -> str:
    """Map an old repo-root path to its new location."""
    head = path.split("/", 1)[0]
    return ("experiments/" + path) if VERSIONS.fullmatch(head) else path


def rewrite_md(content: str, original_path: str) -> str:
    new_source = relocate(original_path)
    old_parent = posixpath.dirname(original_path)
    new_parent = posixpath.dirname(new_source) or "."
    def replace(m: re.Match) -> str:
        url = m.group(2).strip()
        if not url or url.startswith(("#", "/", "http://", "https://", "mailto:", "data:", "sandbox:")):
            return m.group(0)
        # Retain optional Markdown link titles without rewriting them.
        target, *title = url.split(" ", 1)
        pure, sep, fragment = target.partition("#")
        if not pure:
            return m.group(0)
        old_target = posixpath.normpath(posixpath.join(old_parent, pure))
        new_target = relocate(old_target)
        replacement = posixpath.relpath(new_target, new_parent)
        if replacement == ".":
            replacement = posixpath.basename(new_target)
        return m.group(1) + replacement + (sep + fragment if sep else "") + (
            " " + title[0] if title else ""
        ) + m.group(3)
    return MARKDOWN_LINK.sub(replace, content)


def rewrite_python(content: str) -> str:
    # A moved vN/foo.py needs parents[2] to locate the repository root.
    content = content.replace("Path(__file__).resolve().parents[1]",
                              "Path(__file__).resolve().parents[2]")
    # Root-relative references such as ROOT/'v10' need the new parent.
    content = re.sub(r"((?:ROOT|root|base)\s*/\s*['\"])v([1-9]\d*)(?=['\"])",
                     lambda m: m.group(1) + "experiments/v" + m.group(2), content)
    # Textual command paths such as python v10/model.py also change.
    return re.sub(r"(?<![a-zA-Z0-9_/])v([1-9]\d*)/", r"experiments/v\1/", content)


def rewrite_workflow(content: str) -> str:
    content = re.sub(r"(?<![a-zA-Z0-9_/])v([1-9]\d*)/",
                     r"experiments/v\1/", content)
    # Old computational runs become manually reproducible, avoiding
    # expensive unsolicited re-training and concurrent bot pushes on main.
    start = re.search(r"(?m)^on:\s*$", content)
    if start:
        after = re.search(r"(?m)^(?:permissions:|jobs:)\s*$", content[start.end():])
        if after:
            end = start.end() + after.start()
            content = content[:start.start()] + "on:\n  workflow_dispatch:\n" + content[end:]
    return content


def migrate() -> dict:
    dirs = [p for p in ROOT.iterdir() if p.is_dir() and VERSIONS.fullmatch(p.name)]
    if not dirs:
        return {"moved": 0, "rewritten": 0}
    paths = {p.relative_to(ROOT).as_posix(): p for p in ROOT.rglob("*") if p.is_file()
             and ".git" not in p.parts}
    md_text = {path: p.read_text(encoding="utf8") for path, p in paths.items()
               if path.lower().endswith(".md")}
    (ROOT / "experiments").mkdir(exist_ok=True)
    for folder in sorted(dirs):
        dst = ROOT / "experiments" / folder.name
        if dst.exists():
            raise RuntimeError(f"Migration destination exists: {dst}")
        shutil.move(str(folder), str(dst))
    rewritten = 0
    for old_path, before in md_text.items():
        dst = ROOT / relocate(old_path)
        after = rewrite_md(before, old_path)
        if after != before:
            dst.write_text(after, encoding="utf8")
            rewritten += 1
    for old_path, src in paths.items():
        if not (old_path.startswith(tuple(p.name + "/" for p in dirs))
                and old_path.endswith(".py")):
            continue
        dest = ROOT / relocate(old_path)
        before = dest.read_text(encoding="utf8")
        after = rewrite_python(before)
        if before != after:
            dest.write_text(after, encoding="utf8")
            rewritten += 1
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        if path.name == "repository-quality.yml" or path.name == "refactor-layout.yml":
            continue
        before = path.read_text(encoding="utf8")
        after = rewrite_workflow(before)
        if before != after:
            path.write_text(after, encoding="utf8")
            rewritten += 1
    # Root scripts are stable. Only add the new paths when they reference
    # versioned experiments directly; do not touch comments or binaries.
    for path in (ROOT / "scripts").glob("*.py"):
        if path.name in {"refactor_repository.py", "check_repository.py"}:
            continue
        before = path.read_text(encoding="utf8")
        after = re.sub(r"(?<![a-zA-Z0-9_/])v([1-9]\d*)/",
                       r"experiments/v\1/", before)
        if before != after:
            path.write_text(after, encoding="utf8")
            rewritten += 1
    return {"moved": len(dirs), "rewritten": rewritten}


def category(path: str) -> str:
    if path.startswith("demo_data/"):
        return "01_SYNTHETIC"
    if path.startswith(("results/", "docs/", "reference_tem/")):
        return "01_SYNTHETIC" if path.startswith(("results/", "docs/")) else "02_REFERENCE"
    m = re.match(r"experiments/v(\d+)/", path)
    if not m:
        return "02_REFERENCE"
    v = int(m.group(1))
    if v <= 4:
        return "02_REFERENCE"
    if v <= 7:
        return "03_REVIEW_ALIGNMENT"
    if v <= 9:
        return "04_DM3_HRTEM"
    return "05_BENCHMARKS"


GROUPS = [
    ("01_SYNTHETIC", "教師用模擬TEM・正解マスク・初期結果"),
    ("02_REFERENCE", "Pt/Ag実画像・検量・初期画像"),
    ("03_REVIEW_ALIGNMENT", "重なり判定・人手レビュー・座標診断"),
    ("04_DM3_HRTEM", "実DM3・結晶格子・HRTEM検出"),
    ("05_BENCHMARKS", "実測TEM/SEMの正解輪郭・精度評価"),
]


def build_atlases() -> dict:
    dest = ROOT / "docs" / "figures"
    dest.mkdir(parents=True, exist_ok=True)
    images = sorted(p for p in ROOT.rglob("*")
                    if p.is_file() and p.suffix.lower() in IMAGE_EXT
                    and ".git" not in p.parts)
    grouped = {key: [] for key, _ in GROUPS}
    for img in images:
        path = img.relative_to(ROOT).as_posix()
        grouped[category(path)].append(path)
    toc = [
        "# 図・画像アトラス（全画像）", "",
        "> **各画像を少なくとも1つのMarkdownに直接埋め込む**ための索引です。",
        "> 複合図・元画像・正解マスク・解析結果は別ファイルとして残し、未検証の",
        "> 数値を事実と区別します。外部提供画像の権利は提供元に帰属します。", "",
        f"**Git管理下の画像一覧：{len(images)}点**。すべての画像を以下のページに埋め込みます。", "",
    ]
    manifest = []
    for key, title in GROUPS:
        collection = grouped[key]
        filename = key.lower() + ".md"
        toc.append(f"- [{title}（{len(collection)}画像）](figures/{filename})")
        sections = [f"# {title}", "",
                    f"掲載画像：**{len(collection)}点**。図は掲載時の分析バージョンであり、",
                    "最新の性能やモデルの正しさを保証するものではありません。",
                    ""]
        last_dir = None
        for i, path in enumerate(collection, 1):
            dirname = posixpath.dirname(path)
            if dirname != last_dir:
                sections.extend([f"## \`{dirname}/\`", ""])
                last_dir = dirname
            rel = posixpath.relpath(path, "docs/figures")
            sections.extend([f"### {i}. \`{posixpath.basename(path)}\`", "",
                            f"![{path}]({rel})", "",
                            f"原ファイル：[\`{path}\`]({rel})", ""])
            manifest.append(path)
        (dest / filename).write_text("\n".join(sections) + "\n", encoding="utf8")
        toc.append("")
    (ROOT / "docs/FIGURE_INDEX.md").write_text("\n".join(toc) + "\n", encoding="utf8")
    return {"figure_files": len(images), "embedded": len(manifest), "groups": {
        key: len(grouped[key]) for key, _ in GROUPS
    }}


if __name__ == "__main__":
    import json
    state = {"migration": migrate(), "atlas": build_atlases()}
    print(json.dumps(state, ensure_ascii=False, indent=2))
