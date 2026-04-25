"""Thin Anthropic SDK wrapper used by the SeaHealth extractor / validator agents.

Centralizes:

* Lazy creation of an :class:`anthropic.Anthropic` client with ``ANTHROPIC_API_KEY``
  pulled from ``os.environ`` (and ``python-dotenv``-loaded from the repo-root
  ``.env`` if present).
* A small ``structured_call`` helper that uses Claude's tool-use API to force
  the model to return JSON matching a Pydantic ``response_model`` schema, with
  bounded exponential-backoff retries on transient errors.
* A :class:`StructuredCallError` raised when the model does not produce a valid
  ``tool_use`` block matching the requested schema.

This module is intentionally dependency-light so it can be imported from
mock-based unit tests without ever opening a network connection.
"""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

# Repo-root .env, if present, is loaded once on import. The actual
# ``Anthropic()`` constructor reads ``ANTHROPIC_API_KEY`` from the environment
# at call time, which is why ``get_client`` is lazy + cached.
_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env")


# Backoff schedule for retried calls. Indexed by attempt number (0-based).
_BACKOFF_SCHEDULE: tuple[float, ...] = (0.5, 1.0, 2.0)


class StructuredCallError(Exception):
    """Raised when ``structured_call`` cannot extract a valid tool-use payload."""


@lru_cache(maxsize=1)
def get_client() -> anthropic.Anthropic:
    """Return a cached ``anthropic.Anthropic`` client.

    The constructor reads ``ANTHROPIC_API_KEY`` from the environment. We don't
    read the env var explicitly so that test-time monkeypatching (or AWS-style
    bedrock auth) keeps working.
    """
    return anthropic.Anthropic()


def _tool_name_for(model_cls: type[BaseModel]) -> str:
    return f"emit_{model_cls.__name__}"


def _extract_tool_input(message: Any, tool_name: str) -> dict | None:
    """Pull the first ``tool_use`` block matching ``tool_name`` out of a Message.

    Works with both real ``anthropic.types.Message`` instances and the dict-ish
    fakes used in tests.
    """
    blocks = getattr(message, "content", None)
    if blocks is None and isinstance(message, dict):
        blocks = message.get("content")
    if not blocks:
        return None
    for block in blocks:
        block_type = getattr(block, "type", None)
        if block_type is None and isinstance(block, dict):
            block_type = block.get("type")
        if block_type != "tool_use":
            continue
        block_name = getattr(block, "name", None)
        if block_name is None and isinstance(block, dict):
            block_name = block.get("name")
        if block_name != tool_name:
            continue
        block_input = getattr(block, "input", None)
        if block_input is None and isinstance(block, dict):
            block_input = block.get("input")
        if isinstance(block_input, dict):
            return block_input
    return None


def structured_call(
    model: str,
    system: str,
    user: str,
    response_model: type[BaseModel],
    *,
    max_tokens: int = 2048,
    retries: int = 2,
    client: anthropic.Anthropic | None = None,
) -> BaseModel:
    """Call the Messages API forcing the model to invoke a single named tool.

    Args:
        model: Anthropic model id.
        system: System prompt.
        user: User-turn content.
        response_model: Pydantic model class — its JSON schema is used as the
            tool's ``input_schema`` and its instance is what we return.
        max_tokens: Output cap.
        retries: Additional retries on top of the initial attempt for
            ``RateLimitError`` / ``APIError``. Backoff is 0.5s, 1s, 2s.
        client: Override the cached client (handy for tests).

    Returns:
        A validated ``response_model`` instance.

    Raises:
        StructuredCallError: model didn't produce a usable tool_use block, or
            the payload failed Pydantic validation.
        anthropic.APIError: the underlying SDK errored after exhausting
            retries.
    """
    cli = client or get_client()
    tool_name = _tool_name_for(response_model)
    tool = {
        "name": tool_name,
        "description": f"Emit a structured {response_model.__name__} payload.",
        "input_schema": response_model.model_json_schema(),
    }

    last_error: Exception | None = None
    # We try up to (1 + retries) total attempts.
    for attempt in range(retries + 1):
        try:
            message = cli.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": user}],
            )
        except (anthropic.RateLimitError, anthropic.APIError) as exc:
            last_error = exc
            if attempt >= retries:
                raise
            sleep_for = _BACKOFF_SCHEDULE[min(attempt, len(_BACKOFF_SCHEDULE) - 1)]
            time.sleep(sleep_for)
            continue

        payload = _extract_tool_input(message, tool_name)
        if payload is None:
            raise StructuredCallError(
                f"Model {model!r} returned no tool_use block for {tool_name!r}."
            )
        try:
            return response_model.model_validate(payload)
        except ValidationError as exc:
            raise StructuredCallError(
                f"Tool payload failed validation for {response_model.__name__}: {exc}"
            ) from exc

    # Unreachable in practice (loop either returns or raises) but keeps
    # mypy / static checkers happy.
    assert last_error is not None
    raise last_error
