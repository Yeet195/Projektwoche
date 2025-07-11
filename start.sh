#!/bin/bash
# Docker build and run script with installation check and systemd service registration

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

# Function to install Docker
install_docker() {
    echo "Docker not found or not running. Installing Docker..."

    sudo apt-get remove docker docker-engine docker.io containerd runc -y
    sudo apt-get update
    sudo apt-get install ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update

    sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
    
    echo "Docker installation completed!"
    echo "Note: You may need to log out and log back in for group changes to take effect."
    echo "Alternatively, you can run: newgrp docker"

    echo "Testing Docker installation..."
    docker pull node:22-alpine
    docker run -it --rm --entrypoint sh node:22-alpine -c "echo 'Docker is working!'"
}

# Function to create systemd service
create_systemd_service() {
    echo "Creating systemd service for automatic container management..."
    
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Docker Application Service
Requires=docker.service
After=docker.service
StartLimitIntervalSec=0

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
ExecReload=/usr/bin/docker compose restart
Restart=on-failure
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and enable the service
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    
    echo "Systemd service '$SERVICE_NAME' created and enabled."
    echo "Service will automatically start containers on boot and restart on failure."
}

# Function to manage systemd service
manage_service() {
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "Stopping existing service..."
        sudo systemctl stop "$SERVICE_NAME"
    fi
    
    echo "Starting systemd service..."
    sudo systemctl start "$SERVICE_NAME"
    
    # Check service status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "✓ Service '$SERVICE_NAME' is running successfully"
        echo "✓ Containers will automatically restart on crash/reboot"
    else
        echo "✗ Service failed to start. Check status with: sudo systemctl status $SERVICE_NAME"
        return 1
    fi
}

if ! check_docker; then
    install_docker
    if ! check_docker; then
        echo "Docker installation failed or Docker daemon is not running."
        echo "Please check the installation manually or start the Docker service."
        echo "Installation instructions can be found at: https://docs.docker.com/engine/install/ubuntu/"
        exit 1
    fi
fi

echo "Docker is available and running."

echo "Building Docker image..."
docker compose build --no-cache

# Create systemd service
create_systemd_service

echo "Starting Docker containers..."
if [ "$DETACHED" = true ]; then
    # Use systemd service for detached mode
    manage_service
else
    # Run interactively for non-detached mode
    docker compose up
fi

echo ""
echo "=== Service Management Commands ==="
echo "Check status:    sudo systemctl status $SERVICE_NAME"
echo "Stop service:    sudo systemctl stop $SERVICE_NAME"
echo "Start service:   sudo systemctl start $SERVICE_NAME"
echo "Restart service: sudo systemctl restart $SERVICE_NAME"
echo "View logs:       sudo journalctl -u $SERVICE_NAME -f"
echo "Disable service: sudo systemctl disable $SERVICE_NAME"
echo "Remove service:  sudo systemctl disable $SERVICE_NAME && sudo rm $SERVICE_FILE && sudo systemctl daemon-reload"