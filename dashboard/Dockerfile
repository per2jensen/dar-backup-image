# SPDX-License-Identifier: GPL-3.0-or-later

FROM python:3.12-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /tmp/dashboard-requirements.txt

RUN python3 -m pip install --no-cache-dir \
        --requirement /tmp/dashboard-requirements.txt \
    && rm /tmp/dashboard-requirements.txt \
    && groupadd --gid 10001 datasette \
    && useradd --uid 10001 --gid datasette --create-home datasette

USER datasette

EXPOSE 8001

ENTRYPOINT ["datasette"]
