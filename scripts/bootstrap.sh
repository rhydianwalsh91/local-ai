#!/usr/bin/env bash
# Turn a fresh Debian 13 LXC into the AI server (Ollama + Open WebUI), or bring an existing one in
# line with this repo.
# Safe to re-run: every step checks first and only changes what's different.
#
# Normally run for you by scripts/deploy.sh. To run by hand inside the container:
#   bash /opt/local-ai/scripts/bootstrap.sh [--restart] [--update-models]
#
#   --restart        restart Ollama even if its config didn't change (unloads models)
#   --update-models  re-pull every model in ollama/models.txt (may download new versions)
set -euo pipefail

OLLAMA_VERSION="${OLLAMA_VERSION:-0.40.16}"
OVERRIDE_DST=/etc/systemd/system/ollama.service.d/override.conf
OLLAMA_URL=http://127.0.0.1:11434

OPEN_WEBUI_VERSION="${OPEN_WEBUI_VERSION:-v0.13.4}"
OPEN_WEBUI_IMAGE="ghcr.io/open-webui/open-webui:$OPEN_WEBUI_VERSION"
# Host networking so it can reach Ollama on 127.0.0.1 and serve :8080 directly. The memory cap
# means that if Open WebUI ever balloons, it gets restarted instead of the kernel killing a model.
OPEN_WEBUI_RUN_ARGS=(--network host --restart unless-stopped --memory 1536m
  --env-file open-webui/open-webui.env -v open-webui:/app/backend/data)

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

restart=0
update_models=0
for arg in "$@"; do
  case "$arg" in
    --restart) restart=1 ;;
    --update-models) update_models=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

step() { printf '\n==> %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Run as root." >&2; exit 1; }

step "Base packages"
missing=()
for pkg in curl ca-certificates zstd; do
  dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [ ${#missing[@]} -gt 0 ]; then
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${missing[@]}"
else
  echo "already installed"
fi

step "Ollama $OLLAMA_VERSION"
installed="$(ollama --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | tail -1 || true)"
if [ "$installed" != "$OLLAMA_VERSION" ]; then
  echo "installed: ${installed:-none} -> installing $OLLAMA_VERSION"
  curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION="$OLLAMA_VERSION" sh
  restart=1
else
  echo "already at $OLLAMA_VERSION"
fi

step "Ollama settings ($OVERRIDE_DST)"
if ! cmp -s ollama/override.conf "$OVERRIDE_DST"; then
  # Compare the settings systemd actually applies, so a comment-only edit doesn't trigger a restart.
  before="$(systemctl show ollama -p Environment 2>/dev/null || true)"
  install -D -m 644 ollama/override.conf "$OVERRIDE_DST"
  systemctl daemon-reload
  if [ "$(systemctl show ollama -p Environment)" != "$before" ]; then
    echo "updated (settings changed)"
    restart=1
  else
    echo "updated (comments only, no restart needed)"
  fi
else
  echo "unchanged"
fi

systemctl enable --quiet ollama
if [ "$restart" -eq 1 ]; then
  echo "restarting Ollama (any loaded models are unloaded)"
  systemctl restart ollama
elif ! systemctl is-active --quiet ollama; then
  systemctl start ollama
fi

for _ in $(seq 1 30); do
  curl -fsS "$OLLAMA_URL/api/version" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "$OLLAMA_URL/api/version" >/dev/null || { echo "Ollama didn't come up; see: journalctl -u ollama" >&2; exit 1; }

step "Models (ollama/models.txt)"
# Only pull what's missing unless asked: re-pulling can silently swap in a newer upload of a tag.
sed -e 's/#.*//' -e 's/[[:space:]]*$//' ollama/models.txt | while read -r model; do
  [ -n "$model" ] || continue
  if [ "$update_models" -eq 1 ] || ! ollama show "$model" >/dev/null 2>&1; then
    echo "pulling $model"
    ollama pull "$model"
  else
    echo "$model: present"
  fi
done

step "Model variants (ollama/modelfiles)"
for file in ollama/modelfiles/*.Modelfile; do
  [ -e "$file" ] || continue
  name="$(basename "$file" .Modelfile)"
  if ! out="$(ollama create "$name" -f "$file" 2>&1)"; then
    echo "$out" | tail -5 >&2
    exit 1
  fi
  echo "$name: built from $file"
done

step "Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "installing docker.io"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io >/dev/null
fi
# One download at a time: parallel layer downloads from ghcr.io failed with `unexpected EOF` here.
if ! cmp -s open-webui/daemon.json /etc/docker/daemon.json; then
  install -D -m 644 open-webui/daemon.json /etc/docker/daemon.json
  systemctl restart docker
  echo "daemon.json updated"
else
  echo "already set up"
fi

step "Open WebUI $OPEN_WEBUI_VERSION"
if ! docker image inspect "$OPEN_WEBUI_IMAGE" >/dev/null 2>&1; then
  echo "pulling $OPEN_WEBUI_IMAGE (~4.6 GB)"
  docker pull -q "$OPEN_WEBUI_IMAGE"
fi
# Fingerprint of everything that defines the container. If it matches the running one, leave it
# alone; otherwise recreate it. Accounts and chats live in the open-webui volume and are kept.
want="$( { echo "$OPEN_WEBUI_IMAGE"; printf '%s\n' "${OPEN_WEBUI_RUN_ARGS[@]}"; cat open-webui/open-webui.env; } | sha256sum | cut -c1-16)"
have="$(docker inspect -f '{{index .Config.Labels "local-ai.config"}}' open-webui 2>/dev/null || true)"
if [ "$want" != "$have" ]; then
  echo "(re)creating container"
  docker rm -f open-webui >/dev/null 2>&1 || true
  docker run -d --name open-webui --label "local-ai.config=$want" "${OPEN_WEBUI_RUN_ARGS[@]}" "$OPEN_WEBUI_IMAGE" >/dev/null
else
  docker start open-webui >/dev/null
  echo "unchanged"
fi
# Remove older Open WebUI images left behind by an upgrade (they're ~4.6 GB each).
docker images ghcr.io/open-webui/open-webui --format '{{.Repository}}:{{.Tag}}' |
  grep -vxF "$OPEN_WEBUI_IMAGE" | xargs -r docker rmi >/dev/null || true
for _ in $(seq 1 90); do
  curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS http://127.0.0.1:8080/health >/dev/null ||
  { echo "Open WebUI didn't come up; see: docker logs open-webui" >&2; exit 1; }
echo "up at http://$(hostname -I | awk '{print $1}'):8080"

step "Done"
ollama list
