#!/bin/bash
set -e

DATA_DIR=/usr/share/opensearch/data

# Fix Railway volume ownership (mounted as root:root) and drop to opensearch (UID 1000)
mkdir -p "$DATA_DIR"
chown -R 1000:1000 "$DATA_DIR"

exec gosu 1000 /usr/share/opensearch/opensearch-docker-entrypoint.sh "$@"
