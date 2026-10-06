"""
Transformer Library Palette.
Shows categorized tree of all available readers, transformers, and writers.
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem, QApplication
)
from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QDrag, QFont, QIcon
from pyfme.engine.registry import NodeRegistry
from pyfme.engine.nodes.base import NodeCategory


class TransformerTreeWidget(QTreeWidget):
    node_double_clicked = pyqtSignal(str)  # Emits node_type

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.itemDoubleClicked.connect(self._on_double_click)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item or not item.data(0, Qt.ItemDataRole.UserRole):
            return

        node_type = item.data(0, Qt.ItemDataRole.UserRole)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(node_type)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        node_type = item.data(0, Qt.ItemDataRole.UserRole)
        if node_type:
            self.node_double_clicked.emit(node_type)


class TransformerPaletteWidget(QWidget):
    """
    Searchable library pane for adding nodes into the pipeline.
    """

    node_requested = pyqtSignal(str)  # Emits node_type to add to canvas

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(4)

        # Search bar
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter transformers (e.g. buffer, tester)...")
        self.search_box.textChanged.connect(self._filter_nodes)
        self.layout.addWidget(self.search_box)

        # Tree
        self.tree = TransformerTreeWidget(self)
        self.tree.node_double_clicked.connect(self.node_requested.emit)
        self.layout.addWidget(self.tree)

        self._populate_tree()

    def _populate_tree(self, search_text: str = ""):
        self.tree.clear()
        query = search_text.strip().lower()

        categories = [
            NodeCategory.READER,
            NodeCategory.ATTRIBUTE,
            NodeCategory.SPATIAL,
            NodeCategory.SCRIPTING,
            NodeCategory.WRITER,
        ]

        for cat in categories:
            cat_name = cat.value
            nodes = NodeRegistry.get_by_category(cat)

            matching_nodes = [
                n for n in nodes
                if not query or query in n.node_type.lower() or query in n.description.lower()
            ]

            if not matching_nodes:
                continue

            cat_item = QTreeWidgetItem(self.tree)
            cat_item.setText(0, f"{cat_name} ({len(matching_nodes)})")
            font = QFont("Segoe UI", 9)
            font.setBold(True)
            cat_item.setFont(0, font)

            for n_cls in matching_nodes:
                node_item = QTreeWidgetItem(cat_item)
                node_item.setText(0, n_cls.node_type)
                node_item.setToolTip(0, f"<div style='font-family: Segoe UI; font-size: 11px;'><b>{n_cls.node_type}</b><br><span style='color: #81d4fa;'>Category:</span> {cat_name}<br><br>{n_cls.description}</div>")
                node_item.setData(0, Qt.ItemDataRole.UserRole, n_cls.node_type)

            cat_item.setExpanded(True if query else (cat in [NodeCategory.READER, NodeCategory.SPATIAL]))

    def _filter_nodes(self, text: str):
        self._populate_tree(text)
