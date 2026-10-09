"""
Central Node Registry for open-FME. Manages registration, search, and instantiation of nodes.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

if TYPE_CHECKING:
    from pyfme.engine.nodes.base import BaseNode, NodeCategory


class NodeRegistry:
    _nodes: Dict[str, Type[Any]] = {}
    _normalized_index: Dict[str, Type[Any]] = {}

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not name:
            return ""
        return name.lower().replace(" ", "").replace("-", "").replace("_", "")

    @classmethod
    def register(cls, node_class: Type[BaseNode]) -> Type[BaseNode]:
        """Decorator to register a node class."""
        cls._nodes[node_class.node_type] = node_class
        norm_type = cls._normalize_name(node_class.node_type)
        cls._normalized_index[norm_type] = node_class
        if hasattr(node_class, "get_display_name"):
            disp_space = cls._normalize_name(node_class.get_display_name())
            disp_dash = cls._normalize_name(node_class.get_display_name(separator="-"))
            cls._normalized_index[disp_space] = node_class
            cls._normalized_index[disp_dash] = node_class
        return node_class

    @classmethod
    def get(cls, node_type: str) -> Optional[Type[BaseNode]]:
        if not node_type:
            return None
        # 1. Exact match on registered node_type
        if node_type in cls._nodes:
            return cls._nodes[node_type]
        # 2. Normalized match (handles spaces, dashes, case-insensitive, e.g. 'CSV Reader', 'CSV-Reader')
        norm = cls._normalize_name(node_type)
        return cls._normalized_index.get(norm)

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
        norm_q = cls._normalize_name(q)
        results = []
        for node in cls._nodes.values():
            disp = node.get_display_name() if hasattr(node, "get_display_name") else ""
            desc = node.description or ""
            if (
                q in node.node_type.lower()
                or (disp and q in disp.lower())
                or (disp and q in disp.replace(" ", "-").lower())
                or (norm_q and norm_q in cls._normalize_name(node.node_type))
                or q in desc.lower()
            ):
                results.append(node)
        return results
