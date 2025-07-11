#!/bin/bash
# Docker build and run script with installation check

DETACHED=${1:-false}

check_docker() {
    if ! command -v docker &> /dev/null; then
        return 1
    fi
    
    if ! docker info &> /dev/null; then
        return 1
    fi
    
    return 0
}

# Function to install Docker
install_docker() {
    echo "Docker not found or not running. Installing Docker..."

    sudo apt-get remove docker docker-engine docker.io containerd runc -y
    sudo apt-get update
    sudo apt-get install ca-certificates curl gnupg lsb-release -y

    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    sudo apt-get update
    sudo apt-get install docker-ce docker-ce-cli containerd.io docker-compose-plugin -y
    sudo usermod -aG docker $USER
    
    echo "Docker installation completed!"
    echo "Note: You may need to log out and log back in for group changes to take effect."
    echo "Alternatively, you can run: newgrp docker"

    echo "Testing Docker installation..."
    docker pull node:22-alpine
    docker run -it --rm --entrypoint sh node:22-alpine -c "echo 'Docker is working!'"
}

if ! check_docker; then
    install_docker
    if ! check_docker; then
        echo "Docker installation failed or Docker daemon is not running."
        echo "Please check the installation manually or start the Docker service."
        exit 1
    fi
fi

echo "Docker is available and running."

echo "Building Docker image..."
docker compose build --no-cache

echo "Starting Docker containers..."
if [ "$DETACHED" = true ]; then
    docker compose up -d
else
    docker compose up
fi