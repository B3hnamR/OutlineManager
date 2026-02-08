#!/bin/bash
set -e

# ===================================================
#      OUTLINE MANAGER - SMART INSTALLER
#              Author: B3hnamR
# ===================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
PLAIN='\033[0m'

# Paths & Vars
INSTALL_DIR="/opt/outline-manager"
SERVICE_NAME="outline-manager"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
GITHUB_REPO="https://github.com/B3hnamR/OutlineManager" 
DB_FILE="$INSTALL_DIR/users.db"
CONFIG_FILE="$INSTALL_DIR/config.json"
SHORTCUT_CMD="outline"
INFO_FILE="$INSTALL_DIR/.install_info"

# Check Root
[[ $EUID -ne 0 ]] && echo -e "${RED}Error: This script must be run as root!${PLAIN}" && exit 1

clear

install_base_dependencies() {
    # Ensure nano is installed
    echo -e "${YELLOW}>>> Checking System Dependencies...${PLAIN}"
    if ! command -v git &> /dev/null || ! command -v curl &> /dev/null || ! command -v nano &> /dev/null; then
        apt update -y > /dev/null 2>&1
        apt install -y curl git nano > /dev/null 2>&1
    fi
}

install_core_kharej() {
    echo -e "${CYAN}>>> Installing KHAREJ (Core) Components...${PLAIN}"
    apt update -y
    apt install -y python3 python3-pip python3-venv qrencode
    
    mkdir -p "$INSTALL_DIR"
    
    echo -e "${CYAN}>>> Downloading files...${PLAIN}"
    git clone "$GITHUB_REPO" /tmp/outline_temp
    cp /tmp/outline_temp/*.py "$INSTALL_DIR/"
    rm -rf /tmp/outline_temp

    if [ ! -d "$INSTALL_DIR/venv" ]; then
        echo -e "${YELLOW}>>> Setting up Python Environment...${PLAIN}"
        python3 -m venv "$INSTALL_DIR/venv"
        "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
        "$INSTALL_DIR/venv/bin/pip" install flask requests psutil qrcode
    fi

    echo -e "\n${GREEN}--- CONFIGURATION ---${PLAIN}"
    if [ -f "$CONFIG_FILE" ]; then
        echo -e "${YELLOW}Config file already exists. Skipping creation.${PLAIN}"
    else
        echo -e "${CYAN}1. Enter Outline API URL (Management URL):${PLAIN}"
        read -p "> " outline_api
        echo -e "${CYAN}2. Enter YOUR IRAN DOMAIN (Tunnel Address):${PLAIN}"
        read -p "> " tunnel_address

        cat > "$CONFIG_FILE" <<EOF
{
    "outline_api": "$outline_api",
    "tunnel_address": "$tunnel_address",
    "force_port": null,
    "subscription_domain": "$tunnel_address",
    "custom_suffix": "?prefix=%16%03%01%00%40%01%01"
}
EOF
    fi

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

    echo "cd $INSTALL_DIR && ./venv/bin/python3 menu.py" > "/usr/bin/$SHORTCUT_CMD"
    chmod +x "/usr/bin/$SHORTCUT_CMD"

    echo "TYPE=core" > "$INFO_FILE"

    echo -e "\n${GREEN}✔ KHAREJ SERVER INSTALLED SUCCESSFULLY!${PLAIN}"
    echo -e "Use command '${YELLOW}$SHORTCUT_CMD${PLAIN}' to open the menu."
}

install_bridge_iran() {
    echo -e "${CYAN}>>> Installing IRAN (Bridge) Components...${PLAIN}"
    apt update -y
    apt install -y nginx certbot python3-certbot-nginx

    mkdir -p "$INSTALL_DIR"

    echo -e "\n${GREEN}--- BRIDGE CONFIGURATION ---${PLAIN}"
    echo -e "${CYAN}1. Enter your Domain (e.g., sub.example.com):${PLAIN}"
    read -p "> " domain_name

    echo -e "${CYAN}2. Enter KHAREJ Server IP:${PLAIN}"
    read -p "> " kharej_ip

    echo -e "${CYAN}3. Enter your Email (for SSL):${PLAIN}"
    read -p "> " email_addr

    rm -f /etc/nginx/sites-enabled/default

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

    ln -sf "/etc/nginx/sites-available/$domain_name" "/etc/nginx/sites-enabled/"
    if nginx -t; then
        systemctl reload nginx
        echo -e "${YELLOW}>>> Obtaining SSL Certificate...${PLAIN}"
        certbot --nginx -d "$domain_name" --non-interactive --agree-tos -m "$email_addr"
        
        echo "TYPE=bridge" > "$INFO_FILE"
        echo "DOMAIN=$domain_name" >> "$INFO_FILE"
        
        echo -e "\n${GREEN}✔ IRAN SERVER CONFIGURED!${PLAIN}"
        echo -e "Your subscription link will be: https://$domain_name/getsub/..."
    else
        echo -e "${RED}✘ Nginx Config Failed! Check logs.${PLAIN}"
    fi
}

uninstall() {
    if [ -f "$INFO_FILE" ]; then source "$INFO_FILE"; else if [ -f "$SERVICE_FILE" ]; then TYPE="core"; else TYPE="bridge"; fi; fi

    echo -e "${RED}WARNING: You are about to uninstall Outline Manager ($TYPE mode).${PLAIN}"
    read -p "Are you sure? (y/n): " confirm
    if [[ "$confirm" != "y" ]]; then return; fi

    if [ "$TYPE" == "core" ]; then
        echo -e "${YELLOW}>>> Removing Core Components...${PLAIN}"
        read -p "Keep database backup? (y/n): " keep_db
        if [[ "$keep_db" == "y" ]] && [ -f "$DB_FILE" ]; then
            cp "$DB_FILE" "/root/users_backup_$(date +%F).db"
            echo -e "${GREEN}Database backed up.${PLAIN}"
        fi
        systemctl stop $SERVICE_NAME 2>/dev/null || true
        systemctl disable $SERVICE_NAME 2>/dev/null || true
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
        rm -f "/usr/bin/$SHORTCUT_CMD"
        rm -rf "$INSTALL_DIR"
        
    elif [ "$TYPE" == "bridge" ]; then
        echo -e "${YELLOW}>>> Removing Bridge Components...${PLAIN}"
        if [ -z "$DOMAIN" ]; then read -p "Enter the domain to clean up (leave empty if unknown): " DOMAIN; fi
        if [ ! -z "$DOMAIN" ]; then
            certbot delete --cert-name "$DOMAIN" --non-interactive 2>/dev/null || true
            rm -f "/etc/nginx/sites-enabled/$DOMAIN"
            rm -f "/etc/nginx/sites-available/$DOMAIN"
            systemctl reload nginx || true
            echo -e "${GREEN}Removed Nginx config for $DOMAIN${PLAIN}"
        fi
        rm -rf "$INSTALL_DIR"
    fi
    echo -e "${GREEN}>>> Uninstall Complete.${PLAIN}"
    exit 0
}

edit_config() {
    if [ -f "$CONFIG_FILE" ]; then
        nano "$CONFIG_FILE"
        echo -e "${YELLOW}>>> Restarting Service...${PLAIN}"
        systemctl restart $SERVICE_NAME
        echo -e "${GREEN}>>> Done.${PLAIN}"
    else
        echo -e "${RED}Config file not found!${PLAIN}"
    fi
}

show_manage_menu() {
    TYPE="unknown"
    [ -f "$INFO_FILE" ] && source "$INFO_FILE"
    if [ "$TYPE" == "unknown" ]; then if [ -f "$SERVICE_FILE" ]; then TYPE="core"; else TYPE="bridge"; fi; fi

    while true; do
        echo -e "\n${CYAN}--- MANAGER MENU ($TYPE) ---${PLAIN}"
        if [ "$TYPE" == "core" ]; then
            echo "1. Edit Config & Restart"
            echo "2. View Service Logs"
            echo "3. Restart Service"
            echo "4. Update Scripts"
            echo "5. Uninstall"
        elif [ "$TYPE" == "bridge" ]; then
            echo "1. Re-configure Nginx/SSL"
            echo "5. Uninstall"
        fi
        echo "0. Exit"
        echo -e "${CYAN}----------------------------${PLAIN}"
        read -p "Select: " choice

        if [ "$TYPE" == "core" ]; then
            case $choice in
                1) edit_config ;;
                2) journalctl -u $SERVICE_NAME -n 50 -f ;;
                3) systemctl restart $SERVICE_NAME && echo -e "${GREEN}Restarted.${PLAIN}" ;;
                4) 
                    echo -e "${YELLOW}Updating...${PLAIN}"
                    git clone "$GITHUB_REPO" /tmp/outline_update
                    cp /tmp/outline_update/*.py "$INSTALL_DIR/"
                    rm -rf /tmp/outline_update
                    systemctl restart $SERVICE_NAME
                    echo -e "${GREEN}Updated.${PLAIN}"
                    ;;
                5) uninstall ;;
                0) exit 0 ;;
                *) echo "Invalid choice";;
            esac
        elif [ "$TYPE" == "bridge" ]; then
            case $choice in
                1) install_bridge_iran ;; 
                5) uninstall ;;
                0) exit 0 ;;
                *) echo "Invalid choice";;
            esac
        fi
        echo -e "${YELLOW}Press Enter to continue...${PLAIN}"
        read
        clear
    done
}

show_install_menu() {
    clear
    echo -e "\n${CYAN}========================================${PLAIN}"
    echo -e "${CYAN}   OUTLINE MANAGER SETUP (SPLIT MODE)   ${PLAIN}"
    echo -e "${CYAN}========================================${PLAIN}"
    echo "1. Install on KHAREJ Server (Core & Manager)"
    echo "2. Install on IRAN Server (Bridge & SSL)"
    echo "3. Uninstall (Force)"
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
}

install_base_dependencies

if [ -f "$INFO_FILE" ] || [ -f "$SERVICE_FILE" ]; then
    show_manage_menu
else
    if [ "$1" == "install" ]; then show_install_menu
    elif [ "$1" == "uninstall" ]; then uninstall
    else show_install_menu
    fi
fi
