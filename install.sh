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

# --- FUNCTIONS ---

install_base_dependencies() {
    echo -e "${YELLOW}>>> Installing System Dependencies...${PLAIN}"
    apt update -y
    apt install -y curl git
}

install_core_kharej() {
    echo -e "${CYAN}>>> Installing KHAREJ (Core) Components...${PLAIN}"
    apt install -y python3 python3-pip python3-venv qrencode
    
    # Setup Directory
    mkdir -p "$INSTALL_DIR"
    
    # Download Files
    echo -e "${CYAN}>>> Downloading files...${PLAIN}"
    git clone "$GITHUB_REPO" /tmp/outline_temp
    cp /tmp/outline_temp/*.py "$INSTALL_DIR/"
    rm -rf /tmp/outline_temp

    # Venv Setup
    echo -e "${YELLOW}>>> Setting up Python Environment...${PLAIN}"
    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install flask requests psutil qrcode

    # Configuration
    echo -e "\n${GREEN}--- CONFIGURATION ---${PLAIN}"
    echo -e "${CYAN}1. Enter Outline API URL (Management URL from Outline Manager app):${PLAIN}"
    read -p "> " outline_api

    echo -e "${CYAN}2. Enter YOUR IRAN DOMAIN (Tunnel Address):${PLAIN}"
    echo -e "${YELLOW}(Example: sub.myirandomain.com)${PLAIN}"
    read -p "> " tunnel_address

    # Create Config
cat > "$CONFIG_FILE" <<EOF
{
    "outline_api": "$outline_api",
    "tunnel_address": "$tunnel_address",
    "force_port": null,
    "subscription_domain": "$tunnel_address",
    "custom_suffix": "?prefix=%16%03%01%00%40%01%01"
}
EOF

    # Service
    echo -e "${YELLOW}>>> Creating Service...${PLAIN}"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Outline Manager Core Service
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

    # Shortcut
    echo "cd $INSTALL_DIR && ./venv/bin/python3 menu.py" > "/usr/bin/$SHORTCUT_CMD"
    chmod +x "/usr/bin/$SHORTCUT_CMD"

    echo -e "\n${GREEN}✔ KHAREJ SERVER INSTALLED SUCCESSFULLY!${PLAIN}"
    echo -e "Now go to your Iran server and install the 'Iran (Bridge)' mode."
    echo -e "Use command '${YELLOW}$SHORTCUT_CMD${PLAIN}' to open menu."
}

install_bridge_iran() {
    echo -e "${CYAN}>>> Installing IRAN (Bridge) Components...${PLAIN}"
    apt install -y nginx certbot python3-certbot-nginx

    echo -e "\n${GREEN}--- BRIDGE CONFIGURATION ---${PLAIN}"
    echo -e "${CYAN}1. Enter your Domain (e.g., sub.example.com):${PLAIN}"
    read -p "> " domain_name

    echo -e "${CYAN}2. Enter KHAREJ Server IP:${PLAIN}"
    read -p "> " kharej_ip

    echo -e "${CYAN}3. Enter your Email (for SSL):${PLAIN}"
    read -p "> " email_addr

    # Nginx Config
    echo -e "${YELLOW}>>> Configuring Nginx...${PLAIN}"
cat > "/etc/nginx/sites-available/$domain_name" <<EOF
server {
    listen 80;
    server_name $domain_name;

    location /getsub/ {
        proxy_pass http://$kharej_ip:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

    ln -s "/etc/nginx/sites-available/$domain_name" "/etc/nginx/sites-enabled/" 2>/dev/null
    rm /etc/nginx/sites-enabled/default 2>/dev/null
    nginx -t

    if [ $? -eq 0 ]; then
        systemctl reload nginx
        echo -e "${YELLOW}>>> Obtaining SSL Certificate...${PLAIN}"
        certbot --nginx -d "$domain_name" --non-interactive --agree-tos -m "$email_addr"
        echo -e "\n${GREEN}✔ IRAN SERVER CONFIGURED!${PLAIN}"
        echo -e "Your subscription link will be: https://$domain_name/getsub/..."
    else
        echo -e "${RED}✘ Nginx Config Failed! Check logs.${PLAIN}"
    fi
}

uninstall() {
    echo -e "${RED}WARNING: Removing Outline Manager...${PLAIN}"
    systemctl stop $SERVICE_NAME 2>/dev/null
    systemctl disable $SERVICE_NAME 2>/dev/null
    rm "$SERVICE_FILE" 2>/dev/null
    rm -rf "$INSTALL_DIR"
    rm "/usr/bin/$SHORTCUT_CMD" 2>/dev/null
    echo -e "${GREEN}Removed.${PLAIN}"
}

# --- MAIN MENU ---

install_base_dependencies

echo -e "\n${CYAN}========================================${PLAIN}"
echo -e "${CYAN}   OUTLINE MANAGER SETUP (SPLIT MODE)   ${PLAIN}"
echo -e "${CYAN}========================================${PLAIN}"
echo "1. Install on KHAREJ Server (Core & Manager)"
echo "2. Install on IRAN Server (Bridge & SSL)"
echo "3. Uninstall"
echo "0. Exit"
echo -e "${CYAN}----------------------------------------${PLAIN}"
read -p "Select Mode: " mode

case $mode in
    1) install_core_kharej ;;
    2) install_bridge_iran ;;
    3) uninstall ;;
    0) exit 0 ;;
    *) echo "Invalid option" ;;
esac