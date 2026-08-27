#!/usr/bin/env bash
set -euo pipefail

cd /opt/sahsan03/VANET-IDS26
mkdir -p logs

checkpoint="models/final_global_model.pt"
if [[ ! -f "${checkpoint}" ]]; then
  echo "Missing ${checkpoint}. Finish Flower training first."
  exit 1
fi

if ss -ltn 2>/dev/null | grep -q ':9090'; then
  echo "Port 9090 is already listening. Stop the existing IDS server first if needed."
  exit 1
fi

nohup env PYTHONUNBUFFERED=1 CUDA_VISIBLE_DEVICES=1 python3 scripts/closed_loop_ids_server.py \
  --checkpoint "${checkpoint}" \
  --host 127.0.0.1 \
  --port 9090 \
  --mitigation-threshold 0.60 \
  > logs/closed_loop_ids_server.log 2>&1 &

echo "$!" > logs/closed_loop_ids_server.pid
echo "Started closed-loop IDS server on http://127.0.0.1:9090"
echo "Monitor: tail -f /opt/sahsan03/VANET-IDS26/logs/closed_loop_ids_server.log"
