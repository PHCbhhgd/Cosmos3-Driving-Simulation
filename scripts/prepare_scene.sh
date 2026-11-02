#!/usr/bin/env bash
# Prepare 4 seconds of controls; request the tested first 61 camera frames.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
scene="${1:?Usage: prepare_scene.sh straight|lane_change}"
case "$scene" in straight|lane_change) ;; *) exit 2 ;; esac
wsm="$PROJECT_ROOT/storage/venvs/wsm/bin"
"$wsm/python" scripts/prepare_trajectory_scene.py --variant "$scene" --frames 121
"$wsm/python" scripts/render_scene_wsm.py "storage/scenarios/$scene" --frames 121
"$wsm/cosmos-auto-lidar-rangemap" --input-root "storage/scenarios/$scene"   --output-root "storage/scenarios/$scene/lidar_controls" --clip-id "$scene"   --max-frames 41 --export-control --device cpu --no-vis
storage/venvs/auto/bin/python scripts/export_scene_request.py "storage/scenarios/$scene" --frames 61
