"""
Minimal .env loader (no external dependency).

Reads KEY=VALUE lines from a .env file in the project root and sets any that
aren't already in the environment. Supports a few friendly aliases so the
names in .env don't have to match the exact variable names the code uses.

Aliases:
  GMAIL_PASSWORD      -> GMAIL_APP_PASSWORD
  EMAIL_USER / GMAIL  -> GMAIL_USER
"""
from __future__ import annotations

import os
import sys

_ALIASES = {
    "GMAIL_PASSWORD": "GMAIL_APP_PASSWORD",
    "EMAIL_PASSWORD": "GMAIL_APP_PASSWORD",
    "EMAIL_USER": "GMAIL_USER",
    "GMAIL": "GMAIL_USER",
    "GMAIL_ADDRESS": "GMAIL_USER",
}


def load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # Set the raw key and any alias target, without overwriting
                # anything already present in the real environment.
                for target in (key, _ALIASES.get(key)):
                    if target and target not in os.environ:
                        os.environ[target] = value
    except OSError as e:
        print(f"[env] could not read {path}: {e}", file=sys.stderr)
