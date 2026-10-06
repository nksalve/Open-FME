"""
Quick-Add Transformer popup dialog (FME Workbench spacebar shortcut).
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from pyfme.engine.registry import NodeRegistry


class QuickAddDialog(QDialog):
    """
    Floating search popup to quickly find and add transformers.
    """

    node_chosen = pyqtSignal(str)  # Emits node_type

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(320, 380)
        self.setStyleSheet("""
            QDialog {
                background-color: #24242e;
                border: 2px solid #2196f3;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Type transformer name (e.g. Tester)...")
        self.search_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget(self)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.list_widget)

        # Description preview box
        self.desc_label = QLabel("Hover or select a transformer to see its description.", self)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #b0bec5; font-size: 11px; padding: 6px; background-color: #1a1a24; border: 1px solid #2d2d3c; border-radius: 4px;")
        self.desc_label.setFixedHeight(64)
        layout.addWidget(self.desc_label)

        self._populate("")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.list_widget.currentItem()
            if item:
                self._select_item(item)
        elif event.key() == Qt.Key.Key_Down:
            row = self.list_widget.currentRow()
            if row < self.list_widget.count() - 1:
                self.list_widget.setCurrentRow(row + 1)
        elif event.key() == Qt.Key.Key_Up:
            row = self.list_widget.currentRow()
            if row > 0:
                self.list_widget.setCurrentRow(row - 1)
        else:
            super().keyPressEvent(event)

    def _populate(self, query: str):
        self.list_widget.clear()
        matching = NodeRegistry.search(query)
        for node_cls in matching:
            item = QListWidgetItem(f"{node_cls.node_type} - {node_cls.category.value.split()[0]}")
            item.setData(Qt.ItemDataRole.UserRole, node_cls.node_type)
            item.setToolTip(f"<div style='font-family: Segoe UI; font-size: 11px;'><b>{node_cls.node_type}</b><br><span style='color: #81d4fa;'>Category:</span> {node_cls.category.value}<br><br>{node_cls.description}</div>")
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_current_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]):
        if current:
            node_type = current.data(Qt.ItemDataRole.UserRole)
            node_cls = NodeRegistry.get(node_type)
            if node_cls:
                self.desc_label.setText(f"<b>{node_cls.node_type}</b>: {node_cls.description}")
        else:
            self.desc_label.setText("Select a transformer to see its description.")

    def _on_text_changed(self, text: str):
        self._populate(text)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        self._select_item(item)

    def _select_item(self, item: QListWidgetItem):
        node_type = item.data(Qt.ItemDataRole.UserRole)
        if node_type:
            self.node_chosen.emit(node_type)
            self.accept()

    def show_at(self, global_pos: QPoint):
        self.move(global_pos)
        self.search_edit.clear()
        self.search_edit.setFocus()
        self.exec()
