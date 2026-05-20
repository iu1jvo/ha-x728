ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.12-alpine3.22
FROM $BUILD_FROM

# Install library packages
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-smbus \
    py3-gpiod \
    i2c-tools

# Install Python packages
RUN pip3 install --no-cache-dir smbus2

# Create a compatibility wrapper for lgpio, which is used by the original x728_daemon.py.
RUN python3 -c " \
import site, os; \
path = os.path.join(site.getsitepackages()[0], 'lgpio.py'); \
f = open(path, 'w'); \
f.write('import gpiod\n\nclass Wrapper:\n    def __init__(self, num):\n        self.chip = gpiod.Chip(f\"/dev/gpiochip{num}\")\n\ndef gpiochip_open(num):\n    return Wrapper(num)\n'); \
f.close()"

WORKDIR /app
COPY x728_daemon.py .
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
