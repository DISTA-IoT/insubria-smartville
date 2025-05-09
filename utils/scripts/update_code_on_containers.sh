#!/bin/bash

# Replace this with your specific image name
TARGET_IMAGES=(
    "attacker:latest"
    "victim:latest"
    "pox-controller:latest"
    # Add more images as needed
)

for image in "${TARGET_IMAGES[@]}"; do
    echo "Processing containers with image: $image"

    # Get all container IDs that use the target image
    containers=$(docker ps -q --filter "ancestor=$image")

    # Check if any containers were found
    if [ -z "$containers" ]; then
        echo "No running containers found with image: $image"
        exit 0
    fi

    # Loop through each container and perform git pull
    for container in $containers; do
        container_name=$(docker inspect --format='{{.Name}}' "$container" | sed 's/\///')
        echo "Updating code in container $container_name ($container)..."
        docker exec -it "$container" /bin/bash -c 'git pull --rebase'
    done

    echo "All containers image $image updated successfully!"

done

echo "Update process complete for all images!"