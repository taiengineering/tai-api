#!/bin/bash
set -e

DATA_DIR=/usr/share/opensearch/data

# Fix Railway volume ownership (mounted as root:root) before starting OpenSearch.
# Running as root here; opensearch-docker-entrypoint.sh drops to opensearch user.
mkdir -p "$DATA_DIR"
chown -R 1000:1000 "$DATA_DIR"

exec /usr/share/opensearch/opensearch-docker-entrypoint.sh "$@"
