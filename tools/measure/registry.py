"""
Persistent measurement registry — append-only JSON store.
One entry per test run; each entry carries full metadata so results
remain interpretable after version bumps or re-wiring.
"""

import json
import pathlib
import uuid
from datetime import datetime, timezone

REGISTRY_PATH = pathlib.Path(__file__).parent / 'registry.json'


def load() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {'version': 1, 'measurements': []}


def append(entry: dict) -> str:
    """Write entry to registry, returning its assigned UUID."""
    reg = load()
    entry['id'] = str(uuid.uuid4())
    entry['timestamp'] = datetime.now(timezone.utc).isoformat()
    reg['measurements'].append(entry)
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2))
    return entry['id']


def query(module: str = None, platform: str = None,
          plugin_version: str = None) -> list[dict]:
    entries = load()['measurements']
    if module:         entries = [e for e in entries if e.get('module') == module]
    if platform:       entries = [e for e in entries if e.get('platform') == platform]
    if plugin_version: entries = [e for e in entries if e.get('plugin_version') == plugin_version]
    return entries
