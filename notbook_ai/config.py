"""Load YAML + environment configuration. Fails fast on missing secrets."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # optional at runtime if host injects env
    load_dotenv = None


_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    telegram_token: str
    gemini_api_keys: list[str]
    pinecone_api_key: str
    admin_user_ids: frozenset[int]
    raw_config: dict[str, Any]
    project_root: Path


def _load_yaml() -> dict[str, Any]:
    candidates = [
        _ROOT / "config.yaml",
        Path.cwd() / "config.yaml",
    ]
    for path in candidates:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                raise ValueError(f"config.yaml must be a mapping: {path}")
            return data
    raise FileNotFoundError(
        f"config.yaml not found. Looked in: {[str(p) for p in candidates]}"
    )


def _gemini_keys() -> list[str]:
    keys_str = os.getenv("GEMINI_API_KEYS", "")
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    if not keys:
        single = os.getenv("GEMINI_API_KEY", "").strip()
        if single:
            keys = [single]
    return keys


def load_config(*, require_secrets: bool = True) -> Config:
    if load_dotenv is not None:
        # Prefer project .env; do not override already-set process env
        load_dotenv(_ROOT / ".env", override=False)
        load_dotenv(override=False)

    yaml_data = _load_yaml()
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    keys = _gemini_keys()
    pinecone = (os.getenv("PINECONE_API_KEY") or "").strip()

    if require_secrets:
        missing = []
        if not token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not keys:
            missing.append("GEMINI_API_KEY or GEMINI_API_KEYS")
        if not pinecone:
            missing.append("PINECONE_API_KEY")
        if missing:
            print(
                "Missing required environment variables:\n  - "
                + "\n  - ".join(missing)
                + "\nCopy .env.example to .env and fill values.",
                file=sys.stderr,
            )
            raise SystemExit(1)

    admin_raw = os.getenv("ADMIN_USER_IDS", "") or os.getenv("ADMIN_USER_ID", "")
    admin_ids: set[int] = set()
    for part in admin_raw.split(","):
        part = part.strip()
        if part.isdigit():
            admin_ids.add(int(part))

    return Config(
        telegram_token=token,
        gemini_api_keys=keys,
        pinecone_api_key=pinecone,
        admin_user_ids=frozenset(admin_ids),
        raw_config=yaml_data,
        project_root=_ROOT,
    )


config = load_config(require_secrets=True)
