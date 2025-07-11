#!/bin/bash
# Complete Docker and service uninstall script

SERVICE_NAME="docker-app"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "=== Docker and Service Complete Uninstall Script ==="
echo "This will remove:"
echo "- All Docker containers (running and stopped)"
echo "- All Docker images"
echo "- All Docker volumes"
echo "- All Docker networks"
echo "- Docker Engine and all components"
echo "- Systemd service '$SERVICE_NAME'"
echo "- Docker configuration files"
echo ""

read -p "Are you sure you want to proceed? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

echo "Starting uninstall process..."

# Stop and remove systemd service
echo "=== Removing systemd service ==="
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Stopping service '$SERVICE_NAME'..."
    sudo systemctl stop "$SERVICE_NAME"
fi

if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "Disabling service '$SERVICE_NAME'..."
    sudo systemctl disable "$SERVICE_NAME"
fi

if [ -f "$SERVICE_FILE" ]; then
    echo "Removing service file '$SERVICE_FILE'..."
    sudo rm "$SERVICE_FILE"
    sudo systemctl daemon-reload
    echo "Systemd service removed"
else
    echo "Service file not found, skipping..."
fi

# Stop all running containers
echo "=== Stopping all Docker containers ==="
if command -v docker &> /dev/null; then
    RUNNING_CONTAINERS=$(docker ps -q)
    if [ -n "$RUNNING_CONTAINERS" ]; then
        echo "Stopping running containers..."
        docker stop $RUNNING_CONTAINERS
        echo "All containers stopped"
    else
        echo "No running containers found"
    fi

    # Remove all containers
    echo "=== Removing all Docker containers ==="
    ALL_CONTAINERS=$(docker ps -a -q)
    if [ -n "$ALL_CONTAINERS" ]; then
        echo "Removing all containers..."
        docker rm $ALL_CONTAINERS
        echo "All containers removed"
    else
        echo "No containers found"
    fi

    # Remove all images
    echo "=== Removing all Docker images ==="
    ALL_IMAGES=$(docker images -q)
    if [ -n "$ALL_IMAGES" ]; then
        echo "Removing all images..."
        docker rmi -f $ALL_IMAGES
        echo "All images removed"
    else
        echo "No images found"
    fi

    # Remove all volumes
    echo "=== Removing all Docker volumes ==="
    ALL_VOLUMES=$(docker volume ls -q)
    if [ -n "$ALL_VOLUMES" ]; then
        echo "Removing all volumes..."
        docker volume rm $ALL_VOLUMES
        echo "All volumes removed"
    else
        echo "No volumes found"
    fi

    # Remove all networks (except default ones)
    echo "=== Removing Docker networks ==="
    CUSTOM_NETWORKS=$(docker network ls --filter type=custom -q)
    if [ -n "$CUSTOM_NETWORKS" ]; then
        echo "Removing custom networks..."
        docker network rm $CUSTOM_NETWORKS
        echo "Custom networks removed"
    else
        echo "No custom networks found"
    fi

    # Clean up any remaining Docker resources
    echo "=== Cleaning up Docker system ==="
    docker system prune -a -f --volumes
    echo "Docker system cleaned"
else
    echo "Docker command not found, skipping container/image cleanup..."
fi

# Stop Docker service
echo "=== Stopping Docker service ==="
if systemctl is-active --quiet docker; then
    sudo systemctl stop docker
    echo "Docker service stopped"
fi

if systemctl is-active --quiet docker.socket; then
    sudo systemctl stop docker.socket
    echo "Docker socket stopped"
fi

# Remove Docker packages
echo "=== Removing Docker packages ==="
sudo apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras
sudo apt-get purge -y docker docker-engine docker.io containerd runc
sudo apt-get autoremove -y
sudo apt-get autoclean
echo "Docker packages removed"

# Remove Docker directories and files
echo "=== Removing Docker directories and files ==="
sudo rm -rf /var/lib/docker
sudo rm -rf /var/lib/containerd
sudo rm -rf /etc/docker
sudo rm -rf /var/run/docker.sock
sudo rm -rf /usr/local/bin/docker-compose
sudo rm -rf ~/.docker

# Remove Docker group
if getent group docker > /dev/null 2>&1; then
    echo "Removing docker group..."
    sudo groupdel docker
    echo "Docker group removed"
fi

# Remove Docker repository
echo "=== Removing Docker repository ==="
sudo rm -f /etc/apt/sources.list.d/docker.list
sudo rm -f /etc/apt/keyrings/docker.asc
sudo rm -f /etc/apt/keyrings/docker.gpg
sudo apt-get update
echo "Docker repository removed"

# Remove any remaining Docker processes
echo "=== Cleaning up remaining processes ==="
sudo pkill -f docker
sudo pkill -f containerd

# Check for any remaining Docker-related packages
echo "=== Checking for remaining Docker packages ==="
REMAINING_PACKAGES=$(dpkg -l | grep -i docker | awk '{print $2}')
if [ -n "$REMAINING_PACKAGES" ]; then
    echo "Found remaining Docker packages:"
    echo "$REMAINING_PACKAGES"
    echo "Removing them..."
    sudo apt-get purge -y $REMAINING_PACKAGES
    echo "Remaining packages removed"
else
    echo "No remaining Docker packages found"
fi

echo ""
echo "=== Uninstall Complete ==="
echo "All Docker containers, images, volumes, and networks removed"
echo "Docker Engine and all components uninstalled"
echo "Systemd service '$SERVICE_NAME' removed"
echo "Docker configuration files deleted"
echo "Docker repository removed"
echo "Docker group removed"
echo ""
echo "Note: You may want to reboot your system to ensure all changes take effect."
echo "If you had any custom applications or data in Docker volumes, they have been permanently deleted."