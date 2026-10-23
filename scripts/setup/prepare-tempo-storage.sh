#!/usr/bin/env bash
set -euo pipefail

# Run as root before the first deployment. The sparse image limits trace data
# to a dedicated 4 GiB ext4 filesystem outside the checkout.
if [[ "$(id -u)" != 0 ]]; then
  echo "Run as root: sudo bash scripts/setup/prepare-tempo-storage.sh" >&2
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

# Persist the mount on systemd hosts (including remote deployments). Docker's
# restart policies can start Tempo without Compose, so order the daemon itself
# after the mount and fail closed if the trace filesystem cannot be mounted.
# Reloading units does not restart Docker or interrupt existing containers.
if [[ -d /run/systemd/system ]]; then
  mount_unit=$(systemd-escape --path --suffix=mount "$mountpoint_path")
  install -d -m 0755 /etc/systemd/system/docker.service.d
  cat >"/etc/systemd/system/$mount_unit" <<EOF
[Unit]
Description=Bounded platform Tempo trace filesystem
Before=docker.service

[Mount]
What=$image
Where=$mountpoint_path
Type=ext4
Options=loop,nodev,nosuid,noexec

[Install]
WantedBy=local-fs.target
EOF
  cat >/etc/systemd/system/docker.service.d/tempo-storage.conf <<EOF
[Unit]
RequiresMountsFor=$mountpoint_path
EOF
  chmod 0644 "/etc/systemd/system/$mount_unit" \
    /etc/systemd/system/docker.service.d/tempo-storage.conf
  systemctl daemon-reload
  systemctl enable "$mount_unit"
else
  echo "No systemd detected; rerun this script after reboot before Docker starts." >&2
fi
echo "Tempo trace filesystem ready at $mountpoint_path"
