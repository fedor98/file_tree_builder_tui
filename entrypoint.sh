#!/bin/sh
set -e

# Optional: Falls jemand ROOT_DIR setzt, arbeiten wir darin; sonst in /data (Mount).
if [ -n "$ROOT_DIR" ]; then
  cd "$ROOT_DIR" || { echo "ROOT_DIR $ROOT_DIR nicht gefunden"; exit 1; }
fi

exec "$@"