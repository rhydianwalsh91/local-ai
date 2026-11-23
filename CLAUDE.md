# CLAUDE.md

This repo is the recipe for a self-hosted, CPU-only AI server (Ollama in Proxmox LXC 101), plus
`switchboard/`, a package that routes app "jobs" to that server (`AI_ENV=local`) or a
frontier API (`AI_ENV=nonlocal`).
Python exists (via LiteLLM). Other languages (TypeScript is planned) go alongside it under
`switchboard/<language>/`. README.md has the full picture: hosts, settings and the reasons behind them.
Read it before changing server config.

## Working with the owner

- They are not a sysadmin. Explain in plain terms what a change does and why.
- **Ask before anything destructive or disruptive:** deleting models/containers/files on the
  server, changing memory limits, stopping or restarting services (an Ollama restart unloads
  models, so the next request waits 45-110 s).
- Power draw matters more than latency. Measure before claiming a power saving (see "Measuring power").

## Hard rules

- **Never touch VM 100** (192.168.68.161, alias `minipc`). It's a separate project.
- RAM budget: the AI uses at most 28 GB of the host's 32 GB. The container is capped at 25 GB. Both
  models plus Open WebUI use ~24 GB, so **a third model can't be kept loaded alongside them**. At
  24 GB the container thrashed (swap full, everything stalled ~30% of the time, Open WebUI and SSH
  unresponsive). If things hang, check `memory.pressure` in `/sys/fs/cgroup/lxc/101/` on the host.
- **The repo is public.** No secrets, keys, tokens or personal data. LAN IPs are fine. Keys live
  in `.env` (gitignored). `INSTRUCTIONS.md` is the owner's private handoff note and is gitignored. Keep it out of commits.
- Keep the repo matching the server. Change config here, then run `scripts/deploy.sh`. Don't
  hand-edit files on the server.

## Layout

- `proxmox/create-lxc.sh` runs on the Proxmox host (`ssh minipc-hypervisor 'bash -s' < ...`).
- `scripts/bootstrap.sh` runs inside the container (root, from `/opt/local-ai`). It must stay
  idempotent: check before acting, and restart Ollama only if the *effective* systemd environment changed.
- `scripts/deploy.sh` runs on the Mac. It copies `ollama/`, `open-webui/` + `scripts/` to `/opt/local-ai` over SSH
  (tar, no rsync/git in the container), then runs bootstrap.
- `tests/smoke.sh` runs on the Mac against the live API.
- `switchboard/shared/` holds everything the language packages share: `jobs.toml` (the one
  job → model map), `classify-prompt.txt`, and `test-cases/*.json` (config resolution, JSON schema,
  answer normalisation, question validation). **To change shared behaviour, change the test case
  first**, then make every package pass it. Don't fix it in one language only.
- `switchboard/python/src/switchboard/`: `config.py` (loading/merging, `AI_ENV`), `_calls.py`
  (LiteLLM call and error translation), `chat.py`, `classify.py`. `jobs.toml` and
  `classify-prompt.txt` there are **symlinks** to the shared files. Edit the originals, and never
  replace the links with copies.
- A new language package goes in `switchboard/<language>/`. It needs the same API, error names and
  env vars, must bundle the shared files at build time, and must run every case in `shared/test-cases/`.
  Release all packages under one version.

## Verify changes

```bash
cd switchboard/python && uv run pytest                   # unit tests + shared test cases, offline
cd switchboard/python && SWITCHBOARD_LIVE=1 uv run pytest -m live   # against the mini PC
tests/smoke.sh                                           # server health and speed
bash -n scripts/*.sh proxmox/*.sh tests/*.sh             # shell syntax
```

Expected: gemma4-cpu ~6 tok/s output (below 3.5 means speculative decoding is back on), tev1
decision ~8 s warm.

## Gotchas (learned the hard way)

- Use `gemma4-cpu`, never `gemma4:26b`: MTP speculative decoding cuts output to ~2.5 tok/s on this CPU.
- `think` isn't a Modelfile parameter. Send `"think": false` per request (`jobs.toml` does this for local chat).
- tev1 is decision-only. It can't be loaded or prompted via `/api/generate` or `/api/chat` (400
  error). Use `/v1/systemone` (`litellm.systemone` in Python).
- LiteLLM's systemone call makes a stray `POST /v1/systemone/api/show` that gets a 404 in the Ollama
  log. It's harmless; the real request still succeeds.
- LiteLLM needs `tenacity` for `num_retries` but doesn't depend on it. It's in switchboard's deps.
- The Python package installs from git with `#subdirectory=switchboard/python`. Wheel builds
  follow the symlinks, but an sdist wouldn't, so don't publish an sdist.
- `litellm.Timeout` isn't a subclass of `litellm.APIConnectionError`, so catch it first (see `_calls.py`).
- Debug slowness by prompt size: `journalctl -u ollama | grep "new prompt"` and look at `task.n_tokens`.
- Don't run big downloads in parallel. It caused `unexpected EOF` failures from registries.
- Open WebUI (Docker, :8080) must keep the settings in `open-webui/open-webui.env`. Its defaults
  attach built-in tools to every chat (~6,300 hidden tokens, ~5 min per message here) and run
  background title/tag/follow-up requests that queue ahead of real ones. After changing its version
  or settings, have a chat sent through it and check `task.n_tokens` in the Ollama log.
- `ENABLE_PERSISTENT_CONFIG=False` means Open WebUI's admin settings screens don't stick. Settings
  are changed in the env file and deployed. Its data (accounts, chats) is in the `open-webui` volume:
  never delete that without asking.
- The Mac's first SSH/ping to the mini PC sometimes fails with "No route to host" (a Wi-Fi/ARP
  hiccup). Retry before assuming the server is down.

## Measuring power

The host exposes Intel RAPL counters. `/sys/class/powercap/intel-rapl:1/energy_uj` ("psys") is
whole-platform energy in µJ. Read it twice over a known interval on `minipc-hypervisor` and divide.
Baseline on 2026-11-22: ~6.9 W idle with nothing loaded, +~0.25 W with models loaded idle, ~17 W
while loading or generating, and ~708 J per gemma load.

## Open items

- The nonlocal (frontier API) provider isn't chosen yet. `jobs.toml` nonlocal models are empty on
  purpose, so nonlocal calls raise
  `ConfigError` until they're set.
- No project uses switchboard yet. Before moving one to nonlocal, run real examples through both envs and compare.
- Optional later: Tailscale, a third model, Ansible.
