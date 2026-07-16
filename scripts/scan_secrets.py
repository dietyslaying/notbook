#!/usr/bin/env python3
"""Fail if common secret patterns appear in tracked source files."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "data",
    "__pycache__",
    "node_modules",
}

PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "Google API key"),
    (re.compile(r"pcsk_[0-9A-Za-z_-]{20,}"), "Pinecone API key"),
    (re.compile(r"ghp_[0-9A-Za-z]{20,}"), "GitHub PAT"),
    (re.compile(r"rnd_[0-9A-Za-z]{20,}"), "Render API key"),
    (
        re.compile(
            r"""os\.environ\[['\"](?:PINECONE|GEMINI|TELEGRAM)[^'\"]*['\"]\]\s*=\s*['\"][^'\"]{8,}['\"]"""
        ),
        "Hardcoded os.environ assignment",
    ),
]


def main() -> int:
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        if rel.name.startswith(".env") and rel.name != ".env.example":
            continue
        if path.suffix.lower() not in {
            ".py",
            ".js",
            ".ts",
            ".json",
            ".yaml",
            ".yml",
            ".md",
            ".txt",
            ".toml",
            ".sh",
            ".ps1",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat, label in PATTERNS:
            if pat.search(text):
                hits.append(f"{rel}: {label}")
    if hits:
        print("SECRET SCAN FAILED:")
        for h in hits:
            print(" ", h)
        return 1
    print("SECRET SCAN OK — no hardcoded key patterns in source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
