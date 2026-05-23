# ha-x728 — Geekworm X728 UPS for Home Assistant OS

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/iu1jvo6)
[![PayPal](https://img.shields.io/badge/Donate-PayPal-blue?logo=paypal)](https://paypal.me/giulianofavro)
[![GitHub release](https://img.shields.io/github/v/release/iu1jvo/ha-x728?style=flat-square)](https://github.com/iu1jvo/ha-x728/releases/latest)
[![GitHub downloads](https://img.shields.io/github/downloads/iu1jvo/ha-x728/total?style=flat-square)](https://github.com/iu1jvo/ha-x728/releases)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg?style=flat-square)](https://github.com/hacs/integration)
[![Comunity Forum](https://img.shields.io/badge/Community-Forum-success?style=flat-square)](https://community.home-assistant.io/t/meteobridge-weather-logger-integration/154263)


## Index

1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Entities created](#entities-created)
4. [Hardware GPIO reference](#hardware-gpio-reference)
5. [App configuration options](#app-configuration-options)
6. [Installation](#installation)
    1. [App](#1--App)
    2. [Custom Integration (HACS)](#2--custom-integration-hacs)
7. [REST API](#rest-api)
8. [Enable Debug Logging](#enable-debug-logging)
9. [Contribute To The Project](#contribute-to-the-project)
    1. [Integration](#integration)
    2. [App](#app)
10. [Credits](#credits)

## Introduction
Full integration between the [Geekworm X728 UPS HAT](https://wiki.geekworm.com/X728) and **Home Assistant OS** (HAOS).

Consists of two parts that work together:

| Part | What it does |
|---|---|
| **HA App** (`ha-addon-x728/`) | Runs a Python daemon inside a Docker container with access to I2C and GPIO. Reads the hardware and exposes a local REST API. Handles safe shutdown. |
| **Custom Integration** (`custom_components/x728/`) | Pure HA integration that polls the daemon REST API and creates entities. Installable via HACS. |

## Prerequisites

In order to use the HA X728 App, is required the acces to the I2C bus but the I2C bus is not enabled as default.
To enable the I2C bus on HAOS, [follow this istructions](https://www.home-assistant.io/common-tasks/os#enable-i2c).

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

## App configuration options

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

### 1 — App

1. In HA go to **Settings → Apps → Install App → ⋮ → Repositories**
2. Add: `https://github.com/iu1jvo/ha-x728`
3. Install **Geekworm X728 UPS Daemon** and start it
4. Configure options (especially `hw_version`)

### 2 — Custom Integration (HACS)

1. In HACS go to **Integrations → ⋮ → Custom repositories**
2. Add: `https://github.com/iu1jvo/ha-x728` — category **Integration**
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

## Enable Debug Logging

If logs are needed for debugging or reporting an issue, use the following configuration.yaml:

```yaml
logger:
  default: error
  logs:
    custom_components.x728: debug
```

## Contribute To The Project

### Integration

1. Fork and clone the repository.
2. Open in VSCode and choose to open in devcontainer. Must have VSCode devcontainer prerequisites.
3. Run the command container start from VSCode terminal
4. A fresh Home Assistant test instance will install and will eventually be running on port 9125 with this integration running
5. When the container is running, go to http://localhost:9125 and the add x728 from the Integration Page.

### App
1. Fork and clone the repository.
2. Open in VSCode. To test the app, there are two way:
    1. Chose to open in a dev container, the integation will start and run in simulation mode.
    2. run the app script in a terminal:
        ```bash
        cd ha-addon-x728
        SHUTDOWN_VOLTAGE=3.5 SHUTDOWN_CAPACITY=10 DAEMON_PORT=8099 python3 x728_daemon.py
        ```
3. Test the exposed API REST in an another terminal window:
    ```bash
    curl -s http://localhost:8099/api/x728 | python3 -m json.tool
    ```
    or opening `http://localhost:<DAEMON_PORT>` in a browser.

## Credits

Based on the original shell scripts and Python utilities by [iu1jvo](https://github.com/iu1jvo/x728),
which were in turn derived from the official [geekworm-com/x728](https://github.com/geekworm-com/x728) scripts.
