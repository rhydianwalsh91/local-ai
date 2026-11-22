#!/usr/bin/env bash
# Create the "ai" LXC container on the Proxmox host.
#
# Run ON the Proxmox host (not your Mac):
#   ssh minipc-hypervisor 'bash -s' < proxmox/create-lxc.sh
#
# Then, from your Mac, turn the empty container into the AI server:
#   scripts/deploy.sh
#
# Settings can be overridden with environment variables, e.g. CTID=102 bash create-lxc.sh
set -euo pipefail

CTID="${CTID:-101}"
HOSTNAME="${CT_HOSTNAME:-ai}"
TEMPLATE="${TEMPLATE:-debian-13-standard_13.6-1_amd64.tar.zst}" # must be amd64, not arm64
CORES="${CORES:-4}"
MEMORY_MB="${MEMORY_MB:-24576}" # 24 GB cap; whole AI budget is 28 GB of the host's 32 GB
SWAP_MB="${SWAP_MB:-1024}"
DISK_GB="${DISK_GB:-64}"
STORAGE="${STORAGE:-local-lvm}"
BRIDGE="${BRIDGE:-vmbr0}"
SSH_KEYS="${SSH_KEYS:-/root/.ssh/authorized_keys}"

if pct status "$CTID" >/dev/null 2>&1; then
  echo "Container $CTID already exists - not touching it." >&2
  echo "Current config:" >&2
  pct config "$CTID" >&2
  exit 1
fi

if ! pveam list local | grep -q "$TEMPLATE"; then
  echo "Downloading template $TEMPLATE ..."
  pveam update
  pveam download local "$TEMPLATE"
fi

# unprivileged + nesting/keyctl: the standard safe setup for a Debian LXC running systemd services.
# firewall=0: LAN only; Ollama has no auth, so never port-forward 11434 on the router.
pct create "$CTID" "local:vztmpl/$TEMPLATE" \
  --hostname "$HOSTNAME" --ostype debian --arch amd64 \
  --unprivileged 1 --features nesting=1,keyctl=1 \
  --cores "$CORES" --memory "$MEMORY_MB" --swap "$SWAP_MB" \
  --rootfs "$STORAGE:$DISK_GB" \
  --net0 "name=eth0,bridge=$BRIDGE,ip=dhcp,firewall=0" \
  --onboot 1 \
  --description "Local AI server (Ollama). Recipe: github.com/rhydianwalsh91/local-ai" \
  --ssh-public-keys "$SSH_KEYS"

pct start "$CTID"
echo "Waiting for an IP address..."
for _ in $(seq 1 30); do
  ip=$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}') || true
  [ -n "${ip:-}" ] && break
  sleep 2
done
echo "Container $CTID is up at ${ip:-<unknown>}."
echo "Reserve this address in the router (DHCP reservation) so it never changes,"
echo "then run scripts/deploy.sh from your Mac."
