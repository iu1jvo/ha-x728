#!/usr/bin/env python3
"""
X728 UPS Daemon for Home Assistant OS Add-on.

Reads battery voltage/capacity via I2C (MAX17040 @ 0x36),
AC power loss via GPIO6 (PLD pin), and exposes a REST API
on http://0.0.0.0:<PORT>/api/x728

Also handles safe shutdown when battery falls below the
configured threshold voltage or capacity.

Hardware GPIO map:
  GPIO6  -> PLD  (Power Loss Detection, LOW=AC OK, HIGH=AC Lost)
  GPIO20 -> Buzzer
  GPIO26 -> Software shutdown trigger (v2.1+)
  GPIO13 -> Software shutdown trigger (v1.x / v2.0)
  GPIO5  -> Hardware shutdown signal (input)
  GPIO12 -> BOOT signal (output, kept HIGH while running)
"""

import json
import logging
import os
import struct
import subprocess
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------------------------------------------------------------------
# Read configuration from environment variables (set by the add-on config)
# ---------------------------------------------------------------------------
HW_VERSION = os.environ.get("HW_VERSION", "v2.1")   # "v1.x / v2.0" or "v2.1+"
PORT = int(os.environ.get("DAEMON_PORT", "8099"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "10"))   # seconds

# Shutdown thresholds (0 = disabled)
SHUTDOWN_VOLTAGE = float(os.environ.get("SHUTDOWN_VOLTAGE", "3.00"))  # Volts
SHUTDOWN_CAPACITY = int(os.environ.get("SHUTDOWN_CAPACITY", "5"))       # %
SHUTDOWN_DELAY = int(os.environ.get("SHUTDOWN_DELAY", "10"))         # seconds

BUZZER_ON_AC_LOSS = os.environ.get("BUZZER_ON_AC_LOSS", "true").lower() == "true"

# GPIO pin selection based on hardware version
if HW_VERSION.startswith("v1") or HW_VERSION == "v2.0":
    GPIO_SHUTDOWN = 13
    HW_LABEL = "X728 v1.x/v2.0"
else:
    GPIO_SHUTDOWN = 26
    HW_LABEL = f"X728 {HW_VERSION}"

GPIO_PLD = 6
GPIO_BUZZER = 20
GPIO_BOOT = 12

I2C_ADDR = 0x36
I2C_BUS = 1

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [x728-daemon] %(levelname)s: %(message)s",
)
log = logging.getLogger("x728")

# ---------------------------------------------------------------------------
# Import RPi.GPIO gracefully (may not be available in dev/test environments)
# ---------------------------------------------------------------------------
try:
    import RPi.GPIO as GPIO
    import smbus
    GPIO_AVAILABLE = True
except ImportError:
    log.warning("RPi.GPIO / smbus not available – running in SIMULATION mode")
    GPIO_AVAILABLE = False

# ---------------------------------------------------------------------------
# Shared state (written by the monitor thread, read by the HTTP thread)
# ---------------------------------------------------------------------------
state_lock = threading.Lock()
current_state: dict = {
    "voltage": None,
    "capacity": None,
    "ac_present": None,
    "battery_low": False,
    "charging": False,
    "hw_version": HW_LABEL,
    "shutdown_triggered": False,
    "error": None,
}


# ---------------------------------------------------------------------------
# Hardware helpers
# ---------------------------------------------------------------------------

def gpio_setup():
    """Initialise GPIO pins."""
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(GPIO_PLD,    GPIO.IN)
    GPIO.setup(GPIO_BUZZER, GPIO.OUT)
    GPIO.setup(GPIO_BOOT,   GPIO.OUT)
    GPIO.setup(GPIO_SHUTDOWN, GPIO.OUT)
    GPIO.output(GPIO_BOOT, GPIO.HIGH)   # signal: system is up
    GPIO.output(GPIO_BUZZER, GPIO.LOW)
    GPIO.output(GPIO_SHUTDOWN, GPIO.LOW)
    log.info("GPIO configured. Shutdown pin: GPIO%d", GPIO_SHUTDOWN)


def read_voltage(bus) -> float:
    raw = bus.read_word_data(I2C_ADDR, 2)
    swapped = struct.unpack("<H", struct.pack(">H", raw))[0]
    return round(swapped * 1.25 / 1000 / 16, 3)


def read_capacity(bus) -> int:
    raw = bus.read_word_data(I2C_ADDR, 4)
    swapped = struct.unpack("<H", struct.pack(">H", raw))[0]
    return int(swapped / 256)


def do_shutdown():
    """Perform a graceful HA shutdown then cut UPS power."""
    log.warning("SHUTDOWN SEQUENCE STARTED")
    # 1. Ask HA OS to shut down gracefully
    try:
        subprocess.run(["ha", "os", "shutdown"], timeout=30)
    except Exception as e:
        log.error("Failed to call 'ha os shutdown': %s", e)
    # 2. Wait for OS to settle, then pulse the UPS shutdown pin
    time.sleep(SHUTDOWN_DELAY)
    if GPIO_AVAILABLE:
        GPIO.output(GPIO_SHUTDOWN, GPIO.HIGH)
        time.sleep(3)
        GPIO.output(GPIO_SHUTDOWN, GPIO.LOW)


def buzzer_beep(count: int = 1, on_ms: int = 100, off_ms: int = 100):
    if not GPIO_AVAILABLE:
        return
    for _ in range(count):
        GPIO.output(GPIO_BUZZER, GPIO.HIGH)
        time.sleep(on_ms / 1000)
        GPIO.output(GPIO_BUZZER, GPIO.LOW)
        time.sleep(off_ms / 1000)


# ---------------------------------------------------------------------------
# Monitor thread
# ---------------------------------------------------------------------------

def monitor_loop():
    """Background thread: poll hardware and update shared state."""
    bus = None
    if GPIO_AVAILABLE:
        gpio_setup()
        try:
            bus = smbus.SMBus(I2C_BUS)
        except Exception as e:
            log.error("Cannot open I2C bus: %s", e)

    shutdown_pending = False

    while True:
        try:
            voltage  = read_voltage(bus) if bus else None
            capacity = read_capacity(bus) if bus else None
            ac_present = not bool(GPIO.input(GPIO_PLD)) if GPIO_AVAILABLE else None

            # Derive states
            battery_low = False
            if voltage is not None and SHUTDOWN_VOLTAGE > 0 and voltage < SHUTDOWN_VOLTAGE:
                battery_low = True
            if capacity is not None and SHUTDOWN_CAPACITY > 0 and capacity < SHUTDOWN_CAPACITY:
                battery_low = True

            # Charging: AC present and not full
            charging = bool(ac_present and capacity is not None and capacity < 100)

            with state_lock:
                current_state.update({
                    "voltage":   voltage,
                    "capacity":  capacity,
                    "ac_present": ac_present,
                    "battery_low": battery_low,
                    "charging":  charging,
                    "error":     None,
                })

            # --- AC loss buzzer ---
            if GPIO_AVAILABLE and BUZZER_ON_AC_LOSS and ac_present is False:
                buzzer_beep(count=1, on_ms=100, off_ms=100)

            # --- Shutdown logic ---
            if battery_low and not shutdown_pending:
                shutdown_pending = True
                log.warning(
                    "Battery critical (%.2fV / %d%%) – initiating shutdown in %ds",
                    voltage or 0, capacity or 0, SHUTDOWN_DELAY,
                )
                with state_lock:
                    current_state["shutdown_triggered"] = True
                t = threading.Thread(target=do_shutdown, daemon=True)
                t.start()

        except Exception as e:
            log.error("Monitor error: %s", e)
            with state_lock:
                current_state["error"] = str(e)

        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# HTTP REST API
# ---------------------------------------------------------------------------

class X728Handler(BaseHTTPRequestHandler):
    """Minimal HTTP handler exposing /api/x728."""

    def log_message(self, fmt, *args):
        pass  # suppress per-request access log noise

    def do_GET(self):
        if self.path == "/api/x728":
            with state_lock:
                payload = json.dumps(current_state).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Starting X728 daemon | hw=%s | port=%d | poll=%ds", HW_LABEL, PORT, POLL_INTERVAL)
    log.info(
        "Shutdown thresholds: voltage<%.2fV OR capacity<%d%% (delay %ds)",
        SHUTDOWN_VOLTAGE, SHUTDOWN_CAPACITY, SHUTDOWN_DELAY,
    )

    monitor = threading.Thread(target=monitor_loop, daemon=True, name="x728-monitor")
    monitor.start()

    server = HTTPServer(("0.0.0.0", PORT), X728Handler)
    log.info("REST API listening on http://0.0.0.0:%d/api/x728", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Daemon stopped.")
        if GPIO_AVAILABLE:
            GPIO.cleanup()
