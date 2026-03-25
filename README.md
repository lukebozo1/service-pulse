# B.A.S.T.I.O.N.
**Blue-team Automated Security Testing for Infrastructure, Operations, and Networks**

A real-time uptime and service monitoring dashboard for air-gapped lab environments. Monitors SSH, HTTP, and FTP services against a target host, tracks scores over time, and provides credential management — all from a single web interface.

---

## Features

- **Live service monitoring** — SSH, HTTP, and FTP checks run every 60 seconds
- **Score tracking** — each service earns +50 points on success, -10 on failure
- **Score history chart** — line graph of the last 60 minutes per service
- **Recent checks panel** — last 10 check results per service as visual indicators
- **Service logs** — full log console with per-service and errors-only filtering
- **Clickable failures** — red indicators in Recent Checks link directly to the matching log entry
- **SSH credential management** — add, update, and remove accounts via the UI
- **Reset controls** — reset scores or clear logs independently

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Database | SQLite |
| SSH checks | Paramiko |
| HTTP checks | Requests |
| FTP checks | ftplib (stdlib) |
| Frontend | Vanilla JS, Chart.js |

---

## Configuration

All target configuration is at the top of `app.py`:

```python
TARGET_HOST = "10.10.40.50"      # IP of the monitored host
HTTP_URL    = "http://10.10.40.50"
SEARCH_TEXT = "Wikipedia"        # String that must appear in HTTP response
DB_FILE     = "monitor_data.db"
```

Default SSH credentials seeded on first run:

```python
DEFAULT_USERS = [
    ("john",     "john"),
    ("bob",      "bob"),
    ("alice",    "alice"),
    ("patricia", "patricia"),
    ("tyrone",   "tyrone"),
    ("jason",    "jason"),
    ("newuser",  "newuser"),
]
```

These can be managed at runtime through the web UI.

---

## Installation

```bash
pip install flask paramiko requests
python app.py
```

The dashboard is available at `http://0.0.0.0:5000`.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/data` | Current state, score history, recent checks |
| `GET` | `/api/logs` | Service logs (supports `?service=SSH\|HTTP\|FTP` and `?errors=1`) |
| `GET` | `/api/users` | List credentials |
| `POST` | `/api/users` | Add credential `{"username": "", "password": ""}` |
| `PUT` | `/api/users/<id>` | Update password `{"password": ""}` |
| `DELETE` | `/api/users/<id>` | Remove credential |
| `POST` | `/api/reset-scores` | Clear score history and reset in-memory scores to 0 |
| `POST` | `/api/reset-logs` | Clear all log entries |

---

## Database Schema

```sql
history     (id, timestamp, ssh_points, http_points, ftp_points)
credentials (id, username, password)
checks      (id, timestamp, username, ssh_up, http_up, ftp_up)
logs        (id, timestamp, service, status, message)
```

- `history` retains the last **1440** entries (~24 hours at 1/min)
- `checks` retains the last **10** entries (Recent Checks panel)
- `logs` retains the last **300** entries

---

## Check Behaviour

| Service | Method | Success condition |
|---|---|---|
| SSH | Paramiko connect | Authenticated session opens |
| HTTP | GET request | Status 200 and `SEARCH_TEXT` present in body |
| FTP | ftplib anonymous login | Login accepted, no password required |

Each check cycle picks a **random credential** from the database for the SSH attempt. The username of the attempted account is recorded with each check.
