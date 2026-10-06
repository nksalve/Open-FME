"""
open-FME Workbench Main Window.
Integrates the visual canvas, transformer library, parameter inspector,
feature data inspector (table + map), and execution engine.
"""

from __future__ import annotations
import os
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QDockWidget, QToolBar, QToolButton, QProgressBar,
    QLabel, QFileDialog, QMessageBox, QTextEdit, QVBoxLayout, QWidget,
    QApplication, QMenu, QTabWidget
)
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QColor

from pyfme.engine.graph import WorkflowGraph
from pyfme.engine.registry import NodeRegistry
from pyfme.engine.nodes.base import BaseNode
from pyfme.engine.dataset import FeatureDataset
from pyfme.ui.styles import DARK_THEME_QSS
from pyfme.ui.canvas.scene import CanvasScene
from pyfme.ui.canvas.view import CanvasView
from pyfme.ui.palette.transformer_palette import TransformerPaletteWidget
from pyfme.ui.properties.node_properties import NodePropertiesWidget
from pyfme.ui.inspector.inspector_dock import InspectorDockWidget
from pyfme.ui.inspector.translation_log import TranslationLogWidget
from pyfme.ui.navigator.navigator_dock import NavigatorWidget
from pyfme.ui.start_page import StartPageWidget
from pyfme.ui.quick_search import QuickAddDialog
from pyfme.ui.execution_worker import WorkflowExecutionThread


class MainWindow(QMainWindow):
    """
    Primary FME-like Desktop Workbench application window.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("open-FME Workbench - Python Spatial & ETL Automation")
        self.resize(1380, 880)

        # Apply dark theme
        self.setStyleSheet(DARK_THEME_QSS)

        # State
        self.current_file_path: Optional[str] = None
        self.graph = WorkflowGraph("New Workspace")
        self.exec_thread: Optional[WorkflowExecutionThread] = None

        # Build UI Components
        self._init_canvas()
        self._init_docks()
        self._init_toolbars()
        self._init_menus()
        self._init_statusbar()

        # Connect signals
        self._connect_signals()

        # Load a default sample workflow if empty so user immediately sees a working pipeline
        self.load_sample_workflow()

    def _init_canvas(self):
        self.central_tabs = QTabWidget()
        self.central_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #16161b;
            }
            QTabBar::tab {
                background-color: #21212b;
                color: #a0a0b0;
                padding: 6px 18px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: 600;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #16161b;
                color: #ffffff;
                border-top: 2px solid #29b6f6;
            }
            QTabBar::tab:hover:!selected {
                background-color: #2b2b38;
                color: #e0e0e0;
            }
        """)

        # Canvas Scene & View
        self.scene = CanvasScene(self.graph, self)
        self.view = CanvasView(self.scene, self)

        # Start Page Tab
        self.start_page = StartPageWidget(self)
        self.start_page.new_workspace_clicked.connect(self.new_workspace)
        self.start_page.open_workspace_clicked.connect(self.open_workspace)
        self.start_page.open_sample_clicked.connect(self.load_community_mapping_sample)
        self.start_page.open_file_requested.connect(self.load_workspace_file)

        self.central_tabs.addTab(self.start_page, "Start")
        self.central_tabs.addTab(self.view, "Main")
        self.central_tabs.setCurrentIndex(1)  # Default to Main canvas
        self.setCentralWidget(self.central_tabs)

    def _init_docks(self):
        # 1. Left Dock Top: Navigator
        self.navigator_dock = QDockWidget("Navigator", self)
        self.navigator_dock.setObjectName("NavigatorDock")
        self.navigator_widget = NavigatorWidget(self, self)
        self.navigator_dock.setWidget(self.navigator_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.navigator_dock)

        # 2. Left Dock Bottom: Transformer Gallery
        self.palette_dock = QDockWidget("Transformer Gallery", self)
        self.palette_dock.setObjectName("TransformerPaletteDock")
        self.palette_widget = TransformerPaletteWidget(self)
        self.palette_dock.setWidget(self.palette_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.palette_dock)

        # Split left dock area so Navigator is top, Transformer Gallery is bottom
        self.splitDockWidget(self.navigator_dock, self.palette_dock, Qt.Orientation.Vertical)

        # 3. Right Dock: Parameter Editor
        self.props_dock = QDockWidget("Parameter Editor", self)
        self.props_dock.setObjectName("ParametersDock")
        self.props_widget = NodePropertiesWidget(self)
        self.props_dock.setWidget(self.props_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.props_dock)

        # 4. Bottom Dock 1: Feature Data Inspector (Table + Spatial Map)
        self.inspector_dock = QDockWidget("Visual Data Inspector", self)
        self.inspector_dock.setObjectName("InspectorDock")
        self.inspector_widget = InspectorDockWidget(self)
        self.inspector_dock.setWidget(self.inspector_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.inspector_dock)

        # 5. Bottom Dock 2: Translation Log
        self.log_dock = QDockWidget("Translation Log", self)
        self.log_dock.setObjectName("LogDock")
        self.log_widget = TranslationLogWidget(self)
        self.log_dock.setWidget(self.log_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        # Tabify bottom docks so they share the bottom region cleanly
        self.tabifyDockWidget(self.inspector_dock, self.log_dock)
        self.inspector_dock.raise_()

    def _init_toolbars(self):
        self.toolbar = QToolBar("Main Toolbar", self)
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        # File actions
        self.act_new = QAction("New", self)
        self.act_new.setShortcut(QKeySequence.StandardKey.New)
        self.act_new.triggered.connect(self.new_workspace)
        self.toolbar.addAction(self.act_new)

        self.act_gen_ws = QAction("⚡ Generate", self)
        self.act_gen_ws.setToolTip("Generate Workspace (Ctrl+G): Quick format-to-format translation generator")
        self.act_gen_ws.setShortcut(QKeySequence("Ctrl+G"))
        self.act_gen_ws.triggered.connect(self.generate_workspace)
        self.toolbar.addAction(self.act_gen_ws)

        self.act_open = QAction("Open", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self.open_workspace)
        self.toolbar.addAction(self.act_open)

        self.act_save = QAction("Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self.save_workspace)
        self.toolbar.addAction(self.act_save)

        self.toolbar.addSeparator()

        # Reader / Writer Quick Tools
        self.act_add_reader = QAction("📥 Add Reader...", self)
        self.act_add_reader.setToolTip("Add Source Dataset Reader (Ctrl+Alt+R)")
        self.act_add_reader.setShortcut(QKeySequence("Ctrl+Alt+R"))
        self.act_add_reader.triggered.connect(self.add_reader_dialog)
        self.toolbar.addAction(self.act_add_reader)

        self.act_add_writer = QAction("📤 Add Writer...", self)
        self.act_add_writer.setToolTip("Add Destination Dataset Writer (Ctrl+Alt+W)")
        self.act_add_writer.setShortcut(QKeySequence("Ctrl+Alt+W"))
        self.act_add_writer.triggered.connect(self.add_writer_dialog)
        self.toolbar.addAction(self.act_add_writer)

        self.toolbar.addSeparator()

        # Undo / Redo actions from QUndoStack
        self.act_undo = self.scene.undo_stack.createUndoAction(self, "&Undo")
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.toolbar.addAction(self.act_undo)

        self.act_redo = self.scene.undo_stack.createRedoAction(self, "&Redo")
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.toolbar.addAction(self.act_redo)

        self.toolbar.addSeparator()

        # Run button
        self.run_btn = QToolButton()
        self.run_btn.setObjectName("runBtn")
        self.run_btn.setText("▶ Run Entire Workspace (F5)")
        self.run_btn.setShortcut(Qt.Key.Key_F5)
        self.run_btn.clicked.connect(self.run_workflow)
        self.toolbar.addWidget(self.run_btn)

        # Stop button
        self.stop_btn = QToolButton()
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setText("⏹ Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_workflow)
        self.toolbar.addWidget(self.stop_btn)

        # Feature Caching Toggle (FME 2018 flagship capability)
        self.act_cache_toggle = QAction("⚡ Feature Caching", self)
        self.act_cache_toggle.setCheckable(True)
        self.act_cache_toggle.setChecked(True)
        self.act_cache_toggle.setToolTip("Enable/Disable FME Feature Caching on canvas nodes")
        self.toolbar.addAction(self.act_cache_toggle)

        self.toolbar.addSeparator()

        # FME Container / Note tools
        self.act_add_bm = QAction("🔖 Bookmark", self)
        self.act_add_bm.setToolTip("Insert Bookmark Container (Ctrl+B)")
        self.act_add_bm.setShortcut(QKeySequence("Ctrl+B"))
        self.act_add_bm.triggered.connect(self.add_bookmark_action)
        self.toolbar.addAction(self.act_add_bm)

        self.act_add_note = QAction("📝 Note", self)
        self.act_add_note.setToolTip("Insert Yellow Documentation Note")
        self.act_add_note.triggered.connect(self.add_annotation_action)
        self.toolbar.addAction(self.act_add_note)

        self.toolbar.addSeparator()

        # Zoom controls
        zoom_in_act = QAction("Zoom +", self)
        zoom_in_act.triggered.connect(lambda: self.view.scale(1.2, 1.2))
        self.toolbar.addAction(zoom_in_act)

        zoom_out_act = QAction("Zoom -", self)
        zoom_out_act.triggered.connect(lambda: self.view.scale(0.8, 0.8))
        self.toolbar.addAction(zoom_out_act)

        zoom_fit_act = QAction("Zoom Fit", self)
        zoom_fit_act.triggered.connect(self.zoom_fit)
        self.toolbar.addAction(zoom_fit_act)

        self.toolbar.addSeparator()

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(160)
        self.toolbar.addWidget(self.progress_bar)

    def _init_menus(self):
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_gen_ws)
        file_menu.addAction(self.act_open)
        file_menu.addAction(self.act_save)

        save_as_act = QAction("Save As...", self)
        save_as_act.triggered.connect(self.save_as_workspace)
        file_menu.addAction(save_as_act)

        file_menu.addSeparator()

        sample_act = QAction("Load Sample Spatial Pipeline", self)
        sample_act.triggered.connect(self.load_sample_workflow)
        file_menu.addAction(sample_act)

        file_menu.addSeparator()
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()

        self.act_cut = QAction("Cu&t", self)
        self.act_cut.setShortcut(QKeySequence.StandardKey.Cut)
        self.act_cut.triggered.connect(self.scene.cut_selected)
        edit_menu.addAction(self.act_cut)

        self.act_copy = QAction("&Copy", self)
        self.act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self.act_copy.triggered.connect(self.scene.copy_selected)
        edit_menu.addAction(self.act_copy)

        self.act_paste = QAction("&Paste", self)
        self.act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self.act_paste.triggered.connect(lambda: self.scene.paste())
        edit_menu.addAction(self.act_paste)

        self.act_duplicate = QAction("&Duplicate", self)
        self.act_duplicate.setShortcut(QKeySequence("Ctrl+D"))
        self.act_duplicate.triggered.connect(self.scene.duplicate_selected)
        edit_menu.addAction(self.act_duplicate)

        self.act_delete = QAction("&Delete Selected", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.triggered.connect(self.scene.remove_selected)
        edit_menu.addAction(self.act_delete)

        edit_menu.addSeparator()

        self.act_select_all = QAction("Select &All", self)
        self.act_select_all.setShortcut(QKeySequence.StandardKey.SelectAll)
        self.act_select_all.triggered.connect(self.scene.select_all)
        edit_menu.addAction(self.act_select_all)

        self.act_deselect_all = QAction("Deselect All", self)
        self.act_deselect_all.setShortcut(QKeySequence("Escape"))
        self.act_deselect_all.triggered.connect(self.scene.deselect_all)
        edit_menu.addAction(self.act_deselect_all)

        # Readers Menu
        readers_menu = menubar.addMenu("&Readers")
        readers_menu.addAction(self.act_add_reader)

        # Writers Menu
        writers_menu = menubar.addMenu("&Writers")
        writers_menu.addAction(self.act_add_writer)

        # Run Menu
        run_menu = menubar.addMenu("&Run")
        run_act = QAction("Run Entire Workspace", self)
        run_act.setShortcut(Qt.Key.Key_F5)
        run_act.triggered.connect(self.run_workflow)
        run_menu.addAction(run_act)

        run_to_act = QAction("Run to Selected Node", self)
        run_to_act.triggered.connect(self.run_selected_node_to)
        run_menu.addAction(run_to_act)

        run_from_act = QAction("Run From Selected Node", self)
        run_from_act.triggered.connect(self.run_selected_node_from)
        run_menu.addAction(run_from_act)

        run_menu.addSeparator()
        run_menu.addAction(self.act_cache_toggle)

        stop_act = QAction("Stop Translation", self)
        stop_act.triggered.connect(self.stop_workflow)
        run_menu.addAction(stop_act)

        # View Menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.navigator_dock.toggleViewAction())
        view_menu.addAction(self.palette_dock.toggleViewAction())
        view_menu.addAction(self.props_dock.toggleViewAction())
        view_menu.addAction(self.inspector_dock.toggleViewAction())
        view_menu.addAction(self.log_dock.toggleViewAction())

        # Help Menu
        help_menu = menubar.addMenu("&Help")
        about_act = QAction("About open-FME", self)
        about_act.triggered.connect(self.show_about)
        help_menu.addAction(about_act)

    def _init_statusbar(self):
        self.status = self.statusBar()
        self.status_msg = QLabel("Ready")
        self.stats_msg = QLabel("0 Nodes | 0 Connections")
        self.stats_msg.setStyleSheet("color: #8c8c9e; margin-right: 12px;")
        self.status.addWidget(self.status_msg, 1)
        self.status.addPermanentWidget(self.stats_msg)

    def _connect_signals(self):
        # Canvas events
        self.scene.node_selected.connect(self.props_widget.set_node)
        self.scene.node_inspected.connect(self.inspector_widget.inspect_dataset)
        self.scene.run_to_this_requested.connect(self.run_to_this)
        self.scene.run_from_this_requested.connect(self.run_from_this)
        self.scene.graph_modified.connect(self._update_stats)
        self.scene.graph_modified.connect(self.navigator_widget.refresh)

        # Property editor changes
        self.props_widget.parameters_changed.connect(self._on_node_params_changed)

        # Transformer Gallery events
        self.palette_widget.node_requested.connect(self._add_node_center)

        # Quick Add dialog (spacebar/tab)
        self.view.quick_add_requested.connect(self._show_quick_add)

        # Start page generator card
        self.start_page.generate_workspace_clicked.connect(self.generate_workspace)

    def _update_stats(self):
        n_count = len(self.graph.nodes)
        c_count = len(self.graph.connections)
        self.stats_msg.setText(f"{n_count} Nodes | {c_count} Connections")

    def _on_node_params_changed(self, node: BaseNode):
        item = self.scene.node_items.get(node.id)
        if item:
            item.update()

    def _add_node_center(self, node_type: str):
        node = NodeRegistry.create(node_type)
        if node:
            center_scene = self.view.mapToScene(self.view.viewport().rect().center())
            self.scene.add_node_at_position(node, center_scene)

    def _show_quick_add(self, scene_pos: QPointF):
        dialog = QuickAddDialog(self)
        dialog.node_chosen.connect(lambda n_type: self._add_node_at(n_type, scene_pos))
        global_pos = self.view.mapToGlobal(self.view.mapFromScene(scene_pos))
        dialog.show_at(global_pos)

    def _add_node_at(self, node_type: str, pos: QPointF):
        node = NodeRegistry.create(node_type)
        if node:
            self.scene.add_node_at_position(node, pos)

    def zoom_fit(self):
        items_rect = self.scene.itemsBoundingRect()
        if not items_rect.isEmpty():
            self.view.fitInView(items_rect.adjusted(-50, -50, 50, 50), Qt.AspectRatioMode.KeepAspectRatio)

    # -------------------------------------------------------------
    # Execution (Full & FME 2018 Partial Feature Caching Runs)
    # -------------------------------------------------------------
    def run_workflow(self, target_node_id: Optional[str] = None, mode: str = "all"):
        if self.exec_thread and self.exec_thread.isRunning():
            return

        self._last_completed_node = None
        try:
            self.central_tabs.setCurrentIndex(1)
            self.log_dock.raise_()
            self.progress_bar.setVisible(True)
            self.run_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)

            if mode == "to_this" and target_node_id:
                node_obj = self.graph.nodes.get(target_node_id)
                n_name = node_obj.name if node_obj else target_node_id
                self.log_widget.append_log(f"Starting partial run (Run to This) up to node: '{n_name}'", "INFO")
                self.status_msg.setText(f"Running up to {n_name}...")
                ancestors = self.graph.get_ancestors(target_node_id) | {target_node_id}
                for nid in ancestors:
                    item = self.scene.node_items.get(nid)
                    if item:
                        item.set_status("idle")
            elif mode == "from_this" and target_node_id:
                node_obj = self.graph.nodes.get(target_node_id)
                n_name = node_obj.name if node_obj else target_node_id
                self.log_widget.append_log(f"Starting partial run (Run From This) starting from node: '{n_name}'", "INFO")
                self.status_msg.setText(f"Running from {n_name}...")
                descendants = self.graph.get_descendants(target_node_id) | {target_node_id}
                for nid in descendants:
                    item = self.scene.node_items.get(nid)
                    if item:
                        item.set_status("idle")
            else:
                self.log_widget.clear_log()
                self.log_widget.append_log(f"Starting translation for workspace: '{self.graph.name}'", "INFO")
                self.status_msg.setText("Executing workflow...")
                for item in self.scene.node_items.values():
                    item.set_status("idle")

            self.exec_thread = WorkflowExecutionThread(self.graph, target_node_id=target_node_id, mode=mode, parent=self)
            self.exec_thread.log_emitted.connect(self._append_log)
            self.exec_thread.node_started.connect(self._on_node_started)
            self.exec_thread.node_completed.connect(self._on_node_completed)
            self.exec_thread.connection_updated.connect(self._on_connection_updated)
            self.exec_thread.workflow_finished.connect(self._on_workflow_finished)
            self.exec_thread.start()
        except Exception as e:
            self.progress_bar.setVisible(False)
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.log_widget.append_log(f"Failed to initiate execution: {e}", "ERROR")
            self.status_msg.setText(f"Execution startup failed: {e}")

    def run_to_this(self, node_id: str):
        """Executes upstream nodes up to and including node_id, caching outputs (FME 2018 Run to This)."""
        self.run_workflow(target_node_id=node_id, mode="to_this")

    def run_from_this(self, node_id: str):
        """Executes downstream nodes starting from node_id using upstream cached data (FME 2018 Run From This)."""
        self.run_workflow(target_node_id=node_id, mode="from_this")

    def run_selected_node_to(self):
        selected = [i for i in self.scene.selectedItems() if hasattr(i, "node")]
        if selected:
            self.run_to_this(selected[0].node.id)
        else:
            QMessageBox.information(self, "Run to This", "Please select a node on the canvas first.")

    def run_selected_node_from(self):
        selected = [i for i in self.scene.selectedItems() if hasattr(i, "node")]
        if selected:
            self.run_from_this(selected[0].node.id)
        else:
            QMessageBox.information(self, "Run From This", "Please select a node on the canvas first.")

    def stop_workflow(self):
        if self.exec_thread:
            self.exec_thread.request_stop()
            self.status_msg.setText("Stopping...")

    def _append_log(self, message: str, level: str = "INFO"):
        self.log_widget.append_log(message, level)

    def _on_node_started(self, node_id: str):
        try:
            item = self.scene.node_items.get(node_id)
            if item:
                item.set_status("running")
        except Exception:
            pass

    def _on_node_completed(self, node_id: str, success: bool, count: int, duration: float, error: str):
        try:
            item = self.scene.node_items.get(node_id)
            if item:
                status = "success" if success else "error"
                item.set_status(status, error)
                if success:
                    self._last_completed_node = item.node
        except Exception as e:
            self.log_widget.append_log(f"Node completion notification warning: {e}", "WARN")

    def _on_connection_updated(self, from_id: str, from_port: str, to_id: str, to_port: str, count: int):
        try:
            for wire in self.scene.wire_items:
                if wire.from_port and wire.to_port:
                    if (
                        wire.from_port.node_item.node.id == from_id
                        and wire.from_port.port_name == from_port
                        and wire.to_port.node_item.node.id == to_id
                        and wire.to_port.port_name == to_port
                    ):
                        wire.feature_count = count
                        wire.update()
        except Exception:
            pass

    def _on_workflow_finished(self, success: bool, duration: float, summary: str):
        try:
            self.progress_bar.setVisible(False)
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_msg.setText(summary)
            self.log_widget.append_log(f"STATS | {summary}", "STATS", elapsed=duration)
            self.log_widget.append_log(f"STATS | Translation was {'SUCCESSFUL' if success else 'FAILED'}", "STATS", elapsed=duration)
            self.navigator_widget.refresh()

            # Auto-inspect the final completed node's outputs only if execution succeeded
            if success and getattr(self, "_last_completed_node", None):
                last_node = self._last_completed_node
                last_outputs = getattr(last_node, "last_outputs", None)
                if last_outputs and isinstance(last_outputs, dict):
                    out_ports = last_node.get_output_ports()
                    if out_ports:
                        p_name = out_ports[0].name
                        ds = last_outputs.get(p_name)
                        if ds is not None and hasattr(ds, "count") and ds.count() > 0:
                            try:
                                self.inspector_widget.inspect_dataset(last_node, p_name, ds)
                            except Exception as insp_err:
                                self.log_widget.append_log(f"Inspector preview notice: {insp_err}", "WARN")

            # Raise the visual data inspector on success, or log on failure
            if success:
                self.inspector_dock.raise_()
            else:
                self.log_dock.raise_()
        except Exception as e:
            self.log_widget.append_log(f"Post-execution error: {e}", "ERROR")
        finally:
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.progress_bar.setVisible(False)


    # -------------------------------------------------------------
    # Workspace File Operations & FME 2018 Translation Generator
    # -------------------------------------------------------------
    def generate_workspace(self):
        """
        FME 2018 'Generate Workspace' wizard (Ctrl+G).
        Prompts for Reader format/file and Writer format/file, connects them,
        arranges them on the canvas, and initializes the translation pipeline.
        """
        from pyfme.ui.generate_workspace_dialog import GenerateWorkspaceDialog
        dlg = GenerateWorkspaceDialog(self)
        if dlg.exec():
            cfg = dlg.get_config()
            r_type = cfg.get("reader_type", "CSVReader")
            r_path = cfg.get("reader_path", "")
            w_type = cfg.get("writer_type", "GeoJSONWriter")
            w_path = cfg.get("writer_path", "")
            ws_name = cfg.get("workspace_name", "Generated Translation")

            self.new_workspace()
            self.graph.name = ws_name
            self.setWindowTitle(f"open-FME Workbench - {ws_name}")

            reader = NodeRegistry.create(r_type)
            if reader:
                reader.set_param("file_path", r_path)
                reader.x, reader.y = 120, 200
                self.graph.add_node(reader)

            writer = NodeRegistry.create(w_type)
            if writer:
                writer.set_param("file_path", w_path)
                writer.x, writer.y = 520, 200
                self.graph.add_node(writer)

            if reader and writer:
                r_ports = reader.get_output_ports()
                w_ports = writer.get_input_ports()
                if r_ports and w_ports:
                    self.graph.connect(reader.id, r_ports[0].name, writer.id, w_ports[0].name)

            self.scene.set_graph(self.graph)
            self._update_stats()
            self.navigator_widget.refresh()
            self.central_tabs.setCurrentIndex(1)
            self.zoom_fit()
            self.log_dock.raise_()
            self.log_widget.append_log(f"Generated workspace '{ws_name}' ({r_type} -> {w_type})", "INFO")

    def add_reader_dialog(self):
        """Adds a new reader source node to the canvas."""
        from pyfme.ui.generate_workspace_dialog import AddReaderDialog
        dlg = AddReaderDialog(self)
        if dlg.exec():
            r_type, r_path = dlg.get_data()
            reader = NodeRegistry.create(r_type)
            if reader:
                reader.set_param("file_path", r_path)
                center_scene = self.view.mapToScene(self.view.viewport().rect().center())
                self.scene.add_node_at_position(reader, center_scene)
                self.central_tabs.setCurrentIndex(1)
                self.log_widget.append_log(f"Added Reader '{r_type}' ({r_path})", "INFO")

    def add_writer_dialog(self):
        """Adds a new writer destination node to the canvas."""
        from pyfme.ui.generate_workspace_dialog import AddWriterDialog
        dlg = AddWriterDialog(self)
        if dlg.exec():
            w_type, w_path = dlg.get_data()
            writer = NodeRegistry.create(w_type)
            if writer:
                writer.set_param("file_path", w_path)
                center_scene = self.view.mapToScene(self.view.viewport().rect().center())
                self.scene.add_node_at_position(writer, center_scene)
                self.central_tabs.setCurrentIndex(1)
                self.log_widget.append_log(f"Added Writer '{w_type}' ({w_path})", "INFO")

    def new_workspace(self):
        self.graph = WorkflowGraph("Untitled Workspace")
        self.scene.set_graph(self.graph)
        self.props_widget.set_node(None)
        self.inspector_widget.inspect_dataset(BaseNode(), "None", None)
        self.current_file_path = None
        self.setWindowTitle("open-FME Workbench - Untitled Workspace")
        self._update_stats()
        self.navigator_widget.refresh()
        self.central_tabs.setCurrentIndex(1)

    def open_workspace(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open open-FME Workspace", "", "open-FME Workspace (*.fpy *.json);;All Files (*.*)")
        if path:
            self.load_workspace_file(path)

    def save_workspace(self):
        try:
            self.scene.sync_to_graph()
            if not self.current_file_path:
                self.save_as_workspace()
            else:
                self.graph.save_to_file(self.current_file_path)
                self.status_msg.setText(f"Saved: {self.current_file_path}")
                self.log_widget.append_log(f"Workspace saved to: {self.current_file_path}", "INFO")
        except Exception as e:
            if os.environ.get("OPENFME_TEST_MODE") != "1":
                QMessageBox.critical(self, "Save Error", f"Failed to save workspace:\n{str(e)}")
            self.log_widget.append_log(f"Failed to save workspace: {e}", "ERROR")

    def save_as_workspace(self):
        try:
            self.scene.sync_to_graph()
            path, _ = QFileDialog.getSaveFileName(self, "Save Workspace", "workspace.fpy", "open-FME Workspace (*.fpy *.json);;All Files (*.*)")
            if path:
                self.current_file_path = path
                self.graph.save_to_file(path)
                self.setWindowTitle(f"open-FME Workbench - {os.path.basename(path)}")
                self.status_msg.setText(f"Saved: {path}")
                self.log_widget.append_log(f"Workspace saved to: {path}", "INFO")
        except Exception as e:
            if os.environ.get("OPENFME_TEST_MODE") != "1":
                QMessageBox.critical(self, "Save Error", f"Failed to save workspace:\n{str(e)}")
            self.log_widget.append_log(f"Failed to save workspace: {e}", "ERROR")

    def load_workspace_file(self, path: str):
        try:
            loaded_graph = WorkflowGraph.load_from_file(path)
            self.graph = loaded_graph
            self.scene.set_graph(self.graph)
            self.current_file_path = path
            self.setWindowTitle(f"open-FME Workbench - {os.path.basename(path)}")
            self._update_stats()
            self.navigator_widget.refresh()
            self.central_tabs.setCurrentIndex(1)
            self.zoom_fit()
            self.log_widget.append_log(f"Opened workspace: {os.path.basename(path)}", "INFO")
        except Exception as e:
            if os.environ.get("OPENFME_TEST_MODE") != "1":
                QMessageBox.critical(self, "Open Error", f"Failed to load workspace:\n{str(e)}")
            self.log_widget.append_log(f"Failed to load workspace file '{path}': {e}", "ERROR")


    def load_community_mapping_sample(self):
        sample_path = os.path.abspath("sample_data/fme_community_mapping.fpy")
        if os.path.exists(sample_path):
            self.load_workspace_file(sample_path)
        else:
            self.load_sample_workflow()

    def add_bookmark_action(self):
        self.central_tabs.setCurrentIndex(1)
        self.scene.add_bookmark()
        self.navigator_widget.refresh()

    def add_annotation_action(self):
        self.central_tabs.setCurrentIndex(1)
        self.scene.add_annotation()
        self.navigator_widget.refresh()

    def load_sample_workflow(self):
        """Constructs or loads sample spatial ETL pipeline."""
        sample_path = os.path.abspath("sample_data/fme_community_mapping.fpy")
        if os.path.exists(sample_path):
            self.load_workspace_file(sample_path)
            return
        csv_path = os.path.abspath("sample_data/customers.csv")
        out_geojson = os.path.abspath("sample_data/active_customers_buffered.geojson")

        graph = WorkflowGraph("Sample Spatial ETL Workspace")

        # 1. Reader
        reader = NodeRegistry.create("CSVReader")
        reader.set_param("file_path", csv_path)
        reader.x, reader.y = 80, 180
        graph.add_node(reader)

        # 2. Attribute Tester
        tester = NodeRegistry.create("Tester")
        tester.set_param("attribute", "status")
        tester.set_param("operator", "=")
        tester.set_param("test_value", "active")
        tester.x, tester.y = 340, 180
        graph.add_node(tester)

        # 3. Vertex Creator
        vertex = NodeRegistry.create("VertexCreator")
        vertex.set_param("x_attribute", "lon")
        vertex.set_param("y_attribute", "lat")
        vertex.set_param("crs", "EPSG:4326")
        vertex.x, vertex.y = 600, 140
        graph.add_node(vertex)

        # 4. Bufferer
        bufferer = NodeRegistry.create("Bufferer")
        bufferer.set_param("buffer_distance", 0.35)
        bufferer.x, bufferer.y = 860, 140
        graph.add_node(bufferer)

        # 5. Writer
        writer = NodeRegistry.create("GeoJSONWriter")
        writer.set_param("file_path", out_geojson)
        writer.x, writer.y = 1120, 140
        graph.add_node(writer)

        # Connections
        graph.connect(reader.id, "Output", tester.id, "Input")
        graph.connect(tester.id, "Passed", vertex.id, "Input")
        graph.connect(vertex.id, "Output", bufferer.id, "Input")
        graph.connect(bufferer.id, "Output", writer.id, "Input")

        self.graph = graph
        self.scene.set_graph(self.graph)
        self._update_stats()
        self.zoom_fit()

    def show_about(self):
        QMessageBox.about(
            self,
            "About open-FME Workbench",
            "<h3>open-FME Workbench</h3>"
            "<p>A modern open-source visual ETL & Spatial Automation platform for Python.</p>"
            "<p>Built on <b>Polars</b> for high-speed attribute processing, and <b>GeoPandas / Shapely</b> for GIS operations.</p>"
            "<p><b>Keyboard Shortcuts & Tools:</b><br>"
            "• <b>Ctrl+G:</b> Generate Workspace (Reader to Writer Translation)<br>"
            "• <b>Ctrl+Alt+R / Ctrl+Alt+W:</b> Add Reader / Add Writer<br>"
            "• <b>F5:</b> Run entire pipeline<br>"
            "• <b>Right-Click Node:</b> Run to This / Run From This (Feature Caching) & Inspect<br>"
            "• <b>Ctrl+B:</b> Insert Bookmark Container<br>"
            "• <b>Ctrl+Z / Ctrl+Y:</b> Undo / Redo<br>"
            "• <b>Ctrl+C / Ctrl+V / Ctrl+X:</b> Copy / Paste / Cut<br>"
            "• <b>Ctrl+D:</b> Duplicate selected nodes<br>"
            "• <b>Ctrl+A / Esc:</b> Select All / Deselect All<br>"
            "• <b>Delete / Backspace:</b> Remove selected nodes or wires<br>"
            "• <b>Spacebar / Tab:</b> Quick-add transformer search<br>"
            "• <b>Middle-Drag or Alt+Drag:</b> Pan canvas<br>"
            "• <b>Scroll Wheel:</b> Zoom in / out</p>"
        )
