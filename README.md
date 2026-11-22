# local-ai

The recipe for a small self-hosted AI server, plus **switchboard**, a Python package that lets my
projects use it.

The server is a CPU-only mini PC running Proxmox. Ollama runs in an LXC container and serves a chat
model (Gemma 4 26B MoE) and a decision/classification model (tev1). Projects never name a model.
They ask switchboard for a *job* (`ai.chat`, `ai.classify`), and one config file sends that job to
the mini PC (`local`) or to a frontier API (`nonlocal`).

```
 Mac (projects + switchboard) ──LAN──▶ Proxmox host "pve" 192.168.68.200
                                         ├─ VM 100   (separate project, not managed here)
                                         └─ LXC 101 "ai" 192.168.68.158
                                              └─ Ollama :11434 ── gemma4-cpu, tev1:4b
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

## Repo layout

| Path | What it is |
|---|---|
| `proxmox/create-lxc.sh` | Creates LXC 101 on the Proxmox host |
| `ollama/override.conf` | Ollama's systemd settings |
| `ollama/models.txt` | Models pulled from the Ollama library |
| `ollama/modelfiles/*.Modelfile` | Local variants built on those models |
| `scripts/bootstrap.sh` | Runs in the container: turns a fresh Debian 13 LXC into the server. Safe to re-run. |
| `scripts/deploy.sh` | Runs on the Mac: copies `ollama/` + `scripts/` to the container and runs bootstrap |
| `tests/smoke.sh` | Health check plus chat and decision timings |
| `switchboard/shared/` | What every language package shares: the job → model map (`jobs.toml`), the classify prompt, and test cases they must all pass |
| `switchboard/python/` | The Python package ([overview](switchboard/README.md), [Python README](switchboard/python/README.md)) |

## Common tasks

```bash
scripts/deploy.sh                  # apply config changes (restarts Ollama only if settings changed)
scripts/deploy.sh --restart        # force an Ollama restart
scripts/deploy.sh --update-models  # re-pull models from the library (may download newer uploads)
tests/smoke.sh                     # is everything up, and is it as fast as it should be?
```

**Rebuild from scratch:**
1. `ssh minipc-hypervisor 'bash -s' < proxmox/create-lxc.sh`
2. Reserve the new container's IP in the router. If it changed, update `~/.ssh/config`, `jobs.toml` and `tests/smoke.sh`.
3. `scripts/deploy.sh` (downloads about 23 GB of models; give it time)
4. `tests/smoke.sh`

**Add a model:** add its name to `ollama/models.txt`, optionally add a
`ollama/modelfiles/<name>.Modelfile`, then `scripts/deploy.sh`. Check the RAM budget below first.

## Models

| Model | Size in RAM | Used for |
|---|---|---|
| `gemma4-cpu` | ~17 GB | Chat. `gemma4:26b` (Q4_K_M mixture-of-experts, ~4B active parameters) with speculative decoding turned off |
| `tev1:4b` | ~5.7 GB | Decisions/classification through Ollama's `/v1/systemone` endpoint |
| `gemma4:26b` | | Base for `gemma4-cpu`. Don't call it directly (it's slower, see below) |

Both fit in memory together: about 23 GB of the container's 24 GB.

## Why each tweak exists

| Setting | Why |
|---|---|
| `gemma4-cpu` = `gemma4:26b` + `PARAMETER draft_num_predict 0` | The library model ships with MTP speculative decoding on. On this 4-core CPU the draft model competes with the main one for cores, cutting output from ~6 to ~2.5 tok/s. |
| `"think": false` sent per request | Gemma 4 "thinks" by default, which means minutes of hidden tokens per reply on this CPU. `think` isn't a valid Modelfile parameter, so switchboard sends it with each chat request. |
| `OLLAMA_KEEP_ALIVE=30m` | Measured with the CPU's power sensor: a loaded idle model adds only ~0.25 W, but each reload costs ~708 J (42 s at ~17 W). The break-even is ~47 minutes, so 30m is close to power-optimal. Unloading sooner wastes power on reloads. |
| `OLLAMA_CONTEXT_LENGTH=8192` | Keeps the per-model memory (KV cache) small enough for both models to fit in 24 GB. |
| `OLLAMA_FLASH_ATTENTION=1` | Less memory and faster prompt reading on CPU. |
| `OLLAMA_NUM_PARALLEL=1` | With 4 cores, parallel requests just slow each other down. Requests queue instead. |
| `OLLAMA_HOST=0.0.0.0:11434` | Reachable from the LAN. There's no auth, so **never** port-forward this. |
| Container capped at 24 GB, swap 1 GB | The AI must stay within 28 GB of the host's 32 GB, leaving room for Proxmox and VM 100. |
| Unprivileged LXC, `nesting=1,keyctl=1` | The standard safe setup for a Debian container running systemd services. |
| Ollama pinned to 0.40.16 | `bootstrap.sh` installs this exact version so a rebuild matches what was tested. |
| No Open WebUI | It was removed. Its built-in tools added ~6,300 hidden prompt tokens to every chat (~5 minutes to process here), and its background jobs (titles, tags, follow-ups) queued ahead of real requests. |

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
- **Can't connect:** `curl http://192.168.68.158:11434/api/version`. If the container doesn't
  answer, check it's running: `ssh minipc-hypervisor pct status 101`.
- **Big downloads failing with `unexpected EOF`:** don't run large downloads in parallel.

## Security

- Nothing in this repo is secret. API keys live only in `.env` files, which git ignores.
- The Ollama API has no authentication. It must stay on the LAN: no router port-forwarding. For
  remote access, use a VPN such as Tailscale rather than exposing the port.

## Later / optional

- Tailscale for remote access
- A third model (check the RAM budget)
- Ansible, if this grows past one box
