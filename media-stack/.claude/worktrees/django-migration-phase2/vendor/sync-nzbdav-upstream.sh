#!/bin/sh
# Run this at the start of every session before reviewing vendor/nzbdav.
# Guarantees the checkout matches upstream main HEAD exactly - discards
# any local edits in the clone (it's a read-only mirror for review, not
# a working fork; if you need to patch it, branch off before running this).
#
# Usage: sh vendor/sync-nzbdav-upstream.sh
set -eu
cd "$(dirname "$0")/nzbdav"

git fetch origin main
git checkout main
git reset --hard origin/main
git clean -fdx

echo "nzbdav synced to: $(git log -1 --format='%H %ai %s')"
