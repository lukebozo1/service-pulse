from flask import Flask, render_template, jsonify, request
import paramiko
import requests
import ftplib
import threading
import time
import sqlite3
import random

app = Flask(__name__)

# --- Configuration ---
TARGET_HOST = "10.10.40.50"
HTTP_URL = "http://10.10.40.50"
SEARCH_TEXT = "Wikipedia"
DB_FILE = "monitor_data.db"

DEFAULT_USERS = [
    ("john",     "john"),
    ("bob",      "bob"),
    ("alice",    "alice"),
    ("patricia", "patricia"),
    ("tyrone",   "tyrone"),
    ("jason",    "jason"),
    ("newuser",  "newuser"),
]

# Global live state
current_state = {"ssh_up": False, "http_up": False, "ftp_up": False, "current_user": None, "last_check": None, "last_check_ts": None}

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
    # Migrate existing tables to add ftp columns if missing
    for sql in [
        'ALTER TABLE history ADD COLUMN ftp_points INTEGER DEFAULT 0',
        'ALTER TABLE checks  ADD COLUMN ftp_up      INTEGER DEFAULT 0',
    ]:
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    # Seed defaults on first run
    c.execute('SELECT COUNT(*) FROM credentials')
    if c.fetchone()[0] == 0:
        c.executemany('INSERT INTO credentials (username, password) VALUES (?, ?)', DEFAULT_USERS)
    conn.commit()
    conn.close()

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
    c.execute('SELECT ssh_points, http_points, ftp_points FROM history ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return {"ssh": row[0], "http": row[1], "ftp": row[2]} if row else {"ssh": 0, "http": 0, "ftp": 0}

# --- Check Functions ---
def check_ssh_status():
    users = get_users()
    if not users:
        return False, None
    uid, username, password = random.choice(users)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(TARGET_HOST, username=username, password=password, timeout=5)
        client.close()
        print(f"✅ SSH OK  [{username}]")
        return True, username
    except Exception as e:
        print(f"❌ SSH fail [{username}]: {type(e).__name__}")
        return False, username

def check_http_status():
    try:
        r = requests.get(HTTP_URL, timeout=5)
        return r.status_code == 200 and SEARCH_TEXT in r.text
    except Exception:
        return False

def check_ftp_status():
    try:
        ftp = ftplib.FTP(timeout=5)
        ftp.connect(TARGET_HOST)
        ftp.login()  # anonymous, no password
        ftp.quit()
        print("✅ FTP OK  [anonymous]")
        return True
    except Exception as e:
        print(f"❌ FTP fail: {type(e).__name__}")
        return False

# --- Background Monitor ---
def background_monitor():
    global current_state
    init_db()
    scores = get_latest_points()
    while True:
        ssh_up, used_user = check_ssh_status()
        http_up = check_http_status()
        ftp_up  = check_ftp_status()

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
        conn.commit()
        conn.close()

        time.sleep(60)

threading.Thread(target=background_monitor, daemon=True).start()

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def api_data():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT timestamp, ssh_points, http_points, ftp_points FROM history ORDER BY id DESC LIMIT 60')
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
