#!/usr/bin/env bash
# Run a prepared scene, recover decode from saved latents, and validate a fresh bundle.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
scene="${1:?Usage: run_scene_pipeline.sh straight|lane_change [request-joint-61.json]}"
request_name="${2:-request-joint-61.json}"
case "$scene" in
  straight|lane_change) ;;
  *) echo 'Expected straight or lane_change' >&2; exit 2 ;;
esac
cd "$PROJECT_ROOT"
: "${COSMOS3_GPUS:?Select four allocated idle GPUs}"
mkdir -p artifacts outputs
review_python="$PROJECT_ROOT/storage/venvs/review/bin/python"
export COSMOS3_REQUEST="$PROJECT_ROOT/storage/scenarios/$scene/$request_name"
[[ -f "$COSMOS3_REQUEST" ]]
stamp="$(date -u +%Y%m%dT%H%M%S%N)"
export COSMOS3_OUTPUT="$PROJECT_ROOT/outputs/transfer-${scene}-${stamp}"
sample_name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$COSMOS3_REQUEST")"
sample="$COSMOS3_OUTPUT/$sample_name"
bundle="$PROJECT_ROOT/outputs/bundles/${scene}-${stamp}"
log="$PROJECT_ROOT/artifacts/${scene}-${stamp}"
if ! bash scripts/launch_auto.sh transfer scene > "${log}-inference.log" 2>&1; then
  # Only recover a complete denoising result; input/attention/OOM sampling failures remain failures.
  [[ -s "$sample/joint_latents.safetensors" && -s "$sample/joint_latents_args.json" ]]
  # nvidia-smi utilization can report the previous inference interval after the
  # processes have exited. Retry briefly, checking processes and memory each time.
  ready=0
  for attempt in 1 2 3 4 5; do
    if python3 scripts/check_gpus.py --gpus "$COSMOS3_GPUS" > "${log}-decode-gpus.json"; then
      ready=1
      break
    fi
    sleep 2
  done
  [[ "$ready" == 1 ]]
  COSMOS3_GPUS="${COSMOS3_GPUS%%,*}" bash scripts/run_env.sh bash scripts/ubuntu_env.sh \
    storage/venvs/auto/bin/python scripts/decode_joint_latents.py "$sample" > "${log}-decode.log" 2>&1
fi
COSMOS3_GPUS=-1 bash scripts/run_env.sh bash scripts/ubuntu_env.sh \
  storage/venvs/auto/bin/python scripts/package_simulation.py "$sample" --request "$COSMOS3_REQUEST" \
  --scene "storage/scenarios/$scene" --output "$bundle" > "${log}-package.log" 2>&1
"$review_python" scripts/review_sensor_bundle.py "$bundle" > "${log}-review.log" 2>&1
"$review_python" scripts/evaluate_joint_controls.py "$bundle" --scene "storage/scenarios/$scene" > "${log}-controls.log" 2>&1
"$review_python" scripts/check_replay_browser.py "$bundle" --report "${log}-browser.json" > "${log}-browser.log" 2>&1
echo "Validated sensor bundle: $bundle"
