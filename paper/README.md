# Journal Manuscript

The file main.tex is an IEEE journal-style manuscript grounded in the preserved
VANET-IDS26 pipeline, manifests, and server/client logs. The file references.bib
contains the cited primary literature.

## Build

Install a TeX distribution with IEEEtran, then run latexmk -pdf main.tex from
this directory. Alternatively, run pdflatex, bibtex, pdflatex, and pdflatex in
that order.

The current host does not have pdflatex or latexmk, so the manuscript could not
be compiled locally yet.

## Evidence Used

- data/vanet_ids26_master.csv
- data/vanet_ids26_train.csv
- data/vanet_ids26_validation.csv
- data/vanet_ids26_test.csv
- data/manifests/client_partitions_manifest.json
- data/manifests/big_balanced_splits_manifest.json
- logs/server.log
- logs/server_one_malicious.log
- logs/client_0_one_malicious.log through logs/client_3_one_malicious.log
- scripts/flower_vanet_pipeline.py

## Required Before Submission

- Replace anonymous author, affiliation, funding, and acknowledgment fields.
- Add an archival code DOI/commit and confirm the dataset license/citation.
- Run matched honest and poisoned experiments from one immutable partition.
- Use enough clients and a trim proportion that produces a nonzero trim count.
- Evaluate the untouched canonical test set with run/vehicle/time-disjoint splits.
- Select observable fields explicitly, remove post-event proxies, and report a truncation/leakage ablation.
- Add true multi-message temporal windows and compare against the single-message encoder.
- Repeat each configuration over at least five seeds and report confidence intervals.
- Add centralized, local-only, FedAvg, median, and effective trimmed-mean baselines.
