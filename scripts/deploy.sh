#!/usr/bin/env bash
# Push this repo's server config from your Mac to the AI container and apply it.
#
#   scripts/deploy.sh                  # copy files, apply config, rebuild model variants
#   scripts/deploy.sh --restart        # ...and always restart Ollama (unloads models)
#   scripts/deploy.sh --update-models  # ...and re-pull models from the Ollama library
#
# Ollama is only restarted when its config (or version) actually changed, because a restart
# unloads the models and the next request pays the 45-110 s reload. Open WebUI's container is only
# recreated when its version or settings changed.
set -euo pipefail

HOST="${AI_SSH_HOST:-minipc-ai}"   # SSH alias from ~/.ssh/config
REMOTE_DIR=/opt/local-ai

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> Copying ollama/, open-webui/ and scripts/ to $HOST:$REMOTE_DIR"
# COPYFILE_DISABLE / --no-xattrs stop macOS adding ._ files and metadata the Linux tar warns about.
COPYFILE_DISABLE=1 tar --no-xattrs -czf - ollama open-webui scripts |
  ssh "$HOST" "set -e; rm -rf $REMOTE_DIR.new; mkdir -p $REMOTE_DIR.new
    tar --warning=no-unknown-keyword --no-same-owner -xzf - -C $REMOTE_DIR.new
    rm -rf $REMOTE_DIR; mv $REMOTE_DIR.new $REMOTE_DIR"

ssh "$HOST" "bash $REMOTE_DIR/scripts/bootstrap.sh $*"
