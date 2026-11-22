"""ai.classify(): score a piece of text against named questions.

Questions use the System One format (the one tev1 speaks), e.g.

    {"is_complaint": {"type": "noul", "instructions": "Is the customer unhappy?",
                      "criteria": {"true": "Expresses a problem.", "false": "Neutral or happy."}}}

and the result always has the System One answer shape, whichever backend ran:

    {"is_complaint": {"type": "noul", "noul": 0.95}}

Two methods, chosen per env in jobs.toml:
  systemone - the model's native decision endpoint (tev1 on Ollama, in dev).
  json      - ask a chat model for the same answers as structured JSON (frontier model, in prod).
"""

from __future__ import annotations

import json
from typing import Any

import litellm

from ._calls import call
from .config import JobConfig, job_config
from .errors import ConfigError, ModelError

Questions = dict[str, dict[str, Any]]
Answers = dict[str, dict[str, Any]]

SUPPORTED_TYPES = ("noul", "choice", "score")


def classify(text: str, questions: Questions, *, job: str = "classify") -> Answers:
    _check_questions(questions)
    cfg = job_config(job)
    method = cfg.method or "systemone"
    if method == "systemone":
        return _via_systemone(cfg, text, questions)
    if method == "json":
        return _via_json(cfg, text, questions)
    raise ConfigError(f"[{cfg.env}/{cfg.job}] unknown classify method {method!r}; use 'systemone' or 'json'")


def _check_questions(questions: Questions) -> None:
    if not questions:
        raise ValueError("classify() needs at least one question")
    for name, question in questions.items():
        qtype = question.get("type")
        if qtype not in SUPPORTED_TYPES:
            raise ValueError(f"Question {name!r}: type must be one of {SUPPORTED_TYPES}, got {qtype!r}")
        if qtype in ("choice", "score") and not question.get("criteria"):
            raise ValueError(f"Question {name!r}: {qtype} questions need 'criteria'")


# --- systemone --------------------------------------------------------------------------------


def _via_systemone(cfg: JobConfig, text: str, questions: Questions) -> Answers:
    response = call(cfg, litellm.systemone, state=text, questions=questions)
    return {name: answer.model_dump(exclude_none=True) for name, answer in response.answers.items()}


# --- json -------------------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a careful, calibrated classifier. Read the text and answer every question about it.
Reply with JSON only, matching the schema.
- "noul" questions are yes/no: give `noul`, the probability from 0 to 1 that the answer is yes (true).
- "choice" questions: give `probabilities`, how likely each label is (summing to 1).
- "score" questions: criteria list levels from lowest (index 0) to highest. Give `probabilities`,
  how likely each level index is (summing to 1).
Be honest about uncertainty: spread probability out when the text doesn't say."""


def _answer_schema(question: dict[str, Any]) -> dict[str, Any]:
    # Only ask for probabilities; choice/score are derived from them so they can't disagree.
    if question["type"] == "noul":
        props = {"noul": {"type": "number"}}
    elif question["type"] == "choice":
        props = {"probabilities": _probability_object(list(question["criteria"]))}
    else:  # score
        props = {"probabilities": _probability_object([str(i) for i in range(len(question["criteria"]))])}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _probability_object(keys: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {key: {"type": "number"} for key in keys},
        "required": keys,
        "additionalProperties": False,
    }


def _response_format(questions: Questions) -> dict[str, Any]:
    schema = {
        "type": "object",
        "properties": {name: _answer_schema(q) for name, q in questions.items()},
        "required": list(questions),
        "additionalProperties": False,
    }
    return {"type": "json_schema", "json_schema": {"name": "answers", "schema": schema, "strict": True}}


def _via_json(cfg: JobConfig, text: str, questions: Questions) -> Answers:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"text": text, "questions": questions}, ensure_ascii=False)},
    ]
    response = call(cfg, litellm.completion, messages=messages, response_format=_response_format(questions))
    content = response.choices[0].message.content or ""
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as e:
        raise ModelError(f"[{cfg.env}/{cfg.job}] {cfg.model} didn't return valid JSON: {content[:200]!r}") from e
    return to_systemone_shape(questions, raw, label=f"{cfg.env}/{cfg.job}")


def _clamp(value: Any) -> float:
    return min(1.0, max(0.0, float(value)))


def to_systemone_shape(questions: Questions, raw: dict[str, Any], label: str = "json") -> Answers:
    """Validate a model's JSON answers and normalise them into the System One answer shape."""
    answers: Answers = {}
    try:
        for name, question in questions.items():
            got = raw[name]
            qtype = question["type"]
            if qtype == "noul":
                answers[name] = {"type": "noul", "noul": _clamp(got["noul"])}
            elif qtype == "choice":
                probs = _normalised({k: got["probabilities"][k] for k in question["criteria"]})
                answers[name] = {"type": "choice", "choice": max(probs, key=probs.get), "probabilities": probs}
            else:  # score
                levels = [str(i) for i in range(len(question["criteria"]))]
                probs = _normalised({k: got["probabilities"][k] for k in levels})
                answers[name] = {
                    "type": "score",
                    "score": sum(int(k) * p for k, p in probs.items()),  # expected level, like tev1
                    "legend": dict(zip(levels, question["criteria"])),
                    "probabilities": probs,
                }
    except (KeyError, TypeError, ValueError) as e:
        raise ModelError(f"[{label}] reply is missing or has a bad value for {e}: {json.dumps(raw)[:300]}") from e
    return answers


def _normalised(probs: dict[str, Any]) -> dict[str, float]:
    # Floor at 0 but don't cap at 1 before rescaling, so weights like {a: 3, b: 1} keep their ratio.
    weights = {k: max(0.0, float(v)) for k, v in probs.items()}
    total = sum(weights.values())
    if total == 0:
        return {k: 1 / len(weights) for k in weights}
    return {k: v / total for k, v in weights.items()}
