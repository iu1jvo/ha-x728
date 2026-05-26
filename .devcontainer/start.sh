#!/bin/bash
# Start the daemon on background (simulation mode) and keep the container running
export HW_VERSION="v2.1"
export DAEMON_PORT="8099"
export POLL_INTERVAL="10"
export SHUTDOWN_VOLTAGE="0"
export SHUTDOWN_CAPACITY="0"
export SHUTDOWN_DELAY="10"
export BUZZER_ON_AC_LOSS="false"

# Find the workspace directory (fall-back on /workspaces/ha-x728 if empty)
WORKSPACE_DIR="${CONTAINER_WORKSPACE_FOLDER:-/workspaces/ha-x728}"

echo "Using workspace directory: $WORKSPACE_DIR"

echo "Starting X728 daemon in simulation mode..."

APP_DIR="$WORKSPACE_DIR/ha-addon-x728"

if [ -f "$APP_DIR/x728_daemon.py" ]; then
    python3 "$APP_DIR/x728_daemon.py" &
    echo "X728 daemon started with PID $!"
else
    echo "ERROR: x728_daemon.py not found in $APP_DIR"
    exit 1
fi
