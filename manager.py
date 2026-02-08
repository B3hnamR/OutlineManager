import sqlite3
import requests
import datetime
import re
import json
import random
import string
import os
import urllib.parse
import psutil
import time
import shutil
from flask import Flask, request, jsonify, make_response

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
DB_FILE = os.path.join(BASE_DIR, 'users.db')
BACKUP_FILE = os.path.join(BASE_DIR, 'users.db.backup')

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def generate_token(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def init_db():
    if os.path.exists(DB_FILE):
        try: shutil.copy(DB_FILE, BACKUP_FILE)
        except: pass

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (token TEXT PRIMARY KEY, key_id TEXT, name TEXT, expiry_date TEXT, 
                  status TEXT DEFAULT 'active', data_limit INTEGER DEFAULT 0, initial_duration TEXT)''')
    conn.commit()
    conn.close()

def call_api(method, endpoint, data=None):
    conf = load_config()
    url = f"{conf['outline_api']}/{endpoint}"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Note: verify=False is used because Outline typically uses self-signed certs.
            # In a strictly internal network, this is acceptable.
            response = requests.request(method, url, json=data, verify=False, timeout=10)
            if 200 <= response.status_code < 300: return response.json()
            if response.status_code == 404 and method == 'DELETE': return {}
        except requests.exceptions.RequestException:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            else: return None
    return None

def calculate_expiry_date(duration_str, base_date=None):
    s = str(duration_str).strip().lower()
    if s == '0': return '2099-12-31 23:59:59'
    match = re.match(r'^(\d+)([dh]?)$', s)
    if not match: return None 
    value = int(match.group(1))
    unit = match.group(2)
    hours_to_add = value * 24 if unit == 'd' else value
    start_time = base_date if base_date else datetime.datetime.now()
    return (start_time + datetime.timedelta(hours=hours_to_add)).strftime('%Y-%m-%d %H:%M:%S')

def check_local_access():
    # Allow IPv4 localhost and IPv6 localhost
    if request.remote_addr not in ['127.0.0.1', '::1']: 
        return False
    return True

# --- ROUTES ---

@app.route('/server_stats', methods=['GET'])
def server_stats():
    try:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        return jsonify({"cpu": cpu, "ram": ram})
    except: return jsonify({"cpu": 0, "ram": 0})

@app.route('/add', methods=['POST'])
def add_user():
    if not check_local_access(): return jsonify({"error": "Access Denied"}), 403
    conf = load_config()
    data = request.json
    name = data.get('name')
    gb = data.get('gb')
    duration = data.get('duration')
    on_hold = data.get('on_hold', False)

    if on_hold:
        status = 'on_hold'
        expiry_date = None
    else:
        status = 'active'
        expiry_date = calculate_expiry_date(duration)
        if not expiry_date: return jsonify({"error": "Invalid duration format"}), 400

    limit_bytes = 0
    try:
        if gb and str(gb) != '0':
            if not str(gb).replace('.', '', 1).isdigit():
                 return jsonify({"error": "GB must be a number"}), 400
            limit_bytes = int(float(gb) * 1000 * 1000 * 1000)
    except ValueError: return jsonify({"error": "Invalid GB format"}), 400

    # 1. API CALL FIRST
    new_key = call_api('POST', 'access-keys')
    if not new_key: return jsonify({"error": "Outline API Error"}), 500
    key_id = new_key['id']
    
    # 2. Configure Key
    call_api('PUT', f'access-keys/{key_id}/name', {'name': name})
    if limit_bytes > 0:
        call_api('PUT', f'access-keys/{key_id}/data-limit', {'limit': {'bytes': limit_bytes}})

    # 3. DB Insert (Only if API succeeded)
    token = generate_token()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)", 
              (token, key_id, name, expiry_date, status, limit_bytes, duration))
    conn.commit()
    conn.close()

    safe_name = urllib.parse.quote(name)
    sub_link = f"ssconf://{conf['subscription_domain']}/getsub/{token}#{safe_name}"
    
    return jsonify({"status": "Created", "token": token, "link": sub_link, "user": name})

@app.route('/renew', methods=['POST'])
def renew_user():
    if not check_local_access(): return jsonify({"error": "Access Denied"}), 403
    token = request.json.get('token')
    add_gb = request.json.get('gb')
    add_duration = request.json.get('duration')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT key_id, expiry_date, data_limit, status FROM users WHERE token=?", (token,))
    user = c.fetchone()
    if not user: 
        conn.close()
        return jsonify({"error": "Not Found"}), 404
    
    key_id, current_expiry, current_limit, status = user
    new_expiry = current_expiry
    
    if add_duration and str(add_duration).strip():
        now = datetime.datetime.now()
        is_unlimited = False
        if current_expiry:
            try:
                if datetime.datetime.strptime(current_expiry, '%Y-%m-%d %H:%M:%S').year > 2090: is_unlimited = True
            except: pass

        if status == 'on_hold' or not current_expiry or is_unlimited: base_time = now
        else:
             try:
                 curr_obj = datetime.datetime.strptime(current_expiry, '%Y-%m-%d %H:%M:%S')
                 base_time = now if curr_obj < now else curr_obj
             except: base_time = now
        new_expiry = calculate_expiry_date(add_duration, base_time)

    new_limit = current_limit
    limit_changed = False
    
    if add_gb and str(add_gb).strip():
        try:
             if str(add_gb) == '0':
                 new_limit = 0
             else:
                 bytes_to_add = int(float(add_gb) * 1000 * 1000 * 1000)
                 new_limit = bytes_to_add if current_limit == 0 else current_limit + bytes_to_add
             limit_changed = True
        except ValueError: pass 

    # 1. API CALL
    api_ok = True
    if limit_changed:
        if new_limit == 0:
            api_ok = call_api('DELETE', f'access-keys/{key_id}/data-limit') is not None
        else:
            api_ok = call_api('PUT', f'access-keys/{key_id}/data-limit', {'limit': {'bytes': new_limit}}) is not None

    if not api_ok:
        conn.close()
        return jsonify({"error": "API Error"}), 502

    # 2. DB UPDATE
    c.execute("UPDATE users SET expiry_date=?, data_limit=?, status='active' WHERE token=?", (new_expiry, new_limit, token))
    conn.commit()
    conn.close()
    return jsonify({"status": "Renewed", "new_expiry": new_expiry})

@app.route('/list_users', methods=['GET'])
def list_users():
    if not check_local_access(): return jsonify({"error": "Access Denied"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, token, expiry_date, key_id, status, initial_duration, data_limit FROM users")
    db_users = c.fetchall()
    
    keys_data = call_api('GET', 'access-keys')
    metrics_data = call_api('GET', 'metrics/transfer')
    if not keys_data: 
        conn.close()
        return jsonify([])

    usage_map = metrics_data.get('bytesTransferredByUserId', {}) if metrics_data else {}
    limit_map = {k['id']: k.get('dataLimit', {}).get('bytes') for k in keys_data.get('accessKeys', [])}

    user_list = []
    updated_users = []
    now = datetime.datetime.now()

    for row in db_users:
        name, token, expiry, key_id, status, init_duration, limit_db = row
        limit = limit_map.get(key_id, limit_db)
        used = usage_map.get(key_id, 0)

        # Logic: On Hold -> Active upon usage
        if status == 'on_hold' and used > 0:
            new_expiry = calculate_expiry_date(init_duration)
            status = 'active'
            expiry = new_expiry
            updated_users.append((new_expiry, token))
        
        remaining_str = "Unlimited"
        is_depleted = False
        if limit and limit > 0:
            remaining_bytes = limit - used
            if remaining_bytes <= 0: 
                remaining_str = "0 GB"
                is_depleted = True
            else: 
                remaining_str = f"{round(remaining_bytes / (1000**3), 2)} GB"
        
        is_expired = False
        if status == 'active' and expiry:
            try:
                if now > datetime.datetime.strptime(expiry, '%Y-%m-%d %H:%M:%S'): is_expired = True
            except: pass

        user_list.append({
            "name": name, "token": token, "expiry": expiry, "remaining": remaining_str,
            "status": status, "used_bytes": used, "is_depleted": is_depleted, "is_expired": is_expired
        })

    if updated_users:
        c.executemany("UPDATE users SET status='active', expiry_date=? WHERE token=?", updated_users)
        conn.commit()
    conn.close()
    return jsonify(user_list)

@app.route('/suspend', methods=['POST'])
def suspend_user():
    if not check_local_access(): return jsonify({"error": "Access Denied"}), 403
    token = request.json.get('token')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT key_id FROM users WHERE token=?", (token,))
    res = c.fetchone()
    if res:
        key_id = res[0]
        # API First
        if call_api('PUT', f'access-keys/{key_id}/data-limit', {'limit': {'bytes': 1}}):
            c.execute("UPDATE users SET status='suspended' WHERE token=?", (token,))
            conn.commit()
            conn.close()
            return jsonify({"status": "Suspended"})
        else:
            conn.close()
            return jsonify({"error": "API Error"}), 502
    return jsonify({"error": "Not Found"}), 404

@app.route('/unsuspend', methods=['POST'])
def unsuspend_user():
    if not check_local_access(): return jsonify({"error": "Access Denied"}), 403
    token = request.json.get('token')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT key_id, data_limit FROM users WHERE token=?", (token,))
    res = c.fetchone()
    if res:
        key_id, original_limit = res
        api_success = False
        # API First
        if original_limit == 0: 
            if call_api('DELETE', f'access-keys/{key_id}/data-limit'): api_success = True
        else: 
            if call_api('PUT', f'access-keys/{key_id}/data-limit', {'limit': {'bytes': original_limit}}): api_success = True
        
        if api_success:
            c.execute("UPDATE users SET status='active' WHERE token=?", (token,))
            conn.commit()
            conn.close()
            return jsonify({"status": "Active"})
        else:
            conn.close()
            return jsonify({"error": "API Error"}), 502
    return jsonify({"error": "Not Found"}), 404

@app.route('/clean_expired', methods=['POST'])
def clean_expired():
    if not check_local_access(): return jsonify({"error": "Access Denied"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT key_id, expiry_date, name FROM users WHERE status='active'")
    users = c.fetchall()
    deleted_count = 0
    now = datetime.datetime.now()
    for u in users:
        key_id, expiry_str, name = u
        try:
            if expiry_str:
                exp_date = datetime.datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
                if now > exp_date:
                    # API First
                    if call_api('DELETE', f'access-keys/{key_id}'):
                         c.execute("DELETE FROM users WHERE key_id=?", (key_id,))
                         deleted_count += 1
        except: continue
    conn.commit()
    conn.close()
    return jsonify({"deleted": deleted_count})

@app.route('/delete_user', methods=['POST'])
def delete_user():
    if not check_local_access(): return jsonify({"error": "Access Denied"}), 403
    token = request.json.get('token')
    if not token: return jsonify({"error": "Empty Token"}), 400
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT key_id FROM users WHERE token=?", (token,))
    res = c.fetchone()
    if res:
        key_id = res[0]
        # API First
        api_result = call_api('DELETE', f'access-keys/{key_id}')
        if api_result is not None:
            c.execute("DELETE FROM users WHERE token=?", (token,))
            conn.commit()
            conn.close()
            return jsonify({"status": "Deleted"})
        else:
            conn.close()
            return jsonify({"error": "API Error"}), 502
    conn.close()
    return jsonify({"error": "Not Found"}), 404

@app.route('/getsub/<token>')
def get_sub(token):
    # Public Access
    conf = load_config()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT key_id, expiry_date, name, status FROM users WHERE token=?", (token,))
    user = c.fetchone()
    conn.close()

    if not user: return "Invalid Link", 404
    key_id, expiry_str, db_name, status = user
    
    if status == 'suspended': return "Account Suspended", 403
    if status != 'on_hold' and expiry_str:
        try:
            if datetime.datetime.now() > datetime.datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S'): return "Expired", 403
        except: pass

    keys = call_api('GET', 'access-keys')
    if not keys: return "Server Error", 502
    target_key = next((k for k in keys['accessKeys'] if k['id'] == key_id), None)
    if not target_key: return "Key Not Found", 404

    original_url = target_key['accessUrl']
    base = original_url.split('?')[0]
    # Regex Fix: Removed space in group name (?P<u > -> ?P<u>)
    match = re.match(r'ss://(?P<u>[^@]+)@(?P<h>[^:]+):(?P<p>\d+)', base)
    
    final_response_text = original_url 
    if match:
        final_port = conf['force_port'] if conf['force_port'] else match.group('p')
        base_suffix = conf['custom_suffix'].split('#')[0]
        encoded_name = urllib.parse.quote(db_name)
        final_response_text = f"ss://{match.group('u')}@{conf['tunnel_address']}:{final_port}{base_suffix}#{encoded_name}"

    response = make_response(final_response_text)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    
    # Sanitize Filename for Header Injection Protection
    safe_filename = re.sub(r'[^\w\-. ]', '', db_name).strip()
    if not safe_filename:
        safe_filename = f"outline-{token}"
    response.headers['Content-Disposition'] = f'inline; filename="{safe_filename}"'
    return response

if __name__ == '__main__':
    init_db()
    # IPv6/IPv4 Localhost check is implemented in 'check_local_access'
    app.run(host='0.0.0.0', port=5000, debug=False)
