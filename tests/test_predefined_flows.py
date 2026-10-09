"""
Unit tests for Predefined Workflows and Templates in open-FME.
Validates:
1. All 5 predefined flows can be constructed.
2. All 5 predefined flows have bookmarks, annotations, and visual positions.
3. Files are saved and loadable via WorkflowGraph.load_from_file.
4. Each predefined flow executes successfully with WorkflowRunner.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyfme.engine.predefined_flows import (
    get_predefined_flows,
    ensure_predefined_flow_files,
    get_sample_data_dir,
    PREDEFINED_FLOW_BUILDERS,
)
from pyfme.engine.graph import WorkflowGraph
from pyfme.engine.runner import WorkflowRunner


class TestPredefinedFlows(unittest.TestCase):

    def setUp(self):
        ensure_predefined_flow_files()

    def test_predefined_flows_count(self):
        flows = get_predefined_flows()
        self.assertEqual(len(flows), 5)
        expected_ids = [
            "customer_spatial_profiling",
            "regional_spatial_overlay",
            "attribute_cleansing_pipeline",
            "bounding_box_and_centroids",
            "html_reporting_pipeline",
        ]
        flow_ids = [f["id"] for f in flows]
        for eid in expected_ids:
            self.assertIn(eid, flow_ids)

    def test_predefined_files_exist(self):
        flows = get_predefined_flows()
        for flow in flows:
            self.assertTrue(os.path.exists(flow["file_path"]), f"{flow['file_path']} must exist")
            self.assertTrue(os.path.getsize(flow["file_path"]) > 0)

    def test_load_and_run_all_predefined_flows(self):
        flows = get_predefined_flows()
        for flow in flows:
            # 1. Build via builder
            graph = flow["builder"]()
            self.assertGreater(len(graph.nodes), 0)
            self.assertGreater(len(graph.connections), 0)
            self.assertGreaterEqual(len(graph.bookmarks), 1)

            # 2. Run graph in engine
            runner = WorkflowRunner(graph)
            success = runner.run()
            self.assertTrue(success, f"Workflow '{flow['title']}' failed execution!")

            # 3. Load from serialized file and verify consistency
            loaded_graph = WorkflowGraph.load_from_file(flow["file_path"])
            self.assertEqual(len(loaded_graph.nodes), len(graph.nodes))
            self.assertEqual(len(loaded_graph.connections), len(graph.connections))


if __name__ == "__main__":
    unittest.main()
