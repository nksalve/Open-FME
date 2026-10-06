"""
Visual Port (pin) item on a canvas node.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QBrush, QColor, QPen, QPainter, QFont
from pyfme.engine.nodes.base import PortType

if TYPE_CHECKING:
    from pyfme.ui.canvas.node_item import NodeItem


class PortItem(QGraphicsItem):
    RADIUS = 6.0

    def __init__(self, node_item: NodeItem, name: str, port_type: PortType, description: str = "", parent=None):
        super().__init__(parent or node_item)
        self.node_item = node_item
        self.port_name = name
        self.port_type = port_type
        self.description = description
        self.is_hovered = False

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        desc_line = f"<br><span style='color: #b0bec5;'>{description}</span>" if description else ""
        self.setToolTip(f"<b>{name}</b> ({port_type.value.capitalize()} Port){desc_line}")

        # Text label
        self.label = QGraphicsTextItem(name, self)
        font = QFont("Segoe UI", 9)
        font.setBold(False)
        self.label.setFont(font)
        self.label.setDefaultTextColor(QColor("#c8c8d8"))
        if self.port_type == PortType.INPUT:
            self.label.setPos(10, -10)
        else:
            # Right-aligned for output
            self.label.setPos(-self.label.boundingRect().width() - 8, -10)

    def boundingRect(self) -> QRectF:
        r = self.RADIUS + 3
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.is_hovered:
            glow_pen = QPen(QColor(33, 150, 243, 180), 3)
            painter.setPen(glow_pen)
            painter.drawEllipse(QPointF(0, 0), self.RADIUS + 2, self.RADIUS + 2)

        # Base circle
        fill_color = QColor("#00bcd4") if self.is_hovered else QColor("#e0e0e0")
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(QColor("#24242c"), 1.5))
        painter.drawEllipse(QPointF(0, 0), self.RADIUS, self.RADIUS)

        # Center dot
        painter.setBrush(QBrush(QColor("#1e1e24")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), 2.5, 2.5)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def scene_center(self) -> QPointF:
        """Returns pin center in scene coordinates for wire attachment."""
        return self.scenePos()
