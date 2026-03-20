#!/usr/bin/env bash
set -euo pipefail

MODE=""
ASSUME_YES=0

usage() {
  cat <<'USAGE'
Usage:
  gpu-cleanup.sh --safe
  gpu-cleanup.sh --force
  gpu-cleanup.sh --force --yes
  gpu-cleanup.sh --help

Behavior:
  --safe mode:
    - Shows GPU status (if nvidia-smi works)
    - Stops loaded Ollama models (best effort)
    - Shows GPU status again

  --force mode:
    - Includes --safe steps
    - Terminates remaining CUDA compute processes (SIGTERM, then SIGKILL)
    - Optionally restarts ollama service (best effort)
USAGE
}

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

warn() {
  printf '[%s] WARNING: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

show_gpu_status() {
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    warn "nvidia-smi not found. Skipping GPU status."
    return 0
  fi

  if ! nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader; then
    warn "nvidia-smi failed (NVML/driver state may be degraded)."
  fi

  if ! nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader; then
    warn "Could not list compute apps."
  fi
}

get_total_free_mib() {
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo ""
    return 0
  fi

  local values
  values="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null || true)"
  if [[ -z "${values// /}" ]]; then
    echo ""
    return 0
  fi

  echo "$values" | awk '{sum+=$1} END {if (NR>0) printf "%d", sum}'
}

stop_ollama_models() {
  if ! command -v ollama >/dev/null 2>&1; then
    log "ollama not found. Skipping model unload."
    return 0
  fi

  local models
  models="$(ollama ps 2>/dev/null | awk 'NR>1 && NF {print $1}' || true)"

  if [[ -z "${models// /}" ]]; then
    log "No loaded Ollama models found."
    return 0
  fi

  log "Stopping loaded Ollama models (best effort)..."
  while IFS= read -r model; do
    [[ -z "$model" ]] && continue
    log "  ollama stop $model"
    ollama stop "$model" >/dev/null 2>&1 || warn "Failed to stop model: $model"
  done <<< "$models"
}

get_compute_pids() {
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    return 0
  fi

  nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits 2>/dev/null \
    | awk 'NF {print $1}' \
    | sort -u
}

terminate_compute_jobs_force() {
  local pids
  pids="$(get_compute_pids || true)"

  if [[ -z "${pids// /}" ]]; then
    log "No CUDA compute processes to terminate."
    return 0
  fi

  warn "Force mode: terminating CUDA compute processes."
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    if kill -0 "$pid" 2>/dev/null; then
      log "  SIGTERM -> PID $pid"
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done <<< "$pids"

  sleep 3

  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    if kill -0 "$pid" 2>/dev/null; then
      warn "  PID $pid still running, sending SIGKILL"
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done <<< "$pids"
}

restart_ollama_force() {
  if ! command -v systemctl >/dev/null 2>&1; then
    return 0
  fi

  if systemctl is-active --quiet ollama 2>/dev/null; then
    log "Restarting ollama service (best effort)..."
    systemctl restart ollama 2>/dev/null || warn "systemctl restart ollama failed."
  else
    log "ollama service not active, skip restart."
  fi
}

confirm_force() {
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    return 0
  fi

  cat <<'TXT'
Force mode will:
  - terminate active CUDA compute jobs (SIGTERM/SIGKILL)
  - restart ollama service if active
This can interrupt running workloads.
TXT
  read -r -p "Type YES to continue: " answer
  [[ "$answer" == "YES" ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --safe)
      MODE="safe"
      shift
      ;;
    --force)
      MODE="force"
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$MODE" ]]; then
  usage
  exit 0
fi

log "GPU cleanup started"
log "Mode: $(echo "$MODE" | tr '[:lower:]' '[:upper:]')"

log "GPU status before cleanup:"
show_gpu_status
before_free_mib="$(get_total_free_mib)"

stop_ollama_models
sleep 2

if [[ "$MODE" == "force" ]]; then
  if ! confirm_force; then
    log "Aborted by user."
    exit 1
  fi
  terminate_compute_jobs_force
  restart_ollama_force
  sleep 2
fi

log "GPU status after cleanup:"
show_gpu_status
after_free_mib="$(get_total_free_mib)"

if [[ "$before_free_mib" =~ ^[0-9]+$ ]] && [[ "$after_free_mib" =~ ^[0-9]+$ ]]; then
  delta_mib=$((after_free_mib - before_free_mib))
  if (( delta_mib >= 0 )); then
    echo "SUMMARY: Freed VRAM: ${delta_mib} MiB (before: ${before_free_mib} MiB free, after: ${after_free_mib} MiB free)"
  else
    consumed_mib=$(( -delta_mib ))
    echo "SUMMARY: Freed VRAM: 0 MiB (VRAM usage increased by ${consumed_mib} MiB; before: ${before_free_mib} MiB free, after: ${after_free_mib} MiB free)"
  fi
else
  echo "SUMMARY: Freed VRAM: unknown (nvidia-smi/NVML data unavailable)"
fi
