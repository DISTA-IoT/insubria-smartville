window.addEventListener('DOMContentLoaded', (event) => {

    const refreshContainersButton = document.getElementById("refresh-containers");
    const startTrafficButton = document.getElementById("start-traffic");
    const stopTrafficButton = document.getElementById("stop-traffic");

    const createTopologyButton = document.getElementById("create-topology");
    const deleteProjectButton = document.getElementById("delete-project");

    const attachControllerButton = document.getElementById("attach-controller");
    const checkTrafficButton = document.getElementById("check-traffic");

    const initControllerButton = document.getElementById("init-controller");
    const stopControllerButton = document.getElementById("stop-controller");

    const startMSButton = document.getElementById("start-services");
    const stopMSButton = document.getElementById("stop-services");



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
          .then(data => alert(data.msg));
    });

    stopMSButton.addEventListener("click", function() {
        fetch("/stop_services", {method: "POST"})
          .then(response => response.json())
          .then(data => alert(data.msg));
    });

    /*
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
   */

    
  });