#!/usr/bin/with-contenv bashio
# Read options from the HA add-on configuration and pass them
# to the Python daemon as environment variables.

bashio::log.info "Starting X728 UPS Daemon..."

export HW_VERSION=$(bashio::config 'hw_version')
export DAEMON_PORT=$(bashio::config 'daemon_port')
export POLL_INTERVAL=$(bashio::config 'poll_interval')
export SHUTDOWN_VOLTAGE=$(bashio::config 'shutdown_voltage')
export SHUTDOWN_CAPACITY=$(bashio::config 'shutdown_capacity')
export SHUTDOWN_DELAY=$(bashio::config 'shutdown_delay')
export AC_CONFIRM_SECONDS=$(bashio::config 'ac_confirm_seconds')
export PULSE_SECONDS=$(bashio::config 'pulse_seconds')
export BUZZER_ON_AC_LOSS=$(bashio::config 'buzzer_on_ac_loss')
export BUZZER_INTERVAL=$(bashio::config 'buzzer_interval')
export BUZZER_BEEP_MS=$(bashio::config 'buzzer_beep_ms')
export BUZZER_VOLUME=$(bashio::config 'buzzer_volume')
export GPIO_CHIP=$(bashio::config 'gpio_chip')

bashio::log.info "--- GPIO hardware info ---"
bashio::log.info "Available gpiochip devices:"
for chip in /dev/gpiochip*; do
    bashio::log.info "  ${chip}"
done

bashio::log.info "GPIO chip labels:"
for label_file in /sys/class/gpio/gpiochip*/label; do
    chip=$(echo "${label_file}" | grep -o 'gpiochip[0-9]*')
    label=$(cat "${label_file}" 2>/dev/null || echo "unknown")
    bashio::log.info "  ${chip} -> ${label}"
done

bashio::log.info "--- end GPIO info ---"


bashio::log.info "--- Environment Variables ---"
bashio::log.info "hw_version:        ${HW_VERSION}"
bashio::log.info "daemon_port:       ${DAEMON_PORT}"
bashio::log.info "poll_interval:     ${POLL_INTERVAL}s"
bashio::log.info "shutdown_voltage:  ${SHUTDOWN_VOLTAGE}V"
bashio::log.info "shutdown_capacity: ${SHUTDOWN_CAPACITY}%"
bashio::log.info "shutdown_delay:    ${SHUTDOWN_DELAY}s"
bashio::log.info "ac_confirm_seconds: ${AC_CONFIRM_SECONDS}s"
bashio::log.info "pulse_seconds:    ${PULSE_SECONDS}s"
bashio::log.info "buzzer_on_ac_loss: ${BUZZER_ON_AC_LOSS}"
bashio::log.info "buzzer:            every ${BUZZER_INTERVAL}s, ${BUZZER_BEEP_MS} ms, volume ${BUZZER_VOLUME}%"
bashio::log.info "gpio_chip:         ${GPIO_CHIP}"
bashio::log.info "--- end Environment Variables ---"



exec python3 /app/x728_daemon.py
