#!/usr/bin/env bash
# Execute inside ubuntu_env.sh, after installing the official Auto environment.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
variant="${1:?Usage: run_auto.sh sim|transfer [scene|reference]}"
mode="${2:-scene}"
case "$variant" in
  sim) checkpoint=Cosmos3-Nano-Sim-Auto ;;
  transfer) checkpoint=Cosmos3-Nano-Transfer-Auto ;;
  *) echo 'Expected sim or transfer' >&2; exit 2 ;;
esac
case "$mode" in
  scene) resolution="${COSMOS3_RESOLUTION:-480}" ;;
  reference) resolution=720 ;;
  *) echo 'Expected scene or reference (reference is the full upstream example)' >&2; exit 2 ;;
esac
export COSMOS_INTERNAL=0 COSMOS_TRAINING=0
export COSMOS3_SAVE_JOINT_LATENTS=1
export PYTORCH_ALLOC_CONF="${PYTORCH_ALLOC_CONF:-expandable_segments:True}"
# Optional profile used in the tested unprivileged userland; native NCCL defaults otherwise.
if [[ "${COSMOS3_NCCL_PROFILE:-native}" == namespace ]]; then
  export NCCL_SHM_DISABLE="${NCCL_SHM_DISABLE:-0}"
  export NCCL_P2P_DISABLE="${NCCL_P2P_DISABLE:-1}"
  export NCCL_CUMEM_HOST_ENABLE="${NCCL_CUMEM_HOST_ENABLE:-0}"
fi
export IMAGINAIRE_HF_CLI_ENVIRONMENT="$PROJECT_ROOT/storage/venvs/framework-hf-cli"
if [[ "${CUDA_VISIBLE_DEVICES:-}" != "${COSMOS3_GPUS:?Select four allocated GPUs}" ]] ||
   [[ ! "${CUDA_VISIBLE_DEVICES:-}" =~ ^[0-9]+,[0-9]+,[0-9]+,[0-9]+$ ]]; then
  echo 'Select four physical GPUs using COSMOS3_GPUS and scripts/launch_auto.sh.' >&2
  exit 2
fi
export PATH="$PROJECT_ROOT/storage/venvs/auto/bin:$PATH"
request="$PROJECT_ROOT/storage/auto_sample/assets/sample_data/input-${variant}-auto.jsonl"
if [[ "$mode" == scene ]]; then
  request="${COSMOS3_REQUEST:?Set COSMOS3_REQUEST to an absolute prepared request path}"
fi
output="${COSMOS3_OUTPUT:-$PROJECT_ROOT/outputs/${variant}-${mode}-$(date -u +%Y%m%dT%H%M%S%N)}"
if [[ -e "$output" ]]; then
  echo "Preserve existing output; select a fresh COSMOS3_OUTPUT: $output" >&2
  exit 2
fi
extra=()
if [[ "$variant" == transfer ]]; then
  extra+=(--num-steps 35 --per-view-negative-prompt "$(cat "$PROJECT_ROOT/repos/cosmos-framework/.agents/skills/cosmos3-nano-transfer-auto/inference/assets/negative-prompt.txt")")
fi
if [[ "$variant" == sim ]]; then
  python "$PROJECT_ROOT/scripts/check_sim_hardware.py"
fi
cd "$PROJECT_ROOT/repos/cosmos-framework"
exec torchrun --standalone --nproc-per-node=4 -m cosmos_framework.scripts.inference \
  -i "$request" -o "$output" --checkpoint-path "$PROJECT_ROOT/storage/models/$checkpoint" \
  --resolution "$resolution" --cp-size 4 --cfgp-size 1 --dp-shard-size 4 \
  --offload-guardrail-models --no-use-torch-compile --no-diffusion-cache "${extra[@]}"
