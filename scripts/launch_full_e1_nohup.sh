#!/usr/bin/env bash
set -euo pipefail

cd /opt/sahsan03/VANET-IDS26
mkdir -p logs

has_repo_pipeline_processes() {
  for pid in $(pgrep -u "${USER}" -f "scripts/flower_vanet_pipeline.py" || true); do
    if [[ -e "/proc/${pid}/cwd" ]] && [[ "$(readlink "/proc/${pid}/cwd")" == "$(pwd)" ]]; then
      return 0
    fi
  done
  return 1
}

if has_repo_pipeline_processes; then
  echo "Existing VANET pipeline processes detected."
  echo "Run this first: bash scripts/stop_vanet_pipeline.sh"
  exit 1
fi

echo "Starting Flower server on CUDA 1..."
nohup env PYTHONUNBUFFERED=1 CUDA_VISIBLE_DEVICES=1 python3 scripts/flower_vanet_pipeline.py server \
  --address 127.0.0.1:8080 \
  --rounds 10 \
  --robust-aggregation fedtrimmedavg \
  --trimmed-beta 0.1 \
  --min-fit-clients 4 \
  --min-evaluate-clients 4 \
  --min-available-clients 4 \
  --num-labels 27 \
  --label-column multiclass_label \
  --local-epochs 1 \
  --d-model 128 \
  --nhead 8 \
  --num-layers 4 \
  --dropout 0.15 \
  --seed 42 \
  --server-eval-batch-size 64 \
  --server-eval-max-batches 1024 \
  --eval-chunk-rows 100000 \
  > logs/server_full_e1_nohup.log 2>&1 &

server_pid=$!
echo "${server_pid}" > logs/server_full_e1_nohup.pid

echo "Waiting for server port 8080..."
for _ in $(seq 1 120); do
  if ss -ltn 2>/dev/null | grep -q ':8080'; then
    break
  fi
  if ! kill -0 "${server_pid}" 2>/dev/null; then
    echo "Server exited before opening port 8080."
    tail -80 logs/server_full_e1_nohup.log || true
    exit 1
  fi
  sleep 2
done

if ! ss -ltn 2>/dev/null | grep -q ':8080'; then
  echo "Server did not open port 8080 in time."
  tail -80 logs/server_full_e1_nohup.log || true
  exit 1
fi

echo "Starting 4 clients on CUDA 1..."
for client_id in 0 1 2 3; do
  nohup env PYTHONUNBUFFERED=1 CUDA_VISIBLE_DEVICES=1 python3 scripts/flower_vanet_pipeline.py client \
    --client-id "${client_id}" \
    --server-address 127.0.0.1:8080 \
    --label-column multiclass_label \
    --num-labels 27 \
    --batch-size 64 \
    --local-epochs 1 \
    --train-max-batches 10000 \
    --progress-every-batches 1000 \
    --lr 1e-4 \
    --d-model 128 \
    --nhead 8 \
    --num-layers 4 \
    --dropout 0.15 \
    --seed 42 \
    --malicious none \
    --chunk-rows 100000 \
    --eval-max-batches 512 \
    --shuffle-train-chunks \
    --class-weighting global \
    --class-weight-power 1.0 \
    > "logs/client_${client_id}_full_e1_nohup.log" 2>&1 &
  echo "$!" > "logs/client_${client_id}_full_e1_nohup.pid"
done

echo "Started server and 4 clients."
echo "Monitor server: tail -f /opt/sahsan03/VANET-IDS26/logs/server_full_e1_nohup.log"
echo "Check processes: ps -u ${USER} -o pid,etime,pcpu,pmem,cmd | grep flower_vanet_pipeline.py | grep -v grep"
