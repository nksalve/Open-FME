"""
Visual Bezier wire connection between two node ports.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsItem
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainterPath, QPen, QColor, QPainter, QBrush, QFont

if TYPE_CHECKING:
    from pyfme.ui.canvas.port_item import PortItem


class WireItem(QGraphicsPathItem):
    """
    Renders a smooth cubic Bezier link with feature count badge.
    """

    def __init__(
        self,
        from_port: Optional[PortItem] = None,
        to_port: Optional[PortItem] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.from_port = from_port
        self.to_port = to_port
        self.temp_end_point: Optional[QPointF] = None
        self.feature_count: int = 0

        self.setZValue(-1)  # Wires sit behind node cards
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        self.normal_color = QColor("#5c6bc0")
        self.hover_color = QColor("#42a5f5")
        self.selected_color = QColor("#ffca28")
        self.is_hovered = False

        self.update_path()

    def update_path(self):
        if not self.from_port:
            return

        start = self.from_port.scene_center()
        if self.to_port:
            end = self.to_port.scene_center()
        elif self.temp_end_point:
            end = self.temp_end_point
        else:
            return

        # Calculate smooth Bezier curve
        dx = abs(end.x() - start.x()) * 0.55
        dx = max(dx, 40.0)

        c1 = QPointF(start.x() + dx, start.y())
        c2 = QPointF(end.x() - dx, end.y())

        path = QPainterPath()
        path.moveTo(start)
        path.cubicTo(c1, c2, end)

        self.setPath(path)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = self.selected_color if self.isSelected() else (self.hover_color if self.is_hovered else self.normal_color)
        width = 3.0 if (self.isSelected() or self.is_hovered) else 2.2

        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

        # If features flowed across this wire, draw badge pill at curve center
        if self.feature_count > 0:
            mid = self.path().pointAtPercent(0.5)
            text = f"{self.feature_count:,} feats"
            font = QFont("Segoe UI", 8)
            font.setBold(True)
            painter.setFont(font)

            metrics = painter.fontMetrics()
            tw = metrics.horizontalAdvance(text) + 12
            th = metrics.height() + 4

            rect = QRectF(mid.x() - tw / 2, mid.y() - th / 2, tw, th)

            # Draw rounded pill badge
            painter.setPen(QPen(QColor("#3f51b5"), 1))
            painter.setBrush(QBrush(QColor("#1a237e")))
            painter.drawRoundedRect(rect, 4, 4)

            # Text
            painter.setPen(QColor("#ffffff"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)
