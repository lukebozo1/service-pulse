# B.A.S.T.I.O.N.
**Blue-team Automated Security Testing for Infrastructure, Operations, and Networks**

A CTF-style blue team training environment. Students defend a Linux target host against a live attacker while a real-time scoreboard tracks service uptime. The attacker machine runs automated exploit scripts and an AI agent that adaptively uses planted backdoors to keep services down.

---

## Architecture

```
┌─────────────────────┐        HTTP POST /start        ┌─────────────────────┐
│   Checker (Flask)   │ ──────────────────────────────▶ │   Kali Runner       │
│   checker/app.py    │                                  │   kali/run.py       │
│                     │                                  │                     │
│  - Score dashboard  │                                  │  - Attack rounds    │
│  - Admin panel      │                                  │    every 15 min     │
│  - Service checks   │                                  │  - AI agent thread  │
│    every 60s        │                                  │    (continuous)     │
└─────────────────────┘                                  └─────────────────────┘
         │                                                        │
         │ checks SSH/HTTP/FTP                     exploits & backdoors
         ▼                                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Target Host  10.10.40.50                             │
│           nginx  ·  vsftpd 2.3.4  ·  SSH  ·  default credentials           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Components

### `checker/` — Scoreboard & Admin Panel

Flask web app that monitors the target and tracks student scores.

**Features:**
- Live SSH, HTTP, and FTP checks every 60 seconds
- Score tracking (+50 on success, -10 on failure per service)
- Score history chart (last 60 minutes)
- Recent checks panel with clickable failure indicators
- Full service log console with per-service filtering
- SSH credential management via UI
- **Password-protected admin panel** — start competition, configure target, reset scores

**Stack:**

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Database | SQLite |
| SSH checks | Paramiko |
| HTTP checks | Requests |
| FTP checks | ftplib (stdlib) |
| Frontend | Vanilla JS, Chart.js |

**Install & run:**
```bash
pip install flask paramiko requests
cd checker
python3 app.py
```
Dashboard: `http://0.0.0.0:5000`
Admin panel: `http://0.0.0.0:5000/admin` (password: `bastion-admin`)

---

### `kali/` — Attack Runner

Runs on the Kali attacker machine. Waits for the admin panel to signal competition start, then launches scripted attack rounds and an AI agent.

**Attack rounds (every 15 min):**

| Script | Method | Effect |
|---|---|---|
| `attacks/ssh_deface.py` | SSH + sudo escalation | Overwrites nginx index.html, plants bind shell on :4444, adds root crontab |
| `attacks/vsftpd_backdoor.py` | CVE-2011-2523 root shell | Creates `sysmon` backdoor user + NOPASSWD sudo, adds cron re-deface job |
| `attacks/backdoor_exploit.py` | sysmon SSH or bind shell | Stops nginx, vsftpd, and SSH |

**AI agent (`agent.py`):**

Runs continuously alongside the scripted rounds. Connects via bind shell (port 4444) or sysmon SSH, then uses an LLM (via OpenAI-compatible API) in an agentic tool-use loop to:
- Stop all scored services
- Verify and restore persistence (sysmon user, bind shell, cron jobs, nginx deface)
- Adapt based on what defenders have patched

The agent polls every 30 seconds for an open backdoor. After each session it cools down for 120 seconds and reconnects.

**Install & run on Kali:**
```bash
pip3 install paramiko
cd kali
python3 run.py
```

**AI agent config (`kali/config.py`):**
```python
AGENT_ENABLED  = True                          # set False if running agent.py separately
AGENT_API_KEY  = "your-api-key"
AGENT_BASE_URL = "https://mindrouter.uidaho.edu/v1"
AGENT_MODEL    = "qwen/qwen3.5-400b"           # any model that supports tool/function calling
```

> **Note:** If the Kali machine can't reach the AI API (e.g. school network restriction), set `AGENT_ENABLED = False` in `config.py` and run `agent.py` separately on a machine that has API access:
> ```bash
> pip3 install openai paramiko
> python3 agent.py
> ```

---

## Planted Vulnerabilities (Target Host)

Students must find and remediate:

| Vulnerability | How to detect | How to fix |
|---|---|---|
| Default SSH credentials | Try logging in | `passwd <user>` |
| vsftpd 2.3.4 backdoor (CVE-2011-2523) | `vsftpd --version` | Upgrade vsftpd |
| `sysmon` backdoor user | `grep -v nologin /etc/passwd` | `userdel -r sysmon` |
| sysmon sudoers entry | `cat /etc/sudoers.d/sysmon` | `rm /etc/sudoers.d/sysmon` |
| Bind shell on :4444 | `ss -tlnp \| grep 4444` | `pkill -f 'nc.*4444'` |
| Bind shell launcher | `cat /usr/local/bin/.syscheck` | `rm /usr/local/bin/.syscheck` |
| Root crontab entries | `crontab -l` (as root) | `crontab -e` (delete entries) |
| Defaced nginx page | Check index.html for "ACCESS DENIED" | Restore index.html |

---

## Configuration

Target and scoring are configured at runtime via the admin panel, or at the top of each config file:

**`checker/app.py`:**
```python
TARGET_HOST = "10.10.40.50"
SEARCH_TEXT = "Wikipedia"     # must appear in HTTP response for HTTP check to pass
```

**`kali/config.py`:**
```python
TARGET_HOST     = "10.10.40.50"
ATTACK_INTERVAL = 900          # seconds between attack rounds (15 min)
LISTENER_PORT   = 8080         # port that receives /start signal from admin panel
BIND_PORT       = 4444         # bind shell port planted on target
```

---

## Admin Panel

Access at `/admin` (password: `bastion-admin`).

| Action | Description |
|---|---|
| Start Competition | Sends POST `/start` to Kali runner, kicks off attacks |
| Configure | Set TARGET_HOST and SEARCH_TEXT without restarting |
| Reset Scores | Clears score history and recent checks |
| Reset Logs | Clears service log entries |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/data` | Current state, score history, recent checks |
| `GET` | `/api/logs` | Service logs (`?service=SSH\|HTTP\|FTP`, `?errors=1`) |
| `GET` | `/api/users` | List SSH credentials |
| `POST` | `/api/users` | Add credential `{"username": "", "password": ""}` |
| `PUT` | `/api/users/<id>` | Update password |
| `DELETE` | `/api/users/<id>` | Remove credential |
| `POST` | `/api/reset-scores` | Reset scores and recent checks |
| `POST` | `/api/reset-logs` | Clear logs |

---

## Database Schema

```sql
history     (id, timestamp, ssh_points, http_points, ftp_points)
credentials (id, username, password)
checks      (id, timestamp, username, ssh_up, http_up, ftp_up)
logs        (id, timestamp, service, status, message)
config      (key, value)
```

- `history` retains the last **1440** entries (~24 hours at 1/min)
- `checks` retains the last **10** entries (Recent Checks panel)
- `logs` retains the last **300** entries
