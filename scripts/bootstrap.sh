#!/usr/bin/env bash
# Turn a fresh Debian 13 LXC into the AI server, or bring an existing one in line with this repo.
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

step "Done"
ollama list
