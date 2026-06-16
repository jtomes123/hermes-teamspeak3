FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download TS3 client at build time
ARG TS3_CLIENT_URL="https://files.teamspeak-services.com/releases/client/3.6.2/TeamSpeak3-Client-linux_amd64-3.6.2.run"
ARG TS3_CLIENT_CHECKSUM="sha256:b9e2a2a04a7c86d23971f94f0be436369ff0af9f2df2da8f4c3d6f82a2c2b0a5"
ARG TS3_CLIENT_DIR="/opt/ts3client"

COPY scripts/download_ts3_client.sh /tmp/download_ts3_client.sh
RUN chmod +x /tmp/download_ts3_client.sh \
    && /tmp/download_ts3_client.sh "${TS3_CLIENT_URL}" "${TS3_CLIENT_CHECKSUM}" "${TS3_CLIENT_DIR}" \
    && rm /tmp/download_ts3_client.sh

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    pulseaudio \
    pulseaudio-utils \
    ffmpeg \
    libopus0 \
    libopus-dev \
    portaudio19-dev \
    espeak-ng \
    libasound2 \
    libasound2-plugins \
    libpulse0 \
    libpulse-dev \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxrandr2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxcb1 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-util1 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libdbus-1-3 \
    libgl1 \
    libglib2.0-0 \
    libfontconfig1 \
    libfreetype6 \
    libxi6 \
    libxtst6 \
    libnss3 \
    libnspr4 \
    libc6 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 hermes \
    && useradd -m -u 1000 -g hermes -s /bin/bash hermes

# Copy TS3 client from builder
COPY --from=builder /opt/ts3client /opt/ts3client
RUN chown -R hermes:hermes /opt/ts3client

# Install Python package
COPY . /app
RUN pip install --no-cache-dir /app

# Setup directories
RUN mkdir -p /home/hermes/.hermes /home/hermes/ts3_data \
    && chown -R hermes:hermes /home/hermes \
    && mkdir -p /run/pulse \
    && chown hermes:hermes /run/pulse

# Copy scripts
COPY scripts /scripts
RUN chmod +x /scripts/*.sh

# Copy entrypoint and healthcheck
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/healthcheck.sh /usr/local/bin/healthcheck.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/healthcheck.sh

VOLUME ["/home/hermes/.hermes", "/home/hermes/ts3_data"]

ENV PULSE_SERVER=unix:/run/pulse/native
ENV PULSE_RUNTIME_PATH=/run/pulse
ENV TS3_CLIENT_DIR=/opt/ts3client

USER hermes
WORKDIR /home/hermes
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD /usr/local/bin/healthcheck.sh
