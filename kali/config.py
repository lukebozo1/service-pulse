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

# Common nginx web root locations to try in order
NGINX_ROOTS = [
    "/var/www/html",
    "/usr/share/nginx/html",
    "/var/www/nginx-default",
    "/usr/share/nginx/www",
]
