# Closed-Loop OMNeT++/Veins Integration

This folder adds the missing closed-loop interface between the Flower-trained
VANET IDS model and an OMNeT++/Veins SDN-VANET simulation.

## Runtime Flow

```text
Veins vehicle/RSU/SDN module
    -> HTTP POST /predict
    -> Python IDS inference server
    -> final Flower global model
    -> action: allow, monitor, drop_message, isolate_sender
    -> Veins applies SDN mitigation logic
```

## 1. Train and Save the Global Model

The Flower server now saves the final model at:

```text
models/final_global_model.pt
```

Run the normal FL pipeline first:

```bash
cd /opt/sahsan03/VANET-IDS26
bash scripts/launch_full_e1_nohup.sh
```

Wait until the final server log contains:

```text
[server] saved final global model: /opt/sahsan03/VANET-IDS26/models/final_global_model.pt
```

## 2. Start the IDS Inference Server

```bash
cd /opt/sahsan03/VANET-IDS26
CUDA_VISIBLE_DEVICES=1 python3 scripts/closed_loop_ids_server.py \
  --checkpoint models/final_global_model.pt \
  --host 127.0.0.1 \
  --port 9090 \
  --mitigation-threshold 0.60
```

Health check:

```bash
curl http://127.0.0.1:9090/health
```

Prediction test:

```bash
curl -s http://127.0.0.1:9090/predict \
  -H 'Content-Type: application/json' \
  --data @omnetpp_veins_integration/protocol/predict_request_example.json
```

## 3. Connect Veins

Copy these files into your OMNeT++/Veins project:

```text
omnetpp_veins_integration/src/ClosedLoopIdsClient.h
omnetpp_veins_integration/src/ClosedLoopIdsClient.cc
```

Add `ClosedLoopIdsClient.cc` to your simulation build. In your vehicle,
RSU, or SDN-controller module, create one client:

```cpp
ClosedLoopIdsClient ids("127.0.0.1", 9090, 2);
```

For each received BSM/CAM/event, send either the dataset-style `text_input`
or a feature map. See:

```text
omnetpp_veins_integration/examples/VeinsAppHook.cc
```

## 4. Apply Closed-Loop Actions

Recommended mapping inside the simulation:

```text
allow                         process message normally
monitor                       lower trust / log but continue
drop_message                  discard suspicious message
drop_stale_or_replayed_message discard replay/timing attacks
isolate_sender                SDN controller blocks sender or reroutes flows
```

The C++ adapter deliberately avoids third-party JSON/HTTP dependencies. If your
Veins project already uses libcurl or a JSON library, you can replace the small
socket/parsing helper with that project-native implementation.
