#!/bin/sh
# Extracts (or updates) the Stack's tracked files into a mounted host
# directory. Safe to re-run after every image update - it only ever
# overwrites files this image actually contains (docker-compose.yml,
# scripts/, systemd/, docs, .env.example), and those are the only
# files ever baked into this image in the first place. .env and config/
# aren't in this image at all, so a real deployment's secrets/state are
# never at risk from re-running this.
set -eu

TARGET="/out"

if [ ! -d "$TARGET" ] || [ ! -w "$TARGET" ]; then
  cat <<'USAGE'
Mount a target directory at /out:

  docker run --rm -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest

First run scaffolds a fresh install; re-running later pulls in whatever
changed upstream (compose file, scripts, systemd units, docs)
without touching your .env or config/ - neither is ever baked into this
image.
USAGE
  exit 1
fi

case "${1:-}" in
--setup)
  [ -f "$TARGET/.env.example" ] || {
    echo "No .env.example in $TARGET yet - run without --setup first to scaffold files."
    exit 1
  }
  exec python3 /stack/scripts/setup_wizard.py "$TARGET"
  ;;
esac

FIRST_RUN=false
[ -f "$TARGET/docker-compose.yml" ] || FIRST_RUN=true

cp -r /stack/. "$TARGET/"

# This image runs as root, so the copy above lands as root:root by default -
# match whatever UID/GID already owns the mount point instead, so the files
# come out owned by whoever ran `docker run` on the host, not root.
OWNER_UID="$(stat -c '%u' "$TARGET")"
OWNER_GID="$(stat -c '%g' "$TARGET")"
chown -R "$OWNER_UID:$OWNER_GID" "$TARGET"

echo "Stack files written to $TARGET"
echo

if [ "$FIRST_RUN" = true ]; then
  cat <<EOF
This looks like a fresh install. Next steps:
  cd $TARGET
  docker run --rm -p 8090:8090 -v "\$(pwd)":/out ghcr.io/whispersofj/media-stack:latest --setup
                                     # opens a setup wizard at http://localhost:8090
                                     # to fill in .env (or: cp .env.example .env && \$EDITOR .env)
  docker compose up -d              # all services
EOF
else
  cat <<EOF
Updated in place. Your .env and config/ were not touched (this image never
contains them). If docker-compose.yml or systemd/ changed,
re-apply with:
  cd $TARGET
  docker compose up -d --force-recreate
  systemctl --user daemon-reload   # if any systemd unit changed
EOF
fi
