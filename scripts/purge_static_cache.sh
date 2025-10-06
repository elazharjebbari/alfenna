#!/usr/bin/env bash
# Clears hashed static assets and WhiteNoise cache to prevent stale bundles.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATIC_ROOT="${ROOT_DIR}/staticfiles"
WHITENOISE_CACHE="${ROOT_DIR}/static/.whitenoise-cache"

echo "Purging static cache directories..."
if [ -d "${STATIC_ROOT}" ]; then
  rm -rf "${STATIC_ROOT:?}"/*
fi
if [ -d "${WHITENOISE_CACHE}" ]; then
  rm -rf "${WHITENOISE_CACHE}"/*
fi
echo "Done. Re-run 'python manage.py collectstatic --clear -v 2' to rebuild assets."
