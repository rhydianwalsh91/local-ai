# switchboard (Python)

The Python package for [switchboard](../README.md). It routes calls through
[LiteLLM](https://docs.litellm.ai/). The job map, question format, answer shape and error meanings
are described in the [main switchboard README](../README.md).

## Install in a project

```bash
uv add "switchboard @ git+https://github.com/rhydianwalsh91/local-ai#subdirectory=switchboard/python"
# or: pip install "switchboard @ git+https://github.com/rhydianwalsh91/local-ai#subdirectory=switchboard/python"
```

Copy [`.env.example`](../../.env.example) to the project's `.env` and set `AI_ENV`.

## Use

```python
import switchboard as ai

ai.chat("Summarise this in one line: ...")
ai.chat([{"role": "user", "content": "hi"}], system="Be brief.", temperature=0.2)
ai.chat(text, job="summarise")  # a job your project added via SWITCHBOARD_CONFIG

ai.classify("My parcel never arrived!", {
    "is_complaint": {"type": "noul", "instructions": "Is the customer unhappy?"},
})
# {"is_complaint": {"type": "noul", "noul": 0.96}}

try:
    ai.chat("hi")
except ai.ServerUnreachable as e:
    print(e)  # "[local/chat] Can't reach http://192.168.68.158:11434. Is the mini PC on? ..."
```

Extra keyword arguments to `chat` (temperature, max_tokens, ...) go straight to LiteLLM and override
`jobs.toml`. All errors subclass `ai.SwitchboardError`. Invalid questions raise `ValueError`
before any request is made.

## How the shared files get in

`src/switchboard/jobs.toml` and `src/switchboard/classify-prompt.txt` are **symlinks** to
`../shared/jobs.toml` and `../shared/classify-prompt.txt`. Edit the originals. Editable installs (`uv sync`)
read through the links, and wheel builds (including `pip`/`uv` installs from git) copy in the real
contents. Building an sdist (`uv build` without `--wheel`) would leave dangling links, so it
isn't supported. Nothing here is published to PyPI.

## Tests

```bash
cd switchboard/python
uv run pytest                               # unit tests + shared test cases, no network
SWITCHBOARD_LIVE=1 uv run pytest -m live    # also hits the real mini PC
```
