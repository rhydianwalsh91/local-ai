import pytest

import switchboard as ai

# Port 9 on localhost is closed, so the connection is refused instantly; no network needed.
CLOSED = '[env.dev]\napi_base = "http://127.0.0.1:9"\n'


def test_unreachable_server_chat(override):
    override(CLOSED)
    with pytest.raises(ai.ServerUnreachable, match=r"Can't reach http://127.0.0.1:9.*curl"):
        ai.chat("hi")


def test_unreachable_server_classify(override):
    override(CLOSED)
    with pytest.raises(ai.ServerUnreachable):
        ai.classify("hi", {"q": {"type": "noul", "instructions": "Is this a greeting?"}})


def test_all_errors_share_a_base_class():
    for error in (ai.ConfigError, ai.ServerUnreachable, ai.ServerTimeout, ai.ModelError):
        assert issubclass(error, ai.SwitchboardError)
