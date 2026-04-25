"""Databricks workspace client for SeaHealth.

Reads `DATABRICKS_HOST` and `DATABRICKS_TOKEN` from `.env`. The SDK
auto-detects these variable names — do not rename.
"""

from __future__ import annotations

from pathlib import Path

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")


def get_workspace() -> WorkspaceClient:
    return WorkspaceClient()
