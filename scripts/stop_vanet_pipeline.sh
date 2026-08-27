#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/opt/sahsan03/VANET-IDS26"
PATTERN="scripts/flower_vanet_pipeline.py"

for pid in $(pgrep -u "${USER}" -f "${PATTERN}" || true); do
  if [[ -e "/proc/${pid}/cwd" ]] && [[ "$(readlink "/proc/${pid}/cwd")" == "${REPO_ROOT}" ]]; then
    echo "Stopping VANET pipeline process ${pid}"
    kill -TERM "${pid}" 2>/dev/null || true
  fi
done

sleep 3

for pid in $(pgrep -u "${USER}" -f "${PATTERN}" || true); do
  if [[ -e "/proc/${pid}/cwd" ]] && [[ "$(readlink "/proc/${pid}/cwd")" == "${REPO_ROOT}" ]]; then
    echo "Force stopping VANET pipeline process ${pid}"
    kill -KILL "${pid}" 2>/dev/null || true
  fi
done

echo "VANET pipeline processes stopped."
