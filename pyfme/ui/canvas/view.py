"""
Interactive canvas view with smooth pan, zoom, shortcuts, and drag-and-drop.
"""

from __future__ import annotations
from typing import Optional
from PyQt6.QtWidgets import QGraphicsView, QApplication
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QWheelEvent, QMouseEvent, QKeyEvent, QDragEnterEvent, QDropEvent
from pyfme.engine.registry import NodeRegistry
from pyfme.ui.canvas.scene import CanvasScene


class CanvasView(QGraphicsView):
    """
    QGraphicsView supporting pan, zoom, keyboard navigation, and transformer drop.
    """

    quick_add_requested = pyqtSignal(QPointF)  # Emits scene position for quick-add dialog

    def __init__(self, scene: CanvasScene, parent=None):
        super().__init__(scene, parent)
        self.canvas_scene = scene

        # Setup high-performance rendering & optimization
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setAcceptDrops(True)

        self._is_panning = False
        self._space_pressed = False
        self._pan_start_x = 0
        self._pan_start_y = 0

    def wheelEvent(self, event: QWheelEvent):
        """Smooth zooming anchored under cursor with exponential stepping."""
        delta = event.angleDelta().y()
        if delta == 0:
            return

        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor
        zoom_factor = zoom_in_factor if delta > 0 else zoom_out_factor

        current_scale = self.transform().m11()
        if (zoom_factor > 1.0 and current_scale < 5.0) or (zoom_factor < 1.0 and current_scale > 0.15):
            self.scale(zoom_factor, zoom_factor)

    def mousePressEvent(self, event: QMouseEvent):
        # Support Middle Button, Alt+Left, or Space+Left for smooth panning
        is_pan_click = (
            event.button() == Qt.MouseButton.MiddleButton or
            (event.button() == Qt.MouseButton.LeftButton and (event.modifiers() & Qt.KeyboardModifier.AltModifier or self._space_pressed))
        )
        if is_pan_click:
            self._is_panning = True
            self._pan_start_x = event.pos().x()
            self._pan_start_y = event.pos().y()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_panning:
            dx = event.pos().x() - self._pan_start_x
            dy = event.pos().y() - self._pan_start_y
            self._pan_start_x = event.pos().x()
            self._pan_start_y = event.pos().y()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - dx)
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - dy)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._space_pressed else Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        # Undo / Redo
        if ctrl and event.key() == Qt.Key.Key_Z and not shift:
            self.canvas_scene.undo_stack.undo()
            event.accept()
            return
        elif (ctrl and event.key() == Qt.Key.Key_Y) or (ctrl and shift and event.key() == Qt.Key.Key_Z):
            self.canvas_scene.undo_stack.redo()
            event.accept()
            return

        # Clipboard: Cut, Copy, Paste, Duplicate
        elif ctrl and event.key() == Qt.Key.Key_C:
            self.canvas_scene.copy_selected()
            event.accept()
            return
        elif ctrl and event.key() == Qt.Key.Key_X:
            self.canvas_scene.cut_selected()
            event.accept()
            return
        elif ctrl and event.key() == Qt.Key.Key_V:
            self.canvas_scene.paste()
            event.accept()
            return
        elif ctrl and event.key() == Qt.Key.Key_D:
            self.canvas_scene.duplicate_selected()
            event.accept()
            return
        elif ctrl and event.key() == Qt.Key.Key_A:
            self.canvas_scene.select_all()
            event.accept()
            return
        elif ctrl and event.key() == Qt.Key.Key_B:
            cursor_viewport = self.mapFromGlobal(self.cursor().pos())
            scene_pos = self.mapToScene(cursor_viewport)
            self.canvas_scene.add_bookmark(pos=scene_pos)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Escape:
            self.canvas_scene.deselect_all()
            event.accept()
            return

        # Save Flow (Ctrl+S) / Save Flow As (Ctrl+Shift+S)
        elif ctrl and not shift and event.key() == Qt.Key.Key_S:
            win = self.window()
            if hasattr(win, "save_flow"):
                win.save_flow()
            elif hasattr(win, "save_workspace"):
                win.save_workspace()
            event.accept()
            return
        elif ctrl and shift and event.key() == Qt.Key.Key_S:
            win = self.window()
            if hasattr(win, "save_flow_as"):
                win.save_flow_as()
            elif hasattr(win, "save_as_workspace"):
                win.save_as_workspace()
            event.accept()
            return


        # Delete
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.canvas_scene.remove_selected()
            event.accept()
            return

        # Spacebar hold for smooth hand panning
        elif event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return

        # Tab opens FME Quick Add Transformer box
        elif event.key() == Qt.Key.Key_Tab:
            cursor_viewport = self.mapFromGlobal(self.cursor().pos())
            scene_pos = self.mapToScene(cursor_viewport)
            self.quick_add_requested.emit(scene_pos)
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = False
            if not self._is_panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        try:
            import os
            scene_pos = self.mapToScene(event.position().toPoint())

            # 1. Handle dragged files from Windows File Explorer
            if event.mimeData().hasUrls():
                urls = event.mimeData().urls()
                offset_y = 0.0
                for url in urls:
                    file_path = url.toLocalFile()
                    if not file_path:
                        continue

                    ext = os.path.splitext(file_path)[1].lower()
                    node = None

                    if ext in (".csv", ".tsv"):
                        node = NodeRegistry.create("CSVReader")
                        if node:
                            node.set_param("file_path", file_path)
                    elif ext in (".geojson", ".json"):
                        node = NodeRegistry.create("GeoJSONReader")
                        if node:
                            node.set_param("file_path", file_path)
                    elif ext == ".shp":
                        node = NodeRegistry.create("ShapefileReader")
                        if node:
                            node.set_param("file_path", file_path)
                    elif ext in (".xlsx", ".xls"):
                        node = NodeRegistry.create("ExcelReader")
                        if node:
                            node.set_param("file_path", file_path)
                    elif ext in (".parquet", ".geoparquet"):
                        node = NodeRegistry.create("ParquetReader")
                        if node:
                            node.set_param("file_path", file_path)
                    elif ext in (".tif", ".tiff", ".geotiff"):
                        node = NodeRegistry.create("GeoTIFFReader")
                        if node:
                            node.set_param("file_path", file_path)
                    elif ext in (".fpy",):
                        # Load workspace safely
                        try:
                            if hasattr(self.window(), "load_workspace_file"):
                                self.window().load_workspace_file(file_path)
                            elif hasattr(self.window(), "graph"):
                                self.window().graph = WorkflowGraph.load_from_file(file_path)
                                self.canvas_scene.set_graph(self.window().graph)
                                self.window().current_file_path = file_path
                                self.window().setWindowTitle(f"open-FME Workbench - {os.path.basename(file_path)}")
                                self.window()._update_stats()
                                self.window().zoom_fit()
                        except Exception as load_err:
                            if hasattr(self.window(), "log_widget"):
                                self.window().log_widget.append_log(f"Failed to drop workspace: {load_err}", "ERROR")
                        event.acceptProposedAction()
                        return

                    if node:
                        pos = QPointF(scene_pos.x(), scene_pos.y() + offset_y)
                        self.canvas_scene.add_node_at_position(node, pos)
                        offset_y += 70.0

                event.acceptProposedAction()
                return

            # 2. Handle dragged transformer from left palette
            node_type = event.mimeData().text().strip()
            if node_type:
                node = NodeRegistry.create(node_type)
                if node:
                    self.canvas_scene.add_node_at_position(node, scene_pos)
                    event.acceptProposedAction()
        except Exception as e:
            if hasattr(self.window(), "log_widget"):
                self.window().log_widget.append_log(f"Drop event error: {e}", "WARN")

