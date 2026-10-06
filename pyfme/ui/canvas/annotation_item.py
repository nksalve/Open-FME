"""
Annotation / Sticky Note Item for adding documentation on open-FME canvas.
Inspired by FME Workbench Annotations.
"""

from __future__ import annotations
import uuid
from typing import Optional
from PyQt6.QtWidgets import (
    QGraphicsItem, QStyleOptionGraphicsItem, QWidget,
    QInputDialog, QMenu, QColorDialog
)
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QTextOption
)


class AnnotationItem(QGraphicsItem):
    """
    FME Workbench Yellow Sticky Note / Annotation.
    Enables placing documentation, comments, and instructions directly onto the canvas.
    """

    CORNER_RADIUS = 6.0
    RESIZE_HANDLE_SIZE = 10.0

    def __init__(
        self,
        text: str = "Add workflow documentation here...",
        rect: Optional[QRectF] = None,
        bg_color: str = "#fff9c4",
        border_color: str = "#fbc02d",
        annotation_id: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.id = annotation_id or str(uuid.uuid4())
        self.text = text
        self.bg_color = bg_color
        self.border_color = border_color
        self._rect = rect or QRectF(0, 0, 180, 80)

        self._resizing = False
        self._resize_start_pos = QPointF()
        self._resize_start_rect = QRectF()

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        # Position slightly below nodes, above bookmarks
        self.setZValue(-5.0)

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

    def mousePressEvent(self, event):
        pos = event.pos()
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
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.scenePos() - self._resize_start_pos
            new_w = max(100.0, self._resize_start_rect.width() + delta.x())
            new_h = max(50.0, self._resize_start_rect.height() + delta.y())
            self.set_rect(QRectF(self._resize_start_rect.x(), self._resize_start_rect.y(), new_w, new_h))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.scene() and hasattr(self.scene(), "graph_modified"):
            self.scene().graph_modified.emit()

    def mouseDoubleClickEvent(self, event):
        new_text, ok = QInputDialog.getMultiLineText(
            None, "Edit Annotation Note", "Documentation / Comment:", text=self.text
        )
        if ok and new_text.strip():
            self.text = new_text.strip()
            self.update()
            if self.scene() and hasattr(self.scene(), "graph_modified"):
                self.scene().graph_modified.emit()
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu()
        edit_act = menu.addAction("✏️ Edit Text...")
        color_act = menu.addAction("🎨 Change Note Color...")
        menu.addSeparator()
        delete_act = menu.addAction("🗑️ Delete Annotation")

        selected = menu.exec(event.screenPos())
        if selected == edit_act:
            new_text, ok = QInputDialog.getMultiLineText(
                None, "Edit Annotation Note", "Documentation / Comment:", text=self.text
            )
            if ok and new_text.strip():
                self.text = new_text.strip()
                self.update()
                if self.scene() and hasattr(self.scene(), "graph_modified"):
                    self.scene().graph_modified.emit()
        elif selected == color_act:
            chosen = QColorDialog.getColor(QColor(self.bg_color), None, "Select Note Background")
            if chosen.isValid():
                self.bg_color = chosen.name()
                self.update()
                if self.scene() and hasattr(self.scene(), "graph_modified"):
                    self.scene().graph_modified.emit()
        elif selected == delete_act:
            if self.scene():
                self.scene().removeItem(self)
                if hasattr(self.scene(), "annotations"):
                    self.scene().annotations = [a for a in self.scene().annotations if a != self]
                if hasattr(self.scene(), "graph_modified"):
                    self.scene().graph_modified.emit()
        event.accept()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Subtle drop shadow
        shadow_rect = self._rect.translated(2.5, 2.5)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        painter.fillPath(shadow_path, QBrush(QColor(0, 0, 0, 50)))

        # 2. Note body
        note_path = QPainterPath()
        note_path.addRoundedRect(self._rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        painter.fillPath(note_path, QBrush(QColor(self.bg_color)))

        # Border
        pen = QPen(QColor(self.border_color), 1.8 if not self.isSelected() else 2.5)
        if self.isSelected():
            pen.setColor(QColor("#0288d1"))
        painter.setPen(pen)
        painter.drawPath(note_path)

        # 3. Text content
        painter.setPen(QColor("#1e1e1e"))
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        text_rect = self._rect.adjusted(8, 8, -8, -8)

        text_opt = QTextOption()
        text_opt.setWrapMode(QTextOption.WrapMode.WordWrap)
        text_opt.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        painter.drawText(text_rect, self.text, text_opt)

        # 4. Small resize triangle
        handle_x = self._rect.right() - 6
        handle_y = self._rect.bottom() - 6
        painter.setPen(QPen(QColor(self.border_color), 1.2))
        painter.drawLine(int(handle_x - 5), int(handle_y), int(handle_x), int(handle_y - 5))
        painter.drawLine(int(handle_x - 2), int(handle_y), int(handle_x), int(handle_y - 2))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "bg_color": self.bg_color,
            "border_color": self.border_color,
            "x": self.pos().x() + self._rect.x(),
            "y": self.pos().y() + self._rect.y(),
            "width": self._rect.width(),
            "height": self._rect.height(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> AnnotationItem:
        ann = cls(
            text=data.get("text", "Annotation Note"),
            rect=QRectF(0, 0, data.get("width", 180), data.get("height", 80)),
            bg_color=data.get("bg_color", "#fff9c4"),
            border_color=data.get("border_color", "#fbc02d"),
            annotation_id=data.get("id"),
        )
        ann.setPos(data.get("x", 0.0), data.get("y", 0.0))
        return ann
