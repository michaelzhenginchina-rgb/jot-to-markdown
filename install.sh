#!/bin/bash
# Install jot: run the server at login, then open the bookmarklet install page.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${JOT_PORT:-7777}"

# Remember where the store was pointed last time, so a bare ./install.sh does
# not silently move it back to the default and orphan the existing notes.
STORE_DEFAULT="$HOME/highlights"
if [ -f "$HERE/.jot-store" ]; then
  STORE_DEFAULT="$(cat "$HERE/.jot-store")"
fi
STORE="${JOT_STORE:-$STORE_DEFAULT}"
printf '%s\n' "$STORE" > "$HERE/.jot-store"
LABEL="com.jot.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Prefer the project venv - that is where the anthropic SDK lives, and without
# it the 生词 lookups silently degrade to "unconfigured".
if [ -x "$HERE/.venv/bin/python" ]; then
  PY="$HERE/.venv/bin/python"
else
  PY="$(command -v python3 || true)"
  echo "note: no .venv found; 生词 lookups will be disabled." >&2
  echo "      create it with:  python3 -m venv .venv && .venv/bin/pip install anthropic" >&2
fi
if [ -z "$PY" ]; then
  echo "python3 not found. Install it (xcode-select --install) and re-run." >&2
  exit 1
fi

mkdir -p "$STORE" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$HERE/server.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>JOT_PORT</key><string>$PORT</string>
    <key>JOT_STORE</key><string>$STORE</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$STORE/.jot.log</string>
  <key>StandardErrorPath</key><string>$STORE/.jot.log</string>
</dict>
</plist>
PLIST_EOF

DOMAIN="gui/$(id -u)"

# Unload any previous copy, then wait for launchd to actually finish. bootout is
# asynchronous, and bootstrapping into a half-torn-down service fails with
# "Bootstrap failed: 5: Input/output error".
if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  for _ in $(seq 1 40); do
    launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1 || break
    sleep 0.25
  done
fi

# The old process may still hold the port for a moment; binding too early would
# leave KeepAlive crash-looping.
for _ in $(seq 1 40); do
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 || break
  sleep 0.25
done
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is held by something else:" >&2
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >&2
  echo "Re-run with a different port, e.g.  JOT_PORT=7788 ./install.sh" >&2
  exit 1
fi

for attempt in 1 2 3 4 5; do
  if ERR="$(launchctl bootstrap "$DOMAIN" "$PLIST" 2>&1)"; then
    break
  fi
  if [ "$attempt" -eq 5 ]; then
    echo "launchctl bootstrap failed: $ERR" >&2
    exit 1
  fi
  sleep 1
done

# Confirm it is actually answering, not just registered.
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/ping" >/dev/null 2>&1; then
    OK=1; break
  fi
  sleep 0.3
done

if [ "${OK:-}" != "1" ]; then
  echo "Server registered but did not answer on port $PORT. Last log lines:" >&2
  tail -20 "$STORE/.jot.log" >&2 2>/dev/null || true
  exit 1
fi

JOT_PORT="$PORT" JOT_STORE="$STORE" "$PY" "$HERE/build.py"

echo
echo "jot is running on 127.0.0.1:$PORT, saving to $STORE"
# The page is only needed the first time, to drag the bookmarklet onto the
# bookmarks bar. Opening it on every restart is just noise.
if [ "${JOT_OPEN_INSTALL:-}" = "1" ]; then
  open "$HERE/install.html"
else
  echo "Bookmarklet page: open $HERE/install.html  (only needed once)"
fi
