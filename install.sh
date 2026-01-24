#!/bin/bash

# Library App Installer for Ubuntu Server
# Supports: install, uninstall, update, status, config

set -e

# ============================================================================
# Configuration
# ============================================================================
APP_NAME="library-app"
APP_DIR="/opt/$APP_NAME"
CONFIG_FILE="/etc/$APP_NAME/config.env"
LOG_DIR="/var/log/$APP_NAME"
SERVICE_NAME="$APP_NAME"
UV_PATH=""

# ============================================================================
# Helper Functions
# ============================================================================
print_status() {
    echo -e "\033[1;34m==>\033[0m $1"
}

print_error() {
    echo -e "\033[1;31mError:\033[0m $1"
}

print_success() {
    echo -e "\033[1;32mSuccess:\033[0m $1"
}

print_warning() {
    echo -e "\033[1;33mWarning:\033[0m $1"
}

print_info() {
    echo -e "\033[0;36m    $1\033[0m"
}

confirm() {
    read -r -p "$1 [y/N]: " response
    case "$response" in
        [yY][eE][sS]|[yY]) return 0 ;;
        *) return 1 ;;
    esac
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run as root (use sudo)"
        exit 1
    fi
}

get_service_user() {
    # Use SUDO_USER if available, otherwise default to current user
    if [ -n "$SUDO_USER" ]; then
        echo "$SUDO_USER"
    else
        echo "$(whoami)"
    fi
}

# ============================================================================
# Prerequisites Check
# ============================================================================
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    local missing=()
    
    # Check Python 3.10+
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
        PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
        if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
            print_error "Python 3.10+ required, found $PYTHON_VERSION"
            missing+=("python3.10+")
        else
            print_info "Python $PYTHON_VERSION ✓"
        fi
    else
        print_error "Python 3 not found"
        missing+=("python3")
    fi
    
    # Check for uv (check for service user's installation)
    SERVICE_USER=$(get_service_user)
    SERVICE_USER_HOME=$(eval echo ~$SERVICE_USER)
    UV_PATH=""
    
    # Check in service user's local bin first
    if [ -f "$SERVICE_USER_HOME/.local/bin/uv" ]; then
        UV_PATH="$SERVICE_USER_HOME/.local/bin/uv"
    # Then check if uv is in PATH when running as service user
    elif sudo -u "$SERVICE_USER" command -v uv &> /dev/null; then
        UV_PATH=$(sudo -u "$SERVICE_USER" command -v uv)
    fi
    
    if [ -n "$UV_PATH" ]; then
        print_info "uv $($UV_PATH --version | head -1) ✓"
    else
        print_warning "uv not found for user $SERVICE_USER - will attempt to install"
        if confirm "Install uv for $SERVICE_USER now?"; then
            # Install as the service user, not as root
            sudo -u "$SERVICE_USER" bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
            UV_PATH="$SERVICE_USER_HOME/.local/bin/uv"
            if [ -f "$UV_PATH" ]; then
                print_success "uv installed to $UV_PATH"
            else
                print_error "Failed to install uv for $SERVICE_USER"
                exit 1
            fi
        else
            missing+=("uv")
        fi
    fi
    
    # Check for systemd
    if ! command -v systemctl &> /dev/null; then
        print_error "systemd not found - this script requires systemd"
        missing+=("systemd")
    else
        print_info "systemd ✓"
    fi
    
    # Check for curl (needed for downloads)
    if ! command -v curl &> /dev/null; then
        print_warning "curl not found - installing..."
        apt-get update && apt-get install -y curl
    fi
    print_info "curl ✓"
    
    if [ ${#missing[@]} -gt 0 ]; then
        print_error "Missing prerequisites: ${missing[*]}"
        exit 1
    fi
    
    print_success "All prerequisites met"
}

# ============================================================================
# Interactive Configuration
# ============================================================================
configure_interactive() {
    print_status "Configuration Setup"
    echo ""
    
    # Library path
    local default_library="/home/$(get_service_user)/library"
    read -r -p "Library path (where your ebooks are stored) [$default_library]: " LIBRARY_PATH
    LIBRARY_PATH="${LIBRARY_PATH:-$default_library}"
    
    # Validate library path
    if [ ! -d "$LIBRARY_PATH" ]; then
        if confirm "Directory $LIBRARY_PATH does not exist. Create it?"; then
            mkdir -p "$LIBRARY_PATH"
            chown "$(get_service_user):$(get_service_user)" "$LIBRARY_PATH"
            print_success "Created $LIBRARY_PATH"
        else
            print_error "Library path must exist"
            exit 1
        fi
    fi
    
    # Count ebooks
    EBOOK_COUNT=$(find "$LIBRARY_PATH" -type f \( -name "*.epub" -o -name "*.pdf" -o -name "*.mobi" \) 2>/dev/null | wc -l)
    print_info "Found $EBOOK_COUNT ebook(s) in library"
    
    # Port
    local default_port="26657"  # Spells 'BOOKS' on phone keypad
    read -r -p "Server port [$default_port]: " SERVER_PORT
    SERVER_PORT="${SERVER_PORT:-$default_port}"
    
    # Validate port
    if ! [[ "$SERVER_PORT" =~ ^[0-9]+$ ]] || [ "$SERVER_PORT" -lt 1 ] || [ "$SERVER_PORT" -gt 65535 ]; then
        print_error "Invalid port number"
        exit 1
    fi
    
    # Bind address
    local default_bind="0.0.0.0"
    read -r -p "Bind address (0.0.0.0 for all interfaces) [$default_bind]: " BIND_ADDRESS
    BIND_ADDRESS="${BIND_ADDRESS:-$default_bind}"
    
    # Download directory (for Anna's Archive downloads)
    read -r -p "Download directory for new books [$LIBRARY_PATH]: " DOWNLOAD_DIR
    DOWNLOAD_DIR="${DOWNLOAD_DIR:-$LIBRARY_PATH}"
    
    if [ ! -d "$DOWNLOAD_DIR" ]; then
        mkdir -p "$DOWNLOAD_DIR"
        chown "$(get_service_user):$(get_service_user)" "$DOWNLOAD_DIR"
    fi
    
    # Index rebuild interval
    local default_interval="300"
    read -r -p "Index rebuild interval in seconds (0 to disable) [$default_interval]: " INDEX_INTERVAL
    INDEX_INTERVAL="${INDEX_INTERVAL:-$default_interval}"
    
    echo ""
    print_status "Configuration Summary:"
    print_info "Library path:     $LIBRARY_PATH"
    print_info "Server port:      $SERVER_PORT"
    print_info "Bind address:     $BIND_ADDRESS"
    print_info "Download dir:     $DOWNLOAD_DIR"
    print_info "Index interval:   ${INDEX_INTERVAL}s"
    echo ""
    
    if ! confirm "Proceed with installation?"; then
        print_error "Installation cancelled"
        exit 1
    fi
}

# ============================================================================
# Save Configuration
# ============================================================================
save_config() {
    print_status "Saving configuration..."
    
    mkdir -p "$(dirname "$CONFIG_FILE")"
    
    cat > "$CONFIG_FILE" << EOL
# Library App Configuration
# Generated on $(date)

LIBRARY_PATH="$LIBRARY_PATH"
SERVER_PORT="$SERVER_PORT"
BIND_ADDRESS="$BIND_ADDRESS"
DOWNLOAD_DIR="$DOWNLOAD_DIR"
INDEX_INTERVAL="$INDEX_INTERVAL"
EOL
    
    chmod 644 "$CONFIG_FILE"
    print_success "Configuration saved to $CONFIG_FILE"
}

# ============================================================================
# Load Configuration
# ============================================================================
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
        return 0
    else
        print_error "Configuration file not found: $CONFIG_FILE"
        print_info "Run '$0 install' first"
        return 1
    fi
}

# ============================================================================
# Application Setup
# ============================================================================
setup_application() {
    print_status "Setting up application..."
    
    local SERVICE_USER=$(get_service_user)
    local SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Create app directory
    if [ -d "$APP_DIR" ]; then
        print_warning "Application directory exists, backing up..."
        mv "$APP_DIR" "$APP_DIR.backup.$(date +%Y%m%d%H%M%S)"
    fi
    
    mkdir -p "$APP_DIR"
    
    # Copy application files
    print_status "Copying application files..."
    cp -r "$SOURCE_DIR/app" "$APP_DIR/" 2>/dev/null || true
    cp -r "$SOURCE_DIR/anna_poc" "$APP_DIR/" 2>/dev/null || true
    
    # Set ownership before creating venv
    chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
    
    # Set up Python environment with uv
    print_status "Setting up Python environment with uv..."
    
    # Create virtual environment
    sudo -u "$SERVICE_USER" "$UV_PATH" venv "$APP_DIR/.venv"
    
    # Install the app package from the app/ subdirectory (has correct dependencies)
    if [ -d "$APP_DIR/app" ] && [ -f "$APP_DIR/app/pyproject.toml" ]; then
        sudo -u "$SERVICE_USER" "$UV_PATH" pip install --python "$APP_DIR/.venv/bin/python" -e "$APP_DIR/app"
    else
        print_error "app/pyproject.toml not found"
        exit 1
    fi
    
    # Install anna_poc if it exists
    if [ -d "$APP_DIR/anna_poc" ]; then
        sudo -u "$SERVICE_USER" "$UV_PATH" pip install --python "$APP_DIR/.venv/bin/python" -e "$APP_DIR/anna_poc"
    fi
    
    print_success "Application installed to $APP_DIR"
}

# ============================================================================
# Directory & Permissions Setup
# ============================================================================
setup_directories() {
    print_status "Setting up directories and permissions..."
    
    local SERVICE_USER=$(get_service_user)
    
    # Create log directory
    mkdir -p "$LOG_DIR"
    chown "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
    chmod 755 "$LOG_DIR"
    
    # Ensure library path is accessible
    if [ -d "$LIBRARY_PATH" ]; then
        # Check if readable
        if ! sudo -u "$SERVICE_USER" test -r "$LIBRARY_PATH"; then
            print_warning "Library path not readable by $SERVICE_USER, fixing permissions..."
            chmod +rx "$LIBRARY_PATH"
        fi
    fi
    
    # Ensure download directory is writable
    if [ -d "$DOWNLOAD_DIR" ]; then
        if ! sudo -u "$SERVICE_USER" test -w "$DOWNLOAD_DIR"; then
            print_warning "Download directory not writable by $SERVICE_USER, fixing permissions..."
            chown "$SERVICE_USER:$SERVICE_USER" "$DOWNLOAD_DIR"
            chmod 755 "$DOWNLOAD_DIR"
        fi
    fi
    
    print_success "Directories configured"
}

# ============================================================================
# Systemd Service Creation
# ============================================================================
create_services() {
    print_status "Creating systemd services..."
    
    local SERVICE_USER=$(get_service_user)
    local SERVICE_GROUP=$(id -gn "$SERVICE_USER")
    
    # Main web server service
    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOL
[Unit]
Description=Library App Web Server
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="LIBRARY_PATH=$LIBRARY_PATH"
Environment="DOWNLOAD_DIR=$DOWNLOAD_DIR"
EnvironmentFile=$CONFIG_FILE
ExecStart=$APP_DIR/.venv/bin/python -m app.server --port $SERVER_PORT --bind $BIND_ADDRESS
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_DIR/server.log
StandardError=append:$LOG_DIR/server.error.log

[Install]
WantedBy=multi-user.target
EOL

    # Index rebuild service (oneshot)
    cat > /etc/systemd/system/${SERVICE_NAME}-index.service << EOL
[Unit]
Description=Library App Index Rebuild
After=network.target

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="LIBRARY_PATH=$LIBRARY_PATH"
EnvironmentFile=$CONFIG_FILE
ExecStart=$APP_DIR/.venv/bin/python -m app.indexer --library "\$LIBRARY_PATH"
StandardOutput=append:$LOG_DIR/index.log
StandardError=append:$LOG_DIR/index.error.log
EOL

    # Index rebuild timer (if interval > 0)
    if [ "$INDEX_INTERVAL" -gt 0 ]; then
        cat > /etc/systemd/system/${SERVICE_NAME}-index.timer << EOL
[Unit]
Description=Library App Index Rebuild Timer

[Timer]
OnBootSec=30
OnUnitActiveSec=${INDEX_INTERVAL}s
Persistent=true

[Install]
WantedBy=timers.target
EOL
    fi
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable and start services
    systemctl enable ${SERVICE_NAME}.service
    systemctl start ${SERVICE_NAME}.service
    
    if [ "$INDEX_INTERVAL" -gt 0 ]; then
        systemctl enable ${SERVICE_NAME}-index.timer
        systemctl start ${SERVICE_NAME}-index.timer
    fi
    
    print_success "Systemd services created and started"
}

# ============================================================================
# Install
# ============================================================================
do_install() {
    print_status "Starting Library App Installation"
    echo ""
    
    check_root
    check_prerequisites
    configure_interactive
    save_config
    setup_application
    setup_directories
    create_services
    
    echo ""
    print_success "Installation complete!"
    echo ""
    print_status "Access your library at:"
    
    # Get server IP
    local SERVER_IP=$(hostname -I | awk '{print $1}')
    print_info "http://${SERVER_IP}:${SERVER_PORT}"
    print_info "http://localhost:${SERVER_PORT} (from this machine)"
    echo ""
    print_status "Useful commands:"
    print_info "sudo $0 status    - Check service status"
    print_info "sudo $0 config    - View/edit configuration"
    print_info "sudo $0 update    - Update the application"
    print_info "sudo $0 uninstall - Remove the application"
    echo ""
    print_status "Log files:"
    print_info "$LOG_DIR/server.log"
    print_info "$LOG_DIR/server.error.log"
}

# ============================================================================
# Uninstall
# ============================================================================
do_uninstall() {
    print_status "Uninstalling Library App"
    
    check_root
    
    if ! confirm "This will remove the application, services, and logs. Continue?"; then
        print_error "Uninstall cancelled"
        exit 1
    fi
    
    # Stop and disable services
    print_status "Stopping services..."
    systemctl stop ${SERVICE_NAME}.service 2>/dev/null || true
    systemctl stop ${SERVICE_NAME}-index.timer 2>/dev/null || true
    systemctl stop ${SERVICE_NAME}-index.service 2>/dev/null || true
    
    systemctl disable ${SERVICE_NAME}.service 2>/dev/null || true
    systemctl disable ${SERVICE_NAME}-index.timer 2>/dev/null || true
    
    # Remove service files
    print_status "Removing service files..."
    rm -f /etc/systemd/system/${SERVICE_NAME}.service
    rm -f /etc/systemd/system/${SERVICE_NAME}-index.service
    rm -f /etc/systemd/system/${SERVICE_NAME}-index.timer
    systemctl daemon-reload
    
    # Remove application directory
    if [ -d "$APP_DIR" ]; then
        if confirm "Remove application directory ($APP_DIR)?"; then
            rm -rf "$APP_DIR"
            print_info "Removed $APP_DIR"
        fi
    fi
    
    # Remove config
    if [ -f "$CONFIG_FILE" ]; then
        if confirm "Remove configuration ($CONFIG_FILE)?"; then
            rm -f "$CONFIG_FILE"
            rmdir "$(dirname "$CONFIG_FILE")" 2>/dev/null || true
            print_info "Removed configuration"
        fi
    fi
    
    # Remove logs
    if [ -d "$LOG_DIR" ]; then
        if confirm "Remove log files ($LOG_DIR)?"; then
            rm -rf "$LOG_DIR"
            print_info "Removed logs"
        fi
    fi
    
    print_success "Uninstallation complete"
    print_info "Note: Your library files were NOT removed"
}

# ============================================================================
# Update
# ============================================================================
do_update() {
    print_status "Updating Library App"
    
    check_root
    
    if ! load_config; then
        exit 1
    fi
    
    # Check prerequisites (sets UV_PATH)
    check_prerequisites
    
    local SERVICE_USER=$(get_service_user)
    local SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Stop services
    print_status "Stopping services..."
    systemctl stop ${SERVICE_NAME}.service 2>/dev/null || true
    
    # Backup current installation
    if [ -d "$APP_DIR" ]; then
        print_status "Backing up current installation..."
        cp -r "$APP_DIR" "$APP_DIR.backup.$(date +%Y%m%d%H%M%S)"
    fi
    
    # Update application files
    print_status "Updating application files..."
    cp -r "$SOURCE_DIR/app" "$APP_DIR/" 2>/dev/null || true
    cp -r "$SOURCE_DIR/anna_poc" "$APP_DIR/" 2>/dev/null || true
    
    # Update dependencies
    print_status "Updating dependencies..."
    cd "$APP_DIR"
    
    # Update app dependencies
    if [ -d "$APP_DIR/app" ] && [ -f "$APP_DIR/app/pyproject.toml" ]; then
        sudo -u "$SERVICE_USER" "$UV_PATH" pip install --python "$APP_DIR/.venv/bin/python" -e "$APP_DIR/app" --upgrade
    fi
    
    if [ -d "$APP_DIR/anna_poc" ]; then
        sudo -u "$SERVICE_USER" "$UV_PATH" pip install --python "$APP_DIR/.venv/bin/python" -e "$APP_DIR/anna_poc" --upgrade
    fi
    
    # Fix ownership
    chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
    
    # Restart services
    print_status "Restarting services..."
    systemctl start ${SERVICE_NAME}.service
    
    print_success "Update complete"
}

# ============================================================================
# Status
# ============================================================================
do_status() {
    print_status "Library App Status"
    echo ""
    
    # Service status
    print_status "Services:"
    if systemctl is-active --quiet ${SERVICE_NAME}.service; then
        print_success "Web server: running"
    else
        print_error "Web server: stopped"
    fi
    
    if [ -f /etc/systemd/system/${SERVICE_NAME}-index.timer ]; then
        if systemctl is-active --quiet ${SERVICE_NAME}-index.timer; then
            print_success "Index timer: running"
            NEXT_RUN=$(systemctl show ${SERVICE_NAME}-index.timer --property=NextElapseUSecRealtime --value)
            print_info "Next index rebuild: $NEXT_RUN"
        else
            print_warning "Index timer: stopped"
        fi
    else
        print_info "Index timer: not configured"
    fi
    
    echo ""
    
    # Configuration
    if load_config 2>/dev/null; then
        print_status "Configuration:"
        print_info "Library path:   $LIBRARY_PATH"
        print_info "Server port:    $SERVER_PORT"
        print_info "Bind address:   $BIND_ADDRESS"
        print_info "Download dir:   $DOWNLOAD_DIR"
        
        # Count ebooks
        if [ -d "$LIBRARY_PATH" ]; then
            EBOOK_COUNT=$(find "$LIBRARY_PATH" -type f \( -name "*.epub" -o -name "*.pdf" -o -name "*.mobi" \) 2>/dev/null | wc -l)
            print_info "Ebooks found:   $EBOOK_COUNT"
        fi
        
        echo ""
        
        # Access URL
        print_status "Access URL:"
        local SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
        if [ -n "$SERVER_IP" ]; then
            print_info "http://${SERVER_IP}:${SERVER_PORT}"
        fi
        print_info "http://localhost:${SERVER_PORT}"
    fi
    
    echo ""
    
    # Recent logs
    print_status "Recent log entries:"
    if [ -f "$LOG_DIR/server.log" ]; then
        tail -5 "$LOG_DIR/server.log" 2>/dev/null | while read line; do
            print_info "$line"
        done
    else
        print_info "No logs available"
    fi
    
    echo ""
    
    # Recent errors
    if [ -f "$LOG_DIR/server.error.log" ] && [ -s "$LOG_DIR/server.error.log" ]; then
        print_warning "Recent errors:"
        tail -3 "$LOG_DIR/server.error.log" 2>/dev/null | while read line; do
            print_info "$line"
        done
    fi
}

# ============================================================================
# Config
# ============================================================================
do_config() {
    print_status "Library App Configuration"
    echo ""
    
    if [ ! -f "$CONFIG_FILE" ]; then
        print_error "Configuration file not found"
        print_info "Run '$0 install' first"
        exit 1
    fi
    
    print_status "Current configuration ($CONFIG_FILE):"
    echo ""
    cat "$CONFIG_FILE"
    echo ""
    
    if confirm "Edit configuration?"; then
        # Use the user's preferred editor or nano
        ${EDITOR:-nano} "$CONFIG_FILE"
        
        print_status "Configuration updated"
        
        if confirm "Restart services to apply changes?"; then
            check_root
            
            # Reload config into services
            load_config
            
            # Recreate services with new config
            create_services
            
            print_success "Services restarted with new configuration"
        else
            print_warning "Remember to restart services to apply changes:"
            print_info "sudo systemctl restart ${SERVICE_NAME}.service"
        fi
    fi
}

# ============================================================================
# Help
# ============================================================================
show_help() {
    echo "Library App Installer"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  install     Install the application (interactive)"
    echo "  uninstall   Remove the application and services"
    echo "  update      Update to the latest version"
    echo "  status      Show service status and configuration"
    echo "  config      View or edit configuration"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  sudo $0 install"
    echo "  sudo $0 status"
    echo "  $0 config"
}

# ============================================================================
# Main
# ============================================================================
case "${1:-}" in
    install)
        do_install
        ;;
    uninstall)
        do_uninstall
        ;;
    update)
        do_update
        ;;
    status)
        do_status
        ;;
    config)
        do_config
        ;;
    help|--help|-h)
        show_help
        ;;
    "")
        show_help
        exit 1
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
