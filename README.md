# Vehicular Ad Hoc Network (VANET)-IDS26

**VANET-IDS26** is a large-scale Vehicular Ad Hoc Network intrusion detection dataset containing benign VANET messages and 26 cyberattack classes.

The dataset is designed for research on VANET cybersecurity, intrusion detection systems, machine learning, deep learning, transformer-based models, graph learning, and federated learning.

This repository provides documentation, scripts, manifests, and a small balanced sample. The full dataset is hosted on Hugging Face Datasets.

---

## Full Dataset Download

The full dataset is available on Hugging Face:

https://huggingface.co/datasets/mail2sia/VANET-IDS26/tree/main/data

Hugging Face repository:

https://huggingface.co/datasets/mail2sia/VANET-IDS26

Full master file:

```text
data/vanet_ids26_master.csv.gz
````

The full master file is approximately **79 GB** compressed.

---

## Citation Requirement

If you use **VANET-IDS26** in any publication, thesis, dissertation, report, benchmark, software release, model release, or derivative dataset, please cite this dataset and the associated research work.

A formal citation and DOI will be added after the dataset paper or archive DOI is finalized.

Temporary citation:

```bibtex
@dataset{vanet_ids26_2026,
  title  = {VANET-IDS26: A Large-Scale Vehicular Ad Hoc Network Intrusion Detection Dataset with 26 Cyberattack Classes},
  author = {Mahmudul Hasan Porag and collaborators},
  year   = {2026},
  note   = {Dataset for VANET intrusion detection research. DOI and formal citation to be updated after public archive release.}
}
```

---

## Dataset Summary

| Item                  |                       Value |
| --------------------- | --------------------------: |
| Dataset name          |                 VANET-IDS26 |
| Full master file      | `vanet_ids26_master.csv.gz` |
| Full master file size |         Approximately 79 GB |
| Total rows            |                 786,798,378 |
| Benign rows           |                  37,577,963 |
| Attack rows           |                 749,220,415 |
| Columns               |                          46 |
| Binary classes        |                           2 |
| Multiclass labels     |                        0–26 |
| Attack classes        |                          26 |
| Final simulation runs |                          20 |
| Density levels        |                           4 |
| Attacker ratios       |           5%, 10%, 20%, 30% |
| GitHub sample rows    |                      27,000 |
| GitHub sample size    |       Approximately 2.26 MB |

---

## What This Repository Contains

This GitHub repository does **not** contain the full 79 GB dataset file. It contains the release materials needed to understand and use the dataset.

```text
VANET-IDS26/
├── docs/
├── manifests/
├── samples/
│   └── vanet_ids26_sample.csv.gz
├── scripts/
└── README.md
```

The full dataset is stored separately on Hugging Face.

---

## GitHub Sample File

A small balanced sample is included for quick testing:

```text
samples/vanet_ids26_sample.csv.gz
```

The sample contains:

```text
1,000 benign rows
1,000 rows from each attack class 1–26
Total rows: 27,000
Columns: 46
Compressed size: approximately 2.26 MB
```

This sample has the same schema as the full master file. Your validation log confirmed the sample has 46 columns, 27,000 rows, and balanced labels from 0 through 26. 

---

## Dataset Purpose

VANET-IDS26 was created to support reproducible research on intrusion detection in vehicular networks.

It can be used for:

```text
binary intrusion detection
multiclass attack classification
transformer-based IDS using text_input
classical machine learning IDS
deep learning IDS
graph-based IDS
federated learning IDS
non-IID client partitioning
density-based robustness evaluation
attacker-ratio robustness evaluation
attack-family generalization
```

---

## Dataset Design

The dataset contains two main types of records:

```text
benign_base      original benign VANET messages
attack_overlay   attacked or synthetic attack overlay messages
```

The final master file combines:

```text
benign VANET messages + attack overlay messages
```

into one single compressed CSV file:

```text
vanet_ids26_master.csv.gz
```

This design allows researchers to load one file directly and create their own train, validation, and test splits.

---

## Why One Master File?

The dataset is released as one model-ready file so users do not need to reconstruct the dataset from raw simulation folders.

Researchers can directly load:

```text
data/vanet_ids26_master.csv.gz
```

and choose their own splitting method, such as:

```text
random stratified split
run-level split
density-level split
attacker-ratio split
attack-family split
federated client split
```

The dataset intentionally does not force one fixed train/validation/test split.

---

## Source Data Used to Build the Master File

The final master file was built from the final 20 large simulation runs:

```text
dataset/processed/run_001001/messages.csv
dataset/processed/run_001002/messages.csv
...
dataset/processed/run_001020/messages.csv
```

and attack overlays:

```text
dataset/overlays/run_001001/**/attack_overlay.csv
dataset/overlays/run_001002/**/attack_overlay.csv
...
dataset/overlays/run_001020/**/attack_overlay.csv
```

The following old pilot folders are excluded from the final master file:

```text
dataset/processed/run_000001
dataset/processed/run_000002
dataset/attacks/
```

---

## Simulation Runs and Density Levels

The final dataset contains 20 large simulation runs.

| Runs                      | Density   |
| ------------------------- | --------- |
| `run_001001`–`run_001005` | low       |
| `run_001006`–`run_001010` | medium    |
| `run_001011`–`run_001015` | high      |
| `run_001016`–`run_001020` | very_high |

The density is included in the `density` column.

---

## Attacker Ratios

Attack overlays were generated with four attacker ratios:

| Value in dataset | Meaning            |
| ---------------: | ------------------ |
|                5 | 5% attacker ratio  |
|               10 | 10% attacker ratio |
|               20 | 20% attacker ratio |
|               30 | 30% attacker ratio |

For benign rows:

```text
attack_ratio = 0
```

---

## Labels

### Binary Label

Use `binary_label` for binary intrusion detection.

```text
0 = benign
1 = attack
```

### Multiclass Label

Use `multiclass_label` for multiclass intrusion detection.

```text
0  = benign
1  = constant_position
2  = position_offset
3  = random_position
4  = speed_manipulation
5  = acceleration_manipulation
6  = heading_manipulation
7  = lane_spoofing
8  = impossible_kinematics
9  = eventual_stop
10 = false_brake_event
11 = false_emergency_vehicle
12 = false_hazard_event
13 = replay
14 = delayed_message
15 = timestamp_shift
16 = stale_message_replay
17 = sybil
18 = impersonation
19 = pseudonym_abuse
20 = flooding_ddos
21 = beacon_rate_abuse
22 = gnss_spoofing
23 = map_location_spoofing
24 = ghost_vehicle
25 = false_object_injection
26 = object_position_shift
```

---

## Attack Taxonomy

| Label | Attack type               | Family                  | Brief description                            |
| ----: | ------------------------- | ----------------------- | -------------------------------------------- |
|     0 | benign                    | benign                  | Normal VANET message                         |
|     1 | constant_position         | position_falsification  | Reports a fixed false position               |
|     2 | position_offset           | position_falsification  | Reports a shifted false position             |
|     3 | random_position           | position_falsification  | Reports randomly falsified positions         |
|     4 | speed_manipulation        | kinematic_falsification | Manipulates claimed speed                    |
|     5 | acceleration_manipulation | kinematic_falsification | Manipulates claimed acceleration             |
|     6 | heading_manipulation      | kinematic_falsification | Manipulates claimed heading                  |
|     7 | lane_spoofing             | lane_map_falsification  | Reports a false lane                         |
|     8 | impossible_kinematics     | kinematic_falsification | Creates physically implausible motion        |
|     9 | eventual_stop             | kinematic_falsification | Falsifies behavior toward stopping           |
|    10 | false_brake_event         | event_falsification     | Injects or reports false braking events      |
|    11 | false_emergency_vehicle   | event_falsification     | Claims false emergency-vehicle behavior      |
|    12 | false_hazard_event        | event_falsification     | Injects or reports false hazard events       |
|    13 | replay                    | timing_replay           | Replays earlier VANET messages               |
|    14 | delayed_message           | timing_replay           | Delays message timing                        |
|    15 | timestamp_shift           | timing_replay           | Shifts message timestamps                    |
|    16 | stale_message_replay      | timing_replay           | Replays stale messages as current            |
|    17 | sybil                     | identity_spoofing       | Creates multiple claimed identities          |
|    18 | impersonation             | identity_spoofing       | Impersonates another vehicle                 |
|    19 | pseudonym_abuse           | identity_spoofing       | Abuses pseudonym or identity-change behavior |
|    20 | flooding_ddos             | availability_flooding   | Floods the network with excessive messages   |
|    21 | beacon_rate_abuse         | availability_flooding   | Abuses beacon transmission rate              |
|    22 | gnss_spoofing             | position_falsification  | Spoofs GNSS-derived position                 |
|    23 | map_location_spoofing     | lane_map_falsification  | Spoofs map-matched location                  |
|    24 | ghost_vehicle             | identity_spoofing       | Injects a non-existent vehicle identity      |
|    25 | false_object_injection    | event_falsification     | Injects a false perceived object             |
|    26 | object_position_shift     | event_falsification     | Shifts the reported position of an object    |

---

## Column Schema

The full master file and the sample file both contain 46 columns.

| Column                 | Description                                                     |
| ---------------------- | --------------------------------------------------------------- |
| `dataset_name`         | Dataset identifier, always `VANET-IDS26`                        |
| `record_id`            | Unique row identifier in the master file                        |
| `source_type`          | `benign_base` or `attack_overlay`                               |
| `source_file`          | Original file path used to create the row                       |
| `base_run_id`          | Simulation run ID                                               |
| `density`              | Traffic density: low, medium, high, very_high                   |
| `attack_ratio`         | Attacker ratio: 0, 5, 10, 20, or 30                             |
| `message_id`           | Message ID in the master file                                   |
| `base_message_id`      | Original base message ID                                        |
| `overlay_message_id`   | Overlay message ID for attack rows                              |
| `original_message_id`  | Original message ID for replay or delay attacks when applicable |
| `attack_dataset_id`    | Attack overlay dataset identifier                               |
| `time`                 | Simulation time                                                 |
| `claimed_time`         | Claimed message time                                            |
| `physical_sender_id`   | Actual sender vehicle ID                                        |
| `claimed_sender_id`    | Claimed sender identity                                         |
| `sequence_number`      | Message sequence number                                         |
| `true_x`               | True x-coordinate                                               |
| `true_y`               | True y-coordinate                                               |
| `true_speed`           | True vehicle speed                                              |
| `true_acceleration`    | True vehicle acceleration                                       |
| `true_heading`         | True vehicle heading                                            |
| `true_lane`            | True lane identifier                                            |
| `claimed_x`            | Claimed x-coordinate                                            |
| `claimed_y`            | Claimed y-coordinate                                            |
| `claimed_speed`        | Claimed vehicle speed                                           |
| `claimed_acceleration` | Claimed vehicle acceleration                                    |
| `claimed_heading`      | Claimed vehicle heading                                         |
| `claimed_lane`         | Claimed lane identifier                                         |
| `malicious_delay_ms`   | Malicious delay in milliseconds, where applicable               |
| `sybil_group_id`       | Sybil group identifier, where applicable                        |
| `event_type`           | Event type for event-based attacks                              |
| `false_object_id`      | False object identifier, where applicable                       |
| `object_type`          | Type of injected or shifted object                              |
| `object_x`             | Object x-coordinate                                             |
| `object_y`             | Object y-coordinate                                             |
| `attack_start_time`    | Attack start time                                               |
| `attack_notes`         | Additional attack notes                                         |
| `is_attacker`          | Whether the physical sender is an attacker                      |
| `is_synthetic_message` | Whether the row is a synthetic injected message                 |
| `attack_type`          | Human-readable attack type                                      |
| `attack_label`         | Numeric attack label                                            |
| `message_label`        | Original message label from source file                         |
| `binary_label`         | 0 for benign, 1 for attack                                      |
| `multiclass_label`     | 0 for benign, 1–26 for attack class                             |
| `text_input`           | BERT-ready text representation of the VANET message             |

---

## Text Input for Transformer Models

The dataset includes a `text_input` column for transformer-based models such as BERT, DistilBERT, RoBERTa, and similar architectures.

Example format:

```text
time=0.10 ; claimed_time=0.10 ; physical_sender_id=0 ; claimed_sender_id=0 ; sequence_number=1 ; true_x=4.80 ; true_y=1549.97 ; true_speed=12.68 ; ...
```

The `text_input` column intentionally excludes direct label columns such as:

```text
attack_type
attack_label
message_label
binary_label
multiclass_label
```

This reduces direct label leakage.

---

## Loading the Sample

```python
import pandas as pd

df = pd.read_csv("samples/vanet_ids26_sample.csv.gz")

print(df.shape)
print(df["binary_label"].value_counts())
print(df["multiclass_label"].value_counts().sort_index())
```

Expected:

```text
Rows: 27,000
Columns: 46
Labels: 0 through 26
```

---

## Loading the Full Dataset

The full master file is large, so chunked loading is recommended.

```python
import pandas as pd

path = "vanet_ids26_master.csv.gz"

for chunk in pd.read_csv(path, chunksize=100000):
    print(chunk.shape)
    print(chunk.head())
    break
```

Load only selected columns:

```python
import pandas as pd

cols = [
    "text_input",
    "binary_label",
    "multiclass_label",
    "attack_type",
    "base_run_id",
    "density",
    "attack_ratio"
]

for chunk in pd.read_csv(
    "vanet_ids26_master.csv.gz",
    usecols=cols,
    chunksize=100000
):
    print(chunk.shape)
    break
```

---

## Binary IDS Example

```python
import pandas as pd
from sklearn.model_selection import train_test_split

df = pd.read_csv("samples/vanet_ids26_sample.csv.gz")

train_df, test_df = train_test_split(
    df,
    test_size=0.2,
    stratify=df["binary_label"],
    random_state=42
)

X_train = train_df["text_input"]
y_train = train_df["binary_label"]

X_test = test_df["text_input"]
y_test = test_df["binary_label"]
```

---

## Multiclass IDS Example

```python
import pandas as pd
from sklearn.model_selection import train_test_split

df = pd.read_csv("samples/vanet_ids26_sample.csv.gz")

train_df, test_df = train_test_split(
    df,
    test_size=0.2,
    stratify=df["multiclass_label"],
    random_state=42
)

X_train = train_df["text_input"]
y_train = train_df["multiclass_label"]

X_test = test_df["text_input"]
y_test = test_df["multiclass_label"]
```

---

## Suggested Evaluation Protocols

### Protocol A: Random Stratified Split

Use this for quick baseline experiments.

```text
Split randomly while preserving class distribution.
```

### Protocol B: Run-Level Split

Use this to reduce leakage across simulation runs.

Example:

```text
Train:      run_001001 to run_001014
Validation: run_001015 to run_001017
Test:       run_001018 to run_001020
```

### Protocol C: Density Holdout

Use this to evaluate generalization to unseen traffic density.

Example:

```text
Train: low, medium, high
Test:  very_high
```

### Protocol D: Attacker-Ratio Holdout

Use this to evaluate generalization to unseen attacker intensity.

Example:

```text
Train: 5%, 10%, 20%
Test:  30%
```

### Protocol E: Attack-Family Holdout

Use this to evaluate generalization to unseen attack families.

Example:

```text
Train: position_falsification, kinematic_falsification, timing_replay
Test:  identity_spoofing or availability_flooding
```

### Protocol F: Federated Non-IID Split

Use this for federated learning.

Possible client definitions:

```text
client = physical_sender_id
client = base_run_id
client = density
client = attack_family
client = lane/geographic partition
```

---

## Recommended Model Inputs

For transformer-based models:

```text
text_input
```

For structured machine learning models:

```text
time
claimed_time
physical_sender_id
claimed_sender_id
sequence_number
true_x
true_y
true_speed
true_acceleration
true_heading
true_lane
claimed_x
claimed_y
claimed_speed
claimed_acceleration
claimed_heading
claimed_lane
malicious_delay_ms
sybil_group_id
event_type
object_x
object_y
is_attacker
is_synthetic_message
```

Depending on the deployment scenario, users may exclude `is_attacker` and `is_synthetic_message` because these fields may be too informative for some real-world IDS assumptions.

---

## Columns to Avoid as Features

Do not use direct label or identifier columns as model inputs:

```text
attack_type
attack_label
message_label
binary_label
multiclass_label
record_id
source_file
attack_dataset_id
```

Using these as model features may cause label leakage.

---

## Class Imbalance

The full master file is not balanced:

```text
Benign rows: 37,577,963
Attack rows: 749,220,415
```

Researchers may choose to:

```text
use all rows
downsample attack rows
upsample benign rows
create balanced subsets
use class weights
use stratified sampling
evaluate per-attack-class metrics
```

The GitHub sample is balanced across labels 0–26 for easy testing.

---

## Validation Status

The dataset was validated before release.

```text
Overlay run folders: 20
Attack overlay files: 2080
Overlay manifest lines: 2081
Processed big-run folders: 20
Master rows: 786,798,378
Master columns: 46
Python quick-read validation: passed
Full gzip validation: MASTER GZIP OK
Sample gzip validation: SAMPLE GZIP OK
Sample labels: 0–26, 1,000 rows each
```

---

## Rebuilding the Master File

The master file was generated using:

```text
scripts/build_vanet_ids26_master.py
```

Example:

```bash
python scripts/build_vanet_ids26_master.py \
  --output research_ready/vanet_ids26_master.csv.gz \
  --compresslevel 1
```

---

## Creating the GitHub Sample

The sample file was generated using:

```text
scripts/create_vanet_ids26_github_sample.py
```

Example:

```bash
python scripts/create_vanet_ids26_github_sample.py
```

---

## Intended Use

VANET-IDS26 is intended for:

```text
defensive cybersecurity research
VANET intrusion detection benchmarking
machine learning experiments
deep learning experiments
transformer-based IDS experiments
federated learning research
cybersecurity education
reproducible benchmarking
```

---

## Limitations

VANET-IDS26 is simulation-generated.

The attacks represent controlled benchmark scenarios and should not be interpreted as direct real-world incident logs.

Models trained on this dataset should be validated further before use in real vehicular systems.

The full dataset is large, so users should use chunked loading, streaming, or distributed processing for large-scale experiments.

---

## Ethical Use

This dataset is intended for defensive research only. It should be used to build, evaluate, and improve intrusion detection and resilience methods for vehicular networks.

---

## License

A license should be added before formal public release.

Recommended options:

```text
Dataset: CC BY 4.0
Scripts: MIT or Apache-2.0
```

---

## Maintainer

```text
mail2sia
```

---

## Citation Reminder

Please cite **VANET-IDS26** and the associated research work if you use this dataset.


