# SPDX-License-Identifier: GPL-3.0-or-later
#
# dar-backup image based on Ubuntu 24.04 (hardened, lean)

# === Builder Stage: Build dar-backup in isolated venv ===
FROM ubuntu:24.04 AS builder

ARG DAR_BACKUP_VERSION
ENV DEBIAN_FRONTEND=noninteractive

# Install Python and build dependencies for dar-backup
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip dar par2 ca-certificates tzdata file && \
    rm -rf /var/lib/apt/lists/*

# Create a Python venv for dar-backup
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dar-backup, then remove pip/setuptools to reduce attack surface
RUN if [ -n "$DAR_BACKUP_VERSION" ]; then \
      pip install "dar-backup==$DAR_BACKUP_VERSION" --no-cache-dir; \
    else \
      pip install dar-backup --no-cache-dir; \
    fi && \
    pip uninstall -y pip setuptools wheel || true && \
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + && \
    find /opt/venv -type f -name "*.pyc" -delete

# === Final Runtime Stage ===
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:$PATH" \
    DAR_BACKUP_CONFIG=/etc/dar-backup/dar-backup.conf \
    DAR_BACKUP_DIR=/backups \
    DAR_BACKUP_D_DIR=/backup.d \
    DAR_BACKUP_RESTORE_DIR=/restore \
    DAR_BACKUP_DATA_DIR=/data

# Update base and install runtime dependencies only
RUN apt-get update && \
    apt-get dist-upgrade -y && \
    apt-get install -y --no-install-recommends \
        python3-full dar par2 util-linux ca-certificates tzdata && \
    apt-get purge -y --auto-remove && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy dar-backup virtual environment
COPY --from=builder /opt/venv /opt/venv

# Copy configuration and entrypoint
COPY dar-backup.conf /etc/dar-backup/dar-backup.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Remove default 'ubuntu' user and replace with a locked daruser (UID 1000)
RUN userdel -f ubuntu 2>/dev/null || true && \
    rm -rf /home/ubuntu || true && \
    useradd -r -u 1000 -g users \
      -s /usr/sbin/nologin \
      -d /nonexistent \
      daruser && \
    mkdir -p /backups /backup.d /restore /data && \
    chown -R daruser:users /backups /backup.d /restore /data

# Default to root; entrypoint will drop to UID 1000 (daruser) unless overridden with --user
USER root

ENTRYPOINT ["/entrypoint.sh"]
