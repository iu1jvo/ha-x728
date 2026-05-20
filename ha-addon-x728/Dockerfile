ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.12-alpine3.22
FROM $BUILD_FROM

# Install Python deps
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-smbus \
    py3-lgpio \
    python3-dev \
    gcc \
    libc-dev \
    linux-headers \
    i2c-tools \
    libgpiod \
    libgpiod-dev \
    && pip3 install --no-cache-dir smbus2 lgpio

WORKDIR /app
COPY x728_daemon.py .
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
