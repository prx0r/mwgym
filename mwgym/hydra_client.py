"""Real HydraDB client — connects to the running HydraDB Docker instance.

HydraDB runs on port 17687 (Bolt protocol) in Docker.
This client uses the HTTP API for queries.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


HYDRADB_URL = os.environ.get("HYDRADB_URL", "http://localhost:17687")


class RealHydraDB:
    """Real HydraDB client connecting to running Docker instance."""

    def __init__(self, url: str = HYDRADB_URL):
        self.url = url

    def _request(self, method: str, path: str, data: dict = None) -> dict:
        """Make HTTP request to HydraDB."""
        url = f"{self.url}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)}

    def query(self, cypher: str, params: dict = None) -> list[dict]:
        """Run a Cypher query against HydraDB."""
        return self._request("POST", "/cypher", {"cypher": cypher, "params": params or {}})

    def upsert_node(self, node_id: str, label: str, properties: dict = None):
        """Create or update a node."""
        return self._request("POST", "/node", {
            "id": node_id, "label": label, "properties": properties or {},
        })

    def upsert_edge(self, src: str, dst: str, label: str, properties: dict = None):
        """Create or update an edge."""
        return self._request("POST", "/edge", {
            "src": src, "dst": dst, "label": label, "properties": properties or {},
        })

    def stats(self) -> dict:
        """Get graph statistics."""
        return self._request("GET", "/stats")

    def health(self) -> bool:
        """Check if HydraDB is reachable."""
        try:
            result = self.stats()
            return "error" not in result
        except Exception:
            return False
