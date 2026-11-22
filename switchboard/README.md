# switchboard

Apps ask for **jobs**, not models. [`shared/jobs.toml`](shared/jobs.toml) says which model does each job in `local`
(the mini PC's Ollama) and `nonlocal` (a frontier API), and `AI_ENV=local|nonlocal` picks one. Switching
providers is a config change, not a code change.

| Folder | What it is |
|---|---|
| [`shared/`](shared/) | What every language package shares: [`jobs.toml`](shared/jobs.toml) (the job → model map), the classify prompt, and test cases they must all pass |
| [`python/`](python/) | The Python package, built on LiteLLM ([README](python/README.md)) |
| `typescript/` | Planned. See "Adding a language" below |

## Jobs

| Job | local | nonlocal |
|---|---|---|
| `chat` | `gemma4-cpu` on the mini PC | not chosen yet |
| `classify` | `tev1:4b` via `/v1/systemone` | any chat model, asked for the same answers as structured JSON |

A project can add or override jobs without editing the shared file. It points `SWITCHBOARD_CONFIG`
at its own TOML file, which is merged over `jobs.toml`.

## classify: questions and answers

Questions use the System One format that tev1 speaks:

```json
{"is_complaint": {"type": "noul", "instructions": "Is the customer unhappy?",
                  "criteria": {"true": "Expresses a problem.", "false": "Neutral or happy."}},
 "topic":   {"type": "choice", "criteria": {"delivery": "Shipping", "billing": "Payments", "other": null}},
 "urgency": {"type": "score",  "criteria": ["not urgent", "somewhat urgent", "very urgent"]}}
```

The answers have the same shape in local and nonlocal:

```json
{"is_complaint": {"type": "noul", "noul": 0.96},
 "topic":   {"type": "choice", "choice": "delivery", "probabilities": {"delivery": 0.98, "billing": 0.0, "other": 0.02}},
 "urgency": {"type": "score",  "score": 1.9, "legend": {"0": "not urgent", "...": "..."}, "probabilities": {"0": 0.0, "1": 0.09, "2": 0.91}}}
```

- `noul` is the probability that the answer is yes.
- `choice` is the most likely label.
- `score` is the expected level index: 1.9 means "almost very urgent".
- Only tev1 (local) adds a `confidence` field.

## Errors

The error names are the same in every language:

| Error | Meaning |
|---|---|
| `ServerUnreachable` | Couldn't connect at all. For local: is the mini PC on? |
| `ServerTimeout` | Connected but no answer in time. A cold model takes 45-110 s to load, so local timeouts are long (300 s chat, 120 s classify). |
| `ConfigError` | Unknown job, bad `AI_ENV`, or no model set for this env (e.g. nonlocal before it's chosen). |
| `ModelError` | The model answered with an error, a bad API key, or unusable output. |

## Before switching a project to nonlocal

1. Set the nonlocal `model` for each job in `jobs.toml` and put the API key in the project's `.env`.
2. Run a handful of real inputs through both envs and compare the outputs, especially `classify`
   scores. Nonlocal is a different model, so expect the values to differ somewhat.

## Adding a language

Create `switchboard/<language>/` with the same public API (`chat`, `classify`), the same error
names and the same env vars (`AI_ENV`, `SWITCHBOARD_CONFIG`). Bundle `shared/jobs.toml` and
`shared/classify-prompt.txt` at build time, and make its test suite run every case in
`shared/test-cases/`. See [`shared/README.md`](shared/README.md). Release all packages together under one version, since
they share `jobs.toml`.
