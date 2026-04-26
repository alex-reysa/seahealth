"""Shared pytest configuration for the SeaHealth test suite.

Goals:
    * Register the ``slow`` marker so individual tests can opt in without
      polluting other audits' test files.
    * Pin deterministic global seeds for ``random`` (and ``numpy`` if present)
      so tests that incidentally touch RNG state stay reproducible.
    * Expose a session-scoped ``repo_root`` fixture for tests that need to
      resolve files relative to the repository.
    * Avoid eagerly importing ``seahealth.db.databricks_client`` so the suite
      runs without ``.env`` being populated.
"""

from __future__ import annotations

import os
import random
from collections.abc import Iterator
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Marker registration + collection hooks
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers (so ``-m slow`` works without warnings)."""
    config.addinivalue_line(
        "markers",
        "slow: mark a test as slow (e.g. bootstrap CI n>=200, large parquet "
        "round-trips). Skip with ``pytest -m 'not slow'``.",
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _deterministic_seeds() -> None:
    """Reset RNG state at the start of every test for reproducibility."""
    random.seed(0)
    try:  # pragma: no cover - numpy is optional
        import numpy as np  # type: ignore[import-not-found]

        np.random.seed(0)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Filesystem fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the project root (the directory containing ``tests/``)."""
    return Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Environment hygiene
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_anthropic_env() -> Iterator[None]:
    """Tests must never reach the live Anthropic API even if a key is set.

    We deliberately avoid pytest's ``monkeypatch`` fixture here so we don't
    perturb the order in which other autouse fixtures are torn down (some
    tests rely on ``monkeypatch`` being torn down before module-level
    ``cache_clear`` calls).
    """
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved
