# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
# EaveLuxOS in a container: runs as an unprivileged user (uid 10001), the app
# code is owned by root and read-only to it, and all data lives in /data.
#   docker compose up -d --build      (see compose.yaml and MANUAL.md)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EAVELUXOS_DATA_DIR=/data \
    EAVELUXOS_CONTAINER=1 \
    EAVELUXOS_SUPERVISED=1

RUN python -m pip install --no-cache-dir "cryptography==44.0.0" "tzdata==2024.2" \
 && groupadd --system --gid 10001 eavelux \
 && useradd --system --uid 10001 --gid eavelux --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin eavelux \
 && mkdir -p /data && chown eavelux:eavelux /data && chmod 700 /data

WORKDIR /app
COPY main.py LICENSE MANUAL.md ./
COPY eaveluxos ./eaveluxos
RUN python -m compileall -q /app && chmod -R a-w /app

USER 10001:10001
EXPOSE 8787
VOLUME ["/data"]
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import json,urllib.request;json.load(urllib.request.urlopen('http://127.0.0.1:8787/api/session',timeout=4))"]
CMD ["python", "main.py", "run"]
