// ---------- In-GUI Console ----------

function logToConsole(message, level = "info") {
  const console_ = document.getElementById("gui-console-log");
  if (!console_) return;

  const now = new Date();
  const timestamp = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  const entry = document.createElement("div");
  entry.className = `console-entry console-${level}`;
  entry.innerHTML = `<span class="console-ts">[${timestamp}]</span> <span class="console-msg">${message}</span>`;
  console_.appendChild(entry);
  console_.scrollTop = console_.scrollHeight;

  // also keep browser console in sync
  if (level === "error") console.error(message);
  else console.log(message);
}

function clearConsole() {
  const c = document.getElementById("gui-console-log");
  if (c) c.innerHTML = "";
}

function toggleConsole() {
  const body = document.getElementById("gui-console-body");
  const toggle = document.getElementById("gui-console-toggle");
  if (body.style.display === "none") {
    body.style.display = "flex";
    toggle.textContent = "▼";
  } else {
    body.style.display = "none";
    toggle.textContent = "▲";
  }
}

// ---------- end Console ----------


function openTab(evt, tabId) {
      // Hide all tabs
      document.querySelectorAll(".tabcontent").forEach(tab => tab.style.display = "none");

      // Remove 'active' class from all tab buttons
      document.querySelectorAll(".tablink").forEach(btn => btn.classList.remove("active"));

      // Show the selected tab
      document.getElementById(tabId).style.display = "block";

      // Mark the clicked button as active
      evt.currentTarget.classList.add("active");

      // Only poll the controller for packet-queue stats while that tab is
      // actually open, so we don't hammer the controller in the background.
      if (tabId === "packetqueues") startPpfPolling();
      else stopPpfPolling();
    }


// ---------- Pending-packet-features utilisation gauges ----------

let ppfPollTimer = null;
const PPF_POLL_MS = 3000;
// Per-class {packet_count, t} from the previous poll, used to derive the
// consumption rate (packets/sec actually drained) client-side. This is the
// number that stays clearly non-zero under replay even while the pending
// queue reads ~0 -- i.e. the direct answer to "high packet counts but the
// queue looks empty".
const ppfPrev = {};

function ppfUtilColor(u) {
  // 0 -> red, 0.5 -> yellow, >=1 -> green. Matches the "red when empty,
  // green when full" convention requested for the gauges.
  const c = Math.max(0, Math.min(1, u));
  return `hsl(${(120 * c).toFixed(0)}, 75%, 42%)`;
}

function ppfFmtCount(n) {
  if (n === null || n === undefined) return "–";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(n);
}

function renderPendingPacketStats(data) {
  const statusEl = document.getElementById("ppf-status");
  const gaugesEl = document.getElementById("ppf-gauges");
  if (!statusEl || !gaugesEl) return;

  if (data.reachable === false) {
    statusEl.textContent = "controller unreachable";
    statusEl.className = "ppf-status err";
    gaugesEl.innerHTML = `<div class="ppf-empty">${data.msg || "Controller not reachable."}</div>`;
    return;
  }
  if (data.initialized === false) {
    statusEl.textContent = "controller not initialized";
    statusEl.className = "ppf-status warn";
    gaugesEl.innerHTML = `<div class="ppf-empty">Start an experiment to begin capturing packets.</div>`;
    return;
  }

  const classes = data.classes || {};
  const names = Object.keys(classes).sort();
  const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  statusEl.textContent = `live · ${names.length} class${names.length === 1 ? "" : "es"} · ${now}`;
  statusEl.className = "ppf-status ok";

  if (names.length === 0) {
    gaugesEl.innerHTML = `<div class="ppf-empty">No flows seen yet. Start traffic and wait for the first flow-stats poll.</div>`;
    return;
  }

  const nowMs = Date.now();
  const rows = names.map(name => {
    const c = classes[name];
    const bounded = c.utilization !== null && c.utilization !== undefined;
    const util = bounded ? c.utilization : 0;
    const peakUtil = bounded ? (c.peak_utilization || 0) : 0;
    const fillPct = (Math.max(0, Math.min(1, util)) * 100).toFixed(2);
    const peakPct = (Math.max(0, Math.min(1, peakUtil)) * 100).toFixed(2);
    const fillColor = ppfUtilColor(util);

    // Consumption rate (packets/sec drained) from the packet_count delta.
    const prev = ppfPrev[name];
    let rate = null;
    if (prev && nowMs > prev.t && c.packet_count >= prev.count) {
      rate = (c.packet_count - prev.count) / ((nowMs - prev.t) / 1000);
    }
    ppfPrev[name] = { count: c.packet_count, t: nowMs };
    // Dot = live activity: green while packets are actually being consumed,
    // grey when idle -- independent of the (usually low) instantaneous fill.
    const active = rate !== null && rate > 0;
    const dotColor = active ? "hsl(120,70%,40%)" : "#bbb";
    const rateTxt = rate === null ? "…"
                  : rate >= 1 ? `${ppfFmtCount(Math.round(rate))}/s`
                  : rate > 0 ? `${rate.toFixed(1)}/s` : "0/s";

    const capTxt = bounded ? ppfFmtCount(c.capacity) : "∞";
    const utilTxt = bounded ? (util * 100).toFixed(1) + "%" : "unbounded";
    const peakTxt = bounded ? (peakUtil * 100).toFixed(0) + "%" : "";
    const flowsTxt = c.num_flows > 1 ? ` · ${c.num_flows} flows` : "";

    const peakMarker = bounded
      ? `<div class="ppf-peak" style="left:${peakPct}%;" title="peak since last refresh: ${c.peak_pending}"></div>`
      : "";

    return `
      <div class="ppf-row">
        <div class="ppf-label">
          <span class="ppf-dot" style="background:${dotColor};" title="${active ? "consuming packets" : "idle"}"></span>
          <span class="ppf-class">${name}</span>
          <span class="ppf-nums">${ppfFmtCount(c.pending)} / ${capTxt}
            · peak ${ppfFmtCount(c.peak_pending)}${bounded ? " (" + peakTxt + ")" : ""}
            · ${rateTxt} consumed
            · Σ${ppfFmtCount(c.packet_count)}${flowsTxt}</span>
        </div>
        <div class="ppf-track" title="${utilTxt} full">
          <div class="ppf-fill" style="width:${fillPct}%; background:${fillColor};"></div>
          ${peakMarker}
        </div>
      </div>`;
  });

  gaugesEl.innerHTML = rows.join("");
}

function fetchPendingPacketStats() {
  fetch("/pending_packet_feats_stats")
    .then(r => r.json())
    .then(renderPendingPacketStats)
    .catch(err => renderPendingPacketStats({ reachable: false, msg: String(err) }));
}

function startPpfPolling() {
  if (ppfPollTimer) return;
  fetchPendingPacketStats();
  ppfPollTimer = setInterval(fetchPendingPacketStats, PPF_POLL_MS);
}

function stopPpfPolling() {
  if (ppfPollTimer) {
    clearInterval(ppfPollTimer);
    ppfPollTimer = null;
  }
}

// ---------- end pending-packet gauges ----------


// ---------- Per-node traffic speed knobs ----------
// The speed knob for a node is locked (disabled) while that node's traffic is
// running, so the user must stop the node to change its multiplier and then
// restart it -- the multiplier is only read at /replay time.

function nodeFromTrafficButtonId(id) {
  // e.g. "attacker-3_start_traffic" / "victim-0_stop_traffic" -> node name
  return id.replace(/_(start|stop)_traffic$/, "");
}

function speedKnobFor(node) {
  return document.getElementById(`${node}_speed`);
}

function nodeSpeedValue(node) {
  const knob = speedKnobFor(node);
  return knob ? knob.value : undefined;
}

// { hostname: value } for every knob, for the "start all" path.
function collectNodeSpeeds() {
  const out = {};
  document.querySelectorAll(".speed-knob").forEach(knob => {
    out[knob.dataset.node] = knob.value;
  });
  return out;
}

function lockSpeedKnob(node, locked) {
  const knob = speedKnobFor(node);
  if (!knob) return;
  knob.disabled = locked;
  const label = knob.closest(".speed-knob-label");
  if (label) label.classList.toggle("locked", locked);
}

function lockAllSpeedKnobs(locked) {
  document.querySelectorAll(".speed-knob").forEach(knob => {
    knob.disabled = locked;
    const label = knob.closest(".speed-knob-label");
    if (label) label.classList.toggle("locked", locked);
  });
}

// ---------- end traffic speed knobs ----------


function syncRewardInputs(rewardId, newValue) {
  const slider = document.getElementById(`reward_slider_${rewardId}`);
  const number = document.getElementById(`reward_number_${rewardId}`);
  if (slider && slider.value !== String(newValue)) {
    slider.value = newValue;
  }
  if (number && number.value !== String(newValue)) {
    number.value = newValue;
  }
}

function syncParams() {
  const usePacketFeatsCheckbox = document.querySelector("input[name='use_packet_feats']");
  const packetBytesTextBox = document.querySelector("input[name='intrusion_detection.packet_feat_dim']");
  const secondStreamFeatureSizeTextBox = document.querySelector("input[name='neural_modules.second_stream_input_size']");
  const thirdStreamFeatureSizeTextBox = document.querySelector("input[name='neural_modules.third_stream_input_size']");
  const nodeFeaturesCheckbox = document.querySelector("input[name='node_features']");
  const healthMonitoringCheckbox = document.querySelector("input[name='health_monitoring']");
  const metricsCheckboxes = document.querySelectorAll("input[name^='health.probe_metrics.']");

  // uncheck all metric checkboxes when health_monitoring is unchecked
  if (!healthMonitoringCheckbox.checked) {
    metricsCheckboxes.forEach(cb => { cb.checked = false; });
  }

  const checkedCount = Array.from(metricsCheckboxes).filter(cb => cb.checked).length;

  if (usePacketFeatsCheckbox.checked) {
    if (nodeFeaturesCheckbox.checked) {
      // three streams: flow | packet | health
      secondStreamFeatureSizeTextBox.value = packetBytesTextBox.value;
      thirdStreamFeatureSizeTextBox.value = checkedCount;
    } else {
      // two streams: flow | packet
      secondStreamFeatureSizeTextBox.value = packetBytesTextBox.value;
      thirdStreamFeatureSizeTextBox.value = 0;
    }
  } else {
    if (nodeFeaturesCheckbox.checked) {
      // two streams: flow | health
      // shift — second takes whatever third was showing (health count)
      secondStreamFeatureSizeTextBox.value = checkedCount;
      thirdStreamFeatureSizeTextBox.value = 0;
    } else {
      // one stream: flow only
      secondStreamFeatureSizeTextBox.value = 0;
      thirdStreamFeatureSizeTextBox.value = 0;
    }
  }
}

const CONFIG_PARAM_HELP = {
  "smart_switch_log_level": "Log verbosity for the smart switch process.",
  "smart_controller_log_level": "Log verbosity for the smart controller process.",
  "flow_logger_log_level": "Log verbosity for flow logging components.",
  "health_monitoring": "Enable health probes and health-driven monitoring features.",
  "use_packet_feats": "Use packet-level features for intrusion-detection inputs.",
  "node_features": "Use health metrics as node features (requires health monitoring).",
  "resample_packets": "If enabled, periodically resample packets from flows; otherwise reuses initial packets.",
  "wandb.wb_tracking": "Track this run in Weights & Biases.",
  "wandb.wb_project_name": "W&B project name used when tracking is enabled.",
  "wandb.wb_run_name": "W&B run name used when tracking is enabled.",
  "wandb.plots": "Log plots to W&B.",
  "wandb.resource_monitor_interval_secs": "Interval (seconds) for system resource monitoring.",
  "switching_args.flow_idle_timeout": "Idle seconds after which inactive flows are deleted from switch flow tables.",
  "switching_args.arp_timeout": "Seconds before an ARP cache entry expires in the switch.",
  "switching_args.max_buffered_packets": "Max packets buffered while waiting for destination MAC resolution.",
  "switching_args.max_buffering_secs": "Max buffering time while waiting for destination MAC resolution.",
  "switching_args.arp_req_exp_secs": "Wait time before retrying ARP request to avoid ARP flooding.",
  "switching_args.sampling_rate_seconds": "Seconds between sampling rule installations when packet resampling is enabled.",
  "switching_args.sampling_flow_hard_timeout": "Hard timeout (seconds) for installed sampling rules.",
  "intrusion_detection.packets_per_sample": "Number of packets taken per flow sample when packet features are enabled.",
  "intrusion_detection.flows_per_sample": "Flow-statistics time-window length used to build feature vectors.",
  "neural_modules.dropout": "Dropout rate used in neural modules.",
  "intrusion_detection.save_models": "Overwrite and save trained models to disk.",
  "intrusion_detection.k_shot": "Support samples per class for k-shot learning.",
  "intrusion_detection.batch_size": "Training batch size.",
  "intrusion_detection.report_step_freq": "Frequency (steps) to print/report training progress.",
  "intrusion_detection.plot_step_freq": "Frequency (steps) to emit plots/visual diagnostics.",
  "intrusion_detection.online_eval_step_freq": "Frequency (steps) to run online evaluation.",
  "intrusion_detection.online_evaluation": "Enable online evaluation mode.",
  "intrusion_detection.online_evaluation_rounds": "Number of rounds for online evaluation.",
  "intrusion_detection.pretrained_inference": "Use pretrained inference modules for run-time decisions.",
  "intrusion_detection.agent": "Learning agent type (DQN/DDQN/DAI variants).",
  "intrusion_detection.multi_class": "Enable multiclass (instead of binary) classification behavior.",
  "intrusion_detection.automatic_cs_acceptance": "Automatically accept closed-set inference from decision module.",
  "intrusion_detection.boltzmann_sampling": "Use Boltzmann action sampling (DDQN uses epsilon-greedy unless enabled).",
  "intrusion_detection.update_target_freq": "Step interval to update the target model.",
  "intrusion_detection.actor_train_interval_steps": "Step interval to train actor/policy network.",
  "intrusion_detection.agency": "Enable management agent; disable to focus on inference module pretraining.",
  "intrusion_detection.use_per": "Use Prioritized Experience Replay (PER).",
  "intrusion_detection.per_alpha": "PER alpha parameter.",
  "intrusion_detection.per_beta": "PER beta parameter.",
  "intrusion_detection.use_soft_update": "Use soft update for the target model.",
  "intrusion_detection.tau": "Tau parameter for soft update.",
  "intrusion_detection.use_transition_model": "Use transition model for DAI agent.",
  "intrusion_detection.variational_tmodel": "Use variational transition model for DAI agent.",
  "intrusion_detection.epistemic_regularisation_factor": "Epistemic regularisation factor for DAI agent.",
  "intrusion_detection.transitionnet_kl_divergence_regularisation_factor": "KL divergence regularisation factor for DAI agent.",
  "intrusion_detection.variational_variational_transition_loss": "Use variational variational transition loss for DAI agent.",
  "intrusion_detection.leakyrelu_alpha": "LeakyReLU alpha parameter for DAI agent.",
  "intrusion_detection.entropy_reg_coefficient": "Entropy regularisation coefficient for DAI agent.",
  "intrusion_detection.temperature_for_action_sampling": "Temperature for action sampling for DAI agent.",
  "intrusion_detection.surrogate_policy_consistency": "Use surrogate policy consistency for DAI agent.",
  "intrusion_detection.use_critic_to_act": "Use critic to act for DAI agent.",
  "intrusion_detection.greedy_update": "Use greedy update.",
  "intrusion_detection.use_huber_cs": "Use Huber loss for closed-set classification.",
  "neural_modules.custom_inference_model_path": "If false, the names of inference modules (pretrained and to-save) are automatically generated.",
  "neural_modules.custom_classifier_path": "If custom_inference_model_path is true, this is the filename to the classifier module (without extension).",
  "neural_modules.custom_confidence_decoder_path": "If custom_inference_model_path is true, this is the filename to the confidence decoder module (without extension).",
  "intrusion_detection.confidence_strategy": "Strategy to compute inference module confidence scores.",
  "intrusion_detection.greedy_cti": "If True, the agent will perform CTI actions whenever possible on clusters. Otherwise it will use the agent for this actions.",
  "intrusion_detection.cti_period": "If different from -1, then the agent will perform CTI actions every n steps. Otherwise it will use the agent for this actions.",
  "intrusion_detection.price_decay": "Use price decay. (Decay's CTI_price by a gaussian factor (mean 0.7, std 0.4)",
};

function getHelpTextByName(name) {
  if (!name) return "TBD (to be defined).";
  if (CONFIG_PARAM_HELP[name]) return CONFIG_PARAM_HELP[name];
  if (name.startsWith("health.probe_metrics.")) return "Health metric included in node-feature probing.";
  if (name.startsWith("rewards.")) return "Reward weight applied to this traffic-management signal.";
  if (name.startsWith("intrusion_detection.")) return "TBD (to be defined).";
  if (name.startsWith("neural_modules.")) return "TBD (to be defined).";
  return "TBD (to be defined).";
}

function addConfigTooltips() {
  const labels = document.querySelectorAll("#config-form label");
  labels.forEach((label) => {
    if (label.querySelector(".config-help-icon")) return;
    const namedInput = label.querySelector("input[name], select[name], textarea[name]");
    if (!namedInput) return;

    const helpText = getHelpTextByName(namedInput.name);
    const helpIcon = document.createElement("span");
    helpIcon.className = "config-help-icon";
    helpIcon.textContent = "i";
    helpIcon.title = helpText;
    helpIcon.setAttribute("aria-label", helpText);
    helpIcon.setAttribute("role", "img");
    label.appendChild(helpIcon);
  });
}


// ---------- Knowledge drag & drop UI helpers ----------

// create a draggable tag element
function createTag(pattern) {
  const el = document.createElement('div');
  el.className = 'draggable-tag';
  el.draggable = true;
  el.dataset.pattern = pattern;
  el.textContent = pattern;
  el.style.padding = '4px 8px';
  el.style.margin = '4px';
  el.style.border = '1px solid #666';
  el.style.borderRadius = '6px';
  el.style.display = 'inline-block';
  el.addEventListener('dragstart', function(ev) {
    ev.dataTransfer.setData('text/plain', pattern);
    // small visual hint
    ev.dataTransfer.effectAllowed = 'move';
  });
  return el;
}

// allow drop
function allowDrop(ev) {
  ev.preventDefault();
}


// reads DOM zones and store JSON into hidden input
function syncHiddenKnowledge() {
  const knowns = Array.from(document.getElementById('known').children).map(c => c.dataset.pattern);
  const g1s = Array.from(document.getElementById('g1').children).map(c => c.dataset.pattern);
  const g2s = Array.from(document.getElementById('g2').children).map(c => c.dataset.pattern);

  const payload = {
    Knowns: knowns,
    G1s: g1s,
    G2s: g2s
  };
  document.getElementById('knowledge_json').value = JSON.stringify(payload);
  console.log(payload);
}


// handle drop into a dropzone
function onDrop(ev) {
  ev.preventDefault();
  const pattern = ev.dataTransfer.getData('text/plain');
  if (!pattern) return;
  const target = ev.currentTarget;
  // avoid duplicates
  if (![...target.children].some(c => c.dataset && c.dataset.pattern === pattern)) {
    const tag = createTag(pattern);
    target.appendChild(tag);
  }
  // if tag exists elsewhere, remove it from there
  document.querySelectorAll('.draggable-tag').forEach(t => {
    if (t !== null && t.dataset && t.dataset.pattern === pattern && t.parentElement !== target) {
      // remove the older one (we created a new copy)
      t.parentElement.removeChild(t);
    }
  });
  console.log('syncing knowledge');
  syncHiddenKnowledge();
}


// populate UI from initialKnowledge object
function renderKnowledgeUI(initialKnowledge) {
  // produce full list of patterns. try to use attack_patterns + bening_patterns if present
  let allPatterns = [];
  if (initialKnowledge.attack_patterns) allPatterns = allPatterns.concat(initialKnowledge.attack_patterns);
  if (initialKnowledge.bening_patterns) allPatterns = allPatterns.concat(initialKnowledge.bening_patterns);
  // ensure unique
  allPatterns = [...new Set(allPatterns)];

  // prepare dropzones
  const zones = {
    known: document.getElementById('known'),
    g1: document.getElementById('g1'),
    g2: document.getElementById('g2'),
    unassigned: document.getElementById('unassigned')
  };
  // clear
  Object.values(zones).forEach(z => { z.innerHTML = ''; z.addEventListener('dragover', allowDrop); z.addEventListener('drop', onDrop); });

  // place items according to initialKnowledge groups, otherwise into unassigned
  const placed = new Set();
  if (initialKnowledge.Knowns) {
    initialKnowledge.Knowns.forEach(p => {
      zones.known.appendChild(createTag(p)); placed.add(p);
    });
  }
  if (initialKnowledge.G1s) {
    initialKnowledge.G1s.forEach(p => {
      zones.g1.appendChild(createTag(p)); placed.add(p);
    });
  }
  if (initialKnowledge.G2s) {
    initialKnowledge.G2s.forEach(p => {
      zones.g2.appendChild(createTag(p)); placed.add(p);
    });
  }

  // remaining -> unassigned
  allPatterns.forEach(p => {
    if (!placed.has(p)) zones.unassigned.appendChild(createTag(p));
  });

  // fill hidden input initially
  syncHiddenKnowledge();
}





window.addEventListener('DOMContentLoaded', (event) => {

    const configForm = document.getElementById("config-form");

    const refreshContainersButton = document.getElementById("refresh-containers");
    const startTrafficButton = document.getElementById("start-traffic");
    const stopTrafficButton = document.getElementById("stop-traffic");

    const startTrafficButtons = Array.from(document.querySelectorAll('[id$="_start_traffic"]'));
    const stopTrafficButtons = Array.from(document.querySelectorAll('[id$="_stop_traffic"]'))

    const createTopologyButton = document.getElementById("create-topology");

    const attachControllerButton = document.getElementById("attach-controller");
    const checkTrafficButton = document.getElementById("check-traffic");

    const initControllerButton = document.getElementById("init-controller");
    const stopControllerButton = document.getElementById("stop-controller");

    const startMSButton = document.getElementById("start-services");
    const stopMSButton = document.getElementById("stop-services");

    const startZookeeperButton = document.getElementById("start-zookeeper");
    const stopZookeeperButton = document.getElementById("stop-zookeeper");

    const startKafkaButton = document.getElementById("start-kafka");
    const stopKafkaButton = document.getElementById("stop-kafka");

    const startPrometheusButton = document.getElementById("start-prometheus");
    const stopPrometheusButton = document.getElementById("stop-prometheus");

    const startGrafanaButton = document.getElementById("start-grafana");
    const stopGrafanaButton = document.getElementById("stop-grafana");
    const openGrafanaButton = document.getElementById("open-grafana");

    
    var config = {};

    function updateConfigDict() {
        console.log("updating config dict...");
        const formData = new FormData(configForm);
        config = {}; // reset

        // First handle all regular inputs (text, number, selects, checked checkboxes)
        formData.forEach((val, key) => {
            const keys = key.split('.');
            let curr = config;
            for (let i = 0; i < keys.length - 1; i++) {
                const k = keys[i];
                curr[k] = curr[k] || {};
                curr = curr[k];
            }
            curr[keys[keys.length - 1]] = val;
        });

        // Now explicitly handle ALL checkboxes (checked or not)
        const checkboxes = configForm.querySelectorAll('input[type="checkbox"]');
        checkboxes.forEach(cb => {
            const keys = cb.name.split('.');
            let curr = config;
            for (let i = 0; i < keys.length - 1; i++) {
                const k = keys[i];
                curr[k] = curr[k] || {};
                curr = curr[k];
            }
            curr[keys[keys.length - 1]] = cb.checked;
        });

        // parse knowledge_json hidden field and set config.knowledge to an object
        const knowledgeJSON = document.getElementById('knowledge_json')?.value;
        if (knowledgeJSON) {
          try {
            config.knowledge = JSON.parse(knowledgeJSON);
            console.log("updated knowledge:", config.knowledge);
          } catch (e) {
            console.error("Failed to parse knowledge_json", e);
          }
        }

    }

    configForm.addEventListener("submit", function(e) {
      e.preventDefault();
      updateConfigDict();
      logToConsole("Configuration Saved!", "info");
      // TODO: send config dict to backend with fetch/axios
    });
    

    syncParams();
    addConfigTooltips();

    updateConfigDict();

    

    // keep config dict fresh on any form field change (catches selects like log levels)
    configForm.addEventListener("change", function() {
        updateConfigDict();
    });

    if (typeof initialKnowledge !== 'undefined') {
        renderKnowledgeUI(initialKnowledge);
    }

    refreshContainersButton.addEventListener("click", function() {
        fetch("/refresh_containers", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });
  
    startTrafficButton.addEventListener("click", function() {
        // starting all nodes -> lock every knob and send the current values
        lockAllSpeedKnobs(true);
        fetch("/launch_traffic", {
          method: "POST",
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            config_from_frontend: config,
            speeds: collectNodeSpeeds()
          })
        })
          .then(response => response.text())
          .then(data => logToConsole(data));
    });


    stopTrafficButton.addEventListener("click", function() {
        lockAllSpeedKnobs(false);   // all stopped -> knobs editable again
        fetch("/stop_traffic", {method: "POST"})
          .then(response => response.text())
          .then(data => logToConsole(data));
    });

    startTrafficButtons.forEach(button => {
        button.addEventListener("click", function() {
            const node = nodeFromTrafficButtonId(button.id);
            lockSpeedKnob(node, true);   // running -> lock this node's knob
            fetch("/launch_traffic_single", {
                method: "POST",
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                  hostname: button.id,
                  config_from_frontend: config,
                  speed_multiplier: nodeSpeedValue(node)
                })
            })
            .then(response => response.text())
            .then(data => logToConsole(data));
        });
    });

    stopTrafficButtons.forEach(button => {
        button.addEventListener("click", function() {
            const node = nodeFromTrafficButtonId(button.id);
            lockSpeedKnob(node, false);   // stopped -> knob editable again
            fetch("/stop_traffic_single", {
                method: "POST",
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ hostname: button.id,
                                        origin: "MANUALLY"
                                        })
            })
            .then(response => response.text())
            .then(data => logToConsole(data));
        });
    });
  
    
    createTopologyButton.addEventListener("click", function() {
        fetch("/create_topology", {
          method: "POST",
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            config
          })
        })
          .then(response => response.text())
          .then(data => logToConsole(data));
    });
    

    attachControllerButton.addEventListener("click", function() {
        fetch("/attach_controller", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });
  
    checkTrafficButton.addEventListener("click", function() {
        fetch("/check_traffic", {method: "POST"})
          .then(response => response.text())
          .then(data => logToConsole(data));
    });
  
  
    initControllerButton.addEventListener("click", function() {
        updateConfigDict();
        fetch("/initialize_controller", {
            method: "POST",
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
              config_from_frontend: config
            })
        })
        .then(response => response.json())
        .then(data => logToConsole(data.msg));
    });

    stopControllerButton.addEventListener("click", function() {
        fetch("/stop_controller", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });


    startMSButton.addEventListener("click", function() {
        fetch("/start_services", {method: "POST"})
          .then(response => response.json())
          .then(data => {
            logToConsole(data.msg);
            openGrafanaButton.disabled = false;
            openGrafanaButton.classList.remove("disabled");
            openGrafanaButton.classList.add("blue");
          });
    });

    stopMSButton.addEventListener("click", function() {
        fetch("/stop_services", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });


    startZookeeperButton.addEventListener("click", function() {
        fetch("/start_zookeeper", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });

    stopZookeeperButton.addEventListener("click", function() {
        fetch("/stop_zookeeper", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });


    startKafkaButton.addEventListener("click", function() {
        fetch("/start_kafka", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });

    stopKafkaButton.addEventListener("click", function() {
        fetch("/stop_kafka", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });


    startPrometheusButton.addEventListener("click", function() {
        fetch("/start_prometheus", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });

    stopPrometheusButton.addEventListener("click", function() {
        fetch("/stop_prometheus", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });


    startGrafanaButton.addEventListener("click", function() {
        fetch("/start_grafana", {method: "POST"})
          .then(response => response.json())
          .then(data => {
            logToConsole(data.msg);
            openGrafanaButton.disabled = false;
            openGrafanaButton.classList.remove("disabled");
            openGrafanaButton.classList.add("blue");
          });
    });

    stopGrafanaButton.addEventListener("click", function() {
        fetch("/stop_grafana", {method: "POST"})
          .then(response => response.json())
          .then(data => logToConsole(data.msg));
    });
    

  });
