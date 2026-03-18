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
    }


function syncParams() {
  const usePacketFeatsCheckbox = document.querySelector("input[name='packet_monitoring.use_packet_feats']");
  const packetBytesTextBox = document.querySelector("input[name='packet_monitoring.packet_feat_dim']");
  const secondStreamFeatureSizeTextBox = document.querySelector("input[name='neural_modules.second_stream_input_size']");
  const thirdStreamFeatureSizeTextBox = document.querySelector("input[name='neural_modules.third_stream_input_size']");
  const healthMonitoringCheckbox = document.querySelector("input[name='health_monitoring']");
  const metricsCheckboxes = document.querySelectorAll("input[name^='health.']");

  // uncheck all metric checkboxes when health_monitoring is unchecked
  if (!healthMonitoringCheckbox.checked) {
    metricsCheckboxes.forEach(cb => { cb.checked = false; });
  }

  const checkedCount = Array.from(metricsCheckboxes).filter(cb => cb.checked).length;

  if (usePacketFeatsCheckbox.checked) {
    if (healthMonitoringCheckbox.checked) {
      // three streams: flow | packet | health
      secondStreamFeatureSizeTextBox.value = packetBytesTextBox.value;
      thirdStreamFeatureSizeTextBox.value = checkedCount;
    } else {
      // two streams: flow | packet
      secondStreamFeatureSizeTextBox.value = packetBytesTextBox.value;
      thirdStreamFeatureSizeTextBox.value = 0;
    }
  } else {
    if (healthMonitoringCheckbox.checked) {
      // two streams: flow | health
      // shift — second takes whatever third was showing (health count)
      secondStreamFeatureSizeTextBox.value = thirdStreamFeatureSizeTextBox.value || checkedCount;
      thirdStreamFeatureSizeTextBox.value = 0;
    } else {
      // one stream: flow only
      secondStreamFeatureSizeTextBox.value = 0;
      thirdStreamFeatureSizeTextBox.value = 0;
    }
  }
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


    const WandBRunNameTextBox = document.getElementById("wandb-run-name-textbox");
    const WandBTrackCheckBox = document.getElementById("wandb-track-checkbox");

    
    var config = {};

    function updateConfigDict() {
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
        fetch("/launch_traffic", {
          method: "POST",
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            config_from_frontend: config
          })
        })
          .then(response => response.text())
          .then(data => logToConsole(data));
    });
    

    stopTrafficButton.addEventListener("click", function() {
        fetch("/stop_traffic", {method: "POST"})
          .then(response => response.text())
          .then(data => logToConsole(data));
    });

    startTrafficButtons.forEach(button => {
        button.addEventListener("click", function() {
            fetch("/launch_traffic_single", {
                method: "POST",
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                  hostname: button.id,
                  config_from_frontend: config 
                })
            })
            .then(response => response.text())
            .then(data => logToConsole(data));
        });
    });

    stopTrafficButtons.forEach(button => {
        button.addEventListener("click", function() {
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
        const wandbRunName = WandBRunNameTextBox.value;
        const wandbTrack = WandBTrackCheckBox.checked;
        fetch("/initialize_controller", {
            method: "POST",
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
              wandb_run_name: wandbRunName, 
              wandb_track: wandbTrack,
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