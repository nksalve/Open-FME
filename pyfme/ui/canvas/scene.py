"""
Canvas Scene for managing visual nodes, ports, wires, undo/redo, and clipboard operations.
"""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional, Tuple
from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsItem, QGraphicsSceneMouseEvent, QMenu
)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QUndoStack

from pyfme.engine.graph import WorkflowGraph, Connection
from pyfme.engine.nodes.base import BaseNode, PortType
from pyfme.engine.registry import NodeRegistry
from pyfme.engine.dataset import FeatureDataset
from pyfme.ui.canvas.node_item import NodeItem
from pyfme.ui.canvas.port_item import PortItem
from pyfme.ui.canvas.wire_item import WireItem
from pyfme.ui.canvas.bookmark_item import BookmarkItem, BOOKMARK_COLORS
from pyfme.ui.canvas.annotation_item import AnnotationItem
from pyfme.ui.canvas.undo_commands import (
    AddNodeCommand, RemoveItemsCommand, ConnectWireCommand, MoveNodesCommand
)


class CanvasScene(QGraphicsScene):
    """
    QGraphicsScene handling node layout, wire connections, interactive wiring,
    undo/redo stack, and clipboard cut/copy/paste/duplicate.
    """

    node_selected = pyqtSignal(object)  # Emits BaseNode
    node_inspected = pyqtSignal(object, str, object)  # (BaseNode, port_name, FeatureDataset)
    run_to_this_requested = pyqtSignal(str)  # Emits node_id
    run_from_this_requested = pyqtSignal(str)  # Emits node_id
    graph_modified = pyqtSignal()

    def __init__(self, graph: Optional[WorkflowGraph] = None, parent=None):
        super().__init__(parent)
        self.graph = graph or WorkflowGraph()
        self.node_items: Dict[str, NodeItem] = {}
        self.wire_items: List[WireItem] = []
        self.bookmarks: List[BookmarkItem] = []
        self.annotations: List[AnnotationItem] = []

        # Undo/Redo stack
        self.undo_stack = QUndoStack(self)

        # Interactive wiring state
        self.active_wire: Optional[WireItem] = None
        self.drag_start_port: Optional[PortItem] = None

        # Tracking node movement for undo/redo
        self._move_start_positions: Dict[str, QPointF] = {}

        # Internal clipboard buffer
        self._clipboard_data: Optional[Dict[str, Any]] = None

        self._grid_pixmap = self._create_grid_pixmap()
        self.setSceneRect(-5000, -5000, 10000, 10000)
        self.setBackgroundBrush(QBrush(QColor("#16161b")))

        self.rebuild_from_graph()

    def _create_grid_pixmap(self) -> QPixmap:
        """Cached 24x24 grid tile for hardware-accelerated 60+ FPS canvas rendering."""
        size = 24
        pm = QPixmap(size, size)
        pm.fill(QColor("#16161b"))
        p = QPainter(pm)
        p.setPen(QColor("#282834"))
        p.drawPoint(0, 0)
        p.end()
        return pm

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """Draws tiled background brush in zero Python loops."""
        painter.fillRect(rect, QBrush(self._grid_pixmap))

    def set_graph(self, graph: WorkflowGraph):
        self.graph = graph
        self.undo_stack.clear()
        self.rebuild_from_graph()

    def rebuild_from_graph(self):
        self.clear()
        self.node_items.clear()
        self.wire_items.clear()
        self.bookmarks.clear()
        self.annotations.clear()

        # 1. Add all nodes
        for node in self.graph.nodes.values():
            self._create_node_item(node)

        # 2. Add all connections
        for conn in self.graph.connections:
            from_node = self.node_items.get(conn.from_node_id)
            to_node = self.node_items.get(conn.to_node_id)
            if from_node and to_node:
                p_out = from_node.output_port_items.get(conn.from_port)
                p_in = to_node.input_port_items.get(conn.to_port)
                if p_out and p_in:
                    wire = self._create_wire_item(p_out, p_in)
                    wire.feature_count = conn.feature_count

        # 3. Add bookmarks
        for b_data in getattr(self.graph, "bookmarks", []):
            b_item = BookmarkItem.from_dict(b_data)
            self.addItem(b_item)
            self.bookmarks.append(b_item)

        # 4. Add annotations
        for a_data in getattr(self.graph, "annotations", []):
            a_item = AnnotationItem.from_dict(a_data)
            self.addItem(a_item)
            self.annotations.append(a_item)

    def _create_node_item(self, node: BaseNode) -> NodeItem:
        item = NodeItem(node)
        self.addItem(item)
        self.node_items[node.id] = item
        return item

    def _delete_node_item_internal(self, node_item: NodeItem):
        node_id = node_item.node.id
        self.graph.remove_node(node_id)
        # Remove attached wires
        to_remove = [
            w for w in self.wire_items
            if (w.from_port and w.from_port.node_item == node_item) or
               (w.to_port and w.to_port.node_item == node_item)
        ]
        for w in to_remove:
            self.removeItem(w)
            if w in self.wire_items:
                self.wire_items.remove(w)
            if w.from_port and hasattr(w.from_port.node_item, "connected_wires"):
                w.from_port.node_item.connected_wires.discard(w)
            if w.to_port and hasattr(w.to_port.node_item, "connected_wires"):
                w.to_port.node_item.connected_wires.discard(w)
        self.removeItem(node_item)
        if node_id in self.node_items:
            del self.node_items[node_id]

    def _create_wire_item(self, from_port: PortItem, to_port: PortItem) -> WireItem:
        wire = WireItem(from_port, to_port)
        self.addItem(wire)
        self.wire_items.append(wire)
        if hasattr(from_port.node_item, "connected_wires"):
            from_port.node_item.connected_wires.add(wire)
        if hasattr(to_port.node_item, "connected_wires"):
            to_port.node_item.connected_wires.add(wire)
        return wire

    def _remove_wire_item_by_connection(self, from_id: str, from_port: str, to_id: str, to_port: str):
        to_remove = []
        for w in self.wire_items:
            if w.from_port and w.to_port:
                if (
                    w.from_port.node_item.node.id == from_id
                    and w.from_port.port_name == from_port
                    and w.to_port.node_item.node.id == to_id
                    and w.to_port.port_name == to_port
                ):
                    to_remove.append(w)
        for w in to_remove:
            self.removeItem(w)
            if w in self.wire_items:
                self.wire_items.remove(w)
            if w.from_port and hasattr(w.from_port.node_item, "connected_wires"):
                w.from_port.node_item.connected_wires.discard(w)
            if w.to_port and hasattr(w.to_port.node_item, "connected_wires"):
                w.to_port.node_item.connected_wires.discard(w)

    def add_node_at_position(self, node: BaseNode, pos: QPointF) -> NodeItem:
        """Adds node with undo/redo support."""
        cmd = AddNodeCommand(self, node, pos, f"Add {node.node_type}")
        self.undo_stack.push(cmd)
        return self.node_items.get(node.id)

    def update_node_wires(self, node_item: NodeItem):
        """Called when a node moves; updates only connected wire paths."""
        wires = getattr(node_item, "connected_wires", None)
        if wires is not None and len(wires) > 0:
            for wire in wires:
                wire.update_path()
        else:
            for wire in self.wire_items:
                if (wire.from_port and wire.from_port.node_item == node_item) or \
                   (wire.to_port and wire.to_port.node_item == node_item):
                    wire.update_path()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else None)

        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicked on a port pin
            if isinstance(item, PortItem):
                self.drag_start_port = item
                if item.port_type == PortType.OUTPUT:
                    self.active_wire = WireItem(from_port=item)
                else:
                    self.active_wire = WireItem(to_port=item)
                self.active_wire.temp_end_point = event.scenePos()
                self.addItem(self.active_wire)
                event.accept()
                return

            # Record positions for undoable node move
            self._move_start_positions.clear()
            for selected in self.selectedItems():
                if isinstance(selected, NodeItem):
                    self._move_start_positions[selected.node.id] = QPointF(selected.pos())

        super().mousePressEvent(event)

        # Notify selection change
        selected_nodes = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
        if selected_nodes:
            self.node_selected.emit(selected_nodes[0].node)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self.active_wire:
            self.active_wire.temp_end_point = event.scenePos()
            self.active_wire.update_path()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        # 1. Complete wire connection if active
        if self.active_wire and self.drag_start_port:
            item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else None)
            target_port = item if isinstance(item, PortItem) else None

            # Remove temporary drag wire from canvas
            self.removeItem(self.active_wire)
            self.active_wire = None
            start_p = self.drag_start_port
            self.drag_start_port = None

            if target_port and target_port != start_p:
                p1, p2 = start_p, target_port
                if p1.port_type == PortType.OUTPUT and p2.port_type == PortType.INPUT:
                    src_port, dst_port = p1, p2
                elif p1.port_type == PortType.INPUT and p2.port_type == PortType.OUTPUT:
                    src_port, dst_port = p2, p1
                else:
                    src_port, dst_port = None, None

                if src_port and dst_port and src_port.node_item != dst_port.node_item:
                    cmd = ConnectWireCommand(
                        self,
                        src_port.node_item.node.id,
                        src_port.port_name,
                        dst_port.node_item.node.id,
                        dst_port.port_name,
                    )
                    self.undo_stack.push(cmd)
                    event.accept()
                    return

            event.accept()
            return

        super().mouseReleaseEvent(event)

        # 2. Check if moved nodes changed position, and push undo command
        if self._move_start_positions:
            moves = []
            for node_id, old_pos in self._move_start_positions.items():
                item = self.node_items.get(node_id)
                if item and (item.pos() != old_pos):
                    moves.append((node_id, old_pos, QPointF(item.pos())))
            if moves:
                cmd = MoveNodesCommand(self, moves)
                self.undo_stack.push(cmd)
            self._move_start_positions.clear()

    def contextMenuEvent(self, event):
        try:
            item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else None)
            menu = QMenu()

            if isinstance(item, PortItem):
                port_name = item.port_name
                node = item.node_item.node
                action_inspect = menu.addAction(f"Inspect '{port_name}' Data")
                chosen = menu.exec(event.screenPos())
                if chosen == action_inspect:
                    outputs = getattr(node, "last_outputs", None) or {}
                    inputs = getattr(node, "last_inputs", None) or {}
                    ds = outputs.get(port_name) if item.port_type == PortType.OUTPUT else inputs.get(port_name)
                    self.node_inspected.emit(node, port_name, ds or FeatureDataset.empty())
                return

            if isinstance(item, NodeItem):
                action_run_to = menu.addAction("▶  Run to This (Feature Caching)")
                action_run_from = menu.addAction("▶  Run From This")
                action_inspect = menu.addAction("🔍  Inspect Cached Features")
                menu.addSeparator()
                action_cut = menu.addAction("Cut (Ctrl+X)")
                action_copy = menu.addAction("Copy (Ctrl+C)")
                action_duplicate = menu.addAction("Duplicate (Ctrl+D)")
                action_delete = menu.addAction("Delete (Del)")
                chosen = menu.exec(event.screenPos())
                if chosen == action_run_to:
                    self.run_to_this_requested.emit(item.node.id)
                elif chosen == action_run_from:
                    self.run_from_this_requested.emit(item.node.id)
                elif chosen == action_inspect:
                    out_ports = item.node.get_output_ports()
                    port_name = out_ports[0].name if out_ports else "Output"
                    outputs = getattr(item.node, "last_outputs", None) or {}
                    ds = outputs.get(port_name, FeatureDataset.empty())
                    self.node_inspected.emit(item.node, port_name, ds)
                elif chosen == action_cut:
                    self.cut_selected()
                elif chosen == action_copy:
                    self.copy_selected()
                elif chosen == action_duplicate:
                    self.duplicate_selected()
                elif chosen == action_delete:
                    self.remove_selected()
                return
        except Exception:
            return


        # Empty canvas context menu
        undo_text = f"Undo {self.undo_stack.undoText()} (Ctrl+Z)" if self.undo_stack.canUndo() else "Undo (Ctrl+Z)"
        action_undo = menu.addAction(undo_text)
        action_undo.setEnabled(self.undo_stack.canUndo())

        redo_text = f"Redo {self.undo_stack.redoText()} (Ctrl+Y)" if self.undo_stack.canRedo() else "Redo (Ctrl+Y)"
        action_redo = menu.addAction(redo_text)
        action_redo.setEnabled(self.undo_stack.canRedo())

        menu.addSeparator()
        action_paste = menu.addAction("Paste (Ctrl+V)")
        action_select_all = menu.addAction("Select All (Ctrl+A)")
        if not self._clipboard_data or not self._clipboard_data.get("nodes"):
            action_paste.setEnabled(False)

        menu.addSeparator()
        action_add_bm = menu.addAction("🔖 Add Bookmark... (Ctrl+B)")
        action_add_ann = menu.addAction("📝 Add Annotation Note...")

        chosen = menu.exec(event.screenPos())
        if chosen == action_undo:
            self.undo_stack.undo()
        elif chosen == action_redo:
            self.undo_stack.redo()
        elif chosen == action_paste:
            self.paste(offset=QPointF(20, 20))
        elif chosen == action_select_all:
            self.select_all()
        elif chosen == action_add_bm:
            self.add_bookmark(pos=event.scenePos())
        elif chosen == action_add_ann:
            self.add_annotation(pos=event.scenePos())

    def add_bookmark(
        self,
        title: str = "New Bookmark",
        rect: Optional[QRectF] = None,
        color: str = "#2196f3",
        pos: Optional[QPointF] = None
    ) -> BookmarkItem:
        if rect is None:
            selected_nodes = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
            if selected_nodes:
                min_x = min(n.pos().x() for n in selected_nodes) - 30
                min_y = min(n.pos().y() for n in selected_nodes) - 45
                max_x = max(n.pos().x() + n.WIDTH for n in selected_nodes) + 30
                max_y = max(n.pos().y() + n.calculate_height() for n in selected_nodes) + 30
                b_rect = QRectF(0, 0, max(260.0, max_x - min_x), max(180.0, max_y - min_y))
                b_pos = QPointF(min_x, min_y)
            else:
                b_rect = QRectF(0, 0, 360, 240)
                b_pos = pos or QPointF(100, 100)
        else:
            b_rect = rect
            b_pos = pos or QPointF(100, 100)

        bm = BookmarkItem(title=title, rect=b_rect, color=color)
        bm.setPos(b_pos)
        self.addItem(bm)
        self.bookmarks.append(bm)
        self.sync_to_graph()
        self.graph_modified.emit()
        return bm

    def add_annotation(
        self,
        text: str = "Add workflow documentation here...",
        pos: Optional[QPointF] = None,
        bg_color: str = "#fff9c4"
    ) -> AnnotationItem:
        ann = AnnotationItem(text=text, bg_color=bg_color)
        ann.setPos(pos or QPointF(200, 200))
        self.addItem(ann)
        self.annotations.append(ann)
        self.sync_to_graph()
        self.graph_modified.emit()
        return ann

    def sync_to_graph(self):
        """Synchronizes canvas bookmarks and annotations back to WorkflowGraph."""
        self.graph.bookmarks = [b.to_dict() for b in self.bookmarks if b.scene() == self]
        self.graph.annotations = [a.to_dict() for a in self.annotations if a.scene() == self]

    def remove_selected(self):
        """Removes selected nodes, wires, bookmarks, and annotations with full Undo/Redo."""
        node_items = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
        wire_items = [i for i in self.selectedItems() if isinstance(i, WireItem)]
        bookmark_items = [i for i in self.selectedItems() if isinstance(i, BookmarkItem)]
        annotation_items = [i for i in self.selectedItems() if isinstance(i, AnnotationItem)]

        for b in bookmark_items:
            self.removeItem(b)
            if b in self.bookmarks:
                self.bookmarks.remove(b)

        for a in annotation_items:
            self.removeItem(a)
            if a in self.annotations:
                self.annotations.remove(a)

        if node_items or wire_items:
            cmd = RemoveItemsCommand(self, node_items, wire_items)
            self.undo_stack.push(cmd)

        self.sync_to_graph()
        self.graph_modified.emit()

    # -------------------------------------------------------------
    # Clipboard Operations: Cut, Copy, Paste, Duplicate, Select All
    # -------------------------------------------------------------
    def copy_selected(self):
        """Copies selected nodes and their internal connections to clipboard."""
        selected_nodes = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
        if not selected_nodes:
            return

        selected_ids = {i.node.id for i in selected_nodes}
        nodes_data = [i.node.to_dict() for i in selected_nodes]

        # Only copy wires connecting two selected nodes
        connections_data = [
            c.to_dict() for c in self.graph.connections
            if c.from_node_id in selected_ids and c.to_node_id in selected_ids
        ]

        self._clipboard_data = {
            "nodes": nodes_data,
            "connections": connections_data,
        }

    def cut_selected(self):
        """Copies selected items to clipboard and deletes them (undoable)."""
        self.copy_selected()
        self.remove_selected()

    def paste(self, offset: QPointF = QPointF(40, 40)):
        """Pastes clipboard items with unique IDs and offset (undoable)."""
        if not self._clipboard_data or not self._clipboard_data.get("nodes"):
            return

        # Map old IDs to new unique IDs
        id_map: Dict[str, str] = {}
        new_nodes: List[BaseNode] = []

        for n_data in self._clipboard_data["nodes"]:
            old_id = n_data["id"]
            new_id = str(uuid.uuid4())
            id_map[old_id] = new_id

            node = NodeRegistry.create(
                n_data["node_type"],
                node_id=new_id,
                custom_name=n_data.get("custom_name"),
            )
            if node:
                pos = n_data.get("position", {})
                node.x = pos.get("x", 0.0) + offset.x()
                node.y = pos.get("y", 0.0) + offset.y()
                node.params.update(n_data.get("params", {}))
                new_nodes.append(node)

        # Group into undo stack command
        self.undo_stack.beginMacro("Paste Items")
        try:
            for node in new_nodes:
                cmd = AddNodeCommand(self, node, QPointF(node.x, node.y))
                self.undo_stack.push(cmd)

            for c_data in self._clipboard_data.get("connections", []):
                new_from = id_map.get(c_data["from_node_id"])
                new_to = id_map.get(c_data["to_node_id"])
                if new_from and new_to:
                    w_cmd = ConnectWireCommand(
                        self, new_from, c_data["from_port"],
                        new_to, c_data["to_port"]
                    )
                    self.undo_stack.push(w_cmd)
        except Exception:
            pass
        finally:
            self.undo_stack.endMacro()

        # Select only the newly pasted nodes
        self.clearSelection()
        for node in new_nodes:
            item = self.node_items.get(node.id)
            if item:
                item.setSelected(True)


    def duplicate_selected(self):
        """Duplicates selected nodes immediately with an offset."""
        self.copy_selected()
        self.paste(offset=QPointF(40, 40))

    def select_all(self):
        for item in self.items():
            if isinstance(item, (NodeItem, WireItem)):
                item.setSelected(True)

    def deselect_all(self):
        self.clearSelection()
