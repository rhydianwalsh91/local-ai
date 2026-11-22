import json
from types import SimpleNamespace

import litellm
import pytest

import switchboard as ai
from switchboard.classify import to_systemone_shape

QUESTIONS = {
    "is_complaint": {"type": "noul", "instructions": "Is the customer unhappy?"},
    "topic": {"type": "choice", "criteria": {"delivery": None, "billing": None}},
    "urgency": {"type": "score", "criteria": ["low", "medium", "high"]},
}


def test_json_answers_are_normalised_to_systemone_shape():
    raw = {
        "is_complaint": {"noul": 1.3},  # out of range -> clamped
        "topic": {"probabilities": {"delivery": 3, "billing": 1}},  # doesn't sum to 1 -> normalised
        "urgency": {"probabilities": {"0": 0.0, "1": 0.5, "2": 0.5}},
    }
    answers = to_systemone_shape(QUESTIONS, raw)
    assert answers["is_complaint"] == {"type": "noul", "noul": 1.0}
    assert answers["topic"]["choice"] == "delivery"
    assert answers["topic"]["probabilities"] == {"delivery": 0.75, "billing": 0.25}
    assert answers["urgency"]["score"] == pytest.approx(1.5)  # expected level, as tev1 reports it
    assert answers["urgency"]["legend"] == {"0": "low", "1": "medium", "2": "high"}


def test_missing_answer_is_a_model_error():
    with pytest.raises(ai.ModelError, match="is_complaint"):
        to_systemone_shape(QUESTIONS, {"topic": {}, "urgency": {}})


def test_prod_json_method_end_to_end(monkeypatch, override):
    override('[jobs.classify.prod]\nmodel = "someprovider/some-model"\nmethod = "json"\n')
    monkeypatch.setenv("AI_ENV", "prod")
    sent = {}

    def fake_completion(**kwargs):
        sent.update(kwargs)
        reply = {"is_complaint": {"noul": 0.9}, "topic": {"probabilities": {"delivery": 0.2, "billing": 0.8}},
                 "urgency": {"probabilities": {"0": 1, "1": 0, "2": 0}}}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))])

    monkeypatch.setattr(litellm, "completion", fake_completion)
    answers = ai.classify("I was charged twice", QUESTIONS)

    assert sent["model"] == "someprovider/some-model"
    schema = sent["response_format"]["json_schema"]["schema"]
    assert set(schema["required"]) == set(QUESTIONS)
    assert answers["topic"]["choice"] == "billing"
    assert answers["is_complaint"]["noul"] == 0.9


def test_bad_json_reply(monkeypatch, override):
    override('[jobs.classify.prod]\nmodel = "someprovider/some-model"\nmethod = "json"\n')
    monkeypatch.setenv("AI_ENV", "prod")
    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Sure! Here you go"))])
    monkeypatch.setattr(litellm, "completion", lambda **kw: reply)
    with pytest.raises(ai.ModelError, match="valid JSON"):
        ai.classify("hi", QUESTIONS)


@pytest.mark.parametrize("bad", [{}, {"q": {"type": "box", "instructions": "x"}}, {"q": {"type": "choice"}}])
def test_bad_questions_are_rejected_before_any_call(bad):
    with pytest.raises(ValueError):
        ai.classify("hi", bad)
