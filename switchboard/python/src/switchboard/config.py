"""Load jobs.toml and resolve a job to concrete settings for the current AI_ENV."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv

from .errors import ConfigError

ENVS = ("local", "nonlocal")
DEFAULT_ENV = "local"

# Keys that switchboard itself uses; everything else in a job/env table is passed to LiteLLM.
_OWN_KEYS = {"model", "method", "api_base", "timeout"}


@dataclass(frozen=True)
class JobConfig:
    job: str
    env: str
    model: str
    method: str | None = None
    api_base: str | None = None
    timeout: float = 60
    litellm_kwargs: dict[str, Any] = field(default_factory=dict)


@cache
def _load_dotenv() -> None:
    # The calling app's .env (searched upward from the working directory). Real env vars win.
    load_dotenv(find_dotenv(usecwd=True), override=False)


def current_env() -> str:
    _load_dotenv()
    env = os.environ.get("AI_ENV", DEFAULT_ENV).strip().lower()
    if env not in ENVS:
        raise ConfigError(f"AI_ENV must be one of {ENVS}, got {env!r}")
    return env


def merge_config(base: dict, override: dict) -> dict:
    """Deep-merge override onto base: nested tables merge, everything else is replaced."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict:
    """The bundled jobs.toml, with SWITCHBOARD_CONFIG (if set) merged on top."""
    _load_dotenv()
    # switchboard/shared/jobs.toml, symlinked into the package so it ships in the wheel.
    config = tomllib.loads(resources.files("switchboard").joinpath("jobs.toml").read_text())
    override_path = os.environ.get("SWITCHBOARD_CONFIG")
    if override_path:
        path = Path(override_path).expanduser()
        if not path.is_file():
            raise ConfigError(f"SWITCHBOARD_CONFIG points to {path}, which doesn't exist")
        config = merge_config(config, tomllib.loads(path.read_text()))
    return config


def job_config(job: str, env: str | None = None, config: dict | None = None) -> JobConfig:
    env = env or current_env()
    config = config if config is not None else load_config()

    jobs = config.get("jobs", {})
    if job not in jobs:
        raise ConfigError(f"Unknown job {job!r}. Jobs in jobs.toml: {', '.join(sorted(jobs)) or 'none'}")
    if env not in jobs[job]:
        raise ConfigError(f"Job {job!r} has no [jobs.{job}.{env}] section in jobs.toml")

    settings = {**config.get("env", {}).get(env, {}), **jobs[job][env]}
    model = settings.get("model") or ""
    if not model:
        raise ConfigError(
            f"No {env} model is set for job {job!r}. Set model = \"<provider>/<model>\" "
            f"under [jobs.{job}.{env}] in jobs.toml (and put the provider's API key in .env)."
        )
    return JobConfig(
        job=job,
        env=env,
        model=model,
        method=settings.get("method"),
        api_base=settings.get("api_base"),
        timeout=float(settings.get("timeout", 60)),
        litellm_kwargs={k: v for k, v in settings.items() if k not in _OWN_KEYS},
    )
