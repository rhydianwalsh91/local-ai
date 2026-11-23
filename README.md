# local-ai

The recipe for a small self-hosted AI server, plus **switchboard**, a Python package that lets my
projects use it.

The server is a CPU-only mini PC running Proxmox. Ollama runs in an LXC container and serves a chat
model (Gemma 4 26B MoE) and a decision/classification model (tev1). Open WebUI, in the same container,
provides a ChatGPT-style web page for chatting with it. Projects never name a model.
They ask switchboard for a *job* (`ai.chat`, `ai.classify`), and one config file sends that job to
the mini PC (`local`) or to a frontier API (`nonlocal`).

```
 Mac (projects + switchboard) ──LAN──▶ Proxmox host "pve" 192.168.68.200
                                         ├─ VM 100   (separate project, not managed here)
                                         └─ LXC 101 "ai" 192.168.68.158
                                              ├─ Ollama :11434 ── gemma4-cpu, tev1:4b
                                              └─ Open WebUI :8080 (Docker) ──▶ Ollama
```

## Hardware

HP ProDesk 400 G4 Mini: Intel Core i3-8100T (4 cores, AVX2, no usable GPU), 2×16 GB DDR4-2400
(dual channel), 256 GB NVMe. Proxmox VE 9.2.

## Hosts and ports

| What | Address | SSH alias | Notes |
|---|---|---|---|
| Proxmox host | 192.168.68.200 (web UI :8006) | `minipc-hypervisor` | root |
| AI container (LXC 101) | 192.168.68.158 | `minipc-ai` | root. DHCP, reserved in the router |
| Ollama API | http://192.168.68.158:11434 | | **no auth, LAN only** |
| Open WebUI | http://192.168.68.158:8080 | | Chat in the browser. The first account created becomes admin. |

## Repo layout

| Path | What it is |
|---|---|
| `proxmox/create-lxc.sh` | Creates LXC 101 on the Proxmox host |
| `ollama/override.conf` | Ollama's systemd settings |
| `ollama/models.txt` | Models pulled from the Ollama library |
| `ollama/modelfiles/*.Modelfile` | Local variants built on those models |
| `open-webui/open-webui.env` | Open WebUI's settings (the repo is the source of truth, see below) |
| `open-webui/daemon.json` | Docker settings (one download at a time) |
| `scripts/bootstrap.sh` | Runs in the container: turns a fresh Debian 13 LXC into the server. Safe to re-run. |
| `scripts/deploy.sh` | Runs on the Mac: copies `ollama/`, `open-webui/` + `scripts/` to the container and runs bootstrap |
| `tests/smoke.sh` | Health check plus chat and decision timings |
| `switchboard/shared/` | What every language package shares: the job → model map (`jobs.toml`), the classify prompt, and test cases they must all pass |
| `switchboard/python/` | The Python package ([overview](switchboard/README.md), [Python README](switchboard/python/README.md)) |

## Common tasks

```bash
scripts/deploy.sh                  # apply config changes (restarts Ollama / recreates Open WebUI only if their settings changed)
scripts/deploy.sh --restart        # force an Ollama restart
scripts/deploy.sh --update-models  # re-pull models from the library (may download newer uploads)
tests/smoke.sh                     # is everything up, and is it as fast as it should be?
```

**Rebuild from scratch:**
1. `ssh minipc-hypervisor 'bash -s' < proxmox/create-lxc.sh`
2. Reserve the new container's IP in the router. If it changed, update `~/.ssh/config`, `jobs.toml` and `tests/smoke.sh`.
3. `scripts/deploy.sh` (downloads about 23 GB of models and a 4.6 GB Open WebUI image; give it time)
4. `tests/smoke.sh`

**Change an Open WebUI setting:** edit `open-webui/open-webui.env` and run `scripts/deploy.sh`.
Changes made in Open WebUI's own admin settings screens don't stick (they reset on restart),
because `ENABLE_PERSISTENT_CONFIG=False` makes the file win. Accounts, chats and per-model tweaks
live in its `open-webui` Docker volume and are kept.

**Upgrade Open WebUI:** change `OPEN_WEBUI_VERSION` in `scripts/bootstrap.sh`, deploy, then check
prompt sizes (see Troubleshooting). New versions add features that can quietly inject hidden context.

**Add a model:** add its name to `ollama/models.txt`, optionally add a
`ollama/modelfiles/<name>.Modelfile`, then `scripts/deploy.sh`. Check the RAM budget below first.

## Models

| Model | Size in RAM | Used for |
|---|---|---|
| `gemma4-cpu` | ~17 GB | Chat. `gemma4:26b` (Q4_K_M mixture-of-experts, ~4B active parameters) with speculative decoding turned off |
| `tev1:4b` | ~5.7 GB | Decisions/classification through Ollama's `/v1/systemone` endpoint |
| `gemma4:26b` | | Base for `gemma4-cpu`. Don't call it directly (it's slower, see below) |

Both models plus Open WebUI (~0.9 GB) use about 24 GB of the container's 25 GB. That's why the cap
is 25 GB, not 24: at 24 GB, swap filled up and the whole container stalled (Open WebUI and SSH
stopped responding).

## Why each tweak exists

| Setting | Why |
|---|---|
| `gemma4-cpu` = `gemma4:26b` + `PARAMETER draft_num_predict 0` | The library model ships with MTP speculative decoding on. On this 4-core CPU the draft model competes with the main one for cores, cutting output from ~6 to ~2.5 tok/s. |
| `"think": false` sent per request | Gemma 4 "thinks" by default, which means minutes of hidden tokens per reply on this CPU. `think` isn't a valid Modelfile parameter, so switchboard sends it with each chat request. |
| `OLLAMA_KEEP_ALIVE=30m` | Measured with the CPU's power sensor: a loaded idle model adds only ~0.25 W, but each reload costs ~708 J (42 s at ~17 W). The break-even is ~47 minutes, so 30m is close to power-optimal. Unloading sooner wastes power on reloads. |
| `OLLAMA_CONTEXT_LENGTH=8192` | Keeps the per-model memory (KV cache) small enough for both models and Open WebUI to fit in 25 GB. |
| `OLLAMA_FLASH_ATTENTION=1` | Less memory and faster prompt reading on CPU. |
| `OLLAMA_NUM_PARALLEL=1` | With 4 cores, parallel requests just slow each other down. Requests queue instead. |
| `OLLAMA_HOST=0.0.0.0:11434` | Reachable from the LAN. There's no auth, so **never** port-forward this. |
| Container capped at 25 GB, swap 1 GB | Both models + Open WebUI need ~24 GB; 24 GB thrashed. The AI must stay within 28 GB of the host's 32 GB, leaving room for Proxmox and VM 100 (the host keeps ~1.5 GB free). |
| Unprivileged LXC, `nesting=1,keyctl=1` | The standard safe setup for a Debian container running systemd services. |
| Ollama pinned to 0.40.16 | `bootstrap.sh` installs this exact version so a rebuild matches what was tested. |
| Open WebUI: `function_calling: legacy` | With its default ("native") mode, Open WebUI attaches its built-in tools (memory, web search, code interpreter...) to every chat: ~6,300 hidden prompt tokens, ~5 minutes to read on this CPU. Legacy mode doesn't. Set via `DEFAULT_MODEL_PARAMS`, along with `think: false`. |
| Open WebUI: title/tags/follow-up/query/autocomplete generation off | Each is an extra background request to the model. Ollama serves one at a time, so they queued ahead of real messages. |
| Open WebUI: only `gemma4-cpu` listed | `gemma4:26b` is the slow speculative-decoding version and `tev1` can't chat. |
| Open WebUI: `ENABLE_PERSISTENT_CONFIG=False` | Otherwise it copies settings into its database on first start, the database wins from then on, and the repo silently stops being the truth. |
| Open WebUI: 1.5 GB memory cap, host networking | If it ever balloons, Docker restarts it instead of the kernel killing a model. Host networking reaches Ollama on 127.0.0.1. |
| Docker: one download at a time (`daemon.json`) | Parallel layer downloads from ghcr.io failed with `unexpected EOF` here. |

## Measured performance

| | |
|---|---|
| gemma4-cpu output | ~6 tok/s |
| gemma4-cpu prompt reading | ~16-20 tok/s |
| gemma4-cpu load time | 42-110 s |
| tev1 2-question decision | ~8 s warm, ~20 s including load |
| System power, idle | ~6.9 W (nothing loaded), ~7.1 W (models loaded) |
| System power, loading/generating | ~17 W |

## Troubleshooting

- **Slow replies:** check prompt sizes with `ssh minipc-ai 'journalctl -u ollama | grep "new prompt"'`
  and look at `task.n_tokens`. Thousands of tokens for a short question means something is
  injecting hidden context.
- **Everything hangs (even SSH):** the container is probably out of memory. On the host:
  `cat /sys/fs/cgroup/lxc/101/memory.pressure`. A `full avg10` well above 0 means it's thrashing.
  Unloading a model frees memory at once: `curl http://192.168.68.158:11434/api/generate -d '{"model":"gemma4-cpu","keep_alive":0}'`.
- **Can't connect:** `curl http://192.168.68.158:11434/api/version`. If the container doesn't
  answer, check it's running: `ssh minipc-hypervisor pct status 101`.
- **Big downloads failing with `unexpected EOF`:** don't run large downloads in parallel.
- **Open WebUI not loading:** `ssh minipc-ai docker logs --tail 50 open-webui`. To restart it:
  `ssh minipc-ai docker restart open-webui`.
- **Chats and apps waiting on each other:** Open WebUI and switchboard share the same Ollama, which
  answers one request at a time. A long chat reply makes an app's request queue, and vice versa.

## Security

- Nothing in this repo is secret. API keys live only in `.env` files, which git ignores.
- The Ollama API has no authentication. It must stay on the LAN: no router port-forwarding. For
  remote access, use a VPN such as Tailscale rather than exposing the port.
- Open WebUI has its own logins. The first account created becomes admin, so create yours straight
  after a fresh install. Later sign-ups wait as "pending" until the admin approves them. Its session
  key is generated inside its data volume, not stored in this repo.

## Later / optional

- Tailscale for remote access
- A third model (check the RAM budget)
- Ansible, if this grows past one box
