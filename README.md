# ha-x728 — Geekworm X728 UPS for Home Assistant OS

Full integration between the [Geekworm X728 UPS HAT](https://wiki.geekworm.com/X728) and **Home Assistant OS** (HAOS).

Consists of two parts that work together:

| Part | What it does |
|---|---|
| **HA Add-on** (`ha-addon-x728/`) | Runs a Python daemon inside a Docker container with access to I2C and GPIO. Reads the hardware and exposes a local REST API. Handles safe shutdown. |
| **Custom Integration** (`custom_components/x728/`) | Pure HA integration that polls the daemon REST API and creates entities. Installable via HACS. |

---

## Entities created

| Entity | Type | Description |
|---|---|---|
| `sensor.x728_battery_voltage` | Sensor | Battery voltage in Volts |
| `sensor.x728_battery_level` | Sensor | Battery charge in % |
| `sensor.x728_hardware_version` | Sensor (diagnostic) | Detected HW version string |
| `binary_sensor.x728_ac_power` | Binary sensor | ON = AC power present |
| `binary_sensor.x728_battery_low` | Binary sensor | ON = below shutdown threshold |
| `binary_sensor.x728_charging` | Binary sensor | ON = currently charging |

---

## Hardware GPIO reference

| GPIO | Direction | Function |
|---|---|---|
| 6 | IN | PLD – Power Loss Detection (HIGH = AC lost) |
| 12 | OUT | BOOT – held HIGH while system is running |
| 13 | OUT | Shutdown trigger (**v1.x / v2.0** only) |
| 20 | OUT | Buzzer |
| 26 | OUT | Shutdown trigger (**v2.1 / v2.2 / v2.3**) |

---

## Add-on configuration options

| Option | Default | Description |
|---|---|---|
| `hw_version` | `v2.1` | Hardware version — selects shutdown GPIO pin (13 for v1.x/v2.0, 26 for v2.1+) |
| `daemon_port` | `8099` | TCP port the REST API listens on |
| `poll_interval` | `10` | How often to read hardware (seconds) |
| `shutdown_voltage` | `3.00` | Shutdown if battery voltage < this value (V). Set `0` to disable. |
| `shutdown_capacity` | `5` | Shutdown if battery capacity < this value (%). Set `0` to disable. |
| `shutdown_delay` | `10` | Seconds between HA shutdown command and UPS power-off |
| `buzzer_on_ac_loss` | `true` | Beep the buzzer when AC power is lost |

---

## Installation

### 1 — Add-on

1. In HA go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add: `https://github.com/<your-user>/ha-x728`
3. Install **Geekworm X728 UPS Daemon** and start it
4. Configure options (especially `hw_version`)

### 2 — Custom Integration (HACS)

1. In HACS go to **Integrations → ⋮ → Custom repositories**
2. Add: `https://github.com/<your-user>/ha-x728` — category **Integration**
3. Install **Geekworm X728 UPS**
4. Go to **Settings → Integrations → Add Integration → X728**
5. Host: `localhost`, Port: `8099` (or whatever you configured)

---

## REST API

The daemon exposes a single endpoint:

```
GET http://localhost:8099/api/x728
```

Response example:
```json
{
  "voltage": 4.05,
  "capacity": 87,
  "ac_present": true,
  "battery_low": false,
  "charging": false,
  "hw_version": "X728 v2.1",
  "shutdown_triggered": false,
  "error": null
}
```

---

## Credits

Based on the original shell scripts and Python utilities by [iu1jvo](https://github.com/iu1jvo/x728),
which were in turn derived from the official [geekworm-com/x728](https://github.com/geekworm-com/x728) scripts.
