# TIGER / Smartville — Data Supply Chain (IM/DM, controller-side)

This document describes, strictly from the code on `TIGER_PAPER_DO_NOT_DELETE`
in `smartville-controller`, how data is produced, buffered, transformed and
finally consumed by the Inference Module (IM) and Decision Module (DM) inside
`TigerBrain`. It does not describe RL theory or the MDP definition (see
`drl_description.md` in the same repo for that) — it is strictly about the
data path: where samples come from, at what rate, through which buffers, and
how flow-level data and packet-level data differ in production behavior.

---

## 1. Two independent producers feeding one consumer

The controller has **two physically independent data-production pipelines**
that converge into the same per-`Flow` object, and a **third, separate**
pipeline for node telemetry. All three are read once per "tick" by
`TigerBrain.process_input`.

```
                    POX OpenFlow switch
                    /                  \
     (A) pull: periodic                (B) push: async PacketIn
     flow-stats request                events from sampling rules
            |                                  |
   FlowStatsReceived event             SmartSwitch._handle_openflow_PacketIn
            |                          (reason == OFPR_ACTION)
   FlowLogger.process_received_flow    FlowLogger.cache_unprocessed_packets
            |                                  |
   flow.flow_feat_circular_buffer      flow.packet_feat_circular_buffer
   (sliding window, 10000 cap)         (sticky last-packet slot)
                                              + flow.pending_packet_feats
                                              (FIFO queue, burst absorber)
                                                    |
                    \                             /
                     \                           /
                TigerBrain.process_input (tight loop, no sleep)
                     |
            stack_flow_tensors -> Batch(flow_features, packet_features, node_features)
                     |
            get_labels (mutates DynamicLabelEncoder / knowledge base)
                     |
            push_to_replay_buffers (per-class RawReplayBuffer, FIFO, cap 10000)
                     |
       +-------------+--------------------------+
       |                                         |
  online_inference (IM forward pass,        train_inf_module_single_batch
  DM act_on_known_traffic /                 (gradient step, samples ONLY
  act_on_unknown_clusters)                   from replay buffers)


           (C) node telemetry, Kafka, fully decoupled cadence
     attacker/victim health_monitor.py --(Kafka topic per node)--> ConsumerThread
                                                  |
                                  MetricsLogger.metrics_dict[ip][metric]
                                  (deque, maxlen = node_features_time_window)
                                                  |
                                  get_metrics_tensor() pulled at tick time
```

---

## 2. Pipeline A — flow-level statistics (pull-based, periodic)

* **Trigger:** `tiger_server.periodically_requests_stats(FLOWSTATS_FREQ_SECS)`
  runs in its own daemon thread. Every `flowstats_freq_secs` (default **5s**,
  config requires `> 1`), it sends `ofp_stats_request` (flow stats + port
  stats) to every connected OpenFlow switch. The sleep is done in 0.1s
  increments so the thread can react quickly to shutdown, but the *request
  rate itself* is governed purely by this one knob.
* **Arrival:** the switch answers asynchronously; POX fires
  `FlowStatsReceived`, handled by `FlowLogger._handle_flowstats_received` ->
  `process_received_flow` for each reported flow.
* **Filtering/labelling:** a flow stats record is only processed if its
  `(src_ip, dst_ip)` matches an entry in `traffic_dict` (i.e. it is traffic
  between two nodes the experiment knows about). The flow is labelled with
  `traffic_dict[hostname]['pattern']` as `element_class`, and `zda`/`test_zda`
  flags are derived live from `current_knowledge['G1s']`/`G2s']` — **not**
  stored statically, since the curriculum mutates as the DM buys CTI.
* **Feature extraction:** `extract_flow_feature_tensor` builds a 4-dim vector
  `[byte_count, duration_nsec/1e10, duration_sec, packet_count]`
  (`flow_feat_dim: 4`).
* **Storage — sliding window, not a queue:** each new flow-stats vector is
  pushed into `flow.flow_feat_circular_buffer`, a `CircularBuffer` of fixed
  capacity `replay_buffer_max_capacity` (default **10000**) implemented with
  `torch.roll` (oldest row evicted, newest appended at the tail — O(buffer
  size) per insert, not O(1), since the whole tensor is rolled). At
  consumption time, only the **last `flows_per_sample` rows** (default
  **10**) are read via `get_flow_features()` — this 10-row window is what
  feeds the IM's recurrent (GRU) encoder, i.e. a short, fixed-length history
  of the flow's stat evolution at flow-stats-polling resolution
  (10 polls × 5s ≈ last 50 seconds of that flow's stats by default).
* **One row per flow per refresh, no fan-out:** unlike packet data, flow
  feature production is exactly 1:1 with the polling cadence — a flow whose
  stats haven't refreshed since the last poll just contributes the same
  (stale) sliding window again; there's no separate "pending flow features"
  queue. The only place a flow contributes >1 batch row at a tick is via
  packet fan-out (see §3.4).

---

## 3. Pipeline B — packet-level sampling (push-based, bursty, event-driven)

Packet features are independent of, and produced at a different cadence
than, flow stats — this is the most consequential asymmetry in the system.

### 3.1 How packets get to the controller at all

`SmartSwitch.send_sampling_rules` (timer-driven, period
`switching_args.sampling_rate_seconds`, default **15s**) periodically
(re-)installs, per known flow, an OpenFlow rule whose actions include
`self.sampling_action = ofp_action_output(port=OFPP_CONTROLLER, max_len=packet_feat_dim)`
in addition to the normal forwarding actions. This rule is installed once
per flow (`flow_id not in self.sampling_rule_messages`) and hard-timed-out
after `switching_args.sampling_flow_hard_timeout` (default **1s**) — so for
roughly 1 second after each 15-second tick, the switch mirrors a copy of
every matching packet to the controller via `PacketIn` with
`reason == OFPR_ACTION`, on top of normal forwarding. Whether resampling is
even active is gated by the top-level `resample_packets` flag (default
`true`); if `false`, no sampling rule is ever installed and only whatever
packets originally triggered flow-rule installation are seen.

This means packet capture happens in **short, dense bursts**, not a steady
stream, and is **decoupled from `flowstats_freq_secs`** — many packets can
arrive within a fraction of one flow-stats interval, or none at all if the
1-second sampling window happens to miss traffic.

### 3.2 Feature extraction and anonymization

`SmartSwitch._handle_openflow_PacketIn`, on `reason == OFPR_ACTION`, calls
`FlowLogger.cache_unprocessed_packets` directly — this path bypasses all
routing/ARP/buffering logic entirely (explicitly "do NOT touch routing/ARP/
buffers"). `build_packet_tensor` then:
1. Takes the first `packet_feat_dim` raw bytes (default **64**) of the IP
   packet.
2. Zeroes IP header bytes 12–19 (source/dest address) — always anonymized.
3. If `anonymize_transport_ports: true` (default), zeroes the 4 bytes at the
   IHL-derived transport-port offset.
4. Converts to a `uint8`→`float32` tensor, right-padded with zeros if the
   packet is shorter than `packet_feat_dim`.

### 3.3 Two destinations for the same packet tensor

For every matching flow, the same extracted packet tensor is written to
**two different structures** with different semantics:
* `flow.packet_feat_circular_buffer.add(...)` — a sticky "last-known-packet"
  slot (same `CircularBuffer` mechanism as flow stats, but here used to hold
  a fallback value, read via `get_packet_features()`).
* `flow.queue_packet_feature(...)` — appends to `flow.pending_packet_feats`,
  a plain Python list acting as a FIFO burst-absorbing queue, bounded by
  `max_pending_packet_feats` (default **4096**); once full, additional
  captured packets for that flow are **dropped** (silently, logged at
  debug/no escalation) rather than the queue growing unbounded.

### 3.4 Consumption: fan-out and per-tick draining

`TigerBrain.stack_flow_tensors` is where packet data diverges most sharply
from flow data. For each flow, if `use_packet_feats`:
* `flow.drain_packet_feature_chunks(packets_per_sample, max_chunks=max_packet_samples_per_flow_per_tick)`
  pops up to `max_packet_samples_per_flow_per_tick` (default **32**)
  complete chunks of `packets_per_sample` (default **1**) packets each, in
  arrival order, leaving any remainder (an incomplete trailing chunk, or
  chunks beyond the cap) queued for the *next* tick. So a flow with a deep
  backlog drains gradually across several ticks rather than blowing up a
  single batch.
* **Each drained chunk becomes its own batch row**, all sharing the *same*
  (currently valid) `flow_feat_window` for that flow — i.e. one flow can
  contribute anywhere from 0 to 32 rows in a single tick depending purely on
  how many fresh packets it had queued, while still only contributing one
  set of flow-level stats.
* If nothing was freshly captured this tick (`packet_chunks` empty), the flow
  falls back to the sticky last-known packet (`get_packet_features()`) so it
  still contributes exactly **one** row — it is never starved of packet
  features even between sampling bursts.
* `row_flow_indices` records, for every output batch row, which input flow
  produced it — necessary downstream because, with packet fan-out, batch
  rows are **no longer 1:1 with `flows`**; labels, `flow_id`s, etc. must be
  re-expanded via this index (`get_labels`, `_record_flows_for_data_collection`).

**Net effect:** flow-feature production rate is fixed and rate-limited by
`flowstats_freq_secs`; packet-feature production rate is bursty, switch- and
traffic-driven, absorbed by a bounded queue, and rate-limited *downstream*
(per tick, per flow) by `max_packet_samples_per_flow_per_tick` rather than
at the point of capture.

---

## 4. Pipeline C — node telemetry (Kafka, separate cadence again)

Independent of both flow and packet pipelines: `health_monitor.py` (byte-
identical in `smartville_attacker` and `smartville_victim`) publishes
CPU/RAM/RTT/throughput probes to per-node Kafka topics every
`health.probe_frequency_seconds` (default **3s**). On the controller,
`MetricsLogger` spins up one `ConsumerThread` per topic; each thread polls
Kafka (`health.poll_timeout_seconds`, `health.max_failed_polls` govern how
patient/aggressive each poll loop is, and a topic consumer self-terminates
and deletes its topic after too many failed polls). Each metric received is
appended to `metrics_dict[topic_name][metric]`, a `deque(maxlen=health.node_features_time_window)`
(default window **10** samples) — i.e. a fixed-length rolling history per
metric per node, decoupled from both the flow-stats and packet-sampling
clocks.

At tick time, `brain_utils.get_metrics_tensor(metrics_dict, dest_ip, health_args)`
is called once per flow (keyed by the flow's *destination* IP) inside
`stack_flow_tensors`, producing a `[time_window, num_probe_metrics]` tensor;
if the destination IP has never reported (no Kafka messages seen yet), a
tensor of all `-1.0` of the same shape is substituted instead of failing.
This tensor is shared identically across however many packet-fanned rows
that single flow contributes in the tick (it is not itself time-sliced per
row).

---

## 5. The consumption tick: `TigerBrain.process_input`

* **Cadence:** `tiger_server.smart_check()` runs in a dedicated daemon thread
  as a **tight `while` loop with no sleep** — `process_input` is invoked as
  fast as the interpreter/lock allow, not on a fixed period. The only
  natural throttling is (a) `tiger_lock`, shared with the flow-stats-polling
  callback path, and (b) the fact that `process_input` is a no-op
  (`if len(flows) > 0`) whenever `flow_logger.flows_dict` is non-empty but
  nothing new has changed — it still re-stacks and re-pushes the *same*
  sliding-window data every iteration when no new packets/flow-stats have
  arrived in between, since `flows_dict` always reflects current state. This
  means inference/training step frequency is effectively bounded by CPU and
  lock contention, not by any configured "tick" knob.
* **Two construction paths**, chosen by `data_collection_mode`:
  - Normal path: `assembly_input_tensor` = `stack_flow_tensors` (tensors
    only) + `get_labels` (mutates `DynamicLabelEncoder`/knowledge base; **must
    not** run while `self._lock` is held — `add_class_to_knowledge_base` is
    itself `@thread_safe` and would deadlock on the same non-reentrant lock).
  - Data-collection path: same tensor assembly, but handed to
    `FlowDataRecorder.record(...)` instead of (or in addition to) training —
    see §6.
* **`_process_batch`** (shared by the live path and offline replay,
  `process_input_from_record`) does, under `self._lock`:
  1. `push_to_replay_buffers` — every row, split by encoded class label, is
     pushed into that class's `RawReplayBuffer` (plain Python list used as a
     fixed-capacity ring buffer, capacity = `replay_buffer_max_capacity`,
     default **10000**, FIFO overwrite, *not* prioritized — PER only applies
     to the DM's own transition memory, a separate structure in
     `replay_buffer.py`/`tiger_agents.py`).
  2. Gate: `batch_processing_allowed` only flips `True` once at least two
     classes' buffers each exceed `batch_size` (default **16**) samples AND
     at least one of those classes is in `current_knowledge['Knowns']`.
     Until then, samples are buffered but never used for inference/training.
  3. If allowed: `online_inference(batch)` (IM forward pass + DM
     accept/block/buy-CTI decisions, see `drl_description.md`), then
     `train_inf_module_single_batch()` (one gradient step).
  4. Step counter increments either per-tick (`agency=false`) or per DM
     decision (`agency=true`, incremented once per known-class group / per
     anomaly cluster inside `act_on_known_traffic` / `act_on_unknown_clusters`).

### 5.1 What `online_inference` actually samples

`online_inference` does **not** train on the raw online batch alone — it
calls `sample_from_replay_buffers(samples_per_class=batch_size, mode=INFERENCE)`
to draw a balanced auxiliary batch (k-shot "support" + query structure, via
`get_canonical_query_mask`, `k_shot=4` support rows per class) from the
**already-buffered**, historical per-class data, and merges it with the
fresh online batch (`merge_batches`) before the forward pass. The online
batch's rows are always treated as "query" (never as support).

### 5.2 What the training step samples

`train_inf_module_single_batch` is **fully decoupled from whatever the
current online batch contained** — it draws its own fresh balanced sample
from `sample_from_replay_buffers(mode=TRAINING)` and trains purely on that.
So the live flow/packet/node tensors only ever influence training
indirectly, by having been pushed into the per-class replay buffers some
tick(s) earlier.

---

## 6. Data-collection / offline-replay side-channel

When `intrusion_detection.data_collection_mode: true`, `TigerBrain` routes
every assembled batch additionally (or exclusively) through
`FlowDataRecorder`:

* Buffers per-sample tensors in memory; flushes a shard
  (`torch.save`) when **either** `data_collection_shard_size` (default
  **2000**) samples have accumulated **or**
  `data_collection_flush_interval_secs` (default **30s**) have elapsed since
  the last flush — whichever comes first.
* **Storage dtype asymmetry, by design:** `flow_features` are stored as
  `float32` (genuinely continuous: byte counts, durations);
  `packet_features` are stored as `uint8` (raw byte values 0–255, lossless,
  4x smaller) — and converted back to `float32` only at replay time
  (`process_input_from_record`), matching what the live path always fed the
  classifier.
* Only the ground-truth `element_class` string is persisted — never
  `zda`/`test_zda`, since those are functions of the *running experiment's*
  curriculum state at capture time, not a fact about the traffic; they are
  recomputed from whatever curriculum the replaying run is configured with.
* `data_collection_skip_training: true` makes `process_input` return
  immediately after recording — a pure-capture run with no IM/DM compute at
  all (only the step counter still advances if `agency=false`).
* Offline replay (`process_input_from_record`) feeds previously recorded,
  already-grouped-by-tick shards through the exact same `_process_batch`
  used online, so a replay run sees what an online run would have seen for
  that tick.

---

## 7. A buffer that looks similar but is unrelated: switch-side routing buffer

`SmartSwitch.unprocessed_flows` (in `smart_switch.py`) is **not** part of the
ML data pipeline. It buffers raw OpenFlow packets that arrived before the
switch learned a route to their destination (`handle_unknown_ip_packet`),
bounded by `switching_args.max_buffered_packets` (default **5**, oldest
dropped first) and expired after `switching_args.max_buffering_secs`
(default **5s**) via a recurring `Timer(5, ...)`. It exists purely to avoid
dropping forwarding traffic while ARP resolves, and has no interaction with
`Flow`'s circular buffers, the replay buffers, or the IM/DM.

---

## 8. Summary of the production-speed knobs (all in `tiger/config/default.yaml` → `intrusion_detection` / `switching_args` / `health` unless noted)

| Knob | Default | Governs |
|---|---|---|
| `intrusion_detection.flowstats_freq_secs` | 5 | Controller→switch flow-stats poll period (flow-feature production rate) |
| `intrusion_detection.flows_per_sample` | 10 | Sliding-window length read from each flow's stat history per tick |
| `switching_args.sampling_rate_seconds` | 15 | How often packet-mirroring OpenFlow rules are (re)installed per flow |
| `switching_args.sampling_flow_hard_timeout` | 1 | How long each packet-mirroring rule stays active before expiring (burst window length) |
| `resample_packets` (top-level) | true | Whether packet mirroring happens at all |
| `intrusion_detection.packets_per_sample` | 1 | Packets consumed per drained packet-feature chunk |
| `intrusion_detection.max_packet_samples_per_flow_per_tick` | 32 | Caps batch-row fan-out per flow per tick from packet backlog |
| `intrusion_detection.max_pending_packet_feats` | 4096 | Caps the per-flow burst-absorbing packet queue (`Flow.pending_packet_feats`); excess captured packets dropped, not queued |
| `intrusion_detection.packet_feat_dim` | 64 | Bytes of raw packet kept per sample |
| `intrusion_detection.flow_feat_dim` | 4 | Flow-stat feature vector width |
| `intrusion_detection.replay_buffer_max_capacity` | 10000 | Capacity of both `Flow.*_circular_buffer`s and each per-class `RawReplayBuffer` |
| `intrusion_detection.batch_size` | 16 | Samples-per-class drawn for both online-aux and training batches; also the buffering gate threshold |
| `intrusion_detection.k_shot` | 4 | Support-set rows per class inside each sampled batch (query mask) |
| `switching_args.max_buffered_packets` / `max_buffering_secs` | 5 / 5 | Switch-side routing buffer (unrelated to ML pipeline, §7) |
| `health.probe_frequency_seconds` | 3 | Node telemetry publish rate (attacker/victim → Kafka) |
| `health.node_features_time_window` | 10 | Rolling window length kept per node metric on the controller |
| `intrusion_detection.data_collection_shard_size` / `data_collection_flush_interval_secs` | 2000 / 30 | Offline-capture shard flush thresholds |
| (no knob — busy loop) | n/a | `smart_check()`'s inference-tick rate has no period; it is an unthrottled `while` loop gated only by `tiger_lock` contention |
