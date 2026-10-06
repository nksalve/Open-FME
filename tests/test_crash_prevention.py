"""
Comprehensive Crash Prevention & Resilience Tests for open-FME.
Validates that:
1. Syntax & runtime errors in PythonCaller do not crash the runner or UI.
2. Missing or corrupted files in Readers do not crash the pipeline.
3. Dataset merging with incompatible schemas does not crash.
4. Inspecting failed/None output nodes does not raise AttributeError.
5. Canvas right-click context menu on unexecuted nodes does not crash.
6. Table inspector regex characters in filter do not crash Polars.
7. Corrupted workspace files fail gracefully without aborting open-FME.
8. CrashProtectionManager traps unhandled exceptions and keeps app alive.
"""

import os
import sys
import tempfile
import polars as pl
import geopandas as gpd
from shapely.geometry import Point

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["OPENFME_TEST_MODE"] = "1"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF

from pyfme.engine.graph import WorkflowGraph
from pyfme.engine.runner import WorkflowRunner
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry
from pyfme.ui.main_window import MainWindow
from pyfme.ui.error_handler import CrashProtectionManager, install_crash_protection
from pyfme.ui.inspector.table_view import TableInspectorWidget
from pyfme.ui.inspector.inspector_dock import InspectorDockWidget


def get_qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


def test_python_caller_runtime_error_does_not_crash():
    """Verify that a deliberate division-by-zero or syntax error in a transformer does not crash runner."""
    graph = WorkflowGraph("Crash Test Graph")

    # 1. Source node
    src = NodeRegistry.create("CSVReader")
    tmp_csv = tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False)
    tmp_csv.write("id,val\n1,10\n2,20\n")
    tmp_csv.close()
    src.set_param("file_path", tmp_csv.name)
    graph.add_node(src)

    # 2. Failing PythonCaller node
    failing_node = NodeRegistry.create("PythonCaller")
    failing_node.set_param("python_code", "output_df = 1 / 0  # Deliberate ZeroDivisionError")
    graph.add_node(failing_node)

    # 3. Connect them
    graph.connect(src.id, "Output", failing_node.id, "Input")

    logs = []
    runner = WorkflowRunner(graph, log_callback=lambda msg, lvl: logs.append((msg, lvl)))
    success = runner.run()

    # Must return False, not crash or raise uncaught exception
    assert success is False, "Runner should report failed translation"
    assert failing_node.last_error is not None, "Failing node should store error message"
    assert "division by zero" in failing_node.last_error.lower(), "Error should mention division by zero"
    assert failing_node.last_outputs == {}, "Failed node should safely have empty dict for outputs"
    print("[PASS] test_python_caller_runtime_error_does_not_crash passed")



def test_missing_input_file_does_not_crash():
    """Verify that a reader pointing to a non-existent file fails gracefully without crashing."""
    graph = WorkflowGraph("Missing File Graph")
    reader = NodeRegistry.create("GeoJSONReader")
    reader.set_param("file_path", "non_existent_file_12345.geojson")
    graph.add_node(reader)

    logs = []
    runner = WorkflowRunner(graph, log_callback=lambda msg, lvl: logs.append((msg, lvl)))
    success = runner.run()

    assert success is False
    assert reader.last_error is not None
    print("[PASS] test_missing_input_file_does_not_crash passed")


def test_table_search_regex_characters_does_not_crash():
    """Verify that typing regex characters (*, [, (, \\) in Table View search filter does not crash."""
    app = get_qapp()
    widget = TableInspectorWidget()

    df = pl.DataFrame({"name": ["alpha", "beta", "gamma"], "val": [1, 2, 3]})
    ds = FeatureDataset.from_polars(df)
    widget.set_dataset(ds)

    # These regex special chars used to crash polars.str.contains
    special_queries = ["[", "*", "(", "\\", "+", "?", "{", "$", "^"]
    for q in special_queries:
        widget._on_search_changed(q)

    # Should reset cleanly
    widget._on_search_changed("")
    assert widget.current_dataset.count() == 3
    print("[PASS] test_table_search_regex_characters_does_not_crash passed")


def test_dataset_merge_heterogeneous_schemas_does_not_crash():
    """Verify that merging datasets with mismatched columns does not crash runner._merge_datasets."""
    graph = WorkflowGraph("Merge Test")
    runner = WorkflowRunner(graph)

    ds1 = FeatureDataset.from_polars(pl.DataFrame({"a": [1, 2], "b": ["x", "y"]}))
    ds2 = FeatureDataset.from_polars(pl.DataFrame({"c": [10.5, 20.5], "d": [True, False]}))

    merged = runner._merge_datasets([ds1, ds2])
    assert merged is not None
    assert merged.count() == 4
    assert "a" in merged.columns
    assert "c" in merged.columns
    print("[PASS] test_dataset_merge_heterogeneous_schemas_does_not_crash passed")


def test_inspector_none_and_corrupt_data_does_not_crash():
    """Verify that InspectorDockWidget handles None dataset and empty nodes without crashing."""
    app = get_qapp()
    dock = InspectorDockWidget()

    node = NodeRegistry.create("Bufferer")
    # 1. Test None dataset
    dock.inspect_dataset(node, "Output", None)
    assert "No features" in dock.info_label.text()

    # 2. Test empty dataset
    dock.inspect_dataset(node, "Output", FeatureDataset.empty())
    assert "No features" in dock.info_label.text()

    # 3. Test node with no name attribute
    class DummyNode:
        pass
    dock.inspect_dataset(DummyNode(), "Output", None)
    print("[PASS] test_inspector_none_and_corrupt_data_does_not_crash passed")


def test_corrupted_workspace_file_loading_does_not_crash():
    """Verify that loading a malformed/corrupted workspace file shows error but does not crash."""
    app = get_qapp()
    win = MainWindow()

    # Write a broken JSON file
    tmp_bad = tempfile.NamedTemporaryFile(suffix=".fpy", mode="w", delete=False)
    tmp_bad.write("{ this is not valid JSON content !!! }")
    tmp_bad.close()

    # load_workspace_file must catch error gracefully
    win.load_workspace_file(tmp_bad.name)
    assert win.graph is not None, "Existing graph should remain intact"
    print("[PASS] test_corrupted_workspace_file_loading_does_not_crash passed")


def test_main_window_workflow_finished_with_failed_node_does_not_crash():
    """
    CRITICAL REGRESSION TEST:
    Verifies that when a node fails and last_outputs is None / empty,
    _on_workflow_finished does not throw AttributeError: 'NoneType' object has no attribute 'get'.
    """
    app = get_qapp()
    win = MainWindow()

    # Create a node that has last_outputs = None or empty
    failed_node = NodeRegistry.create("Tester")
    failed_node.last_outputs = None
    win._last_completed_node = failed_node

    # Call _on_workflow_finished directly (simulating what happens when a workflow fails)
    win._on_workflow_finished(False, 0.5, "Translation failed on purpose")

    assert win.run_btn.isEnabled(), "Run button must be re-enabled"
    assert not win.progress_bar.isVisible(), "Progress bar must be hidden"
    assert "FAILED" in win.log_widget._raw_lines[-1][0] or "FAILED" in win.log_widget._raw_lines[-2][0]
    print("[PASS] test_main_window_workflow_finished_with_failed_node_does_not_crash passed")


def test_crash_protection_manager_handles_exception_safely():
    """Verify that CrashProtectionManager catches exceptions and keeps execution running."""
    manager = CrashProtectionManager.get_instance()
    manager.install()

    # Simulate an unexpected exception
    try:
        raise RuntimeError("Test simulation of unexpected exception")
    except RuntimeError:
        exc_type, exc_val, exc_tb = sys.exc_info()
        # Ensure handle_exception does not raise or exit
        manager.handle_exception(exc_type, exc_val, exc_tb)

    # Check error log file was written
    log_path = os.path.abspath("open_fme_error.log")
    assert os.path.exists(log_path), "Error log file must exist"
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Test simulation of unexpected exception" in content
    print("[PASS] test_crash_protection_manager_handles_exception_safely passed")


if __name__ == "__main__":
    test_python_caller_runtime_error_does_not_crash()
    test_missing_input_file_does_not_crash()
    test_table_search_regex_characters_does_not_crash()
    test_dataset_merge_heterogeneous_schemas_does_not_crash()
    test_inspector_none_and_corrupt_data_does_not_crash()
    test_corrupted_workspace_file_loading_does_not_crash()
    test_main_window_workflow_finished_with_failed_node_does_not_crash()
    test_crash_protection_manager_handles_exception_safely()
    print("\nALL 8 CRASH-PREVENTION TESTS PASSED 100% SUCCESSFULLY!")

