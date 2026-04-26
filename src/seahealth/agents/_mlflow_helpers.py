"""Defensive MLflow span helper shared by every agent.

`mlflow_span(name, *, attrs=None)` is a context manager that:

* opens a real MLflow span when ``MLFLOW_TRACKING_URI`` is configured AND the
  ``mlflow`` package imports cleanly,
* falls through silently otherwise (yielding ``None`` and never raising).

Yielded value is the active trace id when a real span is open, else ``None``.

This mirrors the defensive pattern already proven in
``seahealth.pipelines.extract._maybe_mlflow_span`` (env-var gate + try/except)
so that adding new spans never breaks the existing
``test_pipeline_skips_mlflow_when_unconfigured`` style guard tests.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


def _extract_trace_id(span: Any) -> str | None:
    """Best-effort pull of the real trace id from an active MLflow span."""
    if span is None:
        return None
    for attr in ("trace_id", "request_id"):
        candidate = getattr(span, attr, None)
        if candidate:
            return str(candidate)
    return None


@contextmanager
def mlflow_span(
    name: str,
    *,
    attrs: dict[str, Any] | None = None,
) -> Iterator[str | None]:
    """Open an MLflow span when tracking is configured; otherwise no-op.

    Args:
        name: Span name (use a stable dotted path: ``seahealth.<agent>.<op>``).
        attrs: Optional span attributes. Stringified by MLflow on the wire.

    Yields:
        The active trace id when an MLflow span was opened, else ``None``.

    The helper never raises: any failure in MLflow imports or span lifecycle
    is logged at warning level and treated as a no-op. Callers can rely on the
    contract that ``with mlflow_span(...)`` is always safe.
    """
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        yield None
        return
    try:
        import mlflow  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised when mlflow missing
        logger.warning("mlflow_span: import failed (%s); skipping span %s", exc, name)
        yield None
        return
    try:
        with mlflow.start_span(name=name, attributes=attrs or {}) as span:
            yield _extract_trace_id(span)
    except Exception as exc:  # pragma: no cover - mlflow span lifecycle failures
        logger.warning("mlflow_span: %s failed (%s); continuing without span", name, exc)
        yield None
