#!/usr/bin/env bash
# Compatibility entry point: use an already compatible OS/container userland.
# This public repository does not install a rootfs or modify the host OS.
set -euo pipefail
exec "$@"
