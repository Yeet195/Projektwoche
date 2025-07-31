#!/bin/bash

DETACHED=${1:-false}
SERVICE_NAME="docker-app"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

check_docker() {
    if ! command -v docker &> /dev/null; then
        return 1
    fi
    
    if ! docker info &> /dev/null; then
        return 1
    fi
    
    return 0
}

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID=$ID
        OS_NAME=$NAME
        OS_VERSION=$VERSION_ID
        OS_CODENAME=$VERSION_CODENAME
    elif type lsb_release >/dev/null 2>&1; then
        OS_ID=$(lsb_release -si | tr '[:upper:]' '[:lower:]')
        OS_NAME=$(lsb_release -si)
        OS_VERSION=$(lsb_release -sr)
        OS_CODENAME=$(lsb_release -sc)
    elif [ -f /etc/debian_version ]; then
        OS_ID="debian"
        OS_NAME="Debian"
        OS_VERSION=$(cat /etc/debian_version)
        case $OS_VERSION in
            12*) OS_CODENAME="bookworm" ;;
            11*) OS_CODENAME="bullseye" ;;
            10*) OS_CODENAME="buster" ;;
            *) OS_CODENAME="stable" ;;
        esac
    else
        echo "Unable to detect OS. This script supports Ubuntu and Debian only."
        exit 1
    fi
    
    echo "Detected OS: $OS_NAME ($OS_ID) $OS_VERSION"
}

install_docker() {
    echo "Docker not found or not running. Installing Docker..."

    detect_os

    case $OS_ID in
        ubuntu|debian)
            echo "Installing Docker for $OS_NAME..."
            ;;
        *)
            echo "Unsupported OS: $OS_NAME. This script supports Ubuntu and Debian only."
            exit 1
            ;;
    esac

    sudo apt-get remove docker docker-engine docker.io containerd runc -y 2>/dev/null || true

    sudo apt-get update

    sudo apt-get install -y ca-certificates curl gnupg lsb-release

    sudo install -m 0755 -d /etc/apt/keyrings

    curl -fsSL "https://download.docker.com/linux/$OS_ID/gpg" | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    if [ -z "$OS_CODENAME" ]; then
        if command -v lsb_release >/dev/null 2>&1; then
            OS_CODENAME=$(lsb_release -cs)
        else
            echo "Unable to determine OS codename. Please install lsb-release package."
            exit 1
        fi
    fi

    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$OS_ID \
        $OS_CODENAME stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update

    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    sudo usermod -aG docker $USER

    sudo systemctl start docker
    sudo systemctl enable docker
    
    echo "Docker installation completed!"
    echo "Note: You may need to log out and log back in for group changes to take effect."
    echo "Alternatively, you can run: newgrp docker"

    echo "Testing Docker installation..."
    if sudo docker run --rm hello-world > /dev/null 2>&1; then
        echo "Docker test successful!"
    else
        echo "Docker test failed. Please check the installation."
        exit 1
    fi
}

create_systemd_service() {
    echo "Creating systemd service for automatic container management..."
    
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Docker Application Service
Requires=docker.service
After=docker.service

[Service]
TimeoutStartSec=0
RemainAfterExit=yes
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
ExecReload=/usr/bin/docker compose restart
Restart=always
RestartSec=60
User=root

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    
    echo "Systemd service '$SERVICE_NAME' created and enabled."
    echo "Service will automatically start containers on boot and restart on failure."
}

manage_service() {
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "Stopping existing service..."
        sudo systemctl stop "$SERVICE_NAME"
    fi
    
    echo "Starting systemd service..."
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl start "$SERVICE_NAME"

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "Service '$SERVICE_NAME' is running successfully"
        echo "Containers will automatically restart on crash/reboot"
    else
        echo "Service failed to start. Check status with: sudo systemctl status $SERVICE_NAME"
        return 1
    fi
}

if ! check_docker; then
    install_docker
    if ! check_docker; then
        echo "Docker installation failed or Docker daemon is not running."
        echo "Please check the installation manually or start the Docker service."
        echo "You can try: sudo systemctl start docker"
        exit 1
    fi
fi

echo "Docker is available and running."

echo "Building Docker image..."
docker compose build --no-cache

create_systemd_service

echo "Starting Docker containers..."
if [ "$DETACHED" = true ]; then
    manage_service
else
    docker compose up
fi