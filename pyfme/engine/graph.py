"""
Directed Acyclic Graph (DAG) for managing FME-style workflows, connections, and serialization.
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from pyfme.engine.nodes.base import BaseNode
from pyfme.engine.registry import NodeRegistry


class Connection:
    """Represents a directional data link from an output port to an input port."""

    def __init__(
        self,
        from_node_id: str,
        from_port: str,
        to_node_id: str,
        to_port: str,
    ):
        self.from_node_id = from_node_id
        self.from_port = from_port
        self.to_node_id = to_node_id
        self.to_port = to_port
        self.feature_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_node_id": self.from_node_id,
            "from_port": self.from_port,
            "to_node_id": self.to_node_id,
            "to_port": self.to_port,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Connection:
        return cls(
            from_node_id=data["from_node_id"],
            from_port=data["from_port"],
            to_node_id=data["to_node_id"],
            to_port=data["to_port"],
        )

    def matches(self, from_id: str, from_port: str, to_id: str, to_port: str) -> bool:
        return (
            self.from_node_id == from_id
            and self.from_port == from_port
            and self.to_node_id == to_id
            and self.to_port == to_port
        )


class WorkflowGraph:
    """
    Manages the complete pipeline graph, nodes, wires, cycle checking, and serialization.
    """

    def __init__(self, name: str = "Untitled Workspace"):
        self.name = name
        self.nodes: Dict[str, BaseNode] = {}
        self.connections: List[Connection] = []
        self.bookmarks: List[Dict[str, Any]] = []
        self.annotations: List[Dict[str, Any]] = []

    def add_node(self, node: BaseNode) -> BaseNode:
        self.nodes[node.id] = node
        return node

    def remove_node(self, node_id: str) -> None:
        if node_id in self.nodes:
            del self.nodes[node_id]
        # Remove any connections involving this node
        self.connections = [
            conn for conn in self.connections
            if conn.from_node_id != node_id and conn.to_node_id != node_id
        ]

    def connect(
        self,
        from_node_id: str,
        from_port: str,
        to_node_id: str,
        to_port: str
    ) -> Optional[Connection]:
        if from_node_id not in self.nodes or to_node_id not in self.nodes:
            return None

        # Prevent duplicate identical connection
        for c in self.connections:
            if c.matches(from_node_id, from_port, to_node_id, to_port):
                return c

        conn = Connection(from_node_id, from_port, to_node_id, to_port)
        self.connections.append(conn)
        return conn

    def disconnect(self, from_node_id: str, from_port: str, to_node_id: str, to_port: str) -> bool:
        initial_len = len(self.connections)
        self.connections = [
            c for c in self.connections
            if not c.matches(from_node_id, from_port, to_node_id, to_port)
        ]
        return len(self.connections) < initial_len

    def get_upstream_connections(self, node_id: str) -> List[Connection]:
        return [c for c in self.connections if c.to_node_id == node_id]

    def get_downstream_connections(self, node_id: str) -> List[Connection]:
        return [c for c in self.connections if c.from_node_id == node_id]

    def get_topological_order(self) -> List[str]:
        """
        Calculates execution order using Kahn's algorithm for topological sorting.
        Raises ValueError if a cycle is detected.
        """
        in_degree: Dict[str, int] = {node_id: 0 for node_id in self.nodes}
        adj: Dict[str, List[str]] = {node_id: [] for node_id in self.nodes}

        for c in self.connections:
            if c.from_node_id in self.nodes and c.to_node_id in self.nodes:
                adj[c.from_node_id].append(c.to_node_id)
                in_degree[c.to_node_id] += 1

        # Queue of nodes with no incoming dependencies (Sources / Readers)
        queue = [node_id for node_id, deg in in_degree.items() if deg == 0]
        order: List[str] = []

        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.nodes):
            raise ValueError("Cycle detected in workflow graph! FME pipelines must be acyclic (DAG).")

        return order

    def get_ancestors(self, node_id: str) -> set[str]:
        """Finds all upstream ancestor nodes leading to the given node."""
        ancestors: set[str] = set()
        stack = [node_id]
        while stack:
            curr = stack.pop()
            for conn in self.get_upstream_connections(curr):
                if conn.from_node_id not in ancestors:
                    ancestors.add(conn.from_node_id)
                    stack.append(conn.from_node_id)
        return ancestors

    def get_descendants(self, node_id: str) -> set[str]:
        """Finds all downstream descendant nodes reachable from the given node."""
        descendants: set[str] = set()
        stack = [node_id]
        while stack:
            curr = stack.pop()
            for conn in self.get_downstream_connections(curr):
                if conn.to_node_id not in descendants:
                    descendants.add(conn.to_node_id)
                    stack.append(conn.to_node_id)
        return descendants

    def get_topological_order_for_subgraph(self, node_ids: set[str]) -> List[str]:
        """Calculates topological execution order for a subset of nodes."""
        full_order = self.get_topological_order()
        return [nid for nid in full_order if nid in node_ids]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": "1.0.0",
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "connections": [conn.to_dict() for conn in self.connections],
            "bookmarks": self.bookmarks,
            "annotations": self.annotations,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowGraph:
        graph = cls(name=data.get("name", "Untitled Workspace"))
        graph.bookmarks = data.get("bookmarks", [])
        graph.annotations = data.get("annotations", [])
        for node_data in data.get("nodes", []):
            node_type = node_data.get("node_type")
            node = NodeRegistry.create(node_type, node_id=node_data["id"], custom_name=node_data.get("custom_name"))
            if node:
                pos = node_data.get("position", {})
                node.x = pos.get("x", 0.0)
                node.y = pos.get("y", 0.0)
                node.params.update(node_data.get("params", {}))
                graph.add_node(node)

        for conn_data in data.get("connections", []):
            graph.connect(
                conn_data["from_node_id"],
                conn_data["from_port"],
                conn_data["to_node_id"],
                conn_data["to_port"],
            )
        return graph

    def save_to_file(self, file_path: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, file_path: str) -> WorkflowGraph:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
