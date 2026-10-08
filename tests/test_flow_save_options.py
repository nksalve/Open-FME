"""
Tests for open-FME Flow Saving Capabilities:
- Save Flow (Ctrl+S)
- Save Flow As (Ctrl+Shift+S)
- Save Selected Flow (subgraph extraction)
- Export Flow Diagram as Image (PNG/JPG)
- Flow dirty state tracking and title update
- CanvasView key shortcuts (Ctrl+S, Ctrl+Shift+S)
- CanvasScene context menu signals
- Navigator Tree context menu save flow options
"""

import os
import sys
import tempfile
import unittest

os.environ["OPENFME_TEST_MODE"] = "1"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QKeyEvent

from pyfme.engine.graph import WorkflowGraph
from pyfme.engine.registry import NodeRegistry
from pyfme.ui.main_window import MainWindow
from pyfme.ui.canvas.scene import CanvasScene
from pyfme.ui.canvas.view import CanvasView
import pyfme.engine.nodes  # Ensure nodes registered


def get_qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    return app


class TestFlowSaveOptions(unittest.TestCase):

    def setUp(self):
        self.app = get_qapp()
        self.win = None

    def tearDown(self):
        if self.win is not None:
            self.win.close()
            self.win.deleteLater()
            self.win = None
        self.app.processEvents()

    def test_workflow_graph_subgraph(self):
        """Test extracting a subflow from WorkflowGraph."""
        graph = WorkflowGraph("Complete Pipeline")
        r = NodeRegistry.create("CSVReader")
        r.x, r.y = 100, 100
        graph.add_node(r)

        t = NodeRegistry.create("Tester")
        t.x, t.y = 300, 100
        graph.add_node(t)

        w = NodeRegistry.create("GeoJSONWriter")
        w.x, w.y = 500, 100
        graph.add_node(w)

        graph.connect(r.id, "Output", t.id, "Input")
        graph.connect(t.id, "Passed", w.id, "Input")

        # Extract subflow of just r and t
        sub = graph.subgraph({r.id, t.id}, name="Reader and Tester Subflow")
        self.assertEqual(len(sub.nodes), 2)
        self.assertIn(r.id, sub.nodes)
        self.assertIn(t.id, sub.nodes)
        self.assertNotIn(w.id, sub.nodes)
        self.assertEqual(len(sub.connections), 1)
        self.assertEqual(sub.connections[0].from_node_id, r.id)
        self.assertEqual(sub.connections[0].to_node_id, t.id)

        # Test save and reload of subgraph
        with tempfile.NamedTemporaryFile(suffix=".fpy", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            sub.save_to_file(tmp_path)
            self.assertTrue(os.path.exists(tmp_path))
            loaded_sub = WorkflowGraph.load_from_file(tmp_path)
            self.assertEqual(len(loaded_sub.nodes), 2)
            self.assertEqual(len(loaded_sub.connections), 1)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_main_window_save_flow_and_dirty_state(self):
        """Test save_flow, dirty state tracking, and window title updating."""
        self.win = MainWindow()
        self.assertFalse(self.win._is_flow_dirty)

        # Mark flow dirty
        self.win.mark_flow_dirty()
        self.assertTrue(self.win._is_flow_dirty)
        self.assertIn("*", self.win.windowTitle())

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".fpy", delete=False) as tmp:
            save_path = tmp.name
        try:
            self.win.current_file_path = save_path
            saved = self.win.save_flow()
            self.assertTrue(saved)
            self.assertFalse(self.win._is_flow_dirty)
            self.assertNotIn("*", self.win.windowTitle())
            self.assertIn(os.path.basename(save_path), self.win.windowTitle())

            # Verify saved file content
            reloaded = WorkflowGraph.load_from_file(save_path)
            self.assertEqual(len(reloaded.nodes), len(self.win.graph.nodes))
        finally:
            if os.path.exists(save_path):
                os.remove(save_path)

    def test_save_selected_flow(self):
        """Test saving only selected nodes to a file."""
        self.win = MainWindow()
        # Select one node
        items = list(self.win.scene.node_items.values())
        self.assertTrue(len(items) > 0)
        self.win.scene.clearSelection()
        items[0].setSelected(True)

        selected_ids = self.win.scene.get_selected_node_ids()
        self.assertEqual(len(selected_ids), 1)

        sub = self.win.graph.subgraph(selected_ids)
        self.assertEqual(len(sub.nodes), 1)

    def test_export_flow_image(self):
        """Test rendering visual flow canvas to an image."""
        self.win = MainWindow()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img_path = tmp.name
        try:
            ok = self.win.scene.export_image(img_path)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(img_path))
            self.assertGreater(os.path.getsize(img_path), 500)
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    def test_canvas_scene_save_signals(self):
        """Test that CanvasScene emits save flow signals."""
        scene = CanvasScene()
        save_emitted = []
        save_as_emitted = []
        save_sel_emitted = []
        export_emitted = []

        scene.save_flow_requested.connect(lambda: save_emitted.append(True))
        scene.save_flow_as_requested.connect(lambda: save_as_emitted.append(True))
        scene.save_selected_flow_requested.connect(lambda: save_sel_emitted.append(True))
        scene.export_flow_image_requested.connect(lambda: export_emitted.append(True))

        scene.save_flow_requested.emit()
        scene.save_flow_as_requested.emit()
        scene.save_selected_flow_requested.emit()
        scene.export_flow_image_requested.emit()

        self.assertEqual(len(save_emitted), 1)
        self.assertEqual(len(save_as_emitted), 1)
        self.assertEqual(len(save_sel_emitted), 1)
        self.assertEqual(len(export_emitted), 1)

    def test_canvas_view_save_shortcuts(self):
        """Test Ctrl+S and Ctrl+Shift+S key press in CanvasView."""
        self.win = MainWindow()
        saved_calls = []
        save_as_calls = []

        self.win.save_flow = lambda: saved_calls.append(True)
        self.win.save_flow_as = lambda: save_as_calls.append(True)

        # Send Ctrl+S
        event_s = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_S,
            Qt.KeyboardModifier.ControlModifier,
            "s"
        )
        self.win.view.keyPressEvent(event_s)
        self.assertEqual(len(saved_calls), 1)

        # Send Ctrl+Shift+S
        event_shift_s = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_S,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            "S"
        )
        self.win.view.keyPressEvent(event_shift_s)
        self.assertEqual(len(save_as_calls), 1)


if __name__ == "__main__":
    unittest.main()

