"""Errors raised by switchboard. Catch SwitchboardError to handle all of them."""


class SwitchboardError(Exception):
    """Base class for every switchboard error."""


class ConfigError(SwitchboardError):
    """jobs.toml is missing a job, an env, or a model."""


class ServerUnreachable(SwitchboardError):
    """Couldn't connect to the model server at all (it's off, asleep, or the address is wrong)."""


class ServerTimeout(SwitchboardError):
    """Connected, but the model didn't answer in time."""


class ModelError(SwitchboardError):
    """The server answered, but with an error or a reply we couldn't use."""
