# switchboard/shared

Everything the language packages (Python now, TypeScript later) share. Each package bundles these
files instead of keeping its own copy, so there's exactly one place to change each of them.

| File | What it is |
|---|---|
| `jobs.toml` | The job → model map for local (the mini PC) and nonlocal (a frontier API). |
| `classify-prompt.txt` | The instructions sent to the nonlocal model for `classify`. Each package sends it as-is (trailing whitespace trimmed). |
| `test-cases/config.json` | How a job's settings are worked out: overrides, env defaults, job values winning, the 60 s default timeout, and the error cases with their wording. |
| `test-cases/classify-schema.json` | The exact JSON schema sent to the nonlocal model for `classify`. |
| `test-cases/classify-answers.json` | How the nonlocal model's reply becomes the answer shape tev1 returns: clamping, rescaling, tie-breaks, the expected score. |
| `test-cases/classify-questions.json` | Question sets that must be rejected before any request is made. |

## Test cases

These are behaviour rules written as data, so every language's tests can load and check them.
Each file has an `about` field explaining the rules in words, and a `cases` list. A case has
either an `expect` (compare numbers with a tolerance of 1e-9) or an `error` with a `type` and,
optionally, a `message_contains` substring.

Error `type`s are the shared names `ConfigError` and `ModelError`, plus `InvalidQuestions`, which
maps to the language's usual argument error (`ValueError` in Python).

The Python runner is [`python/tests/test_shared.py`](../python/tests/test_shared.py). To change a
rule, change the test case here first, then make every package pass it.
