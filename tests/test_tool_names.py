"""
Unit tests for proper tool naming with spaces or dashes across open-FME.
Validates:
1. format_tool_name utility converts CamelCase/acronyms to clean readable names with spaces or dashes.
2. BaseNode and subclasses expose get_display_name().
3. Node instance name defaults to human-friendly display name (e.g. 'CSV Reader').
4. NodeRegistry supports lookups with spaces, dashes, or compact PascalCase (e.g. 'CSV Reader', 'CSV-Reader', 'CSVReader').
5. NodeRegistry.search finds nodes by display name with spaces or dashes.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyfme.engine.nodes.base import format_tool_name, BaseNode
from pyfme.engine.nodes.readers import CSVReader, GeoJSONReader
from pyfme.engine.nodes.transformers.spatial import VertexCreator, Bufferer
from pyfme.engine.nodes.transformers.fme_gdal_saga_vector import AreaOnAreaOverlayer, OGR2OGR, ThreeDForcer
from pyfme.engine.registry import NodeRegistry


class TestToolNames(unittest.TestCase):

    def test_format_tool_name_spaces(self):
        self.assertEqual(format_tool_name("CSVReader"), "CSV Reader")
        self.assertEqual(format_tool_name("CSVWriter"), "CSV Writer")
        self.assertEqual(format_tool_name("GeoJSONReader"), "GeoJSON Reader")
        self.assertEqual(format_tool_name("GeoJSONWriter"), "GeoJSON Writer")
        self.assertEqual(format_tool_name("VertexCreator"), "Vertex Creator")
        self.assertEqual(format_tool_name("AreaOnAreaOverlayer"), "Area On Area Overlayer")
        self.assertEqual(format_tool_name("2DForcer"), "2D Forcer")
        self.assertEqual(format_tool_name("3DForcer"), "3D Forcer")
        self.assertEqual(format_tool_name("OGR2OGR"), "OGR2OGR")
        self.assertEqual(format_tool_name("TINGenerator"), "TIN Generator")
        self.assertEqual(format_tool_name("RasterToPolygonCoercer"), "Raster To Polygon Coercer")
        self.assertEqual(format_tool_name("Bufferer"), "Bufferer")

    def test_format_tool_name_dashes(self):
        self.assertEqual(format_tool_name("CSVReader", separator="-"), "CSV-Reader")
        self.assertEqual(format_tool_name("GeoJSONReader", separator="-"), "GeoJSON-Reader")
        self.assertEqual(format_tool_name("VertexCreator", separator="-"), "Vertex-Creator")
        self.assertEqual(format_tool_name("AreaOnAreaOverlayer", separator="-"), "Area-On-Area-Overlayer")

    def test_node_get_display_name(self):
        self.assertEqual(CSVReader.get_display_name(), "CSV Reader")
        self.assertEqual(CSVReader.get_display_name(separator="-"), "CSV-Reader")
        self.assertEqual(GeoJSONReader.get_display_name(), "GeoJSON Reader")
        self.assertEqual(VertexCreator.get_display_name(), "Vertex Creator")

    def test_node_instance_default_name(self):
        csv_node = CSVReader()
        self.assertEqual(csv_node.name, "CSV Reader")
        self.assertEqual(csv_node.node_type, "CSVReader")

        # Custom name override still works
        custom_node = CSVReader(custom_name="My Custom CSV")
        self.assertEqual(custom_node.name, "My Custom CSV")
        self.assertEqual(custom_node.node_type, "CSVReader")

    def test_registry_get_variants(self):
        # PascalCase
        cls1 = NodeRegistry.get("CSVReader")
        self.assertIsNotNone(cls1)
        self.assertEqual(cls1, CSVReader)

        # Space separated
        cls2 = NodeRegistry.get("CSV Reader")
        self.assertEqual(cls2, CSVReader)

        # Dash separated
        cls3 = NodeRegistry.get("CSV-Reader")
        self.assertEqual(cls3, CSVReader)

        # Case insensitive
        cls4 = NodeRegistry.get("csv reader")
        self.assertEqual(cls4, CSVReader)

    def test_registry_create_variants(self):
        node_space = NodeRegistry.create("CSV Reader")
        self.assertIsNotNone(node_space)
        self.assertIsInstance(node_space, CSVReader)
        self.assertEqual(node_space.name, "CSV Reader")

        node_dash = NodeRegistry.create("CSV-Reader")
        self.assertIsNotNone(node_dash)
        self.assertIsInstance(node_dash, CSVReader)

        node_orig = NodeRegistry.create("CSVReader")
        self.assertIsNotNone(node_orig)
        self.assertIsInstance(node_orig, CSVReader)

    def test_registry_search_variants(self):
        # Search with space
        results_space = NodeRegistry.search("CSV Reader")
        types_space = [n.node_type for n in results_space]
        self.assertIn("CSVReader", types_space)

        # Search with dash
        results_dash = NodeRegistry.search("CSV-Reader")
        types_dash = [n.node_type for n in results_dash]
        self.assertIn("CSVReader", types_dash)

        # Search with lowercase
        results_lower = NodeRegistry.search("csv reader")
        types_lower = [n.node_type for n in results_lower]
        self.assertIn("CSVReader", types_lower)


if __name__ == "__main__":
    unittest.main()
