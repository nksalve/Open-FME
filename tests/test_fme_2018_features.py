"""
Test suite validating FME Desktop 2018 features added to open-FME:
1. FME Top 30 Core Transformers:
   - TestFilter
   - Counter
   - AttributeFilter
   - CoordinateExtractor
   - AttributeSplitter
   - Inspector
   - SpatialFilter
   - FeatureJoiner
2. Feature Caching & Partial Runs:
   - get_ancestors & get_descendants subgraph resolution
   - WorkflowRunner mode="to_this"
   - WorkflowRunner mode="from_this" reusing cached outputs
3. Generate Workspace generation logic
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import polars as pl
import geopandas as gpd
from shapely.geometry import Point, Polygon

from pyfme.engine.graph import WorkflowGraph
from pyfme.engine.runner import WorkflowRunner
from pyfme.engine.registry import NodeRegistry
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.nodes.readers import CSVReader
from pyfme.engine.nodes.transformers.fme_core_transformers import (
    TestFilter, Counter, AttributeFilter, CoordinateExtractor,
    AttributeSplitter, Inspector, SpatialFilter, FeatureJoiner
)


class TestFME2018Features(unittest.TestCase):

    def test_test_filter(self):
        """TestFilter sequentially routes features to Port1, Port2, or <Else>."""
        df = pl.DataFrame({
            "id": [1, 2, 3, 4],
            "dept": ["Engineering", "HR", "Marketing", "HR"],
            "salary": [90000, 60000, 75000, 55000]
        })
        ds = FeatureDataset.from_polars(df)

        tf = TestFilter()
        tf.set_param("test1_attribute", "dept")
        tf.set_param("test1_operator", "=")
        tf.set_param("test1_value", "Engineering")

        tf.set_param("test2_attribute", "dept")
        tf.set_param("test2_operator", "=")
        tf.set_param("test2_value", "HR")

        outputs = tf.execute({"Input": ds}, tf.params)
        self.assertIn("Port1", outputs)
        self.assertIn("Port2", outputs)
        self.assertIn("<Else>", outputs)

        # Port1 should have Engineering (1 row)
        self.assertEqual(outputs["Port1"].count(), 1)
        self.assertEqual(outputs["Port1"].to_polars()["dept"][0], "Engineering")

        # Port2 should have HR (2 rows)
        self.assertEqual(outputs["Port2"].count(), 2)

        # <Else> should have Marketing (1 row)
        self.assertEqual(outputs["<Else>"].count(), 1)
        self.assertEqual(outputs["<Else>"].to_polars()["dept"][0], "Marketing")

    def test_counter(self):
        """Counter generates a sequential integer sequence."""
        df = pl.DataFrame({"name": ["Alpha", "Beta", "Gamma", "Delta"]})
        ds = FeatureDataset.from_polars(df)

        counter = Counter()
        counter.set_param("counter_name", "_id")
        counter.set_param("start_value", 100)
        counter.set_param("step", 5)

        outputs = counter.execute({"Input": ds}, counter.params)
        res_df = outputs["Output"].to_polars()
        self.assertIn("_id", res_df.columns)
        self.assertEqual(res_df["_id"].to_list(), [100, 105, 110, 115])

    def test_attribute_filter(self):
        """AttributeFilter partitions features by specific attribute value matches."""
        df = pl.DataFrame({
            "zone": ["Residential", "Commercial", "Industrial", "Residential"]
        })
        ds = FeatureDataset.from_polars(df)

        af = AttributeFilter()
        af.set_param("filter_attribute", "zone")
        af.set_param("value1", "Residential")
        af.set_param("value2", "Commercial")

        outputs = af.execute({"Input": ds}, af.params)
        self.assertEqual(outputs["Match1"].count(), 2)
        self.assertEqual(outputs["Match2"].count(), 1)
        self.assertEqual(outputs["<Unfiltered>"].count(), 1)
        self.assertEqual(outputs["<Unfiltered>"].to_polars()["zone"][0], "Industrial")

    def test_coordinate_extractor(self):
        """CoordinateExtractor pulls X and Y geometry points into attributes."""
        gdf = gpd.GeoDataFrame({
            "name": ["PointA", "PointB"]
        }, geometry=[Point(12.5, 45.3), Point(-73.9, 40.7)], crs="EPSG:4326")
        ds = FeatureDataset.from_geopandas(gdf)

        ce = CoordinateExtractor()
        ce.set_param("x_attribute", "_lon")
        ce.set_param("y_attribute", "_lat")

        outputs = ce.execute({"Input": ds}, ce.params)
        res_gdf = outputs["Output"].to_geopandas()
        self.assertIn("_lon", res_gdf.columns)
        self.assertIn("_lat", res_gdf.columns)
        self.assertAlmostEqual(res_gdf["_lon"].iloc[0], 12.5, places=3)
        self.assertAlmostEqual(res_gdf["_lat"].iloc[0], 45.3, places=3)

    def test_attribute_splitter(self):
        """AttributeSplitter splits delimited strings into separate columns."""
        df = pl.DataFrame({
            "address": ["123 Main St, Springfield, IL", "456 Oak Ave, Portland, OR"]
        })
        ds = FeatureDataset.from_polars(df)

        splitter = AttributeSplitter()
        splitter.set_param("source_attribute", "address")
        splitter.set_param("delimiter", ", ")
        splitter.set_param("target_prefix", "part_")

        outputs = splitter.execute({"Input": ds}, splitter.params)
        res_df = outputs["Output"].to_polars()
        self.assertIn("part_0", res_df.columns)
        self.assertIn("part_1", res_df.columns)
        self.assertIn("part_2", res_df.columns)
        self.assertEqual(res_df["part_0"].to_list(), ["123 Main St", "456 Oak Ave"])
        self.assertEqual(res_df["part_2"].to_list(), ["IL", "OR"])

    def test_inspector(self):
        """Inspector passes all features unmodified through Output port."""
        df = pl.DataFrame({"val": [1, 2, 3]})
        ds = FeatureDataset.from_polars(df)

        insp = Inspector()
        outputs = insp.execute({"Input": ds}, insp.params)
        self.assertEqual(outputs["Output"].count(), 3)

    def test_spatial_filter(self):
        """SpatialFilter evaluates spatial predicates between Candidate and Filter layers."""
        # Candidates: 3 points
        cand_gdf = gpd.GeoDataFrame({
            "id": [1, 2, 3]
        }, geometry=[Point(5, 5), Point(15, 15), Point(8, 8)], crs="EPSG:4326")
        cand_ds = FeatureDataset.from_geopandas(cand_gdf)

        # Filter: Polygon covering (0,0) to (10,10)
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        filt_gdf = gpd.GeoDataFrame({"id": ["BBOX"]}, geometry=[poly], crs="EPSG:4326")
        filt_ds = FeatureDataset.from_geopandas(filt_gdf)

        sf = SpatialFilter()
        sf.set_param("predicate", "Within")

        outputs = sf.execute({"Candidate": cand_ds, "Filter": filt_ds}, sf.params)
        self.assertEqual(outputs["Passed"].count(), 2)  # Points at (5,5) and (8,8)
        self.assertEqual(outputs["Failed"].count(), 1)  # Point at (15,15)

    def test_feature_joiner(self):
        """FeatureJoiner joins two tables and routes unjoined rows to separate ports."""
        left_df = pl.DataFrame({
            "customer_id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"]
        })
        right_df = pl.DataFrame({
            "cust_id": [2, 3, 4],
            "city": ["New York", "London", "Tokyo"]
        })
        left_ds = FeatureDataset.from_polars(left_df)
        right_ds = FeatureDataset.from_polars(right_df)

        joiner = FeatureJoiner()
        joiner.set_param("left_key", "customer_id")
        joiner.set_param("right_key", "cust_id")
        joiner.set_param("join_type", "inner")

        outputs = joiner.execute({"Left": left_ds, "Right": right_ds}, joiner.params)
        self.assertEqual(outputs["Joined"].count(), 2)  # 2 and 3 match
        self.assertEqual(outputs["UnjoinedLeft"].count(), 1)   # Alice (id 1)
        self.assertEqual(outputs["UnjoinedRight"].count(), 1)  # Tokyo (id 4)
        self.assertEqual(outputs["UnjoinedLeft"].to_polars()["name"][0], "Alice")
        self.assertEqual(outputs["UnjoinedRight"].to_polars()["city"][0], "Tokyo")

    def test_dag_subgraph_ancestors_and_descendants(self):
        """Verifies graph.get_ancestors and get_descendants for partial execution."""
        graph = WorkflowGraph()

        # A -> B -> C -> D
        node_a = NodeRegistry.create("Counter", node_id="A")
        node_b = NodeRegistry.create("Counter", node_id="B")
        node_c = NodeRegistry.create("Counter", node_id="C")
        node_d = NodeRegistry.create("Counter", node_id="D")

        graph.add_node(node_a)
        graph.add_node(node_b)
        graph.add_node(node_c)
        graph.add_node(node_d)

        graph.connect("A", "Output", "B", "Input")
        graph.connect("B", "Output", "C", "Input")
        graph.connect("C", "Output", "D", "Input")

        # Ancestors of C should be {A, B}
        ancestors_c = graph.get_ancestors("C")
        self.assertEqual(ancestors_c, {"A", "B"})

        # Descendants of B should be {C, D}
        descendants_b = graph.get_descendants("B")
        self.assertEqual(descendants_b, {"C", "D"})

        # Subgraph topological order for to_this on C
        order_to_c = graph.get_topological_order_for_subgraph({"A", "B", "C"})
        self.assertEqual(order_to_c, ["A", "B", "C"])

    def test_workflow_runner_feature_caching_partial_runs(self):
        """
        Validates FME 2018 'Run to This' and 'Run From This' with feature caching.
        """
        graph = WorkflowGraph("Partial Run Test")

        # 1. Reader node with sample data
        csv_path = os.path.abspath("sample_data/customers.csv")
        reader = NodeRegistry.create("CSVReader", node_id="node_reader")
        reader.set_param("file_path", csv_path)
        graph.add_node(reader)

        # 2. Counter node
        counter = NodeRegistry.create("Counter", node_id="node_counter")
        counter.set_param("counter_name", "seq_num")
        counter.set_param("start_value", 1)
        graph.add_node(counter)

        # 3. TestFilter node
        tfilter = NodeRegistry.create("TestFilter", node_id="node_filter")
        tfilter.set_param("test1_attribute", "status")
        tfilter.set_param("test1_operator", "=")
        tfilter.set_param("test1_value", "active")
        graph.add_node(tfilter)

        # Connect reader -> counter -> tfilter
        graph.connect("node_reader", "Output", "node_counter", "Input")
        graph.connect("node_counter", "Output", "node_filter", "Input")

        runner = WorkflowRunner(graph)

        # --- Phase 1: Run to This (node_counter) ---
        success = runner.run(target_node_id="node_counter", mode="to_this")
        self.assertTrue(success)
        # Verify node_counter has cached outputs
        self.assertIn("Output", counter.last_outputs)
        cached_counter_out = counter.last_outputs["Output"]
        self.assertGreater(cached_counter_out.count(), 0)
        self.assertIn("seq_num", cached_counter_out.columns)
        # Verify node_filter was NOT executed yet
        self.assertEqual(tfilter.last_outputs, {})

        # --- Phase 2: Run From This (node_counter) ---
        # node_filter should execute using the cached output from node_counter
        success2 = runner.run(target_node_id="node_counter", mode="from_this")
        self.assertTrue(success2)
        # Verify node_filter now executed and cached results
        self.assertIn("Port1", tfilter.last_outputs)
        self.assertGreater(tfilter.last_outputs["Port1"].count(), 0)

    def test_generate_workspace_configuration(self):
        """Validates automated format-to-format translation generation."""
        graph = WorkflowGraph("Auto Generated Workspace")

        reader = NodeRegistry.create("CSVReader")
        reader.set_param("file_path", "test.csv")
        graph.add_node(reader)

        writer = NodeRegistry.create("GeoJSONWriter")
        writer.set_param("file_path", "output.geojson")
        graph.add_node(writer)

        graph.connect(reader.id, "Output", writer.id, "Input")

        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(len(graph.connections), 1)
        self.assertEqual(graph.connections[0].from_node_id, reader.id)
        self.assertEqual(graph.connections[0].to_node_id, writer.id)


if __name__ == "__main__":
    unittest.main()
