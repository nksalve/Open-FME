"""
Central Node Registry for open-FME. Manages registration, search, and instantiation of nodes.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

if TYPE_CHECKING:
    from pyfme.engine.nodes.base import BaseNode, NodeCategory


class NodeRegistry:
    _nodes: Dict[str, Type[Any]] = {}

    @classmethod
    def register(cls, node_class: Type[BaseNode]) -> Type[BaseNode]:
        """Decorator to register a node class."""
        cls._nodes[node_class.node_type] = node_class
        return node_class

    @classmethod
    def get(cls, node_type: str) -> Optional[Type[BaseNode]]:
        return cls._nodes.get(node_type)

    @classmethod
    def create(cls, node_type: str, **kwargs) -> Optional[BaseNode]:
        node_cls = cls.get(node_type)
        if node_cls:
            return node_cls(**kwargs)
        return None

    @classmethod
    def all_nodes(cls) -> Dict[str, Type[BaseNode]]:
        return dict(cls._nodes)

    @classmethod
    def get_by_category(cls, category: Any) -> List[Type[Any]]:
        cat_val = category.value if hasattr(category, "value") else str(category)
        return [node for node in cls._nodes.values() if (node.category.value if hasattr(node.category, "value") else str(node.category)) == cat_val]

    @classmethod
    def search(cls, query: str) -> List[Type[BaseNode]]:
        q = query.lower().strip()
        if not q:
            return list(cls._nodes.values())
        return [
            node for node in cls._nodes.values()
            if q in node.node_type.lower() or q in node.description.lower()
        ]
