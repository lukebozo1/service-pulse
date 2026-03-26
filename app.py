from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import paramiko
import requests
import ftplib
import threading
import time
import sqlite3
import random
from functools import wraps

app = Flask(__name__)
app.secret_key = "bastion-admin-secret-key"

# --- Configuration ---
TARGET_HOST    = "10.10.40.50"
SEARCH_TEXT    = "Wikipedia"
DB_FILE        = "monitor_data.db"
ADMIN_PASSWORD = "bastion-admin"   # Change this before deployment

DEFAULT_USERS = [
    ("john",     "john"),
    ("bob",      "bob"),
    ("alice",    "alice"),
    ("patricia", "patricia"),
    ("tyrone",   "tyrone"),
    ("jason",    "jason"),
    ("newuser",  "newuser"),
]

DEFAULT_CONFIG = {
    "target_host":        TARGET_HOST,
    "search_text":        SEARCH_TEXT,
    "attacker_url":       "http://10.10.40.100:8080/start",
    "competition_active": "0",
}

# Global live state
current_state     = {"ssh_up": False, "http_up": False, "ftp_up": False, "current_user": None, "last_check": None, "last_check_ts": None}
reset_scores_flag = False

# Runtime config — read by monitor thread, updated by admin panel
runtime_config = dict(DEFAULT_CONFIG)

# --- Database ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  ssh_points INTEGER,
                  http_points INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS credentials
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL,
                  password TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS checks
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  username TEXT,
                  ssh_up INTEGER,
                  http_up INTEGER,
                  ftp_up INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  service TEXT,
                  status TEXT,
                  message TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')
    # Migrate existing tables to add ftp columns if missing
    for sql in [
        'ALTER TABLE history ADD COLUMN ftp_points INTEGER DEFAULT 0',
        'ALTER TABLE checks  ADD COLUMN ftp_up      INTEGER DEFAULT 0',
    ]:
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    # Seed credentials on first run
    c.execute('SELECT COUNT(*) FROM credentials')
    if c.fetchone()[0] == 0:
        c.executemany('INSERT INTO credentials (username, password) VALUES (?, ?)', DEFAULT_USERS)
    # Seed config defaults (INSERT OR IGNORE — never overwrite existing values)
    for key, value in DEFAULT_CONFIG.items():
        c.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def load_runtime_config():
    global runtime_config
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT key, value FROM config')
    runtime_config.update(dict(c.fetchall()))
    conn.close()

def save_config_values(updates):
    global runtime_config
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for key, value in updates.items():
        c.execute('INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()
    runtime_config.update(updates)

def get_users():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, username, password FROM credentials ORDER BY id')
    rows = c.fetchall()
    conn.close()
    return rows

def get_latest_points():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT ssh_points, http_points, COALESCE(ftp_points, 0) FROM history ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return {"ssh": row[0], "http": row[1], "ftp": row[2]} if row else {"ssh": 0, "http": 0, "ftp": 0}

# --- Admin Auth ---
def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# --- Check Functions ---
def check_ssh_status():
    host  = runtime_config.get("target_host", TARGET_HOST)
    users = get_users()
    if not users:
        return False, None, "No credentials configured"
    uid, username, password = random.choice(users)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, username=username, password=password, timeout=5)
        client.close()
        print(f"✅ SSH OK  [{username}]")
        return True, username, f"Login OK as {username}"
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"❌ SSH fail [{username}]: {msg}")
        return False, username, f"[{username}] {msg}"

def check_http_status():
    host   = runtime_config.get("target_host", TARGET_HOST)
    search = runtime_config.get("search_text", SEARCH_TEXT)
    try:
        r = requests.get(f"http://{host}", timeout=5)
        if r.status_code == 200 and search in r.text:
            return True, f"HTTP 200, '{search}' found"
        reason = f"HTTP {r.status_code}"
        if search not in r.text:
            reason += f", '{search}' not in response"
        return False, reason
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

def check_ftp_status():
    host = runtime_config.get("target_host", TARGET_HOST)
    try:
        ftp = ftplib.FTP(timeout=5)
        ftp.connect(host)
        ftp.login()  # anonymous
        ftp.quit()
        print("✅ FTP OK  [anonymous]")
        return True, "Anonymous login OK"
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"❌ FTP fail: {msg}")
        return False, msg

# --- Background Monitor ---
def background_monitor():
    global current_state, reset_scores_flag
    init_db()
    load_runtime_config()
    scores = get_latest_points()
    while True:
        if reset_scores_flag:
            scores = {"ssh": 0, "http": 0, "ftp": 0}
            reset_scores_flag = False
        ssh_up, used_user, ssh_msg = check_ssh_status()
        http_up, http_msg          = check_http_status()
        ftp_up, ftp_msg            = check_ftp_status()

        current_state["ssh_up"]        = ssh_up
        current_state["http_up"]       = http_up
        current_state["ftp_up"]        = ftp_up
        current_state["current_user"]  = used_user
        current_state["last_check"]    = time.strftime("%H:%M:%S")
        current_state["last_check_ts"] = int(time.time())

        scores["ssh"]  += 50 if ssh_up  else -10
        scores["http"] += 50 if http_up else -10
        scores["ftp"]  += 50 if ftp_up  else -10

        timestamp = time.strftime("%H:%M")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT INTO history (timestamp, ssh_points, http_points, ftp_points) VALUES (?, ?, ?, ?)",
            (timestamp, scores["ssh"], scores["http"], scores["ftp"])
        )
        c.execute(
            "DELETE FROM history WHERE id NOT IN "
            "(SELECT id FROM history ORDER BY id DESC LIMIT 1440)"
        )
        c.execute(
            "INSERT INTO checks (timestamp, username, ssh_up, http_up, ftp_up) VALUES (?, ?, ?, ?, ?)",
            (time.strftime("%H:%M:%S"), used_user, int(ssh_up), int(http_up), int(ftp_up))
        )
        c.execute(
            "DELETE FROM checks WHERE id NOT IN "
            "(SELECT id FROM checks ORDER BY id DESC LIMIT 10)"
        )
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        c.executemany(
            "INSERT INTO logs (timestamp, service, status, message) VALUES (?, ?, ?, ?)",
            [
                (ts, 'SSH',  'up' if ssh_up  else 'down', ssh_msg),
                (ts, 'HTTP', 'up' if http_up else 'down', http_msg),
                (ts, 'FTP',  'up' if ftp_up  else 'down', ftp_msg),
            ]
        )
        c.execute(
            "DELETE FROM logs WHERE id NOT IN "
            "(SELECT id FROM logs ORDER BY id DESC LIMIT 300)"
        )
        conn.commit()
        conn.close()

        time.sleep(60)

threading.Thread(target=background_monitor, daemon=True).start()

# --- Main Routes ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Admin Routes ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        error = "Invalid password."
    return render_template('admin_login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@require_admin
def admin_panel():
    return render_template('admin.html')

@app.route('/api/admin/config', methods=['GET'])
@require_admin
def admin_get_config():
    return jsonify({
        "target_host":        runtime_config.get("target_host", TARGET_HOST),
        "search_text":        runtime_config.get("search_text", SEARCH_TEXT),
        "attacker_url":       runtime_config.get("attacker_url", DEFAULT_CONFIG["attacker_url"]),
        "competition_active": runtime_config.get("competition_active", "0") == "1",
    })

@app.route('/api/admin/config', methods=['POST'])
@require_admin
def admin_save_config():
    data = request.get_json() or {}
    updates = {}
    if 'target_host' in data:
        val = (data['target_host'] or '').strip()
        if not val:
            return jsonify({"error": "target_host cannot be empty"}), 400
        updates['target_host'] = val
    if 'search_text' in data:
        updates['search_text'] = (data['search_text'] or '').strip()
    if 'attacker_url' in data:
        val = (data['attacker_url'] or '').strip()
        if not val:
            return jsonify({"error": "attacker_url cannot be empty"}), 400
        updates['attacker_url'] = val
    if updates:
        save_config_values(updates)
    return jsonify({"ok": True})

@app.route('/api/admin/start', methods=['POST'])
@require_admin
def admin_start_competition():
    attacker_url = runtime_config.get("attacker_url", DEFAULT_CONFIG["attacker_url"])
    try:
        resp = requests.post(attacker_url, timeout=5, json={"action": "start"})
        resp.raise_for_status()
        save_config_values({"competition_active": "1"})
        return jsonify({"ok": True, "attacker_status": resp.status_code})
    except Exception as e:
        return jsonify({"error": str(e)}), 502

# --- Monitoring API ---
@app.route('/api/data')
def api_data():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT timestamp, ssh_points, http_points, COALESCE(ftp_points, 0) FROM history ORDER BY id DESC LIMIT 60')
    rows = c.fetchall()
    rows.reverse()
    c.execute('SELECT timestamp, username, ssh_up, http_up, ftp_up FROM checks ORDER BY id DESC LIMIT 10')
    checks = c.fetchall()
    conn.close()

    return jsonify({
        "current_state": current_state,
        "history": [{"time": r[0], "ssh": r[1], "http": r[2], "ftp": r[3]} for r in rows],
        "recent_checks": [{"time": r[0], "user": r[1], "ssh_up": bool(r[2]), "http_up": bool(r[3]), "ftp_up": bool(r[4])} for r in checks]
    })

@app.route('/api/logs')
def api_logs():
    service = request.args.get('service')
    errors  = request.args.get('errors')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query  = 'SELECT timestamp, service, status, message FROM logs'
    params = []
    wheres = []
    if service:
        wheres.append('service = ?')
        params.append(service.upper())
    if errors == '1':
        wheres.append("status = 'down'")
    if wheres:
        query += ' WHERE ' + ' AND '.join(wheres)
    query += ' ORDER BY id DESC LIMIT 100'
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return jsonify([{"time": r[0], "service": r[1], "status": r[2], "message": r[3]} for r in rows])

@app.route('/api/reset-scores', methods=['POST'])
def reset_scores():
    global reset_scores_flag
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM history')
    conn.commit()
    conn.close()
    reset_scores_flag = True
    return jsonify({"ok": True})

@app.route('/api/reset-logs', methods=['POST'])
def reset_logs():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM logs')
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# --- Credential Management API ---
@app.route('/api/users', methods=['GET'])
def list_users():
    users = get_users()
    return jsonify([{"id": u[0], "username": u[1], "password": u[2]} for u in users])

@app.route('/api/users', methods=['POST'])
def add_user():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO credentials (username, password) VALUES (?, ?)', (username, password))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return jsonify({"id": new_id, "username": username}), 201

@app.route('/api/users/<int:uid>', methods=['PUT'])
def update_user(uid):
    data = request.get_json() or {}
    password = (data.get('password') or '').strip()
    if not password:
        return jsonify({"error": "password is required"}), 400
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE credentials SET password = ? WHERE id = ?', (password, uid))
    found = c.rowcount > 0
    conn.commit()
    conn.close()
    if not found:
        return jsonify({"error": "user not found"}), 404
    return jsonify({"ok": True})

@app.route('/api/users/<int:uid>', methods=['DELETE'])
def delete_user(uid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM credentials WHERE id = ?', (uid,))
    found = c.rowcount > 0
    conn.commit()
    conn.close()
    if not found:
        return jsonify({"error": "user not found"}), 404
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=False)
