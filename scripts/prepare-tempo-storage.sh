#!/usr/bin/env bash
set -euo pipefail

# Run once as root on the lab host, and again after a reboot. The sparse image
# limits trace data to a dedicated 4 GiB ext4 filesystem outside the checkout.
if [[ "$(id -u)" != 0 ]]; then
  echo "Run as root: sudo bash scripts/prepare-tempo-storage.sh" >&2
  exit 1
fi
base=/var/lib/developer-platform
image="$base/tempo-4g.img"
mountpoint_path="$base/tempo"
install -d -m 0700 "$base" "$mountpoint_path"
if [[ ! -e "$image" ]]; then
  truncate -s 4G "$image"
  mkfs.ext4 -F -q "$image"
fi
if ! mountpoint -q "$mountpoint_path"; then
  mount -o loop,nodev,nosuid,noexec "$image" "$mountpoint_path"
fi
if [[ "$(findmnt -n -o SOURCE --target "$mountpoint_path")" != /dev/loop* ]]; then
  echo "Tempo mount is not a loop device" >&2
  exit 1
fi
chown 10001:10001 "$mountpoint_path"
chmod 0700 "$mountpoint_path"
echo "Tempo trace filesystem ready at $mountpoint_path"
