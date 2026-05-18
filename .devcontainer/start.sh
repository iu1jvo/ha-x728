#!/bin/bash
# Avvia il daemon x728 in background (simulazione, no hardware reale)
export HW_VERSION="v2.1"
export DAEMON_PORT="8099"
export POLL_INTERVAL="10"
export SHUTDOWN_VOLTAGE="0"
export SHUTDOWN_CAPACITY="0"
export SHUTDOWN_DELAY="10"
export BUZZER_ON_AC_LOSS="false"

echo "Starting X728 daemon in simulation mode..."
python3 /x728_daemon.py &
echo "X728 daemon started with PID $!"
