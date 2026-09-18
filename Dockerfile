# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE
#
# `dar-backup` image with a modern DAR built from source.
# Based on Ubuntu 24.04 (slim, multi-stage).
ARG UBUNTU_DIGEST=sha256:0000000000000000000000000000000000000000000000000000000000000000


# Empty fallback overridden by Make's named context for local-wheel builds.
FROM scratch AS dar_backup_dist


# === Builder Stage ===
FROM ubuntu:24.04@${UBUNTU_DIGEST} AS builder

ARG DAR_BACKUP_VERSION
ARG DAR_BACKUP_INSTALL_SOURCE=pypi
ARG DAR_BACKUP_LOCAL_WHEEL
ARG DAR_BACKUP_LOCAL_WHEEL_SHA256
ARG DAR_VERSION

ENV DEBIAN_FRONTEND=noninteractive PATH="/opt/venv/bin:$PATH" DAR_DIR=/usr/local

# Install build deps (Python for dar-backup, toolchain for DAR). The named
# context is empty for PyPI builds and is mounted read-only for local builds.
RUN --mount=type=bind,from=dar_backup_dist,target=/tmp/dar-backup-dist,ro \
    set -eu; \
    apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip gettext-base ca-certificates tzdata file gnupg \
      build-essential autoconf automake libtool pkg-config binutils \
      libkrb5-dev libgcrypt-dev libgpgme-dev libext2fs-dev libthreadar-dev \
      librsync-dev libcurl4-gnutls-dev libargon2-dev \
      bzip2 zlib1g-dev libbz2-dev liblzo2-dev liblzma-dev libzstd-dev liblz4-dev \
      groff doxygen graphviz upx \
  && /usr/bin/python3 -m venv /opt/venv \
  && case "$DAR_BACKUP_INSTALL_SOURCE" in \
       pypi) \
         /opt/venv/bin/python3 -m pip install \
           "dar-backup==$DAR_BACKUP_VERSION" --no-cache-dir; \
         ;; \
       local) \
         if [ -z "$DAR_BACKUP_LOCAL_WHEEL" ]; then \
           echo "ERROR: DAR_BACKUP_LOCAL_WHEEL is required for a local build" >&2; \
           exit 2; \
         fi; \
         wheel_path="/tmp/dar-backup-dist/$DAR_BACKUP_LOCAL_WHEEL"; \
         if [ ! -f "$wheel_path" ]; then \
           echo "ERROR: Local dar-backup wheel not found: $wheel_path" >&2; \
           exit 2; \
         fi; \
         if [ -z "$DAR_BACKUP_LOCAL_WHEEL_SHA256" ]; then \
           echo "ERROR: DAR_BACKUP_LOCAL_WHEEL_SHA256 is required for a local build" >&2; \
           exit 2; \
         fi; \
         actual_sha256="$(sha256sum "$wheel_path")"; \
         actual_sha256="${actual_sha256%% *}"; \
         if [ "$actual_sha256" != "$DAR_BACKUP_LOCAL_WHEEL_SHA256" ]; then \
           echo "ERROR: Local dar-backup wheel changed after validation" >&2; \
           exit 2; \
         fi; \
         /opt/venv/bin/python3 -m pip install "$wheel_path" --no-cache-dir; \
         ;; \
       *) \
         echo "ERROR: DAR_BACKUP_INSTALL_SOURCE must be 'pypi' or 'local'" >&2; \
         exit 2; \
         ;; \
     esac \
  && installed_version="$(/opt/venv/bin/python3 -c \
       'from importlib.metadata import version; print(version("dar-backup"))')" \
  && if [ "$installed_version" != "$DAR_BACKUP_VERSION" ]; then \
       echo "ERROR: Installed dar-backup version '$installed_version' does not match '$DAR_BACKUP_VERSION'" >&2; \
       exit 2; \
     fi



# Copy DAR source, signature, and Denis Corbin's GPG key
COPY src/dar/dar-${DAR_VERSION}.tar.gz /tmp/dar-${DAR_VERSION}.tar.gz
COPY src/dar/dar-${DAR_VERSION}.tar.gz.sig /tmp/
COPY doc/denis-corbin.gpg /tmp/


# Verify dar tarball signature (fail hard if invalid)
# Denis Corbin's DAR signing key is used to verify the signature
RUN set -e; \
    gpg --batch --import /tmp/denis-corbin.gpg \
  && gpg --batch --verify /tmp/dar-${DAR_VERSION}.tar.gz.sig /tmp/dar-${DAR_VERSION}.tar.gz \
  || (echo "ERROR: GPG signature verification failed for DAR ${DAR_VERSION}" >&2 && exit 1)  \
  && tar xzf /tmp/dar-${DAR_VERSION}.tar.gz -C /tmp \
  && rm -f /tmp/denis-corbin.gpg /tmp/dar-${DAR_VERSION}.tar.gz.sig /tmp/dar-${DAR_VERSION}.tar.gz



RUN set -e; \
    cd /tmp/dar-${DAR_VERSION} \
  && CXXFLAGS=-O ./configure --prefix="$DAR_DIR" LDFLAGS="-lgssapi_krb5" --disable-python-binding \
  && make -j$(nproc) \
  && make install-strip \
  && echo "/usr/local/lib" > /etc/ld.so.conf.d/local.conf \
  && ldconfig; \
    if ! dar_version_output="$(/usr/local/bin/dar --version 2>&1)"; then \
      echo "ERROR: unable to execute newly built DAR ${DAR_VERSION}: ${dar_version_output}" >&2; \
      exit 1; \
    fi; \
    printf '%s\n' "${dar_version_output}" > /tmp/dar-version.txt; \
    if ! grep -Fq "dar version ${DAR_VERSION}" /tmp/dar-version.txt; then \
      echo "ERROR: DAR ${DAR_VERSION} build failed version check: ${dar_version_output}" >&2; \
      exit 1; \
    fi; \
    rm -f /tmp/dar-version.txt /tmp/dar-${DAR_VERSION}.tar.gz



# Verify DAR build capabilities (fail if ANY check is missing)
RUN set -e; \
    echo "🔍 Verifying DAR feature set..."; \
    if ! /usr/local/bin/dar -Q --version > /tmp/dar_features.txt 2>&1; then \
      echo "ERROR: unable to read the newly built DAR feature set" >&2; \
      cat /tmp/dar_features.txt >&2; \
      exit 2; \
    fi; \
    cat /tmp/dar_features.txt; \
    require_feature() { \
      if ! grep -Fq "$1" /tmp/dar_features.txt; then \
        echo "ERROR: DAR build lacks required capability: $2" >&2; \
        exit 2; \
      fi; \
    }; \
    require_feature "gzip compression (libz)      : YES" "gzip compression"; \
    require_feature "bzip2 compression (libbzip2) : YES" "bzip2 compression"; \
    require_feature "lzo compression (liblzo2)    : YES" "lzo compression"; \
    require_feature "xz compression (liblzma)     : YES" "xz compression"; \
    require_feature "zstd compression (libzstd)   : YES" "zstd compression"; \
    require_feature "lz4 compression (liblz4)     : YES" "lz4 compression"; \
    require_feature "Strong encryption (libgcrypt): YES" "strong encryption"; \
    require_feature "Public key ciphers (gpgme)   : YES" "public-key ciphers"; \
    require_feature "Extended Attributes support  : YES" "extended attributes"; \
    require_feature "Large files support (> 2GB)  : YES" "large-file support"; \
    require_feature "ext2fs NODUMP flag support   : YES" "ext2fs NODUMP flags"; \
    require_feature "Integer size used            : 64 bits" "64-bit integers"; \
    require_feature "Thread safe support          : YES" "thread safety"; \
    require_feature "Furtive read mode support    : YES" "furtive reads"; \
    require_feature "Linux ext2/3/4 FSA support   : YES" "Linux ext filesystem attributes"; \
    require_feature "Linux statx() support        : YES" "Linux statx"; \
    require_feature "Posix fadvise support        : YES" "POSIX fadvise"; \
    require_feature "Large dir. speed optimi.     : YES" "large-directory optimization"; \
    require_feature "Timestamp read accuracy      : 1 nanosecond" "nanosecond timestamp reads"; \
    require_feature "Timestamp write accuracy     : 1 nanosecond" "nanosecond timestamp writes"; \
    require_feature "Restores dates of symlinks   : YES" "symlink date restoration"; \
    require_feature "Multiple threads (libthreads): YES" "multiple threads"; \
    require_feature "Delta compression (librsync) : YES" "delta compression"; \
    require_feature "Remote repository (libcurl)  : YES" "remote repositories"; \
    require_feature "argon2 hashing (libargon2)   : YES" "argon2 hashing"; \
    echo "✅ DAR feature verification passed"


# Generate the offline documentation only after DAR is built so README or
# documentation-command edits do not invalidate the expensive DAR layer.
COPY scripts/image_docs.py /tmp/image_docs.py
COPY README.md /tmp/image-README.md
RUN set -eu; \
    if [ -n "$DAR_BACKUP_VERSION" ]; then \
      /opt/venv/bin/python3 /tmp/image_docs.py install \
        --output-dir /opt/image-docs \
        --image-readme /tmp/image-README.md \
        --expected-version "$DAR_BACKUP_VERSION"; \
    else \
      /opt/venv/bin/python3 /tmp/image_docs.py install \
        --output-dir /opt/image-docs \
        --image-readme /tmp/image-README.md; \
    fi

# Generate command-specific registration files for bash-completion's lazy
# loader. Keeping this in the builder avoids retaining generation tooling solely
# for runtime shell initialization.
RUN set -eu; \
    mkdir -p /opt/bash-completion \
  && for command in dar-backup cleanup manager; do \
       /opt/venv/bin/register-python-argcomplete "$command" \
         > "/opt/bash-completion/$command"; \
       test -s "/opt/bash-completion/$command"; \
     done


# Cleanup builder stage to reduce layer size
RUN set -e; \
    pip uninstall -y pip setuptools wheel || true \
  && find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + \
  && find /opt/venv -type f -name "*.pyc" -delete \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# === Final Runtime Stage ===
ARG UBUNTU_DIGEST=sha256:0000000000000000000000000000000000000000000000000000000000000000
FROM ubuntu:24.04@${UBUNTU_DIGEST}
ARG DAR_VERSION
ARG DAR_BACKUP_VERSION

ENV DEBIAN_FRONTEND=noninteractive PATH="/opt/venv/bin:$PATH" \
    LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 \
    DAR_BACKUP_CONFIG=/etc/dar-backup/dar-backup.conf \
    DAR_BACKUP_DIR=/backups DAR_BACKUP_D_DIR=/backup.d \
    DAR_BACKUP_RESTORE_DIR=/restore DAR_BACKUP_DATA_DIR=/data


# Copy venv + DAR (built from source)
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/bin/dar* /usr/local/bin/
COPY --from=builder /usr/local/lib/libdar* /usr/local/lib/
COPY --from=builder /etc/ld.so.conf.d/local.conf /etc/ld.so.conf.d/local.conf
# Copy libthreadar and fix symlink chain
# libthreadar: amd64-specific path (x86_64-linux-gnu) — see note at top of file.
# The .so version number (currently 1000) may change between Ubuntu releases.
# When upgrading the base image, verify with:
#   apt-cache show libthreadar-dev | grep Version
# or inspect the builder stage:
#   docker run --rm dar-backup:dev ls /usr/lib/x86_64-linux-gnu/libthreadar*
COPY --from=builder /usr/lib/x86_64-linux-gnu/libthreadar.so.1000 /usr/lib/x86_64-linux-gnu/
RUN set -e; \
    ln -sf libthreadar.so.1000 /usr/lib/x86_64-linux-gnu/libthreadar.so  && ldconfig \
  && printf '%s\n' \
       'path-include=/usr/share/man/man1/par2.1.gz' \
       'path-include=/usr/share/man/man1/par2create.1.gz' \
       'path-include=/usr/share/man/man1/par2repair.1.gz' \
       'path-include=/usr/share/man/man1/par2verify.1.gz' \
       > /etc/dpkg/dpkg.cfg.d/zz-dar-backup-par2-man \
  && apt-get update && apt-get upgrade -y \
  && apt-get install -y --no-install-recommends \
       python3-minimal python3-venv gettext-base par2 util-linux ca-certificates tzdata libc-bin \
       bash-completion man-db less \
       zlib1g libbz2-1.0 liblz4-1 liblzma5 libzstd1 liblzo2-2 libargon2-1 \
       libgcrypt20 libgpgme11 libkrb5-3 librsync2 libext2fs2 \
       libcurl3-gnutls locales \
  && locale-gen en_US.UTF-8 da_DK.UTF-8 fr_FR.UTF-8 es_ES.UTF-8 de_DE.UTF-8 \
  && update-locale LANG=en_US.UTF-8 \
  && ldconfig \
  && mkdir -p /opt/par2-man/man1 \
  && for manual in par2 par2create par2repair par2verify; do \
       manual_path="/usr/share/man/man1/${manual}.1.gz"; \
       if [ ! -f "$manual_path" ]; then \
         echo "ERROR: PAR2 manual was not installed: $manual_path" >&2; \
         exit 2; \
       fi; \
       cp "$manual_path" /opt/par2-man/man1/; \
     done \
  && rm -f /etc/dpkg/dpkg.cfg.d/zz-dar-backup-par2-man \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
  && rm -rf /usr/share/doc /usr/share/man /usr/share/locale \
  && mkdir -p /usr/share/man/man1 \
  && cp /opt/par2-man/man1/*.1.gz /usr/share/man/man1/ \
  && rm -rf /opt/par2-man


# Retain the manuals built from the verified DAR source plus the PAR2 manuals,
# and install the generated argcomplete registrations. Ubuntu's
# /etc/bash.bashrc ships with completion disabled, so enable the standard
# loader for all interactive users.
COPY --from=builder /usr/local/share/man/man1/ /usr/local/share/man/man1/
COPY --from=builder /opt/bash-completion/ /usr/share/bash-completion/completions/
RUN set -e; \
    man_diversion="$(dpkg-divert --list /usr/bin/man)"; \
    if [ -n "$man_diversion" ]; then \
      rm -f /usr/bin/man; \
      dpkg-divert --quiet --remove --rename /usr/bin/man; \
    fi; \
    printf '%s\n' \
      '' \
      '# Enable system-wide programmable completion in interactive shells.' \
      'if ! declare -F _completion_loader >/dev/null && [ -r /usr/share/bash-completion/bash_completion ]; then' \
      '  . /usr/share/bash-completion/bash_completion' \
      'fi' \
      >> /etc/bash.bashrc \
  && test -x /usr/bin/man \
  && test -f /usr/local/share/man/man1/dar.1 \
  && MANPAGER=cat PAGER=cat man dar | grep -q 'creates, tests, lists, extracts' \
  && for command in par2 par2create par2repair par2verify; do \
       command -v "$command" >/dev/null; \
       "$command" --help >/dev/null; \
       test -f "/usr/share/man/man1/${command}.1.gz"; \
       MANPAGER=cat PAGER=cat man "$command" >/dev/null; \
     done


# Refresh linker cache so libdar64 is found
RUN set -e; \
    ldconfig \
  && echo "Checking DAR version '${DAR_VERSION}'"; \
    if ! dar_version_output="$(/usr/local/bin/dar --version 2>&1)"; then \
      echo "ERROR: unable to execute runtime DAR ${DAR_VERSION}: ${dar_version_output}" >&2; \
      exit 1; \
    fi; \
    printf '%s\n' "${dar_version_output}" > /tmp/dar-version.txt; \
    if ! grep -Fq "dar version ${DAR_VERSION}" /tmp/dar-version.txt; then \
      echo "ERROR: runtime DAR ${DAR_VERSION} failed version check: ${dar_version_output}" >&2; \
      exit 1; \
    fi; \
    rm -f /tmp/dar-version.txt


# Final cleanup of venv (tests, pip, setuptools, wheel)
RUN set -e; \
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + \
  && find /opt/venv -type f -name "*.pyc" -delete \
  && find /opt/venv -type d -name "tests" -exec rm -rf {} + \
  && rm -rf /opt/venv/lib/python*/site-packages/pip \
            /opt/venv/lib/python*/site-packages/setuptools \
            /opt/venv/lib/python*/site-packages/wheel

            
COPY dar-backup.conf /etc/dar-backup/dar-backup.conf
COPY entrypoint.sh /entrypoint.sh
COPY LICENSE /LICENSE
COPY --from=builder /opt/image-docs /usr/share/doc/dar-backup
COPY scripts/image_docs.py /usr/local/bin/dar-backup-image-docs
RUN set -e; \
    chmod +x /entrypoint.sh /usr/local/bin/dar-backup-image-docs \
  && ln -s dar-backup-image-docs /usr/local/bin/dar-backup-image-info \
  && ln -s /usr/share/doc/dar-backup/image /usr/share/doc/dar-backup-image \
  && ln -s /usr/share/doc/dar-backup-image/README.md /README.md

# Replace ubuntu user with daruser (UID 1000)
RUN set -e; \
  userdel -f ubuntu 2>/dev/null || true \
  && rm -rf /home/ubuntu || true \
  && useradd -r -u 1000 -g users \
       -s /usr/sbin/nologin -d /nonexistent daruser \
  && mkdir -p /backups /backup.d /restore /data \
  && chown -R daruser:users /backups /backup.d /restore /data

# Container starts as root intentionally — entrypoint.sh drops privileges
# to RUN_AS_UID/RUN_AS_GID via setpriv before executing dar-backup.
# Do NOT add USER daruser here; it would break the permission-fix and
# privilege-drop logic in entrypoint.sh.
ENTRYPOINT ["/entrypoint.sh"]
