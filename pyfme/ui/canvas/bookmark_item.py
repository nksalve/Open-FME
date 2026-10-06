"""
Bookmark Item for visual grouping of nodes on open-FME canvas.
Inspired by FME Workbench Bookmarks.
"""

from __future__ import annotations
import uuid
from typing import List, Optional, Set
from PyQt6.QtWidgets import (
    QGraphicsItem, QGraphicsRectItem, QStyleOptionGraphicsItem, QWidget,
    QInputDialog, QColorDialog, QMenu
)
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QLinearGradient
)


# Standard FME Bookmark Color Palette
BOOKMARK_COLORS = {
    "Pink": "#e91e63",
    "Purple": "#9c27b0",
    "Deep Purple": "#673ab7",
    "Indigo": "#3f51b5",
    "Blue": "#2196f3",
    "Cyan": "#00bcd4",
    "Teal": "#009688",
    "Green": "#4caf50",
    "Orange": "#ff9800",
    "Deep Orange": "#ff5722",
    "Brown": "#795548",
    "Grey": "#607d8b",
}


class BookmarkItem(QGraphicsItem):
    """
    FME Workbench Bookmark container item.
    Encloses and groups nodes with a colored header and translucent body.
    Dragging the bookmark moves all contained nodes together.
    """

    HEADER_HEIGHT = 28.0
    CORNER_RADIUS = 6.0
    RESIZE_HANDLE_SIZE = 12.0

    def __init__(
        self,
        title: str = "New Bookmark",
        rect: Optional[QRectF] = None,
        color: str = "#2196f3",
        bookmark_id: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.id = bookmark_id or str(uuid.uuid4())
        self.title = title
        self.color = color  # Hex color string
        self._rect = rect or QRectF(0, 0, 320, 220)

        # Resizing state
        self._resizing = False
        self._resize_start_pos = QPointF()
        self._resize_start_rect = QRectF()

        # Dragging state for moving contained nodes
        self._last_pos = QPointF()
        self._contained_nodes_before_move: List[QGraphicsItem] = []

        # Flags: send geometry changes, movable, selectable
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        # Keep bookmarks below wires and nodes
        self.setZValue(-10.0)

    @property
    def rect(self) -> QRectF:
        return self._rect

    def set_rect(self, rect: QRectF):
        self.prepareGeometryChange()
        self._rect = rect
        self.update()

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-6, -6, 6, 6)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(self._rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        return path

    def get_contained_node_items(self) -> List[QGraphicsItem]:
        """Finds all NodeItems whose center is within this bookmark's scene bounds."""
        if not self.scene():
            return []
        from pyfme.ui.canvas.node_item import NodeItem

        scene_rect = self.mapRectToScene(self._rect)
        nodes: List[QGraphicsItem] = []
        for item in self.scene().items():
            if isinstance(item, NodeItem):
                node_center = item.mapToScene(item.boundingRect().center())
                if scene_rect.contains(node_center):
                    nodes.append(item)
        return nodes

    def mousePressEvent(self, event):
        pos = event.pos()
        # Check if clicking on bottom-right resize handle
        handle_rect = QRectF(
            self._rect.right() - self.RESIZE_HANDLE_SIZE,
            self._rect.bottom() - self.RESIZE_HANDLE_SIZE,
            self.RESIZE_HANDLE_SIZE,
            self.RESIZE_HANDLE_SIZE,
        )
        if handle_rect.contains(pos) and event.button() == Qt.MouseButton.LeftButton:
            self._resizing = True
            self._resize_start_pos = event.scenePos()
            self._resize_start_rect = QRectF(self._rect)
            event.accept()
            return

        self._resizing = False
        self._last_pos = self.pos()
        # Record all nodes currently contained in this bookmark
        self._contained_nodes_before_move = self.get_contained_node_items()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.scenePos() - self._resize_start_pos
            new_w = max(160.0, self._resize_start_rect.width() + delta.x())
            new_h = max(100.0, self._resize_start_rect.height() + delta.y())
            self.set_rect(QRectF(self._resize_start_rect.x(), self._resize_start_rect.y(), new_w, new_h))
            event.accept()
            return

        # Normal move: calculate movement delta
        old_scene_pos = self.mapToScene(QPointF(0, 0))
        super().mouseMoveEvent(event)
        new_scene_pos = self.mapToScene(QPointF(0, 0))
        delta = new_scene_pos - old_scene_pos

        # Move all contained nodes by the exact same delta
        if self.scene() and delta.manhattanLength() > 0.1:
            for node_item in self._contained_nodes_before_move:
                # Only move if the node itself is not already selected (to avoid double-moving)
                if not node_item.isSelected():
                    node_item.setPos(node_item.pos() + delta)
                    if hasattr(self.scene(), "update_node_wires"):
                        self.scene().update_node_wires(node_item)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.scene() and hasattr(self.scene(), "graph_modified"):
            self.scene().graph_modified.emit()

    def mouseDoubleClickEvent(self, event):
        # Double click on header to rename bookmark
        if event.pos().y() <= self.HEADER_HEIGHT:
            new_title, ok = QInputDialog.getText(
                None, "Edit Bookmark Title", "Bookmark Title:", text=self.title
            )
            if ok and new_title.strip():
                self.title = new_title.strip()
                self.update()
                if self.scene() and hasattr(self.scene(), "graph_modified"):
                    self.scene().graph_modified.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        rename_act = menu.addAction("✏️ Rename Bookmark...")
        color_menu = menu.addMenu("🎨 Change Color")
        for color_name, color_hex in BOOKMARK_COLORS.items():
            act = color_menu.addAction(color_name)
            act.setData(color_hex)
        custom_color_act = color_menu.addAction("Custom Color...")

        menu.addSeparator()
        zoom_act = menu.addAction("🔍 Zoom to Bookmark")
        delete_act = menu.addAction("🗑️ Delete Bookmark")

        selected = menu.exec(event.screenPos())
        if selected == rename_act:
            new_title, ok = QInputDialog.getText(
                None, "Edit Bookmark", "Bookmark Title:", text=self.title
            )
            if ok and new_title.strip():
                self.title = new_title.strip()
                self.update()
                if self.scene() and hasattr(self.scene(), "graph_modified"):
                    self.scene().graph_modified.emit()
        elif selected == custom_color_act:
            chosen = QColorDialog.getColor(QColor(self.color), None, "Select Bookmark Color")
            if chosen.isValid():
                self.color = chosen.name()
                self.update()
                if self.scene() and hasattr(self.scene(), "graph_modified"):
                    self.scene().graph_modified.emit()
        elif selected in color_menu.actions():
            self.color = selected.data()
            self.update()
            if self.scene() and hasattr(self.scene(), "graph_modified"):
                self.scene().graph_modified.emit()
        elif selected == zoom_act:
            if self.scene() and self.scene().views():
                self.scene().views()[0].fitInView(self.mapRectToScene(self._rect).adjusted(-40, -40, 40, 40), Qt.AspectRatioMode.KeepAspectRatio)
        elif selected == delete_act:
            if self.scene():
                self.scene().removeItem(self)
                if hasattr(self.scene(), "bookmarks"):
                    self.scene().bookmarks = [b for b in self.scene().bookmarks if b != self]
                if hasattr(self.scene(), "graph_modified"):
                    self.scene().graph_modified.emit()
        event.accept()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        base_color = QColor(self.color)
        bg_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 38)
        header_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 215)
        border_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 230)

        # 1. Background body
        body_path = QPainterPath()
        body_path.addRoundedRect(self._rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        painter.setBrush(QBrush(bg_color))
        pen = QPen(border_color, 2.0 if not self.isSelected() else 3.0)
        if self.isSelected():
            pen.setColor(QColor("#ffffff"))
        painter.setPen(pen)
        painter.drawPath(body_path)

        # 2. Header Bar
        header_rect = QRectF(self._rect.x(), self._rect.y(), self._rect.width(), self.HEADER_HEIGHT)
        header_path = QPainterPath()
        header_path.moveTo(header_rect.x(), header_rect.bottom())
        header_path.lineTo(header_rect.x(), header_rect.y() + self.CORNER_RADIUS)
        header_path.quadTo(header_rect.x(), header_rect.y(), header_rect.x() + self.CORNER_RADIUS, header_rect.y())
        header_path.lineTo(header_rect.right() - self.CORNER_RADIUS, header_rect.y())
        header_path.quadTo(header_rect.right(), header_rect.y(), header_rect.right(), header_rect.y() + self.CORNER_RADIUS)
        header_path.lineTo(header_rect.right(), header_rect.bottom())
        header_path.closeSubpath()

        painter.fillPath(header_path, QBrush(header_color))

        # 3. Bookmark Title Text & Folder/Tag Icon
        painter.setPen(QColor("#ffffff"))
        font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        painter.setFont(font)
        title_rect = QRectF(header_rect.x() + 10, header_rect.y(), header_rect.width() - 20, header_rect.height())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"▼  {self.title}")

        # 4. Resize Handle Indicator in bottom-right corner
        handle_x = self._rect.right() - 8
        handle_y = self._rect.bottom() - 8
        painter.setPen(QPen(border_color, 1.5))
        painter.drawLine(int(handle_x - 6), int(handle_y), int(handle_x), int(handle_y - 6))
        painter.drawLine(int(handle_x - 3), int(handle_y), int(handle_x), int(handle_y - 3))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "color": self.color,
            "x": self.pos().x() + self._rect.x(),
            "y": self.pos().y() + self._rect.y(),
            "width": self._rect.width(),
            "height": self._rect.height(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookmarkItem:
        bm = cls(
            title=data.get("title", "Bookmark"),
            rect=QRectF(0, 0, data.get("width", 320), data.get("height", 220)),
            color=data.get("color", "#2196f3"),
            bookmark_id=data.get("id"),
        )
        bm.setPos(data.get("x", 0.0), data.get("y", 0.0))
        return bm
