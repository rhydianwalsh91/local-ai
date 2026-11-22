"""ai.chat(): free-text generation."""

from __future__ import annotations

from typing import Any

import litellm

from ._calls import call
from .config import job_config
from .errors import ModelError

Messages = list[dict[str, Any]]


def chat(prompt: str | Messages, *, system: str | None = None, job: str = "chat", **kwargs: Any) -> str:
    """Send a prompt (or a list of chat messages) to the model for `job` and return its reply text.

    Extra keyword arguments (temperature, max_tokens, ...) go straight to LiteLLM and override jobs.toml.
    """
    cfg = job_config(job)
    messages: Messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else list(prompt)
    if system:
        messages.insert(0, {"role": "system", "content": system})

    response = call(cfg, litellm.completion, messages=messages, **kwargs)
    content = response.choices[0].message.content
    if content is None:
        raise ModelError(f"[{cfg.env}/{cfg.job}] {cfg.model} returned an empty reply")
    return content
