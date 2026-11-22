"""Calls the real dev server. Skipped unless SWITCHBOARD_LIVE=1 (a cold start takes ~1-2 minutes)."""

import os

import pytest

import switchboard as ai

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("SWITCHBOARD_LIVE") != "1", reason="set SWITCHBOARD_LIVE=1 to run"),
]


def test_chat():
    reply = ai.chat("Reply with just the word: pong", max_tokens=20)
    assert "pong" in reply.lower()


def test_classify():
    answers = ai.classify(
        "This is the third time my order has arrived broken. I want a refund.",
        {"is_complaint": {"type": "noul", "instructions": "Is the customer unhappy?"}},
    )
    assert answers["is_complaint"]["type"] == "noul"
    assert answers["is_complaint"]["noul"] > 0.8
