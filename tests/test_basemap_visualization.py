"""
Unit and integration tests for OpenStreetMap (OSM) and ArcGIS basemap visualizer.
"""

import os
import sys
import tempfile
import unittest
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["OPENFME_TEST_MODE"] = "1"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtCore import QPointF

from pyfme.engine.dataset import FeatureDataset
from pyfme.ui.inspector.map_view import (
    MapCanvasWidget, MapInspectorWidget, BasemapTileManager,
    BASEMAP_CONFIGS, MERCATOR_R, MERCATOR_W
)


def get_qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


class TestBasemapVisualization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_qapp()

    def test_basemap_configs_presence(self):
        """Verify OSM and all ArcGIS basemap configurations exist."""
        expected_keys = [
            "osm", "arcgis_imagery", "arcgis_streets", "arcgis_topo",
            "arcgis_dark", "arcgis_light", "arcgis_natgeo", "arcgis_ocean", "none"
        ]
        for key in expected_keys:
            self.assertIn(key, BASEMAP_CONFIGS)
            cfg = BASEMAP_CONFIGS[key]
            self.assertIn("name", cfg)
            self.assertIn("max_zoom", cfg)

    def test_canvas_initialization_and_bounds(self):
        """Verify MapCanvasWidget initializes with world bounds."""
        canvas = MapCanvasWidget()
        self.assertIsNotNone(canvas.bounds)
        self.assertAlmostEqual(canvas.bounds[0], -MERCATOR_R)
        self.assertAlmostEqual(canvas.bounds[2], MERCATOR_R)
        self.assertEqual(canvas.basemap_provider, "osm")
        self.assertEqual(canvas.basemap_opacity, 1.0)
        self.assertTrue(canvas.show_vectors)

    def test_basemap_switching(self):
        """Verify switching between OSM and ArcGIS basemaps."""
        canvas = MapCanvasWidget()
        for key in BASEMAP_CONFIGS.keys():
            canvas.set_basemap(key)
            self.assertEqual(canvas.basemap_provider, key)

    def test_opacity_control(self):
        """Verify opacity changes."""
        canvas = MapCanvasWidget()
        canvas.set_basemap_opacity(0.65)
        self.assertAlmostEqual(canvas.basemap_opacity, 0.65)
        canvas.set_basemap_opacity(1.5)  # clamped to 1.0
        self.assertEqual(canvas.basemap_opacity, 1.0)
        canvas.set_basemap_opacity(-0.2)  # clamped to 0.0
        self.assertEqual(canvas.basemap_opacity, 0.0)

    def test_world_screen_coordinate_roundtrip(self):
        """Verify world_to_screen and screen_to_world invert each other."""
        canvas = MapCanvasWidget()
        canvas.resize(800, 600)
        canvas.zoom_to_extent()

        test_wx, test_wy = -1000000.0, 5000000.0
        sp = canvas.world_to_screen(test_wx, test_wy)
        wp = canvas.screen_to_world(sp.x(), sp.y())

        self.assertAlmostEqual(wp.x(), test_wx, places=2)
        self.assertAlmostEqual(wp.y(), test_wy, places=2)

    def test_screen_to_lonlat_projection(self):
        """Verify screen_to_lonlat calculates accurate WGS84 degrees."""
        canvas = MapCanvasWidget()
        canvas.resize(800, 600)
        canvas.zoom_to_extent()

        # Center of canvas is (0, 0) in world coords
        center_x = canvas.width() / 2.0
        center_y = canvas.height() / 2.0
        lon, lat = canvas.screen_to_lonlat(center_x, center_y)
        self.assertAlmostEqual(lon, 0.0, places=1)
        self.assertAlmostEqual(lat, 0.0, places=1)

    def test_dataset_reprojection_and_bounds(self):
        """Verify spatial dataset in EPSG:4326 is projected to EPSG:3857 for map alignment."""
        canvas = MapCanvasWidget()
        gdf = gpd.GeoDataFrame({
            "name": ["Seattle", "Portland"],
            "geometry": [Point(-122.3321, 47.6062), Point(-122.6784, 45.5152)]
        }, crs="EPSG:4326")
        ds = FeatureDataset.from_geopandas(gdf)

        canvas.set_dataset(ds)
        self.assertIsNotNone(canvas._display_gdf)
        self.assertTrue(canvas.is_geographic)
        # Bounds should now be in Web Mercator meters (< -10,000,000)
        minx, miny, maxx, maxy = canvas.bounds
        self.assertLess(minx, -10000000)
        self.assertGreater(maxy, 5000000)

    def test_offscreen_canvas_rendering(self):
        """Verify that paintEvent renders without errors on offscreen image."""
        inspector = MapInspectorWidget()
        inspector.resize(800, 600)

        # Polygon and Line features
        poly = Polygon([[-122.4, 37.7], [-122.3, 37.7], [-122.3, 37.8], [-122.4, 37.8], [-122.4, 37.7]])
        line = LineString([[-122.4, 37.7], [-122.3, 37.8]])
        gdf = gpd.GeoDataFrame({"geometry": [poly, line]}, crs="EPSG:4326")
        ds = FeatureDataset.from_geopandas(gdf)
        inspector.set_dataset(ds)

        img = QImage(800, 600, QImage.Format.Format_ARGB32)
        img.fill(0)
        painter = QPainter(img)
        inspector.canvas.render(painter)
        painter.end()

        # Switch to ArcGIS Satellite and render again
        inspector.canvas.set_basemap("arcgis_imagery")
        painter = QPainter(img)
        inspector.canvas.render(painter)
        painter.end()

    def test_inspector_toolbar_controls(self):
        """Verify inspector toolbar buttons, combo boxes and sliders."""
        inspector = MapInspectorWidget()
        # Combo selection
        idx = inspector.basemap_combo.findData("arcgis_streets")
        self.assertGreaterEqual(idx, 0)
        inspector.basemap_combo.setCurrentIndex(idx)
        self.assertEqual(inspector.canvas.basemap_provider, "arcgis_streets")

        # Opacity slider
        inspector.opacity_slider.setValue(75)
        self.assertEqual(inspector.opacity_val_lbl.text(), "75%")
        self.assertAlmostEqual(inspector.canvas.basemap_opacity, 0.75)

        # Vector overlay toggle
        inspector.vector_check.setChecked(False)
        self.assertFalse(inspector.canvas.show_vectors)
        inspector.vector_check.setChecked(True)
        self.assertTrue(inspector.canvas.show_vectors)

        # Zoom buttons
        z0 = inspector.canvas.zoom
        inspector.zoom_in_btn.click()
        self.assertGreater(inspector.canvas.zoom, z0)
        inspector.zoom_out_btn.click()
        self.assertAlmostEqual(inspector.canvas.zoom, z0, places=1)


if __name__ == "__main__":
    unittest.main()
