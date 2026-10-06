"""
Visual Node Card for FME canvas workspace.
"""

from __future__ import annotations
from typing import Dict, List, Optional
from PyQt6.QtWidgets import (
    QGraphicsItem, QGraphicsTextItem, QStyleOptionGraphicsItem, QWidget
)
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QLinearGradient
)
from pyfme.engine.nodes.base import BaseNode, PortType
from pyfme.ui.styles import CATEGORY_COLORS
from pyfme.ui.canvas.port_item import PortItem


class NodeItem(QGraphicsItem):
    """
    Renders an FME-style rounded transformer card with colored header,
    ports, status badges, and interactive dragging.
    """

    WIDTH = 180.0
    HEADER_HEIGHT = 32.0
    PORT_ROW_HEIGHT = 22.0
    CORNER_RADIUS = 6.0

    def __init__(self, node: BaseNode, parent=None):
        super().__init__(parent)
        self.node = node
        self.status = "idle"  # idle, running, success, error
        self.status_message = ""

        self.input_port_items: Dict[str, PortItem] = {}
        self.output_port_items: Dict[str, PortItem] = {}
        self.connected_wires = set()

        # Graphics item configuration
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        # Set position from node
        self.setPos(node.x, node.y)

        # Build port items
        self._init_ports()

        # Build rich hover tooltip
        self._update_tooltip()

    def _update_tooltip(self):
        import html
        cat_str = self.node.category.value if hasattr(self.node.category, "value") else str(self.node.category)
        safe_name = html.escape(str(self.node.name))
        safe_type = html.escape(str(self.node.node_type))
        safe_desc = html.escape(str(self.node.description))
        safe_msg = html.escape(str(self.status_message)) if self.status_message else ""

        tip = (
            f"<div style='font-family: Segoe UI, sans-serif; font-size: 11px;'>"
            f"<b style='font-size: 13px; color: #29b6f6;'>{safe_name}</b> "
            f"<span style='color: #9e9ea8;'>({safe_type})</span><br>"
            f"<span style='color: #ffb74d;'>Category:</span> {cat_str}<br><br>"
            f"<b>Description:</b><br>{safe_desc}<br><hr style='border: 0; border-top: 1px solid #444;'>"
            f"<b>Status:</b> {self.status.capitalize()}<br>"
            f"<b>Features Processed:</b> {self.node.features_processed:,}<br>"
            f"<b>Duration:</b> {self.node.execution_duration_sec:.3f}s"
        )
        if safe_msg:
            tip += f"<br><span style='color: #ef5350;'><b>Message:</b> {safe_msg}</span>"
        tip += "</div>"
        self.setToolTip(tip)


    def _init_ports(self):
        in_ports = self.node.get_input_ports()
        out_ports = self.node.get_output_ports()

        # Input ports on left
        for i, p in enumerate(in_ports):
            y_pos = self.HEADER_HEIGHT + 14 + (i * self.PORT_ROW_HEIGHT)
            port_item = PortItem(self, p.name, PortType.INPUT, description=p.description)
            port_item.setPos(0, y_pos)
            self.input_port_items[p.name] = port_item

        # Output ports on right
        for i, p in enumerate(out_ports):
            y_pos = self.HEADER_HEIGHT + 14 + (i * self.PORT_ROW_HEIGHT)
            port_item = PortItem(self, p.name, PortType.OUTPUT, description=p.description)
            port_item.setPos(self.WIDTH, y_pos)
            self.output_port_items[p.name] = port_item

    def calculate_height(self) -> float:
        in_count = len(self.node.get_input_ports())
        out_count = len(self.node.get_output_ports())
        max_ports = max(in_count, out_count, 1)
        return self.HEADER_HEIGHT + (max_ports * self.PORT_ROW_HEIGHT) + 20.0

    def boundingRect(self) -> QRectF:
        h = self.calculate_height()
        return QRectF(-5, -5, self.WIDTH + 10, h + 10)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        h = self.calculate_height()
        rect = QRectF(0, 0, self.WIDTH, h)

        cat_name = self.node.category.value if hasattr(self.node.category, "value") else str(self.node.category)
        theme = CATEGORY_COLORS.get(cat_name, {
            "header": "#37474f",
            "bg": "#1c2226",
            "border": "#546e7a",
        })

        # 1. Background Card Body
        card_path = QPainterPath()
        card_path.addRoundedRect(rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        painter.setBrush(QBrush(QColor(theme["bg"])))
        if self.isSelected():
            painter.setPen(QPen(QColor("#29b6f6"), 2.2))
        else:
            painter.setPen(QPen(QColor(theme["border"]), 1.2))
        painter.drawPath(card_path)

        # 2. Header Bar
        header_path = QPainterPath()
        header_rect = QRectF(0, 0, self.WIDTH, self.HEADER_HEIGHT)
        header_path.setFillRule(Qt.FillRule.WindingFill)
        header_path.addRoundedRect(header_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        # Rectify bottom corners
        header_path.addRect(QRectF(0, self.HEADER_HEIGHT - self.CORNER_RADIUS, self.WIDTH, self.CORNER_RADIUS))

        painter.setBrush(QBrush(QColor(theme["header"])))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(header_path)

        # 3. Header Text (Node Name and Type)
        painter.setPen(QColor("#ffffff"))
        title_font = QFont("Segoe UI", 9)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(10, 0, self.WIDTH - 40, self.HEADER_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.node.name,
        )

        # 4. Status Indicator Badge in Header
        status_rect = QRectF(self.WIDTH - 24, 8, 16, 16)
        if self.status == "success":
            painter.setBrush(QBrush(QColor("#4caf50")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(status_rect)
            painter.setPen(QPen(QColor("#ffffff"), 1.8))
            # Draw tiny checkmark
            painter.drawLine(QPointF(status_rect.x() + 4, status_rect.y() + 8), QPointF(status_rect.x() + 7, status_rect.y() + 11))
            painter.drawLine(QPointF(status_rect.x() + 7, status_rect.y() + 11), QPointF(status_rect.x() + 12, status_rect.y() + 4))
        elif self.status == "error":
            painter.setBrush(QBrush(QColor("#e53935")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(status_rect)
            painter.setPen(QPen(QColor("#ffffff"), 1.8))
            # Draw tiny cross
            painter.drawLine(QPointF(status_rect.x() + 4, status_rect.y() + 4), QPointF(status_rect.x() + 12, status_rect.y() + 12))
            painter.drawLine(QPointF(status_rect.x() + 12, status_rect.y() + 4), QPointF(status_rect.x() + 4, status_rect.y() + 12))
        elif self.status == "running":
            painter.setBrush(QBrush(QColor("#00bcd4")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(status_rect)

        # 5. Footer Feature Count Badge
        if self.node.features_processed > 0 or self.node.execution_duration_sec > 0:
            badge_text = f"{self.node.features_processed} feats • {self.node.execution_duration_sec:.2f}s"
            footer_font = QFont("Segoe UI", 8)
            painter.setFont(footer_font)
            painter.setPen(QColor("#9fa8da"))
            painter.drawText(
                QRectF(10, h - 16, self.WIDTH - 20, 14),
                Qt.AlignmentFlag.AlignCenter,
                badge_text,
            )

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Sync node data coordinate
            self.node.x = self.pos().x()
            self.node.y = self.pos().y()
            # Notify scene to update all connected wires
            if self.scene() and hasattr(self.scene(), "update_node_wires"):
                self.scene().update_node_wires(self)
        return super().itemChange(change, value)

    def set_status(self, status: str, message: str = ""):
        self.status = status
        self.status_message = message
        self._update_tooltip()
        self.update()
