"""
Navigator Tree Dock for open-FME Workbench.
Replicates the iconic FME Workbench Navigator panel, showing:
- Workspace Name & Paths
- Readers & Feature Types
- Writers & Datasets
- Transformers list and count
- Bookmarks list and count
- Annotations list and count
- User & Workspace Parameters
Clicking or double-clicking any item navigates and centers the canvas on it.
"""

from __future__ import annotations
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLineEdit,
    QHBoxLayout, QLabel, QHeaderView, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QIcon, QFont, QColor

from pyfme.engine.graph import WorkflowGraph
from pyfme.ui.canvas.node_item import NodeItem
from pyfme.ui.canvas.bookmark_item import BookmarkItem
from pyfme.ui.canvas.annotation_item import AnnotationItem


class NavigatorWidget(QWidget):
    """
    FME Workbench Navigator Dock.
    Synchronizes in real-time with the canvas scene, providing a complete structural tree
    of the pipeline.
    """

    item_selected = pyqtSignal(object)  # Emits target graphics item or node to navigate to

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Quick Filter search box
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter Navigator items...")
        self.search_input.textChanged.connect(self._filter_tree)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #212129;
                border: 1px solid #3d3d4d;
                border-radius: 4px;
                padding: 4px 8px;
                color: #e0e0e0;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #29b6f6;
            }
        """)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(16)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1a1a22;
                border: 1px solid #2e2e3a;
                border-radius: 4px;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QTreeWidget::item {
                padding: 3px 2px;
                border-radius: 3px;
            }
            QTreeWidget::item:hover {
                background-color: #2b2b38;
            }
            QTreeWidget::item:selected {
                background-color: #1976d2;
                color: #ffffff;
            }
        """)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.tree)

    def _on_context_menu(self, pos):
        if not self.main_window:
            return
        menu = QMenu(self)
        act_save = menu.addAction("💾  Save Flow (Ctrl+S)")
        act_save_as = menu.addAction("💾  Save Flow As... (Ctrl+Shift+S)")
        act_export = menu.addAction("🖼️  Export Flow Image...")

        chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen == act_save:
            if hasattr(self.main_window, "save_flow"):
                self.main_window.save_flow()
            elif hasattr(self.main_window, "save_workspace"):
                self.main_window.save_workspace()
        elif chosen == act_save_as:
            if hasattr(self.main_window, "save_flow_as"):
                self.main_window.save_flow_as()
            elif hasattr(self.main_window, "save_as_workspace"):
                self.main_window.save_as_workspace()
        elif chosen == act_export:
            if hasattr(self.main_window, "export_flow_image"):
                self.main_window.export_flow_image()


    def refresh(self):
        """Rebuilds the Navigator tree hierarchy from the active canvas scene."""
        if not self.main_window or not hasattr(self.main_window, "scene"):
            return

        scene = self.main_window.scene
        graph = scene.graph

        self.tree.clear()

        # 1. Root Workspace node
        ws_name = graph.name or "Untitled Workspace"
        if self.main_window.current_file_path:
            import os
            ws_name = os.path.basename(self.main_window.current_file_path)
        root_ws = QTreeWidgetItem(["📁  " + ws_name])
        root_ws.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.tree.addTopLevelItem(root_ws)

        # 2. Readers group
        readers = [
            n for n in scene.node_items.values()
            if getattr(n.node.category, "name", str(n.node.category)).upper() in ("READER", "INPUT") or "READER" in n.node.node_type.upper()
        ]
        readers_item = QTreeWidgetItem([f"📥  Readers ({len(readers)})"])
        readers_item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        root_ws.addChild(readers_item)
        for r in readers:
            r_child = QTreeWidgetItem([f"📄  {r.node.name} [{r.node.node_type}]"])
            r_child.setData(0, Qt.ItemDataRole.UserRole, r)
            readers_item.addChild(r_child)

        # 3. Writers group
        writers = [
            n for n in scene.node_items.values()
            if getattr(n.node.category, "name", str(n.node.category)).upper() in ("WRITER", "OUTPUT") or "WRITER" in n.node.node_type.upper()
        ]
        writers_item = QTreeWidgetItem([f"📤  Writers ({len(writers)})"])
        writers_item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        root_ws.addChild(writers_item)
        for w in writers:
            w_child = QTreeWidgetItem([f"💾  {w.node.name} [{w.node.node_type}]"])
            w_child.setData(0, Qt.ItemDataRole.UserRole, w)
            writers_item.addChild(w_child)

        # 4. Transformers group
        transformers = [
            n for n in scene.node_items.values()
            if n not in readers and n not in writers
        ]
        trans_item = QTreeWidgetItem([f"⚙️  Transformers ({len(transformers)})"])
        trans_item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        root_ws.addChild(trans_item)
        for t in transformers:
            t_child = QTreeWidgetItem([f"🔹  {t.node.name} [{t.node.node_type}]"])
            t_child.setData(0, Qt.ItemDataRole.UserRole, t)
            trans_item.addChild(t_child)

        # 5. Bookmarks group
        bookmarks = getattr(scene, "bookmarks", [])
        bm_item = QTreeWidgetItem([f"🔖  Bookmarks ({len(bookmarks)})"])
        bm_item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        root_ws.addChild(bm_item)
        for b in bookmarks:
            b_child = QTreeWidgetItem([f"🏷️  {b.title}"])
            b_child.setData(0, Qt.ItemDataRole.UserRole, b)
            bm_item.addChild(b_child)

        # 6. Annotations group
        annotations = getattr(scene, "annotations", [])
        ann_item = QTreeWidgetItem([f"📝  Annotations ({len(annotations)})"])
        ann_item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        root_ws.addChild(ann_item)
        for a in annotations:
            preview = (a.text[:24] + "...") if len(a.text) > 24 else a.text
            a_child = QTreeWidgetItem([f"💬  {preview}"])
            a_child.setData(0, Qt.ItemDataRole.UserRole, a)
            ann_item.addChild(a_child)

        # 7. User Parameters
        user_params = QTreeWidgetItem(["🔧  User Parameters (3)"])
        user_params.addChild(QTreeWidgetItem(["Published Parameters"]))
        user_params.addChild(QTreeWidgetItem(["Private Parameters"]))
        user_params.addChild(QTreeWidgetItem(["FME Engine Parameters"]))
        root_ws.addChild(user_params)

        # 8. Workspace Parameters
        ws_params = QTreeWidgetItem(["📋  Workspace Parameters"])
        ws_params.addChild(QTreeWidgetItem([f"Name: {graph.name}"]))
        ws_params.addChild(QTreeWidgetItem(["Logging: INFO"]))
        root_ws.addChild(ws_params)

        root_ws.setExpanded(True)
        readers_item.setExpanded(True)
        writers_item.setExpanded(True)
        bm_item.setExpanded(True)
        if len(transformers) <= 12:
            trans_item.setExpanded(True)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        target = item.data(0, Qt.ItemDataRole.UserRole)
        if not target or not self.main_window:
            return

        scene = self.main_window.scene
        view = self.main_window.view

        # Deselect others and select target
        scene.clearSelection()
        target.setSelected(True)

        # Center view on target item
        view.centerOn(target)

        # If it's a NodeItem, select it in the parameter inspector
        if isinstance(target, NodeItem):
            self.main_window.props_widget.set_node(target.node)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        target = item.data(0, Qt.ItemDataRole.UserRole)
        if not target or not self.main_window:
            return

        view = self.main_window.view
        # Smoothly zoom to item
        if isinstance(target, BookmarkItem):
            rect = target.mapRectToScene(target.rect).adjusted(-40, -40, 40, 40)
            view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        elif isinstance(target, (NodeItem, AnnotationItem)):
            rect = target.mapRectToScene(target.boundingRect()).adjusted(-80, -80, 80, 80)
            view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _filter_tree(self, text: str):
        query = text.strip().lower()

        def filter_item(item: QTreeWidgetItem) -> bool:
            match = query in item.text(0).lower()
            child_matches = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_matches = True
            is_visible = match or child_matches or (query == "")
            item.setHidden(not is_visible)
            if query and child_matches:
                item.setExpanded(True)
            return is_visible

        root = self.tree.topLevelItem(0)
        if root:
            filter_item(root)
