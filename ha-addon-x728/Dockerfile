ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.12-alpine3.22
FROM $BUILD_FROM

# Install library packages
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-smbus \
    i2c-tools \
    libgpiod
# Install Python packages
RUN pip3 install --no-cache-dir smbus2 python-periphery rpi-lgpio

# Create symlink for lgpio to maintain compatibility with older versions of rpi_lgpio
RUN python3 -c "import os, site; d=site.getsitepackages()[0]; os.symlink(os.path.join(d, 'rpi_lgpio'), os.path.join(d, 'lgpio'))"


WORKDIR /app
COPY x728_daemon.py .
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
