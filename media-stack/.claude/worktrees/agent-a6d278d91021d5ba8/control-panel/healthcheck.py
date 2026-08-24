#!/usr/bin/env python3
"""Distroless-compatible healthcheck for control-panel.

Used by docker-compose healthcheck with CMD format (no shell).
Exits 0 if healthy, 1 if not.
"""
import sys
import urllib.request
import urllib.error

try:
    urllib.request.urlopen("http://localhost:8420/healthz", timeout=5)
    sys.exit(0)
except (urllib.error.URLError, Exception):
    sys.exit(1)
