"""Runs the language-neutral cases in switchboard/shared/test-cases. Every switchboard package must pass these."""

import json
import re
from pathlib import Path

import pytest

import switchboard as ai
from switchboard.classify import _check_questions, _response_format, to_systemone_shape
from switchboard.config import job_config, merge_config

SHARED = Path(__file__).resolve().parents[2] / "shared"
ERRORS = {"ConfigError": ai.ConfigError, "ModelError": ai.ModelError, "InvalidQuestions": ValueError}


def load(name: str) -> dict:
    return json.loads((SHARED / "test-cases" / name).read_text())


def cases(name: str):
    return [pytest.param(case, id=case["name"]) for case in load(name)["cases"]]


def expect_error(case: dict):
    contains = case["error"].get("message_contains")
    return pytest.raises(ERRORS[case["error"]["type"]], match=re.escape(contains) if contains else None)


def assert_close(got, want, path="answers"):
    if isinstance(want, dict):
        assert isinstance(got, dict) and set(got) == set(want), f"{path}: keys {sorted(got)} != {sorted(want)}"
        for key in want:
            assert_close(got[key], want[key], f"{path}.{key}")
    elif isinstance(want, (int, float)) and not isinstance(want, bool):
        assert got == pytest.approx(want, abs=1e-9), f"{path}: {got} != {want}"
    else:
        assert got == want, f"{path}: {got!r} != {want!r}"


@pytest.mark.parametrize("case", cases("config.json"))
def test_config(case):
    config = merge_config(load("config.json")["base"], case.get("override", {}))
    if "error" in case:
        with expect_error(case):
            job_config(case["job"], case["env"], config)
        return
    cfg = job_config(case["job"], case["env"], config)
    got = {"model": cfg.model, "method": cfg.method, "api_base": cfg.api_base,
           "timeout": cfg.timeout, "passthrough": cfg.litellm_kwargs}
    assert_close(got, case["expect"], "config")


@pytest.mark.parametrize("case", cases("classify-schema.json"))
def test_classify_schema(case):
    assert _response_format(case["questions"]) == case["response_format"]


@pytest.mark.parametrize("case", cases("classify-answers.json"))
def test_classify_answers(case):
    questions = load("classify-answers.json")["questions"]
    if "error" in case:
        with expect_error(case):
            to_systemone_shape(questions, case["raw"])
        return
    assert_close(to_systemone_shape(questions, case["raw"]), case["expect"])


@pytest.mark.parametrize("case", cases("classify-questions.json"))
def test_classify_questions(case):
    with expect_error(case):
        _check_questions(case["questions"])


def test_prompt_is_the_shared_one():
    from switchboard.classify import _SYSTEM_PROMPT

    assert _SYSTEM_PROMPT == (SHARED / "classify-prompt.txt").read_text().strip()
