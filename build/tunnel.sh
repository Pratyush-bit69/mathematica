#!/usr/bin/env bash
# Keep a public tunnel to the local MATHEMATICA server alive.
#
#   ./build/tunnel.sh            run in the foreground (Ctrl-C stops it)
#   ./build/tunnel.sh --daemon   run in the background
#
# The current public URL is written to ./live-url.txt and to
# http://127.0.0.1:8080/live-url.txt so it can always be found locally.
#   ./build/tunnel.sh --daemon  run detached (pid in .tunnel.pid)
#   ./build/tunnel.sh --stop    stop the detached daemon
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLOUDFLARED=/tmp/opencode/cloudflared
PORT=8080
URLFILE="$ROOT/live-url.txt"
LOG=/tmp/opencode/tunnel.log
PIDFILE="$ROOT/.tunnel.pid"

if [ ! -x "$CLOUDFLARED" ]; then
  echo "cloudflared not found at $CLOUDFLARED" >&2
  exit 1
fi

# --daemon: re-launch this script detached, then return immediately
if [ "${1:-}" = "--daemon" ]; then
  DAEMON_LOG=/tmp/opencode/tunnel-daemon.log
  nohup "$0" >> "$DAEMON_LOG" 2>&1 &
  echo $! > "$PIDFILE"
  echo "tunnel daemon started (pid $(cat "$PIDFILE")), log $DAEMON_LOG"
  exit 0
fi

if [ "${1:-}" = "--stop" ]; then
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" && echo "tunnel daemon stopped"
  else
    echo "no tunnel daemon running"
  fi
  rm -f "$PIDFILE"
  exit 0
fi

current=""
pid=""

cleanup() {
  [ -n "$pid" ] && kill "$pid" 2>/dev/null
  return 0
}
trap cleanup EXIT
publish() {
  local url="$1"
  [ -z "$url" ] && return
  printf '%s\n' "$url" > "$URLFILE"
  cp "$URLFILE" /tmp/opencode/live-url.txt 2>/dev/null
  echo "$url"
}

while true; do
  : > "$LOG"
  "$CLOUDFLARED" tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate \
      >> "$LOG" 2>&1 &
  pid=$!
  # wait for the URL to appear
  for _ in $(seq 1 40); do
    sleep 1
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1)
    if [ -n "$url" ] && [ "$url" != "$current" ]; then
      current="$url"
      publish "$url" >/dev/null
      echo "tunnel up: $url"
      break
    fi
    kill -0 "$pid" 2>/dev/null || break
  done
  # keep the tunnel alive until it dies
  while kill -0 "$pid" 2>/dev/null; do
    sleep 5
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1)
    if [ -n "$url" ] && [ "$url" != "$current" ]; then
      current="$url"; publish "$url" >/dev/null
      echo "tunnel changed: $url"
    fi
  done
  echo "tunnel died, restarting in 3s..." >&2
  sleep 3
done
