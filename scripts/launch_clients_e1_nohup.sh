#!/usr/bin/env bash
set -euo pipefail

cd /opt/sahsan03/VANET-IDS26
mkdir -p logs

client_running() {
  local client_id="$1"
  for pid in $(pgrep -u "${USER}" -f "scripts/flower_vanet_pipeline.py client --client-id ${client_id} " || true); do
    if [[ -e "/proc/${pid}/cwd" ]] && [[ "$(readlink "/proc/${pid}/cwd")" == "$(pwd)" ]]; then
      return 0
    fi
  done
  return 1
}

if ! ss -ltn 2>/dev/null | grep -q ':8080'; then
  echo "Flower server is not listening on port 8080. Start the server first."
  exit 1
fi

for client_id in 0 1 2 3; do
  if client_running "${client_id}"; then
    echo "Client ${client_id} is already running."
    continue
  fi

  echo "Starting client ${client_id} on CUDA 1..."
  nohup env PYTHONUNBUFFERED=1 CUDA_VISIBLE_DEVICES=1 python3 scripts/flower_vanet_pipeline.py client \
    --client-id "${client_id}" \
    --server-address 127.0.0.1:8080 \
    --label-column multiclass_label \
    --num-labels 27 \
    --batch-size 16 \
    --local-epochs 1 \
    --d-model 128 \
    --nhead 8 \
    --num-layers 4 \
    --dropout 0.15 \
    --seed 42 \
    --malicious none \
    --chunk-rows 100000 \
    --eval-max-batches 512 \
    --class-weighting global \
    --class-weight-power 0.5 \
    > "logs/client_${client_id}_full_e1_nohup.log" 2>&1 &
  echo "$!" > "logs/client_${client_id}_full_e1_nohup.pid"
done

echo "Client launch command complete."
