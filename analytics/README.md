# Collected-data analytics

`tiger_data_analytics.ipynb` — exploratory analysis and **open-set recognition
(OSR) feasibility** study for traffic captured by the controller's
`FlowDataRecorder` (`smartville-controller`, run with
`intrusion_detection.data_collection_mode: true`).

The notebook is **self-contained**: it imports nothing from the controller
codebase and only reads the on-disk artefacts of a capture run
(`manifest.json`, `shards_index.jsonl`, `shard_*.pt`). The open-set curriculum
(`Knowns` / `G1s` / `G2s`) is reconstructed from the manifest exactly as
`TigerBrain.get_zda_labels` does at replay time, so `zda`/`test_zda` are derived
here (they are deliberately *not* persisted by the recorder).

## What it produces

1. **Class balancing** — per-class counts (coloured by curriculum group),
   benign/malicious split, imbalance ratio / entropy / Gini, and class-mix drift
   over capture ticks.
2. **Input-space geometry (PCA)** — scree + 2-D projections of the flow-stats
   window (`[10,4]→40-D`), the raw packet bytes (`64-D`), and their standardised
   combination, coloured by group and by benign/malicious, plus a per-class
   small-multiples highlight grid.
3. **Separability metrics** — t-SNE embedding, class-centroid distance heatmap,
   per-class silhouette scores.
4. **Open-set feasibility** — fits an "unknown-ness" detector on the `Knowns`
   only and measures how well it separates the `G2` test zero-days:
   score distributions (known vs. G1 vs. G2), per-stream × per-score **AUROC**
   heatmap (`centroid`, `mahalanobis`, `kNN`, `MSP`, `energy`), the open-set
   ROC, **per-zero-day detectability**, and a known-retention vs. open-set-recall
   operating trade-off — ending in an automated feasibility verdict.

## Usage

1. Install deps (any recent scientific-Python stack):
   `pip install torch numpy pandas scikit-learn matplotlib scipy jupyter`
2. Open the notebook and set `DATA_ROOT` (cell **0**) to your capture directory
   — either the collection root containing `run_*/` (newest is auto-selected) or
   a single `run_*/` dir. It can also be set via the `TIGER_DATA_ROOT` env var.
3. *Run All.*

No captured data handy? The last cell writes a tiny synthetic run in the exact
recorder format so the whole notebook can be exercised end-to-end for pipeline
validation (uncomment `write_synthetic_smoketest()`, then point `DATA_ROOT` at
`./_synth_smoketest`).

## Notes

- `SKIP_FIRST_SHARD = True` mirrors `offline_replay.py`, which skips the first
  shard-index entry (an initial packet-repetition warm-up artefact).
- AUROC is computed against **ground-truth** labels: it measures how much
  open-set signal exists *in the data*, not the accuracy of any deployed
  detector — the learned IM representation can do better than these
  linear/geometric probes.
