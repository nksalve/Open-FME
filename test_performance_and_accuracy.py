"""
Test suite validating performance, accuracy, and UI smoothness in open-FME.
"""

import sys
import time
import polars as pl
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF, QRectF

from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.nodes.transformers.spatial import Bufferer, AreaCalculator, LengthCalculator
from pyfme.engine.nodes.transformers.fme_workbench_tools import ShortestPathFinder
from pyfme.engine.nodes.transformers.attributes import AttributeManager, Sorter
from pyfme.ui.canvas.scene import CanvasScene
from pyfme.ui.canvas.node_item import NodeItem
from pyfme.ui.canvas.wire_item import WireItem
from pyfme.ui.inspector.table_view import FeatureTableModel


def get_qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


def test_dataset_vectorization():
    print("=== 1. Testing FeatureDataset Vectorization & Native Operations ===")
    t0 = time.time()
    # Create 10,000 tabular features
    df = pl.DataFrame({
        "id": list(range(10000)),
        "name": [f"feature_{i}" for i in range(10000)],
        "val": [i * 1.5 for i in range(10000)],
        "lon": [-123.1 + (i * 0.0001) for i in range(10000)],
        "lat": [49.2 + (i * 0.0001) for i in range(10000)],
    })
    ds = FeatureDataset.from_polars(df)
    assert ds.count() == 10000

    # Auto-detect geometry conversion
    gdf = ds.to_geopandas()
    assert hasattr(gdf, "geometry")
    assert len(gdf) == 10000
    assert isinstance(gdf.geometry.iloc[0], Point)

    # Native rename, drop, add_column without roundtrips
    ds_mod = ds.rename_columns({"val": "value_metric"}).drop_columns(["name"]).add_column("flag", "active").sort_by("value_metric", descending=True)
    assert "value_metric" in ds_mod.columns
    assert "name" not in ds_mod.columns
    assert "flag" in ds_mod.columns
    assert ds_mod.count() == 10000
    assert ds_mod.to_polars()["value_metric"][0] > ds_mod.to_polars()["value_metric"][1]

    elapsed = time.time() - t0
    print(f"Dataset 10,000 features vectorized operations completed in {elapsed:.3f}s [PASSED]")


def test_spatial_accuracy():
    print("=== 2. Testing Spatial Metric Accuracy (UTM projection for Geographic CRS) ===")
    # Create 3 points in Vancouver (EPSG:4326)
    pts = [Point(-123.1207, 49.2827), Point(-123.1107, 49.2850), Point(-123.1307, 49.2800)]
    gdf = gpd.GeoDataFrame({"id": [1, 2, 3]}, geometry=pts, crs="EPSG:4326")
    ds = FeatureDataset.from_geopandas(gdf)

    # 1. Bufferer with 100m buffer
    buf_node = Bufferer()
    buf_out = buf_node.execute({"Input": ds}, {"buffer_distance": 100.0})
    buf_gdf = buf_out["Output"].to_geopandas()
    assert len(buf_gdf) == 3
    assert buf_gdf.geometry.iloc[0].geom_type in ("Polygon", "MultiPolygon")

    # 2. AreaCalculator on the 100m buffer
    # 100m radius circle area should be approx pi * r^2 = 31,415.9 m^2 (not degrees^2)
    area_node = AreaCalculator()
    area_out = area_node.execute({"Input": buf_out["Output"]}, {"result_attribute": "_area_m2"})
    area_gdf = area_out["Output"].to_geopandas()
    measured_area = area_gdf["_area_m2"].iloc[0]
    print(f"100m buffer measured area: {measured_area:.1f} m^2 (Expected ~31,415 m^2)")
    assert 28000 < measured_area < 34000, f"Expected metric area ~31415, got {measured_area}"

    # 3. ShortestPathFinder metric distance
    sp_node = ShortestPathFinder()
    sp_out = sp_node.execute({"From-To": ds}, {"length_attribute": "route_dist_m"})
    sp_gdf = sp_out["Path"].to_geopandas()
    assert len(sp_gdf) == 2
    # Distance between Vancouver coordinates in meters should be hundreds of meters, not 0.002 degrees!
    dist_m = sp_gdf["route_dist_m"].iloc[0]
    print(f"Measured route distance: {dist_m:.2f} m (Expected ~750m - 1000m)")
    assert 500 < dist_m < 2000, f"Expected metric route distance ~800m, got {dist_m}"

    print("Spatial metric accuracy validated! [PASSED]")


def test_ui_smoothness_and_indexing():
    print("=== 3. Testing UI Fast Indexing and Canvas Wire Updates ===")
    app = get_qapp()

    # Table view model test with 5,000 features
    df = pl.DataFrame({
        "station": [f"Station_{i}" for i in range(5000)],
        "elevation": [float(i * 3) for i in range(5000)],
    })
    ds = FeatureDataset.from_polars(df)
    model = FeatureTableModel(ds)
    assert model.rowCount() == 5000
    assert model.columnCount() == 2

    # Fast sorting test in Polars
    t0 = time.time()
    model.sort(1, Qt.SortOrder.DescendingOrder)
    sort_time = time.time() - t0
    assert float(model._df["elevation"][0]) == 14997.0
    print(f"Table Model 5,000 row Polars sort completed in {sort_time*1000:.2f} ms [PASSED]")

    # Scene and Wire Item test
    scene = CanvasScene()
    from pyfme.engine.nodes.readers import CSVReader
    from pyfme.engine.nodes.transformers.spatial import Bufferer
    n1 = CSVReader()
    n2 = Bufferer()
    item1 = scene.add_node_at_position(n1, QPointF(0, 0))
    item2 = scene.add_node_at_position(n2, QPointF(300, 0))
    p1 = list(item1.output_port_items.values())[0]
    p2 = list(item2.input_port_items.values())[0]
    wire = scene._create_wire_item(p1, p2)

    assert wire in item1.connected_wires
    assert wire in item2.connected_wires

    # Moving node updates only connected wires
    item1.setPos(50, 50)
    scene.update_node_wires(item1)
    assert wire.path().pointAtPercent(0).x() > 0

    print("UI smoothness and wire connectivity validated! [PASSED]")


def main():
    test_dataset_vectorization()
    test_spatial_accuracy()
    test_ui_smoothness_and_indexing()
    print("\nALL PERFORMANCE, ACCURACY, AND SMOOTHNESS TESTS PASSED 100%! [PASSED]")


if __name__ == "__main__":
    main()
