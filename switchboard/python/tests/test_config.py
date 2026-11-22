import pytest

import switchboard as ai
from switchboard.config import job_config


def test_dev_chat_uses_the_mini_pc():
    cfg = job_config("chat")
    assert cfg.model == "ollama_chat/gemma4-cpu"
    assert cfg.api_base == "http://192.168.68.158:11434"
    assert 120 <= cfg.timeout <= 300  # long enough for a cold model load
    assert cfg.litellm_kwargs["think"] is False


def test_job_settings_override_env_settings():
    assert job_config("classify").timeout == 120  # job's own value beats [env.dev] timeout = 300


def test_ai_env_picks_the_column(monkeypatch, override):
    override('[jobs.chat.prod]\nmodel = "someprovider/some-model"\n')
    monkeypatch.setenv("AI_ENV", "prod")
    cfg = job_config("chat")
    assert cfg.env == "prod"
    assert cfg.model == "someprovider/some-model"
    assert cfg.api_base is None
    assert "think" not in cfg.litellm_kwargs  # dev-only Ollama setting must not leak into prod


def test_bad_ai_env(monkeypatch):
    monkeypatch.setenv("AI_ENV", "staging")
    with pytest.raises(ai.ConfigError, match="AI_ENV"):
        ai.current_env()


def test_unset_prod_model_gives_a_clear_error(monkeypatch):
    monkeypatch.setenv("AI_ENV", "prod")
    with pytest.raises(ai.ConfigError, match=r"No prod model is set for job 'chat'"):
        job_config("chat")


def test_unknown_job():
    with pytest.raises(ai.ConfigError, match="Unknown job 'summarise'"):
        job_config("summarise")


def test_override_adds_a_job_and_keeps_the_rest(override):
    override('[jobs.summarise.dev]\nmodel = "ollama_chat/gemma4-cpu"\ntemperature = 0.2\n')
    assert job_config("summarise").litellm_kwargs["temperature"] == 0.2
    assert job_config("summarise").api_base == "http://192.168.68.158:11434"  # inherited from [env.dev]
    assert job_config("chat").model == "ollama_chat/gemma4-cpu"


def test_missing_override_file(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_CONFIG", "/nonexistent/jobs.toml")
    with pytest.raises(ai.ConfigError, match="doesn't exist"):
        job_config("chat")
