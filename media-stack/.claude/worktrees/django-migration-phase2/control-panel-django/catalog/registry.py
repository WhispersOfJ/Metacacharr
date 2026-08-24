"""Curated software catalog - entries are split by category into
entries/*.py, each verified against real GitHub/Docker Hub/LinuxServer.io
listings before being written (see each module's header comment for its
verification date). Not an open image installer - see the design note
below for why install/remove goes through the Docker SDK, not compose.

Ported near-verbatim from control-panel/services/catalog/registry.py for
the Django/DRF rewrite (Task 10). Only change: the entries import path,
from `services.catalog.entries` to `catalog.entries`. Every constant name
and value is otherwise byte-identical.

Design note on HOW this installs, which differs from the original
pitch's "writes docker-compose.yml" framing: this container has no bind
mount of the repo's docker-compose.yml and no `docker compose` CLI in its
own image (checked before writing this - see Dockerfile). It only has
docker.sock. So install/remove goes straight through the Docker SDK
(docker_client.containers.run/.stop/.remove) instead of editing the
compose file at all. A catalog container is a real, independently-
running Docker container on the same `stacknet` network, with its own
`restart: unless-stopped` policy - it survives a reboot or crash the same
way a compose service would, but a `docker compose down && up` on the
main stack won't touch it (compose has never heard of it). That's a
strictly smaller blast radius than the alternative (a bad compose-file
write breaking `docker compose up` for the entire stack), which is why
this shape won out over the treatment doc's original assumption.
"""
from catalog.entries import (
    browser_games,
    docker_host,
    household_access,
    indexer_completion,
    library_quality,
    media,
    monitoring,
    notifications,
    retroarch,
    security,
)

CATALOG_LABEL = "media-stack.catalog"  # label key marking a container as catalog-managed
NETWORK = "stacknet"

CATALOG: list[dict] = [
    *monitoring.CATALOG,
    *notifications.CATALOG,
    *indexer_completion.CATALOG,
    *library_quality.CATALOG,
    *household_access.CATALOG,
    *docker_host.CATALOG,
    *security.CATALOG,
    *media.CATALOG,
    *browser_games.CATALOG,
    *retroarch.CATALOG,
]

CATALOG_BY_ID = {entry["id"]: entry for entry in CATALOG}

assert len(CATALOG) >= 41, f"catalog registry has fewer entries than expected: {len(CATALOG)}"
