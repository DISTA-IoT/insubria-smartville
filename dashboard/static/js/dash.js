window.addEventListener('DOMContentLoaded', (event) => {

    const refreshContainersButton = document.getElementById("refresh-containers");
    const startTrafficButton = document.getElementById("start-traffic");
    const stopTrafficButton = document.getElementById("stop-traffic");

    const startTrafficButtons = Array.from(document.querySelectorAll('[id$="_start_traffic"]'));
    const stopTrafficButtons = Array.from(document.querySelectorAll('[id$="_stop_traffic"]'))

    const createTopologyButton = document.getElementById("create-topology");
    const deleteProjectButton = document.getElementById("delete-project");

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


    refreshContainersButton.addEventListener("click", function() {
        fetch("/refresh_containers", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });
  
    startTrafficButton.addEventListener("click", function() {
        fetch("/launch_traffic", {method: "POST"})
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
                body: JSON.stringify({ hostname: button.id })
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
        fetch("/create-topology", {method: "POST"})
          .then(response => response.text())
          .then(data => console.log(data));
    });
  
    deleteProjectButton.addEventListener("click", function() {
        fetch("/delete-project", {method: "POST"})
          .then(response => response.text())
          .then(data => console.log(data));
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
        fetch("/initialize_controller", {method: "POST"})
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

    openGrafanaButton.addEventListener("click", function() {
        fetch("/open_grafana", {method: "GET"})
          .then(response => response.json())
          .then(data => log(data.msg));
    });
    
  });