# Answer normalisation, the JSON schema and question validation are covered by the shared
# cases in switchboard/shared/test-cases (test_shared.py). These tests cover the Python wiring around them.
import json
from types import SimpleNamespace

import litellm
import pytest

import switchboard as ai
from switchboard.classify import _SYSTEM_PROMPT

QUESTIONS = {
    "is_complaint": {"type": "noul", "instructions": "Is the customer unhappy?"},
    "topic": {"type": "choice", "criteria": {"delivery": None, "billing": None}},
    "urgency": {"type": "score", "criteria": ["low", "medium", "high"]},
}


def test_prod_json_method_end_to_end(monkeypatch, override):
    override('[jobs.classify.nonlocal]\nmodel = "someprovider/some-model"\nmethod = "json"\n')
    monkeypatch.setenv("AI_ENV", "nonlocal")
    sent = {}

    def fake_completion(**kwargs):
        sent.update(kwargs)
        reply = {"is_complaint": {"noul": 0.9}, "topic": {"probabilities": {"delivery": 0.2, "billing": 0.8}},
                 "urgency": {"probabilities": {"0": 1, "1": 0, "2": 0}}}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))])

    monkeypatch.setattr(litellm, "completion", fake_completion)
    answers = ai.classify("I was charged twice", QUESTIONS)

    assert sent["model"] == "someprovider/some-model"
    assert sent["messages"][0]["content"] == _SYSTEM_PROMPT
    assert json.loads(sent["messages"][1]["content"]) == {"text": "I was charged twice", "questions": QUESTIONS}
    assert set(sent["response_format"]["json_schema"]["schema"]["required"]) == set(QUESTIONS)
    assert answers["topic"]["choice"] == "billing"
    assert answers["is_complaint"]["noul"] == 0.9


def test_bad_json_reply(monkeypatch, override):
    override('[jobs.classify.nonlocal]\nmodel = "someprovider/some-model"\nmethod = "json"\n')
    monkeypatch.setenv("AI_ENV", "nonlocal")
    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Sure! Here you go"))])
    monkeypatch.setattr(litellm, "completion", lambda **kw: reply)
    with pytest.raises(ai.ModelError, match="valid JSON"):
        ai.classify("hi", QUESTIONS)


def test_bad_questions_fail_before_any_request(monkeypatch):
    def no_network(**kwargs):
        raise AssertionError("classify() made a request with invalid questions")

    monkeypatch.setattr(litellm, "systemone", no_network)
    with pytest.raises(ValueError):
        ai.classify("hi", {"q": {"type": "box", "instructions": "x"}})
