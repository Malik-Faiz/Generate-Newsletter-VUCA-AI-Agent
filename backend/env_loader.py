"""
env_loader.py
─────────────────
A minimal, dependency-free .env file loader — reads KEY=VALUE lines from
a .env file next to this module and puts them into os.environ (without
overriding anything already set in the real environment). This avoids
adding python-dotenv as a dependency; it's a handful of lines and this
app doesn't need anything fancier (no multiline values, no variable
expansion).

Import this before anything that reads os.environ at import time
(e.g. newsletter_ai.py reads GROQ_MODEL at module load).
"""

import os
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"


def load_env():
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
