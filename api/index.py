"""Vercel Python entrypoint for the SeaHealth FastAPI backend.

Vercel's Python runtime auto-detects an ASGI `app` symbol in `api/*.py`.
The real FastAPI app lives at `seahealth.api.main:app` and defines its
routes at root (`/health`, `/query`, ...). Public traffic to this function
arrives with a `/api/...` prefix (per the rewrite in `vercel.json`), so we
mount the inner app under `/api` here. The mount strips the prefix before
the inner app's router sees the request, so the existing route table works
unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the `seahealth` package importable when the function runs.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import FastAPI  # noqa: E402

from seahealth.api.main import app as inner_app  # noqa: E402

app = FastAPI(title="SeaHealth on Vercel", docs_url=None, redoc_url=None)
app.mount("/api", inner_app)
