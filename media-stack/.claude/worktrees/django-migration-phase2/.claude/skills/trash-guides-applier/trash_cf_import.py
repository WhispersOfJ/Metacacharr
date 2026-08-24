#!/usr/bin/env python3
"""Fetch a TRaSH-Guides Radarr/Sonarr custom-format JSON and convert it to this
repo's trash-guides-applier profile shape (fields-as-dict -> fields-as-list).

Usage:
    trash_cf_import.py <app radarr|sonarr> <cf-filename-without-.json>

Example:
    trash_cf_import.py radarr anime-dual-audio
"""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/{app}/cf/{name}.json"


def convert(trash_cf: dict) -> dict:
    specs = []
    for spec in trash_cf["specifications"]:
        fields = spec["fields"]
        # TRaSH publishes a single {"value": x} dict; Radarr/Sonarr's real API
        # (and this repo's applier.py) expect a list of {"name": "value", "value": x}.
        field_list = [{"name": k, "value": v} for k, v in fields.items()]
        specs.append({
            "name": spec["name"],
            "implementation": spec["implementation"],
            "negate": spec.get("negate", False),
            "required": spec.get("required", False),
            "fields": field_list,
        })
    score = trash_cf.get("trash_scores", {}).get("default", 0)
    return {
        "name": trash_cf["name"],
        "score": score,
        "note": f"TRaSH-Guides trash_id {trash_cf['trash_id']}.",
        "specifications": specs,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 1
    app, name = sys.argv[1], sys.argv[2]
    url = BASE.format(app=app, name=name)
    with urllib.request.urlopen(url, timeout=15) as resp:
        trash_cf = json.loads(resp.read())
    print(json.dumps(convert(trash_cf), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
