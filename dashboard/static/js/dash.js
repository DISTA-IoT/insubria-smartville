window.addEventListener('DOMContentLoaded', (event) => {

    const refreshContainersButton = document.getElementById("refresh-containers");
    const startTrafficButton = document.getElementById("start-traffic");
    const stopTrafficButton = document.getElementById("stop-traffic");

    const createTopologyButton = document.getElementById("create-topology");
    const deleteProjectButton = document.getElementById("delete-project");

    const attachControllerButton = document.getElementById("attach-controller");
    const fixTrafficButton = document.getElementById("fix-traffic");

    const getLabelsButton = document.getElementById("get-labels");
    const getFlowrewardsButton = document.getElementById("get-flow-rewards");

    const getCurriculaButton = document.getElementById("get-curricula");


    const startExperimentButton = document.getElementById("start-experiment");
    const startMitigationButton = document.getElementById("start-mitigation");
    const stopMitigationButton = document.getElementById("stop-mitigation");
    

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
          .then(data => console.log(data));
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
          .then(response => response.text())
          .then(data => console.log(data));
    });
  
    fixTrafficButton.addEventListener("click", function() {
        fetch("/fix_traffic", {method: "POST"})
          .then(response => response.text())
          .then(data => console.log(data));
    });
  
  
    getLabelsButton.addEventListener("click", function() {
        fetch("/labels", {method: "GET"})
          .then(response => response.text())
          .then(data => console.log(data));
    });

    getFlowrewardsButton.addEventListener("click", function() {
        fetch("/flow_rewards", {method: "GET"})
          .then(response => response.text())
          .then(data => console.log(data));
    });
  
    getCurriculaButton.addEventListener("click", function() {
        fetch("/curricula", {method: "GET"})
          .then(response => response.text())
          .then(data => console.log(data));
    });
  
    startAttackButtons.forEach(button => {
        button.addEventListener("click", function() {
            fetch("/start-attack", {
                method: "POST",
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ vehicle_name: button.id })
            })
            .then(response => response.text())
            .then(data => console.log(data));
        });
    });
  
    stopAttackButtons.forEach(button => {
        button.addEventListener("click", function() {
            fetch("/stop-attack", {
                method: "POST",
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ vehicle_name: button.id,
                                        origin: "MANUALLY"
                                      })
            })
            .then(response => response.text())
            .then(data => console.log(data));
        });
    });
  
    startExperimentButton.addEventListener("click", function() {
      fetch("/start-experiment", {method: "POST"})
        .then(response => response.text())
        .then(data => console.log(data));
    });
  
  
    startMitigationButton.addEventListener("click", function() {
        fetch("/start-mitigation", {method: "POST"})
          .then(response => response.text())
          .then(data => console.log(data));
    });
    
    stopMitigationButton.addEventListener("click", function() {
        fetch("/stop-mitigation", {method: "POST"})
          .then(response => response.text())
          .then(data => console.log(data));
    });
    
  });