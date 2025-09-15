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
  const healthParams = {};
  metricsCheckboxes.forEach(cb => {
      healthParams[cb.name] = cb.checked;
  });
  const checkedCount = Array.from(metricsCheckboxes).filter(cb => cb.checked).length;

  console.log(`healthMonitoringCheckbox.checked: ${healthMonitoringCheckbox.checked}`);
  console.log("Health parameters:", healthParams);
  console.log(`Number of checked health parameters: ${checkedCount}`);
  console.log(`usePacketFeatsCheckbox.checked: ${usePacketFeatsCheckbox.checked}`);
  console.log(`packetBytesTextBox.value: ${packetBytesTextBox.value}`);


  if(usePacketFeatsCheckbox.checked){
    if(healthMonitoringCheckbox.checked){
      // three steams.
      // first stream: flow features 
      // second stream: packet features
      // third stream: health features
      secondStreamFeatureSizeTextBox.enabled = true;
      thirdStreamFeatureSizeTextBox.enabled = true;
      secondStreamFeatureSizeTextBox.value = packetBytesTextBox.value;
      thirdStreamFeatureSizeTextBox.value = checkedCount;
    }
    else{
      // two steams.
      // first stream: flow features 
      // second stream: packet features
      secondStreamFeatureSizeTextBox.enabled = true;
      thirdStreamFeatureSizeTextBox.enabled = false;
      secondStreamFeatureSizeTextBox.value = packetBytesTextBox.value;
      thirdStreamFeatureSizeTextBox.value = 0;
    }
  }else{
    if(healthMonitoringCheckbox.checked){
      // two steams.
      // first stream: flow features 
      // second stream: health features
      secondStreamFeatureSizeTextBox.enabled = true;
      thirdStreamFeatureSizeTextBox.enabled = false;
      secondStreamFeatureSizeTextBox.value = checkedCount;
      thirdStreamFeatureSizeTextBox.value = 0;
    }
    else{
      // one steam.
      // first stream: flow features 
      secondStreamFeatureSizeTextBox.enabled = false;
      thirdStreamFeatureSizeTextBox.enabled = false;
      secondStreamFeatureSizeTextBox.value = 0;
      thirdStreamFeatureSizeTextBox.value = 0;
    }
  }
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
    }

    configForm.addEventListener("submit", function(e) {
      e.preventDefault();
      updateConfigDict();
      alert("Configuration Saved!!");
      // TODO: send config dict to backend with fetch/axios
    });

    updateConfigDict();

    refreshContainersButton.addEventListener("click", function() {
        fetch("/refresh_containers", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
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
          .then(data => alert(data));
    });
    

    stopTrafficButton.addEventListener("click", function() {
        fetch("/stop_traffic", {method: "POST"})
          .then(response => response.text())
          .then(data => alert(data));
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
            .then(data => alert(data));
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
            .then(data => alert(data));
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
          .then(data => alert(data));
    });
    

    attachControllerButton.addEventListener("click", function() {
        fetch("/attach_controller", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });
  
    checkTrafficButton.addEventListener("click", function() {
        fetch("/check_traffic", {method: "POST"})
          .then(response => response.text())
          .then(data => alert(data));
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
        .then(data => alert(data.msg));
    });

    stopControllerButton.addEventListener("click", function() {
        fetch("/stop_controller", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });


    startMSButton.addEventListener("click", function() {
        fetch("/start_services", {method: "POST"})
          .then(response => response.json())
          .then(data => {
            alert(data.msg);
            openGrafanaButton.disabled = false;
            openGrafanaButton.classList.remove("disabled");
            openGrafanaButton.classList.add("blue");
          }
          );
    });

    stopMSButton.addEventListener("click", function() {
        fetch("/stop_services", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });


    startZookeeperButton.addEventListener("click", function() {
        fetch("/start_zookeeper", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });

    stopZookeeperButton.addEventListener("click", function() {
        fetch("/stop_zookeeper", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });


    startKafkaButton.addEventListener("click", function() {
        fetch("/start_kafka", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });

    stopKafkaButton.addEventListener("click", function() {
        fetch("/stop_kafka", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });


    startPrometheusButton.addEventListener("click", function() {
        fetch("/start_prometheus", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });

    stopPrometheusButton.addEventListener("click", function() {
        fetch("/stop_prometheus", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });


    startGrafanaButton.addEventListener("click", function() {
        fetch("/start_grafana", {method: "POST"})
          .then(response => response.json())
          .then(data => {
            alert(data.msg);
            openGrafanaButton.disabled = false;
            openGrafanaButton.classList.remove("disabled");
            openGrafanaButton.classList.add("blue");
          });
    });

    stopGrafanaButton.addEventListener("click", function() {
        fetch("/stop_grafana", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });
    
    

  });