#!/bin/bash
set -e

DATA_DIR=/usr/share/opensearch/data

# Fix volume ownership when container starts as root (Railway volume mounts as root:root)
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    chown -R 1000:1000 "$DATA_DIR"
    exec su -s /bin/bash opensearch -- /usr/share/opensearch/opensearch-docker-entrypoint.sh "$@"
fi

# Already running as opensearch user
exec /usr/share/opensearch/opensearch-docker-entrypoint.sh "$@"
