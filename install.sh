#!/bin/bash

# ===================================================
#      OUTLINE MANAGER - INSTALLATION SCRIPT
#              Author: B3hnamR
# ===================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
PLAIN='\033[0m'

# Config
INSTALL_DIR="/opt/outline-manager"
SERVICE_NAME="outline-manager"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
GITHUB_REPO="https://github.com/B3hnamR/OutlineManager" 
DB_FILE="$INSTALL_DIR/users.db"
CONFIG_FILE="$INSTALL_DIR/config.json"
SHORTCUT_CMD="outline"

# Check Root
[[ $EUID -ne 0 ]] && echo -e "${RED}Error: This script must be run as root!${PLAIN}" && exit 1

clear

install_dependencies() {
    echo -e "${YELLOW}>>> Installing System Dependencies...${PLAIN}"
    apt update -y
    apt install -y python3 python3-pip python3-venv git curl nginx qrencode
    echo -e "${GREEN}>>> Dependencies Installed.${PLAIN}"
}

setup_environment() {
    echo -e "${YELLOW}>>> Setting up Directory & Virtual Environment...${PLAIN}"
    
    if [ ! -d "$INSTALL_DIR" ]; then
        mkdir -p "$INSTALL_DIR"
    fi

    # Download or Copy Files
    if [ -f "manager.py" ] && [ -f "menu.py" ]; then
        echo -e "${CYAN}>>> Copying local files...${PLAIN}"
        cp manager.py menu.py "$INSTALL_DIR/"
    else
        echo -e "${CYAN}>>> Downloading files from GitHub...${PLAIN}"
        git clone "$GITHUB_REPO" /tmp/outline_temp
        cp /tmp/outline_temp/*.py "$INSTALL_DIR/"
        rm -rf /tmp/outline_temp
    fi

    # Create Venv
    if [ ! -d "$INSTALL_DIR/venv" ]; then
        python3 -m venv "$INSTALL_DIR/venv"
    fi

    # Install Python Libs
    echo -e "${YELLOW}>>> Installing Python Libraries...${PLAIN}"
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install flask requests psutil qrcode
}

configure_project() {
    echo -e "${YELLOW}>>> Configuring Project...${PLAIN}"
    
    if [ -f "$CONFIG_FILE" ]; then
        read -p "Config file exists. Overwrite? (y/n): " overwrite
        if [[ "$overwrite" != "y" ]]; then return; fi
    fi

    echo -e "${CYAN}Enter Outline API URL (Management URL):${PLAIN}"
    read -p "> " outline_api

    echo -e "${CYAN}Enter Server IP (Tunnel Address):${PLAIN}"
    read -p "> " tunnel_address

    echo -e "${CYAN}Enter Subscription Domain (e.g., example.com):${PLAIN}"
    read -p "> " sub_domain

    # Create config.json with Optimized Prefix
cat > "$CONFIG_FILE" <<EOF
{
    "outline_api": "$outline_api",
    "tunnel_address": "$tunnel_address",
    "force_port": null,
    "subscription_domain": "$sub_domain",
    "custom_suffix": "?prefix=%16%03%01%00%40%01%01"
}
EOF
    echo -e "${GREEN}>>> Config saved!${PLAIN}"
}

create_service() {
    echo -e "${YELLOW}>>> Creating Systemd Service...${PLAIN}"
    
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Outline Manager Service
After=network.target

[Service]
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/manager.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    systemctl restart $SERVICE_NAME
    echo -e "${GREEN}>>> Service Started & Enabled!${PLAIN}"
}

create_shortcut() {
    echo "cd $INSTALL_DIR && ./venv/bin/python3 menu.py" > "/usr/bin/$SHORTCUT_CMD"
    chmod +x "/usr/bin/$SHORTCUT_CMD"
}

print_summary() {
    echo -e "\n${GREEN}=======================================${PLAIN}"
    echo -e "${GREEN}      INSTALLATION COMPLETE! 🚀      ${PLAIN}"
    echo -e "${GREEN}=======================================${PLAIN}"
    echo -e "${CYAN}Installation Path:${PLAIN} $INSTALL_DIR"
    echo -e "${CYAN}Service Name:${PLAIN}      $SERVICE_NAME"
    echo -e "${CYAN}Config File:${PLAIN}       $CONFIG_FILE"
    echo -e "${CYAN}Command to Run:${PLAIN}    ${YELLOW}$SHORTCUT_CMD${PLAIN}"
    echo -e "${GREEN}=======================================${PLAIN}"
    
    echo -e "${YELLOW}NOTE:${PLAIN} If you use Nginx for subscription link (port 80),"
    echo -e "ensure you have added the 'location /getsub/' proxy block to Nginx."
}

full_install() {
    install_dependencies
    setup_environment
    configure_project
    create_service
    create_shortcut
    print_summary
}

uninstall() {
    echo -e "${RED}WARNING: This will remove Outline Manager.${PLAIN}"
    read -p "Keep database backup? (y/n): " keep_db
    
    if [[ "$keep_db" == "y" ]]; then
        if [ -f "$DB_FILE" ]; then
            cp "$DB_FILE" "/root/users_backup_$(date +%F).db"
            echo -e "${GREEN}Database backed up to /root/users_backup_...db${PLAIN}"
        fi
    fi

    systemctl stop $SERVICE_NAME
    systemctl disable $SERVICE_NAME
    rm "$SERVICE_FILE"
    systemctl daemon-reload
    
    rm -rf "$INSTALL_DIR"
    rm "/usr/bin/$SHORTCUT_CMD"
    
    echo -e "${GREEN}>>> Uninstallation Complete.${PLAIN}"
}

# --- Menu ---

show_menu() {
    echo -e "\n${CYAN}--- OUTLINE MANAGER INSTALLER ---${PLAIN}"
    echo "1. Install / Update"
    echo "2. Edit Config"
    echo "3. Restart Service"
    echo "4. View Logs"
    echo "5. Uninstall"
    echo "0. Exit"
    echo -e "${CYAN}-------------------------------${PLAIN}"
    read -p "Select: " choice

    case $choice in
        1) full_install ;;
        2) nano "$CONFIG_FILE" && systemctl restart $SERVICE_NAME ;;
        3) systemctl restart $SERVICE_NAME && echo -e "${GREEN}Restarted.${PLAIN}" ;;
        4) journalctl -u $SERVICE_NAME -n 50 -f ;;
        5) uninstall ;;
        0) exit 0 ;;
        *) echo "Invalid option" ;;
    esac
}

# Run
if [ "$1" == "install" ]; then
    full_install
elif [ "$1" == "uninstall" ]; then
    uninstall
else
    show_menu
fi