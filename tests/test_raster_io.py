"""
Unit & Integration Test Suite for Raster / GeoTIFF Input and Output in open-FME.
Tests GeoTIFFReader, RasterReader, GeoTIFFWriter, RasterWriter, FeatureDataset raster handling,
and end-to-end raster translation pipelines.
"""

import os
import sys
import tempfile
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rasterio
from rasterio.transform import from_origin
import geopandas as gpd
from shapely.geometry import box, Point, Polygon

from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry
from pyfme.engine.graph import WorkflowGraph
from pyfme.engine.nodes.base import NodeCategory
from pyfme.engine.nodes.readers import GeoTIFFReader, RasterReader
from pyfme.engine.nodes.writers import GeoTIFFWriter, RasterWriter
from pyfme.ui.generate_workspace_dialog import FORMAT_READERS, FORMAT_WRITERS, AddReaderDialog, AddWriterDialog


class TestRasterIO(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_single_band_tif = os.path.join(self.tmp_dir.name, "single_band.tif")
        self.test_multi_band_tif = os.path.join(self.tmp_dir.name, "multi_band.tif")

        # Create synthetic single-band raster: 20x30, elevation values
        self.data_1b = np.arange(600, dtype=np.float32).reshape(20, 30) + 100.0
        self.transform_1b = from_origin(10.0, 50.0, 0.5, 0.5)

        with rasterio.open(
            self.test_single_band_tif, "w", driver="GTiff",
            height=20, width=30, count=1,
            dtype=rasterio.float32, crs="EPSG:4326",
            transform=self.transform_1b, nodata=-9999.0
        ) as dst:
            dst.write(self.data_1b, 1)

        # Create synthetic 3-band raster: 10x15, RGB bands
        self.data_3b = np.zeros((3, 10, 15), dtype=np.uint8)
        self.data_3b[0] = 50
        self.data_3b[1] = 100
        self.data_3b[2] = 200
        self.transform_3b = from_origin(0.0, 40.0, 1.0, 1.0)

        with rasterio.open(
            self.test_multi_band_tif, "w", driver="GTiff",
            height=10, width=15, count=3,
            dtype=rasterio.uint8, crs="EPSG:3857",
            transform=self.transform_3b
        ) as dst:
            dst.write(self.data_3b)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_node_registration_and_metadata(self):
        """Test GeoTIFFReader, RasterReader, GeoTIFFWriter, RasterWriter are registered with correct category."""
        self.assertIn("GeoTIFFReader", NodeRegistry.all_nodes())
        self.assertIn("RasterReader", NodeRegistry.all_nodes())
        self.assertIn("GeoTIFFWriter", NodeRegistry.all_nodes())
        self.assertIn("RasterWriter", NodeRegistry.all_nodes())

        r_cls = NodeRegistry.get("GeoTIFFReader")
        self.assertEqual(r_cls.category, NodeCategory.READER)
        self.assertEqual(len(r_cls.get_input_ports()), 0)
        self.assertEqual(len(r_cls.get_output_ports()), 1)

        w_cls = NodeRegistry.get("GeoTIFFWriter")
        self.assertEqual(w_cls.category, NodeCategory.WRITER)
        self.assertEqual(len(w_cls.get_input_ports()), 1)
        self.assertEqual(len(w_cls.get_output_ports()), 1)

    def test_geotiff_reader_single_band(self):
        """Test reading a single-band GeoTIFF file."""
        reader = GeoTIFFReader()
        out = reader.execute({}, {"file_path": self.test_single_band_tif})
        self.assertIn("Output", out)
        ds = out["Output"]
        self.assertTrue(ds.has_raster())
        self.assertEqual(ds.count(), 1)

        # Check raster data
        data, prof = ds.get_raster()
        self.assertIsNotNone(data)
        self.assertEqual(prof["count"], 1)
        self.assertEqual(prof["width"], 30)
        self.assertEqual(prof["height"], 20)

        # Check bounds
        b = ds.get_bounds()
        self.assertIsNotNone(b)
        self.assertAlmostEqual(b[0], 10.0)
        self.assertAlmostEqual(b[2], 25.0)  # 10.0 + 30 * 0.5

        # Check GeoDataFrame representation
        gdf = ds.to_geopandas()
        self.assertEqual(len(gdf), 1)
        self.assertIn("raster_file", gdf.columns)
        self.assertIn("bands", gdf.columns)
        self.assertEqual(gdf["bands"].iloc[0], 1)

        # Check Polars representation
        df = ds.to_polars()
        self.assertEqual(len(df), 1)
        self.assertIn("width", df.columns)

    def test_geotiff_reader_multi_band(self):
        """Test reading a multi-band GeoTIFF file."""
        reader = GeoTIFFReader()
        out = reader.execute({}, {"file_path": self.test_multi_band_tif})
        ds = out["Output"]
        self.assertTrue(ds.has_raster())
        data, prof = ds.get_raster()
        self.assertEqual(prof["count"], 3)
        self.assertEqual(data.shape, (3, 10, 15))

    def test_geotiff_reader_specific_band(self):
        """Test reading a specific band (e.g. band 2) from a multi-band GeoTIFF file."""
        reader = GeoTIFFReader()
        out = reader.execute({}, {"file_path": self.test_multi_band_tif, "band_index": 2})
        ds = out["Output"]
        data, prof = ds.get_raster()
        self.assertEqual(prof["count"], 1)
        self.assertEqual(data.shape, (10, 15))
        self.assertEqual(data[0, 0], 100)

    def test_geotiff_writer_from_raster_dataset(self):
        """Test writing raster dataset directly to a new GeoTIFF file."""
        reader = GeoTIFFReader()
        r_out = reader.execute({}, {"file_path": self.test_single_band_tif})

        out_path = os.path.join(self.tmp_dir.name, "written_output.tif")
        writer = GeoTIFFWriter()
        w_out = writer.execute({"Input": r_out["Output"]}, {"file_path": out_path, "compression": "lzw"})

        self.assertTrue(os.path.exists(out_path))

        # Validate with rasterio
        with rasterio.open(out_path) as src:
            self.assertEqual(src.count, 1)
            self.assertEqual(src.width, 30)
            self.assertEqual(src.height, 20)
            self.assertEqual(src.compression.name.lower(), "lzw")
            read_back = src.read(1)
            np.testing.assert_array_almost_equal(read_back, self.data_1b)

    def test_raster_reader_and_writer_aliases(self):
        """Test RasterReader and RasterWriter aliases produce identical results."""
        r_node = NodeRegistry.create("RasterReader")
        self.assertIsInstance(r_node, RasterReader)
        r_out = r_node.execute({}, {"file_path": self.test_single_band_tif})
        self.assertTrue(r_out["Output"].has_raster())

        w_node = NodeRegistry.create("RasterWriter")
        self.assertIsInstance(w_node, RasterWriter)
        out_path = os.path.join(self.tmp_dir.name, "alias_output.tif")
        w_node.execute({"Input": r_out["Output"]}, {"file_path": out_path})
        self.assertTrue(os.path.exists(out_path))

    def test_pipeline_geotiff_reader_to_slope_to_writer(self):
        """Test pipeline: GeoTIFFReader -> SlopeCalculator -> GeoTIFFWriter."""
        reader = NodeRegistry.create("GeoTIFFReader")
        r_res = reader.execute({}, {"file_path": self.test_single_band_tif})

        slope_node = NodeRegistry.create("SlopeCalculator")
        s_res = slope_node.execute({"Input": r_res["Output"]}, {})
        self.assertTrue(s_res["Output"].has_raster())

        out_slope_tif = os.path.join(self.tmp_dir.name, "pipeline_slope.tif")
        writer = NodeRegistry.create("GeoTIFFWriter")
        w_res = writer.execute({"Input": s_res["Output"]}, {"file_path": out_slope_tif})

        self.assertTrue(os.path.exists(out_slope_tif))
        with rasterio.open(out_slope_tif) as src:
            self.assertEqual(src.width, 30)
            self.assertEqual(src.height, 20)
            slope_data = src.read(1)
            self.assertGreater(float(np.nanmax(slope_data)), 0.0)

    def test_pipeline_geotiff_reader_to_extents_coercer(self):
        """Test pipeline: GeoTIFFReader -> RasterExtentsCoercer (Raster to Vector)."""
        reader = NodeRegistry.create("GeoTIFFReader")
        r_res = reader.execute({}, {"file_path": self.test_single_band_tif})

        coercer = NodeRegistry.create("RasterExtentsCoercer")
        c_res = coercer.execute({"Input": r_res["Output"]}, {})
        gdf = c_res["Output"].to_geopandas()
        self.assertEqual(len(gdf), 1)
        self.assertEqual(gdf.geometry.iloc[0].geom_type, "Polygon")

    def test_geotiff_writer_vector_rasterization(self):
        """Test GeoTIFFWriter rasterizing vector polygon features."""
        p = box(0.0, 0.0, 10.0, 10.0)
        gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[p], crs="EPSG:4326")
        ds = FeatureDataset.from_geopandas(gdf)

        out_rasterized = os.path.join(self.tmp_dir.name, "vector_rasterized.tif")
        writer = GeoTIFFWriter()
        writer.execute({"Input": ds}, {"file_path": out_rasterized})

        self.assertTrue(os.path.exists(out_rasterized))
        with rasterio.open(out_rasterized) as src:
            self.assertEqual(src.count, 1)
            self.assertEqual(src.width, 512)
            self.assertEqual(src.height, 512)
            data = src.read(1)
            self.assertEqual(int(data.max()), 1)

    def test_format_dialog_options(self):
        """Test FORMAT_READERS and FORMAT_WRITERS have GeoTIFF entries."""
        self.assertIn("GeoTIFF / Raster (*.tif, *.tiff)", FORMAT_READERS)
        self.assertEqual(FORMAT_READERS["GeoTIFF / Raster (*.tif, *.tiff)"], "GeoTIFFReader")

        self.assertIn("GeoTIFF / Raster (*.tif, *.tiff)", FORMAT_WRITERS)
        self.assertEqual(FORMAT_WRITERS["GeoTIFF / Raster (*.tif, *.tiff)"], "GeoTIFFWriter")


if __name__ == "__main__":
    unittest.main()
