"""switchboard: apps ask for jobs, not models.

    import switchboard as ai

    ai.chat("Write a haiku about mini PCs")
    ai.classify("My order never arrived!", {
        "is_complaint": {"type": "noul", "instructions": "Is the customer unhappy?"},
    })

jobs.toml maps each job to a model for local (the mini PC) and nonlocal (a frontier API);
AI_ENV=local|nonlocal picks the column.
"""

from .chat import chat
from .classify import classify
from .config import current_env, job_config
from .errors import ConfigError, ModelError, ServerTimeout, ServerUnreachable, SwitchboardError

__all__ = [
    "chat",
    "classify",
    "current_env",
    "job_config",
    "SwitchboardError",
    "ConfigError",
    "ServerUnreachable",
    "ServerTimeout",
    "ModelError",
]
