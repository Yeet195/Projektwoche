#!/bin/bash
# Docker build and run script with installation check and systemd service registration

DETACHED=${1:-false}
SERVICE_NAME="docker-app"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
WRAPPER_SCRIPT="$SCRIPT_DIR/docker-service-wrapper.sh"

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

# Function to create wrapper script
create_wrapper_script() {
    echo "Creating wrapper script..."
    
    cat > "$WRAPPER_SCRIPT" << 'EOF'
#!/bin/bash
# Docker service wrapper script for systemd

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Function to cleanup on exit
cleanup() {
    echo "Stopping containers..."
    docker compose down
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Start containers
echo "Starting Docker containers..."
docker compose up -d

# Check if containers started successfully
if [ $? -ne 0 ]; then
    echo "Failed to start containers"
    exit 1
fi

echo "Containers started successfully"

# Keep the script running and monitor containers
while true; do
    # Check if any containers have stopped
    if ! docker compose ps --services --filter "status=running" | grep -q .; then
        echo "Some containers have stopped, restarting..."
        docker compose up -d
    fi
    sleep 30
done
EOF

    chmod +x "$WRAPPER_SCRIPT"
    echo "✓ Wrapper script created at $WRAPPER_SCRIPT"
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
Type=simple
Restart=always
RestartSec=10
User=root
WorkingDirectory=$SCRIPT_DIR
ExecStart=$WRAPPER_SCRIPT
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0
TimeoutStopSec=30

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
    
    # Wait a moment for service to start
    sleep 5
    
    # Check service status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "✓ Service '$SERVICE_NAME' is running successfully"
        echo "✓ Containers will automatically restart on crash/reboot"
        
        # Show service status
        echo ""
        echo "=== Service Status ==="
        sudo systemctl status "$SERVICE_NAME" --no-pager -l
    else
        echo "✗ Service failed to start. Check status with: sudo systemctl status $SERVICE_NAME"
        echo "Check logs with: sudo journalctl -u $SERVICE_NAME -f"
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

# Create wrapper script and systemd service
create_wrapper_script
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