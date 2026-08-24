"""Browser Games catalog entries - verified against Docker Hub/GitHub
listings on 2026-08-15 by research-agent dispatch, reviewed before merge
(see docs/superpowers/plans/2026-08-15-control-panel-catalog-expansion.md
Task 3). Host ports allocated in the 82xx range.
"""

CATALOG: list[dict] = [
    {
        "id": "scribble-rs",
        "name": "Scribble.rs",
        "category": "Browser Games",
        "pitch": "Real-time multiplayer Pictionary-style drawing game - no accounts, no setup, just open in your browser and draw.",
        "image": "biosmarcel/scribble.rs",
        "tag": "latest",
        "ports": {"8080/tcp": 8200},
        "volumes": {},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~6.8MB image, Go binary, negligible RAM",
        "doc_url": "https://github.com/scribble-rs/scribble.rs",
        "caveat": "Needs WebSocket-aware reverse-proxy configuration if placed behind a proxy later (not needed for direct port access).",
    },
    {
        "id": "razzia",
        "name": "Razzia",
        "category": "Browser Games",
        "pitch": "Self-hosted Kahoot-style quiz game - create multiplayer quizzes, share a room code, and play with friends.",
        "image": "ralex91/razzia",
        "tag": "latest",
        "ports": {"3000/tcp": 8201},
        "volumes": {
            "catalog_razzia_config": {"bind": "/app/config", "mode": "rw"},
        },
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~52.4MB image, single Node process",
        "doc_url": "https://github.com/Ralex91/Razzia",
        "caveat": "Change the default manager password inside config/game.json after first run - not set via environment variable.",
    },
    {
        "id": "mah",
        "name": "Mah",
        "category": "Browser Games",
        "pitch": "HTML5 Mahjong Solitaire - play classic tile-matching solitaire, no install needed, responsive design.",
        "image": "ffalt/mah",
        "tag": "latest",
        "ports": {"80/tcp": 8202},
        "volumes": {},
        "environment": {},
        "cap_add": [],
        "devices": [],
        "footprint": "~31.8MB image, static file server",
        "doc_url": "https://github.com/ffalt/mah",
        "caveat": "The project's dedicated docs page was unreachable during verification - port mapping is based on the Docker Hub docker run command.",
    },
]
