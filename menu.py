import os
import json
import requests
import time
import sys
import readline
import qrcode
import re
from datetime import datetime

GREEN = '\033[92m'
RED = '\033[91m'
CYAN = '\033[96m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'
MAGENTA = '\033[95m'

API_URL = "http://127.0.0.1:5000"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
SERVICE_NAME = "outline-manager"

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_qr(data):
    qr = qrcode.QRCode(version=1, box_size=1, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    qr.print_ascii(invert=True)

def get_server_stats():
    try:
        res = requests.get(f"{API_URL}/server_stats", timeout=2)
        if res.status_code == 200:
            stats = res.json()
            return f"CPU: {stats['cpu']}% | RAM: {stats['ram']}%"
    except: return "Server: Offline"
    return "Stats: N/A"

def print_header():
    clear()
    stats = get_server_stats()
    print(f"{CYAN}======================================================================{RESET}")
    print(f"{CYAN}                  OUTLINE MANAGER (ULTIMATE EDITION)                  {RESET}")
    print(f"{CYAN}                      Author: B3hnamR                                 {RESET}")
    print(f"{MAGENTA}           {stats}                                                    {RESET}")
    print(f"{CYAN}======================================================================{RESET}")

def get_validated_input(prompt, validator=None, error_msg="Invalid Input", allow_empty=False):
    while True:
        try:
            val = input(prompt)
            if val.lower() == 'c':
                print(f"{YELLOW}Operation Cancelled.{RESET}")
                return None
            if not val:
                if allow_empty: return "" 
                else:
                    print(f"{RED}Error: Input cannot be empty (type 'c' to cancel).{RESET}")
                    continue
            if validator:
                if not validator(val):
                    print(f"{RED}Error: {error_msg}{RESET}")
                    continue
            return val
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Cancelled.{RESET}")
            return None

def is_valid_duration(val):
    if val == '0': return True
    return bool(re.match(r'^\d+[dh]$', val.lower()))

def is_valid_number(val):
    if val == '0': return True
    return val.replace('.', '', 1).isdigit()

def is_valid_yes_no(val):
    return val.lower() in ['y', 'n', 'yes', 'no']

def calculate_time_left(expiry_str, status):
    if status == 'on_hold': return f"{CYAN}WAITING...{RESET}"
    if not expiry_str: return "Unknown"
    try:
        if "2099" in expiry_str: return "Forever"
        exp_date = datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        delta = exp_date - now
        if delta.total_seconds() < 0: return "EXPIRED"
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0: return f"{days}d {hours}h"
        else: return f"{hours}h left"
    except: return "Unknown"

def create_user():
    print_header()
    print(f"{YELLOW}[ Create New User ]{RESET}")
    print(f"{CYAN}(Type 'c' to cancel at any time){RESET}\n")
    
    name = get_validated_input("Enter Name: ")
    if name is None: return

    gb = get_validated_input("Enter GB Limit (0 for Unlimited): ", 
                             validator=is_valid_number, error_msg="Must be a number (e.g. 5 or 0)")
    if gb is None: return
    
    duration = get_validated_input("Enter Duration: ", 
                                   validator=is_valid_duration, error_msg="Use format '30d' or '5h'")
    if duration is None: return

    on_hold_input = get_validated_input("Start timer on first connection? (y/n): ",
                                        validator=is_valid_yes_no, error_msg="y or n")
    if on_hold_input is None: return
    on_hold = True if on_hold_input.lower().startswith('y') else False
    
    try:
        res = requests.post(f"{API_URL}/add", json={"name": name, "gb": gb, "duration": duration, "on_hold": on_hold})
        if res.status_code == 200:
            data = res.json()
            print(f"\n{GREEN}✔ User Created Successfully!{RESET}")
            print(f"Name:  {data.get('user')}")
            print(f"Token: {data.get('token')}")
            print(f"Link:  {GREEN}{data.get('link')}{RESET}")
            print(f"\n{YELLOW}Scan to Import:{RESET}")
            print_qr(data.get('link'))
        else: print(f"{RED}Error: {res.text}{RESET}")
    except Exception as e: print(f"{RED}Service Error: {e}{RESET}")
    get_validated_input(f"\nPress Enter to return...", allow_empty=True)

def bulk_create_users():
    print_header()
    print(f"{YELLOW}[ Bulk User Creation ]{RESET}")
    base_name = get_validated_input("Enter Base Name: ")
    if base_name is None: return
    
    count_str = get_validated_input("How many users? ", validator=is_valid_number, error_msg="Must be number")
    if count_str is None: return
    count = int(count_str)

    gb = get_validated_input("GB Limit (0 for Unlimited): ", validator=is_valid_number, error_msg="Must be number")
    if gb is None: return

    duration = get_validated_input("Duration (e.g. 30d): ", validator=is_valid_duration)
    if duration is None: return
    
    on_hold_input = get_validated_input("Start timer on first connection? (y/n): ", validator=is_valid_yes_no)
    if on_hold_input is None: return
    on_hold = True if on_hold_input.lower().startswith('y') else False
    
    show_qr = get_validated_input("Show QR Codes? (y/n): ", allow_empty=True, validator=is_valid_yes_no)
    if show_qr is None: show_qr = 'n'

    print(f"\n{CYAN}Creating {count} users...{RESET}\n")
    created_list = []
    
    for i in range(1, count + 1):
        user_name = f"{base_name}_{i}"
        try:
            res = requests.post(f"{API_URL}/add", json={"name": user_name, "gb": gb, "duration": duration, "on_hold": on_hold})
            if res.status_code == 200:
                data = res.json()
                print(f"{GREEN}✔ Created: {user_name}{RESET}")
                created_list.append(f"{data['link']}")
                if show_qr.lower().startswith('y'):
                    print_qr(data['link'])
                    print("-" * 20)
            else: print(f"{RED}✘ Failed: {user_name}{RESET}")
        except: pass

    if created_list:
        filename = f"bulk_{base_name}_{int(time.time())}.txt"
        with open(filename, "w") as f:
            for line in created_list: f.write(line + "\n")
        print(f"\n{GREEN}✔ Saved to: {YELLOW}{filename}{RESET}")
    get_validated_input("\nPress Enter to return...", allow_empty=True)

def list_users(sort_by_usage=False):
    print_header()
    try:
        res = requests.get(f"{API_URL}/list_users")
        if res.status_code == 200:
            users = res.json()
            if sort_by_usage:
                users.sort(key=lambda x: x.get('used_bytes', 0), reverse=True)
                title = "TOP USERS (By Usage)"
            else:
                title = "USER LIST"

            print(f"{YELLOW}--- {title} ---{RESET}")
            print(f"{'NAME':<12} {'TOKEN':<12} {'STATUS':<10} {'DATA LEFT':<12} {'TIME LEFT':<12}")
            print("-" * 65)
            
            for u in users:
                time_left = calculate_time_left(u['expiry'], u.get('status'))
                status_color = GREEN
                state_text = "Active"
                if u.get('status') == 'suspended':
                    status_color = YELLOW
                    state_text = "SUSPENDED"
                elif u.get('status') == 'on_hold':
                    status_color = CYAN
                    state_text = "ON HOLD"
                elif u.get('is_expired', False) or u.get('is_depleted', False):
                    status_color = RED
                    state_text = "Expired"
                print(f"{status_color}{u['name']:<12} {u['token']:<12} {state_text:<10} {u['remaining']:<12} {time_left:<12}{RESET}")
        else: print(f"{RED}Error fetching list.{RESET}")
    except Exception as e: print(f"{RED}Error: {e}{RESET}")
    get_validated_input("\nPress Enter...", allow_empty=True)

def delete_user_menu():
    print_header()
    print(f"{YELLOW}[ Advanced Delete Users ]{RESET}")
    try:
        res = requests.get(f"{API_URL}/list_users")
        if res.status_code != 200: return
        users = res.json()
    except: return

    if not users:
        print(f"{RED}No users found.{RESET}")
        time.sleep(2)
        return

    print(f"{'#':<4} {'NAME':<15} {'TOKEN':<12}")
    print("-" * 35)
    for idx, u in enumerate(users):
        print(f"{CYAN}{idx+1:<4}{RESET} {u['name']:<15} {u['token']:<12}")
    
    print("-" * 35)
    print(f"{YELLOW}Enter numbers (e.g. 1, 3-5, all) or 'c' to cancel{RESET}")
    
    selection = get_validated_input(f"{BOLD}Select > {RESET}")
    if selection is None: return

    indexes_to_delete = []
    if selection.lower() == 'all':
        confirm_all = get_validated_input(f"{RED}Delete ALL? (yes/no): {RESET}", validator=is_valid_yes_no)
        if confirm_all and confirm_all.lower() in ['yes', 'y']:
            indexes_to_delete = list(range(len(users)))
        else: return
    else:
        try:
            parts = selection.split(',')
            for part in parts:
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    for i in range(start, end + 1):
                        indexes_to_delete.append(i - 1)
                else:
                    indexes_to_delete.append(int(part.strip()) - 1)
        except ValueError:
            print(f"{RED}Invalid format.{RESET}")
            time.sleep(1)
            return

    valid_indexes = [i for i in indexes_to_delete if 0 <= i < len(users)]
    if not valid_indexes: return

    print(f"\n{RED}Deleting {len(valid_indexes)} users...{RESET}")
    confirm = get_validated_input("Confirm? (y/n): ", validator=is_valid_yes_no)
    if confirm and confirm.lower() in ['y', 'yes']:
        for i in valid_indexes:
            user = users[i]
            try:
                requests.post(f"{API_URL}/delete_user", json={"token": user['token']})
                print(f"{GREEN}✔ Deleted: {user['name']}{RESET}")
            except: pass
    get_validated_input("\nPress Enter...", allow_empty=True)

def manage_user_actions():
    print_header()
    print(f"{YELLOW}[ Manage User Actions ]{RESET}")
    print("1. Renew / Extend User")
    print("2. Suspend User")
    print("3. Unsuspend User")
    print("4. Clean Expired Users")
    
    action = get_validated_input(f"\n{CYAN}Select Action (or 'c' to cancel): {RESET}")
    if action is None: return

    if action == '4':
        confirm = get_validated_input(f"{RED}Delete ALL expired? (y/n): {RESET}", validator=is_valid_yes_no)
        if confirm and confirm.lower() in ['y', 'yes']:
            res = requests.post(f"{API_URL}/clean_expired")
            print(f"{GREEN}Deleted {res.json()['deleted']} users.{RESET}")
        time.sleep(2)
        return

    token = get_validated_input("Enter User Token: ")
    if token is None: return

    if action == '1': 
        print(f"{CYAN}Leave empty to skip.{RESET}")
        add_gb = get_validated_input("Add GB: ", allow_empty=True, validator=is_valid_number, error_msg="Number only")
        if add_gb is None and add_gb != "": return
        print(f"{CYAN}(Format: 30d, 5h){RESET}")
        add_time = get_validated_input("Extend Time: ", allow_empty=True, 
                                       validator=lambda x: is_valid_duration(x) if x else True)
        if add_time is None and add_time != "": return
        if not add_gb and not add_time: return
        
        payload = {"token": token}
        if add_gb: payload['gb'] = add_gb
        if add_time: payload['duration'] = add_time
        res = requests.post(f"{API_URL}/renew", json=payload)
        if res.status_code == 200: print(f"{GREEN}✔ Renewed!{RESET}")
        else: print(f"{RED}Failed.{RESET}")

    elif action == '2':
        res = requests.post(f"{API_URL}/suspend", json={"token": token})
        if res.status_code == 200: print(f"{YELLOW}✔ Suspended.{RESET}")
        else: print(f"{RED}Failed: {res.text}{RESET}")
    
    elif action == '3':
        res = requests.post(f"{API_URL}/unsuspend", json={"token": token})
        if res.status_code == 200: print(f"{GREEN}✔ Activated.{RESET}")
        else: print(f"{RED}Failed: {res.text}{RESET}")
    time.sleep(1.5)

def edit_config():
    print_header()
    try:
        with open(CONFIG_FILE, 'r') as f: conf = json.load(f)
    except:
        print(f"{RED}Config missing!{RESET}")
        return
    print(f"1. API URL: {conf.get('outline_api', '')}")
    print(f"2. Tunnel Addr: {conf.get('tunnel_address', '')}")
    print(f"3. Force Port: {conf.get('force_port', 'None')}")
    print(f"4. Suffix: {conf.get('custom_suffix', '')}")
    
    choice = get_validated_input("\nSelect item (0 to cancel): ", allow_empty=True)
    if not choice or choice == '0': return
    
    key_map = {'1': 'outline_api', '2': 'tunnel_address', '3': 'force_port', '4': 'custom_suffix'}
    key = key_map.get(choice)
    if key:
        new_val = get_validated_input(f"Enter new value for {key}: ")
        if new_val is None: return
        if key == 'force_port':
             conf[key] = int(new_val) if new_val.lower() not in ['none', ''] else None
        else:
             conf[key] = new_val
        with open(CONFIG_FILE, 'w') as f: json.dump(conf, f, indent=4)
        os.system(f"systemctl restart {SERVICE_NAME}")
        print(f"{GREEN}Updated & Restarted!{RESET}")
        time.sleep(2)

def show_logs():
    try: os.system(f"journalctl -u {SERVICE_NAME} -n 50 -f")
    except KeyboardInterrupt: pass

def main_menu():
    while True:
        try:
            print_header()
            print("1. Create User")
            print("2. List Users")
            print(f"3. {MAGENTA}Top Users{RESET}")
            print(f"4. {YELLOW}Manage Users{RESET}")
            print("5. Delete User (Advanced)")
            print("6. Bulk Create Users")
            print("7. Settings")
            print("8. Logs")
            print("0. Exit")
            choice = input(f"\n{CYAN}Select: {RESET}")
            if choice == '1': create_user()
            elif choice == '2': list_users(False)
            elif choice == '3': list_users(True)
            elif choice == '4': manage_user_actions()
            elif choice == '5': delete_user_menu()
            elif choice == '6': bulk_create_users()
            elif choice == '7': edit_config()
            elif choice == '8': show_logs()
            elif choice == '0': break
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception: time.sleep(1)

if __name__ == '__main__':
    main_menu()