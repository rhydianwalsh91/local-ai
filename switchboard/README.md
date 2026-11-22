# switchboard

Apps ask for **jobs**, not models. `jobs.toml` says which model does each job in `dev` (the
mini PC's Ollama) and `prod` (a frontier API), and `AI_ENV=dev|prod` picks one. Calls go
through [LiteLLM](https://docs.litellm.ai/), so switching providers is a config change, not a code change.

## Install in a project

```bash
uv add "switchboard @ git+https://github.com/rhydianwalsh91/local-ai#subdirectory=switchboard"
# or: pip install "switchboard @ git+https://github.com/rhydianwalsh91/local-ai#subdirectory=switchboard"
```

Copy [`.env.example`](../.env.example) to the project's `.env` and set `AI_ENV`.

## Use

```python
import switchboard as ai

ai.chat("Summarise this in one line: ...")
ai.chat([{"role": "user", "content": "hi"}], system="Be brief.", temperature=0.2)

ai.classify("My parcel never arrived!", {
    "is_complaint": {"type": "noul", "instructions": "Is the customer unhappy?",
                     "criteria": {"true": "Expresses a problem.", "false": "Neutral or happy."}},
    "topic": {"type": "choice", "criteria": {"delivery": "Shipping", "billing": "Payments", "other": None}},
    "urgency": {"type": "score", "criteria": ["not urgent", "somewhat urgent", "very urgent"]},
})
# {"is_complaint": {"type": "noul", "noul": 0.96},
#  "topic": {"type": "choice", "choice": "delivery", "probabilities": {...}},
#  "urgency": {"type": "score", "score": 1.9, "legend": {...}, "probabilities": {...}}}
```

Question types: `noul` (yes/no, returns the probability of yes), `choice` (pick a label) and
`score` (a level on a scale; `score` is the expected level index). The answer shape is the same in
dev and prod. Only tev1 (dev) adds a `confidence` field.

| Job | dev | prod |
|---|---|---|
| `chat` | `gemma4-cpu` on the mini PC | not chosen yet |
| `classify` | `tev1:4b` via `/v1/systemone` | any chat model, asked for the same answers as structured JSON |

Add your own jobs (e.g. `summarise`) in a project-level TOML file and point
`SWITCHBOARD_CONFIG` at it. It's merged over the bundled `jobs.toml`, so you only write what's
different. Then call `ai.chat(text, job="summarise")`.

## Errors

Everything raises a subclass of `ai.SwitchboardError`:

| Error | Meaning |
|---|---|
| `ServerUnreachable` | Couldn't connect at all. In dev: is the mini PC on? |
| `ServerTimeout` | Connected but no answer in time. A cold model takes 45-110 s to load. |
| `ConfigError` | Unknown job, bad `AI_ENV`, or no model set for this env (e.g. prod before it's chosen). |
| `ModelError` | The model answered with an error, a bad API key, or unusable output. |

Dev timeouts are long (300 s for chat, 120 s for classify) because the mini PC is slow to load models.

## Tests

```bash
cd switchboard
uv run pytest                        # unit tests, no network needed
SWITCHBOARD_LIVE=1 uv run pytest -m live   # also hits the real dev server
```

## Before switching a project to prod

1. Set the prod `model` for each job in `jobs.toml` and put the API key in `.env`.
2. Run a handful of real example inputs through both envs (`AI_ENV=dev` and `AI_ENV=prod`) and
   compare the outputs, especially `classify` scores. The prod method is a different model, so
   expect the values to differ somewhat.
