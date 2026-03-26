# ── AI agent (MindRouter / OpenAI-compatible) ─────────────────────────
AGENT_ENABLED    = True        # set False on Kali (no MindRouter access); run agent.py standalone instead
AGENT_API_KEY    = "YOUR_MINDROUTER_API_KEY"
AGENT_BASE_URL   = "https://mindrouter.uidaho.edu/v1"
AGENT_MODEL      = "qwen/qwen3.5-400b"

TARGET_HOST      = "10.10.40.50"
ATTACK_INTERVAL  = 900          # seconds between attack rounds (15 min)
LISTENER_PORT    = 8080         # port the admin panel POSTs to

# SSH credentials to try (mirror of checker's default list)
DEFAULT_CREDS = [
    ("john",     "john"),
    ("bob",      "bob"),
    ("alice",    "alice"),
    ("patricia", "patricia"),
    ("tyrone",   "tyrone"),
    ("jason",    "jason"),
    ("newuser",  "newuser"),
]

BIND_PORT        = 4444                       # port the planted bind shell listens on
BIND_SCRIPT_PATH = "/usr/local/bin/.syscheck" # where the bind shell launcher is written
SYSMON_USER      = "sysmon"
SYSMON_PASS      = "sysmon123"

# Common nginx web root locations to try in order
NGINX_ROOTS = [
    "/var/www/html",
    "/usr/share/nginx/html",
    "/var/www/nginx-default",
    "/usr/share/nginx/www",
]
