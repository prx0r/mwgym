"""HydraDB — real graph database adapter.

Connects to HydraDB via Bolt protocol.
Replaces SQLite fallback when HydraDB is available.
Same API either way.

IMPORTANT: HydraDB requires relationships for all operations.
- Nodes are created through relationship patterns (MERGE/CREATE)
- Standalone node creation is not supported
- We use a root node as an anchor for standalone nodes
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

try:
    from neo4j import GraphDatabase
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False


HYDRADB_URL = os.environ.get("HYDRADB_URL", "bolt://localhost:7687")
HYDRADB_TOKEN = os.environ.get("HYDRADB_TOKEN", "")
ROOT_NODE_ID = 0  # Special id for root node


def _load_token() -> str:
    """Load auth token from file or env."""
    if HYDRADB_TOKEN:
        return HYDRADB_TOKEN
    token_file = "/root/workerkit/data/hydradb/auth-token"
    if os.path.exists(token_file):
        return open(token_file).read().strip()
    return ""


def _to_int_id(node_id: str) -> int:
    """Convert string id to integer for HydraDB."""
    return int(hashlib.md5(node_id.encode()).hexdigest()[:8], 16) % 1000000000


class HydraDBAdapter:
    """Real HydraDB connection via Bolt protocol.
    
    Supports the limited Cypher subset:
    - MERGE for creating relationships (with optional node creation)
    - CREATE for relationship paths
    - MATCH with label/property predicates
    - RETURN with property projections or count(*)
    - SET for updating properties
    - DELETE/DETACH DELETE after MATCH
    """

    def __init__(self, url: str = "", token: str = ""):
        if not HAS_NEO4J:
            raise ImportError("neo4j package not installed: pip install neo4j")
        
        self.url = url or HYDRADB_URL
        self.token = token or _load_token()
        if not self.token:
            raise ValueError("No auth token. Set HYDRADB_TOKEN or create /root/workerkit/data/hydradb/auth-token")
        
        self._driver = GraphDatabase.driver(
            self.url,
            auth=("neo4j", self.token),
        )
        
        # Ensure root node exists
        self._ensure_root()

    def _ensure_root(self):
        """Ensure root node exists for anchoring standalone nodes."""
        try:
            self._write(f'''
                MERGE (root:Root {{id: {ROOT_NODE_ID}, node_id: \"root\"}})-[:_SELF]->(root)
            ''')
        except Exception:
            pass  # Root may already exist

    def close(self):
        if self._driver:
            self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _run(self, query: str, params: dict = None) -> list[dict]:
        """Run a Cypher query and return results as list of dicts."""
        with self._driver.session(database="default") as session:
            result = session.run(query, params or {})
            return [dict(r) for r in result]

    def _write(self, query: str, params: dict = None):
        """Run a write query (no return value)."""
        with self._driver.session(database="default") as session:
            session.run(query, params or {})

    # ─── Node Operations ──────────────────────────────────────────────

    def upsert_node(self, label: str, node_id: str, properties: dict = None):
        """Create or update a node. Uses MERGE on id.
        
        Note: MERGE in HydraDB creates relationships, not standalone nodes.
        We create nodes implicitly through relationship patterns.
        For standalone nodes, we use a relationship to the root node.
        
        IMPORTANT: HydraDB requires id to be an integer. We use a hash
        of the string id to generate a unique integer.
        """
        props = properties or {}
        int_id = _to_int_id(node_id)
        
        # Build property string
        prop_parts = [f"id: {int_id}", f"node_id: \"{node_id}\""]
        for k, v in props.items():
            if isinstance(v, str):
                prop_parts.append(f"{k}: \"{v}\"")
            elif isinstance(v, (int, float, bool)):
                prop_parts.append(f"{k}: {v}")
        prop_str = ", ".join(prop_parts)
        
        # Use MERGE with relationship to root node to create node
        # Must do this in separate steps due to HydraDB limitations
        self._write(f'''
            MERGE (n:{label} {{{prop_str}}})-[:PART_OF]->(root:Root {{id: {ROOT_NODE_ID}}})
        ''')

    def upsert_edge(self, src_label: str, src_id: str, 
                    dst_label: str, dst_id: str,
                    edge_type: str, properties: dict = None):
        """Create or update an edge between two nodes.
        
        Note: HydraDB requires MERGE for relationship creation.
        MATCH + CREATE is not supported.
        """
        props = properties or {}
        src_int = _to_int_id(src_id)
        dst_int = _to_int_id(dst_id)
        
        prop_parts = []
        for k, v in props.items():
            if isinstance(v, str):
                prop_parts.append(f"{k}: \"{v}\"")
            elif isinstance(v, (int, float, bool)):
                prop_parts.append(f"{k}: {v}")
        
        if prop_parts:
            prop_str = " {" + ", ".join(prop_parts) + "}"
        else:
            prop_str = ""
        
        # Use MERGE for relationship creation (CREATE + MATCH not supported)
        self._write(f'''
            MERGE (a:{src_label} {{id: $src_id}})-[:{edge_type}{prop_str}]->(b:{dst_label} {{id: $dst_id}})
        ''', {"src_id": src_int, "dst_id": dst_int})

    def get_node(self, label: str, node_id: str) -> dict | None:
        """Get a node by label and id."""
        int_id = _to_int_id(node_id)
        result = self._run(
            f'MATCH (n:{label} {{id: $id}}) RETURN n',
            {"id": int_id}
        )
        if result:
            node = result[0].get("n", {})
            if isinstance(node, dict):
                return node
        return None

    def get_edges(self, src_label: str, src_id: str, 
                  edge_type: str = None) -> list[dict]:
        """Get edges from a source node.
        
        Note: HydraDB requires exactly one relationship type per pattern.
        We must specify the edge_type parameter.
        
        Also note: RETURN only supports <binding>.<property> or count(*).
        We cannot return labels() or type(r).
        """
        src_int = _to_int_id(src_id)
        
        if edge_type:
            query = f'''
                MATCH (a:{src_label} {{id: $src_id}})-[r:{edge_type}]->(b)
                RETURN b.node_id AS dst_id
            '''
        else:
            # If no edge_type specified, return empty
            # This is a limitation of HydraDB
            return []
        
        return self._run(query, {"src_id": src_int})

    def query(self, cypher: str, params: dict = None) -> list[dict]:
        """Run a arbitrary Cypher query."""
        return self._run(cypher, params)

    def count_nodes(self, label: str) -> int:
        """Count nodes with a label."""
        result = self._run(f'MATCH (n:{label}) RETURN count(*) AS count')
        return result[0]["count"] if result else 0

    def delete_node(self, label: str, node_id: str):
        """Delete a node and all its edges."""
        int_id = _to_int_id(node_id)
        self._write(
            f'MATCH (n:{label} {{id: $id}}) DETACH DELETE n',
            {"id": int_id}
        )

    def stats(self) -> dict:
        """Get database statistics.
        
        Note: HydraDB requires label in MATCH.
        We count nodes with specific labels.
        """
        # Count Run nodes
        result = self._run('MATCH (n:Run) RETURN count(*) AS count')
        run_count = result[0]["count"] if result else 0
        
        return {"Run": run_count}

    def health(self) -> bool:
        """Check if HydraDB is reachable."""
        try:
            self._run("MATCH (n:Root) RETURN count(*) AS count")
            return True
        except Exception:
            return False
