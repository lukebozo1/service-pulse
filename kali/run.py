"""
Kali attack runner.

Usage:
    python3 run.py

Listens on LISTENER_PORT for an HTTP POST /start from the B.A.S.T.I.O.N.
admin panel.  Once received, begins the attack loop:

    Round 1 immediately, then every ATTACK_INTERVAL seconds (15 min).

Each round runs:
    1. ssh_deface    — SSH in with default creds, overwrite nginx index.html
    2. vsftpd_backdoor — CVE-2011-2523 root shell, install persistence

Requires:
    pip3 install paramiko
"""

import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

from config import LISTENER_PORT, ATTACK_INTERVAL, TARGET_HOST
from attacks import ssh_deface, vsftpd_backdoor

# ── State ─────────────────────────────────────────────────────────────
_started = False
_lock    = threading.Lock()


# ── Logging ───────────────────────────────────────────────────────────
def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── Attack loop ───────────────────────────────────────────────────────
def attack_round(round_num):
    log(f"━━━ Round {round_num} — target {TARGET_HOST} ━━━")

    log("[1/2] SSH deface")
    try:
        ok = ssh_deface.run(log)
        log(f"      {'OK' if ok else 'FAILED'}")
    except Exception as e:
        log(f"      ERROR: {e}")

    log("[2/2] vsftpd backdoor")
    try:
        ok = vsftpd_backdoor.run(log)
        log(f"      {'OK' if ok else 'FAILED'}")
    except Exception as e:
        log(f"      ERROR: {e}")

    log(f"━━━ Round {round_num} complete — next in {ATTACK_INTERVAL // 60} min ━━━\n")


def attack_loop():
    round_num = 1
    while True:
        attack_round(round_num)
        round_num += 1
        time.sleep(ATTACK_INTERVAL)


def start_attacks():
    global _started
    with _lock:
        if _started:
            return False
        _started = True
    log("*** Competition started — launching attack loop ***")
    threading.Thread(target=attack_loop, daemon=True).start()
    return True


# ── HTTP listener ─────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/start":
            launched = start_attacks()
            if launched:
                body = b"started"
                log(f"Start signal received from {self.client_address[0]}")
            else:
                body = b"already running"
                log("Duplicate start signal ignored")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # silence default access log


# ── Entry point ───────────────────────────────────────────────────────
if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", LISTENER_PORT), Handler)
    log(f"Listening on 0.0.0.0:{LISTENER_PORT} — waiting for start signal")
    log(f"Attack interval: every {ATTACK_INTERVAL // 60} minutes")
    log(f"Target: {TARGET_HOST}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Stopped.")
