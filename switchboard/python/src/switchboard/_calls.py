"""Thin wrapper around LiteLLM calls that turns its exceptions into clear switchboard errors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import litellm

from .config import JobConfig
from .errors import ModelError, ServerTimeout, ServerUnreachable

litellm.suppress_debug_info = True  # no "Give Feedback / Get Help" banners on every error

T = TypeVar("T")


def _where(cfg: JobConfig) -> str:
    return cfg.api_base or f"the {cfg.model.split('/')[0]} API"


def call(cfg: JobConfig, fn: Callable[..., T], **kwargs: Any) -> T:
    """Run fn (a litellm function) with the job's model/api_base/timeout plus kwargs."""
    params = {"model": cfg.model, "timeout": cfg.timeout, **cfg.litellm_kwargs, **kwargs}
    if cfg.api_base:
        params["api_base"] = cfg.api_base
    try:
        return fn(**params)
    # Timeout must come first: it's a subclass of the connection error in the openai hierarchy.
    except litellm.Timeout as e:
        hint = (
            " The first request after the model unloads can take 45-110 s just to load it; "
            "raise `timeout` for this job in jobs.toml if that's what happened."
            if cfg.env == "local"
            else ""
        )
        raise ServerTimeout(
            f"[{cfg.env}/{cfg.job}] {cfg.model} at {_where(cfg)} didn't answer within {cfg.timeout:.0f} s.{hint}"
        ) from e
    except litellm.APIConnectionError as e:
        # LiteLLM also uses APIConnectionError for some non-network failures; only call it
        # "unreachable" when the underlying cause really was the network.
        if _is_network_error(e):
            hint = (
                f" Is the mini PC on? Check with: curl {cfg.api_base}/api/version"
                if cfg.env == "local" and cfg.api_base
                else ""
            )
            raise ServerUnreachable(f"[{cfg.env}/{cfg.job}] Can't reach {_where(cfg)}.{hint}") from e
        raise ModelError(f"[{cfg.env}/{cfg.job}] {cfg.model} failed: {e}") from e
    except litellm.AuthenticationError as e:
        raise ModelError(
            f"[{cfg.env}/{cfg.job}] {cfg.model} rejected the API key. Check the key in your .env file."
        ) from e
    except litellm.NotFoundError as e:
        raise ModelError(
            f"[{cfg.env}/{cfg.job}] {cfg.model} wasn't found at {_where(cfg)}. "
            "Check the model name in jobs.toml (and `ollama list` on the mini PC for local)."
        ) from e
    except litellm.APIError as e:
        raise ModelError(f"[{cfg.env}/{cfg.job}] {cfg.model} failed: {e}") from e


_NETWORK_MARKERS = (
    "connection refused",
    "no route to host",
    "name or service not known",
    "nodename nor servname",
    "network is unreachable",
    "connecterror",
    "connection reset",
    "all connection attempts failed",
)


def _is_network_error(error: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (ConnectionError, OSError)) or type(current).__name__ == "ConnectError":
            return True
        if any(marker in str(current).lower() for marker in _NETWORK_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False
