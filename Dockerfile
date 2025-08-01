# SPDX-License-Identifier: GPL-3.0-or-later
#
# dar-backup image with modern DAR (2.7.18) built from source.
# Based on Ubuntu 24.04 (slim, multi-stage).

# === Builder Stage ===
FROM ubuntu:24.04 AS builder

ARG DAR_BACKUP_VERSION
ARG DAR_VERSION=2.7.19
ENV DEBIAN_FRONTEND=noninteractive PATH="/opt/venv/bin:$PATH" DAR_DIR=/usr/local

# Install build deps (Python for dar-backup, toolchain for DAR)
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip gettext-base ca-certificates tzdata file gnupg \
      build-essential autoconf automake libtool pkg-config binutils \
      libkrb5-dev libgcrypt-dev libgpgme-dev libext2fs-dev libthreadar-dev \
      librsync-dev libcurl4-gnutls-dev libargon2-dev \
      bzip2 zlib1g-dev libbz2-dev liblzo2-dev liblzma-dev libzstd-dev liblz4-dev \
      groff doxygen graphviz upx \
  && python3 -m venv /opt/venv \
  && if [ -n "$DAR_BACKUP_VERSION" ]; then \
       pip install "dar-backup==$DAR_BACKUP_VERSION" --no-cache-dir; \
     else \
       pip install dar-backup --no-cache-dir; \
     fi



# Copy DAR source, signature, and Denis Corbin's GPG key
COPY src/dar/dar-${DAR_VERSION}.tar.gz /tmp/dar-${DAR_VERSION}.tar.gz
COPY src/dar/dar-${DAR_VERSION}.tar.gz.sig /tmp/
COPY doc/denis-corbin.gpg /tmp/

# Verify dar tarball signature (fail hard if invalid)
# Denis Corbin's dar-backup GPG key is used to verify the signature
RUN gpg --batch --import /tmp/denis-corbin.gpg \
  && gpg --batch --verify /tmp/dar-${DAR_VERSION}.tar.gz.sig /tmp/dar-${DAR_VERSION}.tar.gz \
  || (echo "❌ GPG signature verification failed for DAR ${DAR_VERSION}" && exit 1)  \
  && tar xzf /tmp/dar-${DAR_VERSION}.tar.gz -C /tmp \
  && rm -f /tmp/denis-corbin.gpg /tmp/dar-${DAR_VERSION}.tar.gz.sig /tmp/dar-${DAR_VERSION}.tar.gz



RUN cd /tmp/dar-${DAR_VERSION} \
  && CXXFLAGS=-O ./configure --prefix="$DAR_DIR" LDFLAGS="-lgssapi_krb5" --disable-python-binding \
  && make -j$(nproc) \
  && make install-strip \
  && echo "/usr/local/lib" > /etc/ld.so.conf.d/local.conf \
  && ldconfig \
  && ( /usr/local/bin/dar --version | grep -q "dar version ${DAR_VERSION}, Copyright (C) 2002-2025 Denis Corbin" \
       || (echo "❌ DAR ${DAR_VERSION} build failed version check" && exit 1) ) \
  && rm -f /tmp/dar-${DAR_VERSION}.tar.gz



# Verify DAR build capabilities (fail if ANY check is missing)
RUN set -e; \
    echo "🔍 Verifying DAR feature set..."; \
    /usr/local/bin/dar -Q --version | tee /tmp/dar_features.txt; \
    grep -q "gzip compression (libz)      : YES" /tmp/dar_features.txt; \
    grep -q "bzip2 compression (libbzip2) : YES" /tmp/dar_features.txt; \
    grep -q "lzo compression (liblzo2)    : YES" /tmp/dar_features.txt; \
    grep -q "xz compression (liblzma)     : YES" /tmp/dar_features.txt; \
    grep -q "zstd compression (libzstd)   : YES" /tmp/dar_features.txt; \
    grep -q "lz4 compression (liblz4)     : YES" /tmp/dar_features.txt; \
    grep -q "Strong encryption (libgcrypt): YES" /tmp/dar_features.txt; \
    grep -q "Public key ciphers (gpgme)   : YES" /tmp/dar_features.txt; \
    grep -q "Extended Attributes support  : YES" /tmp/dar_features.txt; \
    grep -q "Large files support (> 2GB)  : YES" /tmp/dar_features.txt; \
    grep -q "ext2fs NODUMP flag support   : YES" /tmp/dar_features.txt; \
    grep -q "Integer size used            : 64 bits" /tmp/dar_features.txt; \
    grep -q "Thread safe support          : YES" /tmp/dar_features.txt; \
    grep -q "Furtive read mode support    : YES" /tmp/dar_features.txt; \
    grep -q "Linux ext2/3/4 FSA support   : YES" /tmp/dar_features.txt; \
    grep -q "Linux statx() support        : YES" /tmp/dar_features.txt; \
    grep -q "Posix fadvise support        : YES" /tmp/dar_features.txt; \
    grep -q "Large dir. speed optimi.     : YES" /tmp/dar_features.txt; \
    grep -q "Timestamp read accuracy      : 1 nanosecond" /tmp/dar_features.txt; \
    grep -q "Timestamp write accuracy     : 1 nanosecond" /tmp/dar_features.txt; \
    grep -q "Restores dates of symlinks   : YES" /tmp/dar_features.txt; \
    grep -q "Multiple threads (libthreads): YES" /tmp/dar_features.txt; \
    grep -q "Delta compression (librsync) : YES" /tmp/dar_features.txt; \
    grep -q "Remote repository (libcurl)  : YES" /tmp/dar_features.txt; \
    grep -q "argon2 hashing (libargon2)   : YES" /tmp/dar_features.txt; \
    echo "✅ DAR feature verification passed"


# Cleanup builder stage to reduce layer size
RUN pip uninstall -y pip setuptools wheel || true \
  && find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + \
  && find /opt/venv -type f -name "*.pyc" -delete \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# === Final Runtime Stage ===
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive PATH="/opt/venv/bin:$PATH" \
    DAR_BACKUP_CONFIG=/etc/dar-backup/dar-backup.conf \
    DAR_BACKUP_DIR=/backups DAR_BACKUP_D_DIR=/backup.d \
    DAR_BACKUP_RESTORE_DIR=/restore DAR_BACKUP_DATA_DIR=/data


# Copy venv + DAR (built from source)
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/bin/dar* /usr/local/bin/
COPY --from=builder /usr/local/lib/libdar* /usr/local/lib/
COPY --from=builder /etc/ld.so.conf.d/local.conf /etc/ld.so.conf.d/local.conf
# Copy libthreadar and fix symlink chain
COPY --from=builder /usr/lib/x86_64-linux-gnu/libthreadar.so.1000 /usr/lib/x86_64-linux-gnu/
RUN ln -sf libthreadar.so.1000 /usr/lib/x86_64-linux-gnu/libthreadar.so  && ldconfig


# Install runtime deps (minimal)
# ldconfig to register libdar64
# link libthreadar.so to the expected location
RUN apt-get update && apt-get dist-upgrade -y \
  && apt-get install -y --no-install-recommends \
       python3-minimal python3-venv gettext-base par2 util-linux ca-certificates tzdata libc-bin \
       # Compression and hashing runtimes
       zlib1g libbz2-1.0 liblz4-1 liblzma5 libzstd1 liblzo2-2 libargon2-1 \
       # Crypto, GPG, Kerberos, and backup libraries
       libgcrypt20 libgpgme11 libkrb5-3 librsync2 libext2fs2 \
       # Networking and remote repo support
       libcurl3-gnutls \
  && ldconfig \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
  && rm -rf /usr/share/doc /usr/share/man /usr/share/locale


# Refresh linker cache so libdar64 is found
RUN ldconfig \
  # Sanity check DAR after copy
  && echo "Checking DAR version...\"${DAR_VERSION}\"  " \
  && /usr/local/bin/dar -Q --version | grep -q "dar version ${DAR_VERSION}"

# Final cleanup of venv (tests, pip, setuptools, wheel)
RUN find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + \
  && find /opt/venv -type f -name "*.pyc" -delete \
  && find /opt/venv -type d -name "tests" -exec rm -rf {} + \
  && rm -rf /opt/venv/lib/python*/site-packages/pip \
            /opt/venv/lib/python*/site-packages/setuptools \
            /opt/venv/lib/python*/site-packages/wheel

COPY dar-backup.conf /etc/dar-backup/dar-backup.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Replace ubuntu user with daruser (UID 1000)
RUN userdel -f ubuntu 2>/dev/null || true \
  && rm -rf /home/ubuntu || true \
  && useradd -r -u 1000 -g users \
       -s /usr/sbin/nologin -d /nonexistent daruser \
  && mkdir -p /backups /backup.d /restore /data \
  && chown -R daruser:users /backups /backup.d /restore /data

USER root
ENTRYPOINT ["/entrypoint.sh"]
