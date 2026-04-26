"""Helpers for the workspace SQL warehouse used by SeaHealth provisioning + queries.

Reuses the WorkspaceClient from `databricks_client.py`. Idempotent — safe to call
`ensure_running` repeatedly.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

from .databricks_client import get_workspace

_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def _redact_secrets(value: object) -> str:
    """Return a log/error-safe string with bearer tokens removed."""
    return _BEARER_RE.sub("Bearer [REDACTED]", str(value))


def _state_value(state: Any) -> str:
    """Normalize SDK enum/string state values for comparisons and errors."""
    return getattr(state, "value", state) or "UNKNOWN"


def _rows_to_dicts(columns: list[str], data_array: list[list[Any]]) -> list[dict[str, Any]]:
    """Map Databricks result arrays to stable dict rows keyed by every column."""
    rows: list[dict[str, Any]] = []
    for row in data_array:
        rows.append(
            {
                column: row[idx] if idx < len(row) else None
                for idx, column in enumerate(columns)
            }
        )
    return rows


def get_warehouse_id() -> str:
    """Return a SQL warehouse id.

    Resolution order:
      1. ``DATABRICKS_WAREHOUSE_ID`` env var if set.
      2. The first warehouse returned by ``warehouses.list()`` (alphabetical via
         the API). For the SeaHealth workspace this resolves to "Serverless
         Starter Warehouse" id ``6ad31cb2ae70ef44``.

    Raises:
        RuntimeError: when no warehouse is visible to the caller.
    """
    env_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
    if env_id:
        return env_id

    w = get_workspace()
    warehouses = list(w.warehouses.list())
    if not warehouses:
        raise RuntimeError(
            "no SQL warehouses visible to current PAT — provision one in the workspace UI"
        )
    return warehouses[0].id


def ensure_running(warehouse_id: str | None = None, timeout_s: int = 180) -> str:
    """Ensure a SQL warehouse is in RUNNING state, starting it if needed.

    Polls ``warehouses.get`` until state is ``RUNNING`` or the timeout expires.

    Args:
        warehouse_id: optional explicit id; resolved via :func:`get_warehouse_id`
            when omitted.
        timeout_s: seconds to wait for the warehouse to reach RUNNING.

    Returns:
        The warehouse id (echoed for chaining).

    Raises:
        TimeoutError: if the warehouse does not reach RUNNING within ``timeout_s``.
    """
    wid = warehouse_id or get_warehouse_id()
    w = get_workspace()
    info = w.warehouses.get(wid)

    state = info.state.value if info.state is not None else "UNKNOWN"
    if state == "RUNNING":
        return wid

    if state in {"STOPPED", "STOPPING"}:
        # Fire-and-forget start; we'll poll below.
        try:
            w.warehouses.start(wid)
        except Exception:  # pragma: no cover - already starting / racing
            pass

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        info = w.warehouses.get(wid)
        state = info.state.value if info.state is not None else "UNKNOWN"
        if state == "RUNNING":
            return wid
        if state in {"DELETED", "DELETING"}:
            raise RuntimeError(f"warehouse {wid} is being deleted (state={state})")
        time.sleep(3)

    raise TimeoutError(f"warehouse {wid} did not reach RUNNING within {timeout_s}s")


def execute_sql(
    sql: str,
    warehouse_id: str | None = None,
    catalog: str | None = None,
    schema: str | None = None,
    wait_timeout_s: int = 50,
) -> list[dict[str, Any]]:
    """Execute a SQL statement on a warehouse and return rows as a list of dicts.

    Uses ``statement_execution.execute_statement`` with synchronous waiting.
    For DDL statements (CREATE TABLE, etc.) the result list will be empty.

    Args:
        sql: the SQL text. Multi-statement is not supported by the API; pass
            statements one at a time.
        warehouse_id: target warehouse; resolved via :func:`get_warehouse_id`.
        catalog: optional default catalog for unqualified identifiers.
        schema: optional default schema.
        wait_timeout_s: how long the API will block waiting for completion
            before returning a polling token. We poll until the statement
            finishes regardless of this value.

    Returns:
        A list of dicts keyed by column name. DDL returns ``[]``.

    Raises:
        RuntimeError: when the statement finishes with a FAILED/CANCELED state.
    """
    wid = warehouse_id or get_warehouse_id()
    w = get_workspace()

    # API requires wait_timeout to be 0s OR between 5s and 50s inclusive.
    wt = 0 if wait_timeout_s <= 0 else max(5, min(50, wait_timeout_s))
    resp = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=wid,
        catalog=catalog,
        schema=schema,
        wait_timeout=f"{wt}s",
    )

    statement_id = resp.statement_id
    if not statement_id:
        raise RuntimeError("statement execution did not return a statement_id")
    status = resp.status

    # Poll until terminal state.
    while status is not None and _state_value(status.state) in {"PENDING", "RUNNING"}:
        time.sleep(1)
        resp = w.statement_execution.get_statement(statement_id)
        status = resp.status

    if status is None or _state_value(status.state) != "SUCCEEDED":
        err = ""
        if status is not None and status.error is not None:
            err = _redact_secrets(f"{status.error.error_code}: {status.error.message}")
        state_str = _state_value(status.state) if status else "UNKNOWN"
        raise RuntimeError(
            f"statement failed (state={state_str}): {err}\n"
            f"SQL: {_redact_secrets(sql)[:200]}"
        )

    # No result manifest → DDL or no-result statement.
    manifest = resp.manifest
    result = resp.result
    if manifest is None or result is None or manifest.schema is None:
        return []

    columns = [c.name for c in (manifest.schema.columns or [])]
    rows: list[dict[str, Any]] = []

    rows.extend(_rows_to_dicts(columns, result.data_array or []))

    # Fetch additional chunks if any.
    next_chunk_idx = result.next_chunk_index
    seen_chunks: set[int] = set()
    while next_chunk_idx is not None:
        if next_chunk_idx in seen_chunks:
            raise RuntimeError(f"statement result chunk loop detected at {next_chunk_idx}")
        seen_chunks.add(next_chunk_idx)
        chunk = w.statement_execution.get_statement_result_chunk_n(
            statement_id, next_chunk_idx
        )
        rows.extend(_rows_to_dicts(columns, chunk.data_array or []))
        next_chunk_idx = chunk.next_chunk_index

    return rows
