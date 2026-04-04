#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source /home/ayodele/Desktop/marlon-music/venv/bin/activate

echo "Starting Stem Separator server at http://localhost:5000 ..."
python audio_api.py &
SERVER_PID=$!

sleep 2
xdg-open http://localhost:5000 2>/dev/null || true

echo "Server running (PID $SERVER_PID). Press Ctrl+C to stop."
wait $SERVER_PID
