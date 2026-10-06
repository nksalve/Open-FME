"""
Undo / Redo Commands using PyQt6 QUndoCommand.
Provides full undo/redo history for node creation, deletion, movement,
wire connections, and parameter changes.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from PyQt6.QtGui import QUndoCommand
from PyQt6.QtCore import QPointF

if TYPE_CHECKING:
    from pyfme.ui.canvas.scene import CanvasScene
    from pyfme.engine.nodes.base import BaseNode
    from pyfme.engine.graph import Connection


class AddNodeCommand(QUndoCommand):
    """Command to add a node to the canvas."""

    def __init__(self, scene: CanvasScene, node: BaseNode, pos: QPointF, text: str = "Add Transformer"):
        super().__init__(text)
        self.scene = scene
        self.node = node
        self.pos = pos
        self.node_id = node.id

    def redo(self):
        self.node.x = self.pos.x()
        self.node.y = self.pos.y()
        self.scene.graph.add_node(self.node)
        self.scene._create_node_item(self.node)
        self.scene.graph_modified.emit()

    def undo(self):
        item = self.scene.node_items.get(self.node_id)
        if item:
            self.scene._delete_node_item_internal(item)
        self.scene.graph_modified.emit()


class RemoveItemsCommand(QUndoCommand):
    """Command to delete selected nodes and wires, with full restoration on undo."""

    def __init__(self, scene: CanvasScene, node_items: List[Any], wire_items: List[Any], text: str = "Delete"):
        super().__init__(text)
        self.scene = scene
        self.saved_nodes: List[Dict[str, Any]] = [item.node.to_dict() for item in node_items]
        self.saved_connections: List[Dict[str, Any]] = []

        # Find all connections attached to these nodes, plus standalone selected wires
        node_ids = {item.node.id for item in node_items}
        for conn in self.scene.graph.connections:
            if conn.from_node_id in node_ids or conn.to_node_id in node_ids:
                if conn.to_dict() not in self.saved_connections:
                    self.saved_connections.append(conn.to_dict())

        for wire in wire_items:
            if wire.from_port and wire.to_port:
                c_dict = {
                    "from_node_id": wire.from_port.node_item.node.id,
                    "from_port": wire.from_port.port_name,
                    "to_node_id": wire.to_port.node_item.node.id,
                    "to_port": wire.to_port.port_name,
                }
                if c_dict not in self.saved_connections:
                    self.saved_connections.append(c_dict)

    def redo(self):
        for n_data in self.saved_nodes:
            n_id = n_data["id"]
            item = self.scene.node_items.get(n_id)
            if item:
                self.scene._delete_node_item_internal(item)

        for c_data in self.saved_connections:
            self.scene.graph.disconnect(
                c_data["from_node_id"], c_data["from_port"],
                c_data["to_node_id"], c_data["to_port"]
            )
            self.scene._remove_wire_item_by_connection(
                c_data["from_node_id"], c_data["from_port"],
                c_data["to_node_id"], c_data["to_port"]
            )
        self.scene.graph_modified.emit()

    def undo(self):
        from pyfme.engine.registry import NodeRegistry

        # 1. Restore nodes
        for n_data in self.saved_nodes:
            node = NodeRegistry.create(n_data["node_type"], node_id=n_data["id"], custom_name=n_data.get("custom_name"))
            if node:
                pos = n_data.get("position", {})
                node.x = pos.get("x", 0.0)
                node.y = pos.get("y", 0.0)
                node.params.update(n_data.get("params", {}))
                self.scene.graph.add_node(node)
                self.scene._create_node_item(node)

        # 2. Restore connections
        for c_data in self.saved_connections:
            self.scene.graph.connect(
                c_data["from_node_id"], c_data["from_port"],
                c_data["to_node_id"], c_data["to_port"]
            )
            from_node = self.scene.node_items.get(c_data["from_node_id"])
            to_node = self.scene.node_items.get(c_data["to_node_id"])
            if from_node and to_node:
                p_out = from_node.output_port_items.get(c_data["from_port"])
                p_in = to_node.input_port_items.get(c_data["to_port"])
                if p_out and p_in:
                    self.scene._create_wire_item(p_out, p_in)

        self.scene.graph_modified.emit()


class ConnectWireCommand(QUndoCommand):
    """Command to connect an output port to an input port."""

    def __init__(self, scene: CanvasScene, from_node_id: str, from_port: str, to_node_id: str, to_port: str, text: str = "Connect Ports"):
        super().__init__(text)
        self.scene = scene
        self.from_id = from_node_id
        self.from_port = from_port
        self.to_id = to_node_id
        self.to_port = to_port

    def redo(self):
        conn = self.scene.graph.connect(self.from_id, self.from_port, self.to_id, self.to_port)
        if conn:
            from_node = self.scene.node_items.get(self.from_id)
            to_node = self.scene.node_items.get(self.to_id)
            if from_node and to_node:
                p_out = from_node.output_port_items.get(self.from_port)
                p_in = to_node.input_port_items.get(self.to_port)
                if p_out and p_in:
                    self.scene._create_wire_item(p_out, p_in)
        self.scene.graph_modified.emit()

    def undo(self):
        self.scene.graph.disconnect(self.from_id, self.from_port, self.to_id, self.to_port)
        self.scene._remove_wire_item_by_connection(self.from_id, self.from_port, self.to_id, self.to_port)
        self.scene.graph_modified.emit()


class MoveNodesCommand(QUndoCommand):
    """Command recording movement of one or more nodes."""

    def __init__(self, scene: CanvasScene, moves: List[Tuple[str, QPointF, QPointF]], text: str = "Move"):
        super().__init__(text)
        self.scene = scene
        self.moves = moves  # List of (node_id, old_pos, new_pos)

    def redo(self):
        for node_id, _, new_pos in self.moves:
            item = self.scene.node_items.get(node_id)
            if item:
                item.setPos(new_pos)
                item.node.x = new_pos.x()
                item.node.y = new_pos.y()
                self.scene.update_node_wires(item)
        self.scene.graph_modified.emit()

    def undo(self):
        for node_id, old_pos, _ in self.moves:
            item = self.scene.node_items.get(node_id)
            if item:
                item.setPos(old_pos)
                item.node.x = old_pos.x()
                item.node.y = old_pos.y()
                self.scene.update_node_wires(item)
        self.scene.graph_modified.emit()
