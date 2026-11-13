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
import time
import threading
import pwd
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------------------------------------------------------------------
# Read configuration from environment variables (set by the add-on config)
# ---------------------------------------------------------------------------
HW_VERSION = os.environ.get("HW_VERSION", "v2.1")   # supported values: v1, v2.0, v2.1+
PORT = int(os.environ.get("DAEMON_PORT", "8099"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "10"))   # seconds

# Shutdown thresholds (0 = disabled)
SHUTDOWN_VOLTAGE = float(os.environ.get("SHUTDOWN_VOLTAGE", "3.00"))  # Volts
SHUTDOWN_CAPACITY = int(os.environ.get("SHUTDOWN_CAPACITY", "5"))       # %
SHUTDOWN_DELAY = int(os.environ.get("SHUTDOWN_DELAY", "10"))         # seconds
PULSE_SECONDS = 2.0   # GPIO shutdown pulse; Geekworm: must not exceed 2 s
AC_CONFIRM_SECONDS = int(os.environ.get("AC_CONFIRM_SECONDS", "20"))  # AC lost for this long

BUZZER_ON_AC_LOSS = os.environ.get("BUZZER_ON_AC_LOSS", "true").lower() == "true"
# "autodetect" or specific path like "/dev/gpiochip0"
GPIO_CHIP = os.environ.get("GPIO_CHIP", "autodetect")

CHIP_FALLBACK = "/dev/gpiochip0"  # used if autodetect fails


def normalize_hw_version(hw_version: str) -> str:
    """Normalize hardware version strings to the groups we actually support."""
    value = (hw_version or "").strip().lower().replace(" ", "")
    aliases = {
        "v1": "v1",
        "v1.x": "v1",
        "v1.x/v2.0": "v1",
        "v2.0": "v2.0",
        "v2.1": "v2.1+",
        "v2.1+": "v2.1+",
    }
    if value in aliases:
        return aliases[value]
    if value.startswith("v2.") and value[3:]:
        try:
            int(value[3:].replace(".", ""))
        except ValueError:
            pass
        else:
            return "v2.1+"
    return "v2.1+"


# GPIO pin selection based on the supported hardware families
HW_VERSION_NORMALIZED = normalize_hw_version(HW_VERSION)
if HW_VERSION_NORMALIZED == "v1":
    GPIO_SHUTDOWN = 13
    HW_LABEL = "X728 v1"
elif HW_VERSION_NORMALIZED == "v2.0":
    GPIO_SHUTDOWN = 13
    HW_LABEL = "X728 v2.0"
else:
    GPIO_SHUTDOWN = 26
    HW_LABEL = "X728 v2.1+"

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
# Global Hardware State & Graceful Imports
# ---------------------------------------------------------------------------
gpio_lines = {}  # unused with gpiod v2
GPIO_AVAILABLE = False  # pylint: disable=invalid-name
I2C_AVAILABLE = False  # pylint: disable=invalid-name

try:
    import gpiod
    GPIO_AVAILABLE = True  # pylint: disable=invalid-name
except (ImportError, RuntimeError) as err:
    log.warning("gpiod not available – GPIO running in SIMULATION mode (%s)", err)

try:
    import smbus2
    I2C_AVAILABLE = True  # pylint: disable=invalid-name
except (ImportError, RuntimeError) as err:
    log.warning("smbus2 not available – I2C running in SIMULATION mode (%s)", err)

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
# Known GPIO controller names per platform
_KNOWN_CONTROLLERS = [
    "pinctrl-rp1",      # Raspberry Pi 5
    "pinctrl-bcm2711",  # Raspberry Pi 4
    "pinctrl-bcm2835",  # Raspberry Pi 3 / Zero
]

# gpiod v2 request handle (set in gpio_setup, used in gpio_read/write)
_gpio_request = None  # pylint: disable=invalid-name


def find_gpio_chip() -> str:
    """Auto-detect the correct gpiochip by controller name (gpiod v2 API).

    Scans /dev/gpiochip* and matches against known RPi controller labels.
    Falls back to GPIO_CHIP env var if detection fails.
    """
    for i in range(5):
        path = f"/dev/gpiochip{i}"
        if not os.path.exists(path):
            continue
        try:
            with gpiod.Chip(path) as chip:
                label = chip.get_info().label
                for controller in _KNOWN_CONTROLLERS:
                    if controller in label:
                        log.info("Auto-detected GPIO chip: %s (label: %s)", path, label)
                        return path
        except Exception:  # pylint: disable=broad-except
            continue
    log.warning("GPIO chip auto-detection failed, using fallback: %s", CHIP_FALLBACK)
    return CHIP_FALLBACK


def gpio_setup():
    """Initialise GPIO pins via gpiod v2 API."""
    global _gpio_request  # pylint: disable=global-statement

    chip_path = find_gpio_chip() if GPIO_CHIP == "autodetect" else GPIO_CHIP

    # Build line configuration: INPUT for PLD, OUTPUT for the rest
    line_config = {
        GPIO_PLD: gpiod.LineSettings(
            direction=gpiod.line.Direction.INPUT
        ),
        GPIO_BUZZER: gpiod.LineSettings(
            direction=gpiod.line.Direction.OUTPUT,
            output_value=gpiod.line.Value.INACTIVE,
        ),
        GPIO_BOOT: gpiod.LineSettings(
            direction=gpiod.line.Direction.OUTPUT,
            output_value=gpiod.line.Value.ACTIVE,    # HIGH = system is up
        ),
        GPIO_SHUTDOWN: gpiod.LineSettings(
            direction=gpiod.line.Direction.OUTPUT,
            output_value=gpiod.line.Value.INACTIVE,
        ),
    }

    _gpio_request = gpiod.request_lines(
        chip_path,
        consumer="x728-daemon",
        config=line_config,
    )

    log.info(
        "GPIO configured via gpiod v2 (%s). Shutdown pin: GPIO%d",
        chip_path, GPIO_SHUTDOWN,
    )


def gpio_read(pin: int) -> int:
    """Read the current value of a GPIO pin (1=high, 0=low)."""
    if _gpio_request is None:
        return 0
    val = _gpio_request.get_value(pin)
    return 1 if val == gpiod.line.Value.ACTIVE else 0


def gpio_write(pin: int, value: int) -> None:
    """Write a value to a GPIO pin (1=high, 0=low)."""
    if _gpio_request is None:
        return
    gpio_val = gpiod.line.Value.ACTIVE if value else gpiod.line.Value.INACTIVE
    _gpio_request.set_value(pin, gpio_val)


def read_voltage(bus) -> float:
    """Read battery voltage from MAX17040 via I2C."""
    raw = bus.read_word_data(I2C_ADDR, 2)
    swapped = struct.unpack("<H", struct.pack(">H", raw))[0]
    return round(swapped * 1.25 / 1000 / 16, 3)


def read_capacity(bus) -> int:
    """Read battery capacity from MAX17040 via I2C (clamped to 0-100 %).

    The MAX17040 state of charge can exceed 100 % (103 % seen on a full pack)."""
    raw = bus.read_word_data(I2C_ADDR, 4)
    swapped = struct.unpack("<H", struct.pack(">H", raw))[0]
    return max(0, min(100, int(swapped / 256)))


def supervisor_host_shutdown() -> bool:
    """Ask the Supervisor to shut down the host (graceful HAOS poweroff).

    Needs ``hassio_api: true`` and ``hassio_role: manager`` in config.yaml."""
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        log.error("SUPERVISOR_TOKEN missing: hassio_api not enabled?")
        return False
    req = urllib.request.Request(
        "http://supervisor/host/shutdown", data=b"{}", method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            log.warning("Supervisor host/shutdown -> HTTP %s", resp.status)
            return True
    except Exception as e:  # pylint: disable=broad-except
        log.error("Supervisor host/shutdown FAILED: %s", e)
        return False


def pulse_ups_shutdown():
    """Send one HIGH pulse on the UPS shutdown pin.

    The board cuts the 5 V output some tens of seconds after the pulse."""
    if not (GPIO_AVAILABLE and _gpio_request is not None):
        log.error("Pulse SKIPPED: GPIO not available")
        return
    log.warning("Pulse GPIO%d HIGH for %.1fs", GPIO_SHUTDOWN, PULSE_SECONDS)
    gpio_write(GPIO_SHUTDOWN, 1)
    time.sleep(PULSE_SECONDS)
    gpio_write(GPIO_SHUTDOWN, 0)
    log.warning("Pulse finished")


def _ac_ok_now() -> bool:
    """True if the PLD pin says AC is present (LOW = AC ok)."""
    try:
        return bool(GPIO_AVAILABLE and _gpio_request is not None
                    and not gpio_read(GPIO_PLD))
    except Exception:  # pylint: disable=broad-except
        return False


_ac_lost_since = None  # monotonic time since AC has been continuously lost


def ac_sampler():
    """Sample the PLD pin every second and remember for how long AC has been
    lost without interruption (a flapping PLD signal keeps resetting it)."""
    global _ac_lost_since  # pylint: disable=global-statement
    last = None
    last_log = 0.0
    while True:
        time.sleep(1)
        if not (GPIO_AVAILABLE and _gpio_request is not None):
            continue
        try:
            lost = bool(gpio_read(GPIO_PLD))
        except Exception:  # pylint: disable=broad-except
            continue
        now = time.monotonic()
        if lost:
            if _ac_lost_since is None:
                _ac_lost_since = now
        else:
            _ac_lost_since = None
        if lost != last:
            if last is not None and now - last_log >= 3:
                log.warning("AC LOST" if lost else "AC RESTORED")
                last_log = now
            last = lost


def ac_lost_confirmed() -> bool:
    """True once AC has been continuously lost for AC_CONFIRM_SECONDS."""
    since = _ac_lost_since
    return since is not None and time.monotonic() - since >= AC_CONFIRM_SECONDS


def do_shutdown():
    """Grace delay (cancelled if AC returns), UPS shutdown pulse, then
    graceful HAOS shutdown.

    The pulse is sent BEFORE the host shutdown: HAOS stops the app container
    while shutting down, so a pulse sent afterwards may never be sent.
    Once the pulse has been sent the shutdown can no longer be cancelled."""
    log.warning("SHUTDOWN SEQUENCE STARTED (delay %ds)", SHUTDOWN_DELAY)
    deadline = time.monotonic() + SHUTDOWN_DELAY
    ok_count = 0
    while time.monotonic() < deadline:
        time.sleep(1)
        ok_count = ok_count + 1 if _ac_ok_now() else 0
        if ok_count >= 3:
            log.warning("AC restored during delay: shutdown CANCELLED")
            with state_lock:
                current_state["shutdown_triggered"] = False
            return
    pulse_ups_shutdown()
    time.sleep(1)
    supervisor_host_shutdown()


def buzzer_beep(count: int = 1, on_ms: int = 100, off_ms: int = 100):
    """Sound the buzzer for the given number of pulses."""
    if not GPIO_AVAILABLE:
        return
    for _ in range(count):
        gpio_write(GPIO_BUZZER, 1)
        time.sleep(on_ms / 1000)
        gpio_write(GPIO_BUZZER, 0)
        time.sleep(off_ms / 1000)


# ---------------------------------------------------------------------------
# Monitor thread
# ---------------------------------------------------------------------------

def monitor_loop():
    """Background thread: poll hardware and update shared state."""
    bus = None
    if GPIO_AVAILABLE:
        try:
            gpio_setup()
        except Exception as e:  # pylint: disable=broad-except
            log.error("GPIO hardware setup failed. Running GPIO in simulation: %s", e)

    if I2C_AVAILABLE:
        try:
            bus = smbus2.SMBus(I2C_BUS)
        except Exception as e:  # pylint: disable=broad-except
            log.error("Cannot open I2C bus: %s", e)

    while True:
        try:
            voltage = read_voltage(bus) if bus else None
            capacity = read_capacity(bus) if bus else None
            ac_present = (
                not bool(gpio_read(GPIO_PLD))
                if GPIO_AVAILABLE and _gpio_request is not None
                else None
            )

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
            if GPIO_AVAILABLE and _gpio_request is not None \
                    and BUZZER_ON_AC_LOSS and ac_present is False:
                buzzer_beep(count=1, on_ms=100, off_ms=100)

            # --- Shutdown logic (only while running on battery) ---
            with state_lock:
                already = current_state.get("shutdown_triggered")
            if battery_low and ac_lost_confirmed() and not already:
                log.warning(
                    "Battery critical (%.2fV / %d%%) – initiating shutdown in %ds",
                    voltage or 0, capacity or 0, SHUTDOWN_DELAY,
                )
                with state_lock:
                    current_state["shutdown_triggered"] = True
                t = threading.Thread(target=do_shutdown, daemon=True)
                t.start()

        except Exception as e:  # pylint: disable=broad-except
            log.error("Monitor error: %s", e)
            with state_lock:
                current_state["error"] = str(e)

        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# HTTP REST API
# ---------------------------------------------------------------------------

class X728Handler(BaseHTTPRequestHandler):
    """Minimal HTTP handler exposing /api/x728."""

    def log_message(self, fmt, *args):  # pylint: disable=arguments-differ
        pass  # suppress per-request access log noise

    def do_GET(self):   # pylint: disable=invalid-name
        """Handle GET requests."""
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
    log.info("Script executed by: %s (UID: %d)", pwd.getpwuid(os.getuid()).pw_name, os.getuid())

    threading.Thread(target=ac_sampler, daemon=True, name="x728-ac").start()
    monitor = threading.Thread(target=monitor_loop, daemon=True, name="x728-monitor")
    monitor.start()

    server = HTTPServer(("0.0.0.0", PORT), X728Handler)
    log.info("REST API listening on http://0.0.0.0:%d/api/x728", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Daemon stopped.")
        if GPIO_AVAILABLE and _gpio_request is not None:
            _gpio_request.release()
