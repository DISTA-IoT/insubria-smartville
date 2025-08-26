#!/bin/bash

BRANCH=$1

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

    # Loop through each container and switch to the branch
    for container in $containers; do
        container_name=$(docker inspect --format='{{.Name}}' "$container" | sed 's/\///')
        echo "Switching to branch $BRANCH in container $container_name ($container)..."
        docker exec -it "$container" /bin/bash -c "git fetch"
        docker exec -it "$container" /bin/bash -c "git checkout $BRANCH"
    done

    echo "All containers image $image switched successfully!"

done

echo "Swithce to branch process complete for all images!"
