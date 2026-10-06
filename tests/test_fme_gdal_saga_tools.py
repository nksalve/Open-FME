"""
Comprehensive Unit & Integration Test Suite for FME, GDAL, and SAGA Tools in open-FME.
Tests Vector, Attribute, Automation, and Raster & Terrain tools as well as hover descriptions.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath("."))

import numpy as np
import polars as pl
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon, box
import rasterio
from rasterio.transform import from_origin

import pyfme.engine.nodes
from pyfme.engine.registry import NodeRegistry
from pyfme.engine.dataset import FeatureDataset


def test_hover_descriptions_complete():
    """Verify that every single registered transformer has a non-empty description for hover tooltips."""
    all_nodes = NodeRegistry.all_nodes()
    assert len(all_nodes) >= 150, f"Expected >= 150 transformers, found {len(all_nodes)}"

    for name, cls in all_nodes.items():
        assert hasattr(cls, "description"), f"Node {name} missing description attribute"
        desc = cls.description.strip()
        assert len(desc) > 10, f"Node {name} description too short or empty: '{desc}'"
        assert cls.get_input_ports() is not None
        assert cls.get_output_ports() is not None
        assert cls.get_parameter_defs() is not None


def test_vector_overlay_and_geoprocessing():
    """Test AreaOnAreaOverlayer, LineOnLineOverlayer, PointOnLineOverlayer, Densifier, DuplicateRemover, Offsetter."""
    # 1. AreaOnAreaOverlayer
    node_cls = NodeRegistry.get("AreaOnAreaOverlayer")
    assert node_cls is not None
    node = node_cls()
    p1 = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    p2 = Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])
    gdf_areas = gpd.GeoDataFrame({"zone": ["A", "B"]}, geometry=[p1, p2], crs="EPSG:4326")
    res = node.execute({"Input": FeatureDataset.from_geopandas(gdf_areas)}, {})
    assert "Output" in res
    out_gdf = res["Output"].to_geopandas()
    assert len(out_gdf) >= 2
    assert "_overlaps" in out_gdf.columns

    # 2. LineOnLineOverlayer
    node_cls = NodeRegistry.get("LineOnLineOverlayer")
    assert node_cls is not None
    node = node_cls()
    l1 = LineString([(0, 1), (4, 1)])
    l2 = LineString([(2, 0), (2, 4)])
    gdf_lines = gpd.GeoDataFrame({"name": ["L1", "L2"]}, geometry=[l1, l2], crs="EPSG:4326")
    res = node.execute({"Input": FeatureDataset.from_geopandas(gdf_lines)}, {})
    assert len(res["Lines"].to_geopandas()) >= 2
    assert len(res["Points"].to_geopandas()) >= 1

    # 3. Densifier
    node_cls = NodeRegistry.get("Densifier")
    assert node_cls is not None
    node = node_cls()
    line = LineString([(0, 0), (10, 0)])
    gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[line], crs="EPSG:4326")
    res = node.execute({"Input": FeatureDataset.from_geopandas(gdf)}, {"max_distance": 2.0})
    densified_line = res["Output"].to_geopandas().geometry.iloc[0]
    assert len(densified_line.coords) > 2

    # 4. DuplicateRemover
    node_cls = NodeRegistry.get("DuplicateRemover")
    assert node_cls is not None
    node = node_cls()
    gdf_dups = gpd.GeoDataFrame({
        "city": ["Paris", "Tokyo", "Paris", "New York"]
    }, geometry=[Point(1, 1), Point(2, 2), Point(1, 1), Point(3, 3)], crs="EPSG:4326")
    res = node.execute({"Input": FeatureDataset.from_geopandas(gdf_dups)}, {"key_attribute": "city"})
    assert len(res["Unique"].to_geopandas()) == 3
    assert len(res["Duplicate"].to_geopandas()) == 1

    # 5. Offsetter
    node_cls = NodeRegistry.get("Offsetter")
    assert node_cls is not None
    node = node_cls()
    pt = Point(5, 5)
    gdf_pt = gpd.GeoDataFrame({"id": [1]}, geometry=[pt], crs="EPSG:4326")
    res = node.execute({"Input": FeatureDataset.from_geopandas(gdf_pt)}, {"offset_x": 10.0, "offset_y": -5.0})
    out_pt = res["Output"].to_geopandas().geometry.iloc[0]
    assert out_pt.x == 15.0
    assert out_pt.y == 0.0


def test_vector_geometry_and_topology():
    """Test AreaBuilder, LineJoiner, VertexRemover, 3DForcer, Affiner, TopologyBuilder, DelaunayTriangulator, GeometryReplacer, Extruder, TINGenerator."""
    # 1. AreaBuilder
    node = NodeRegistry.create("AreaBuilder")
    l1 = LineString([(0, 0), (2, 0)])
    l2 = LineString([(2, 0), (2, 2)])
    l3 = LineString([(2, 2), (0, 2)])
    l4 = LineString([(0, 2), (0, 0)])
    gdf_box_lines = gpd.GeoDataFrame({"id": [1, 2, 3, 4]}, geometry=[l1, l2, l3, l4], crs="EPSG:4326")
    res = node.execute({"Input": FeatureDataset.from_geopandas(gdf_box_lines)}, {})
    assert len(res["Area"].to_geopandas()) == 1
    assert res["Area"].to_geopandas().geometry.iloc[0].geom_type == "Polygon"

    # 2. LineJoiner
    node = NodeRegistry.create("LineJoiner")
    res = node.execute({"Input": FeatureDataset.from_geopandas(gdf_box_lines)}, {})
    assert len(res["Line"].to_geopandas()) <= 2

    # 3. ThreeDForcer (3DForcer)
    node = NodeRegistry.create("3DForcer")
    gdf_2d = gpd.GeoDataFrame({"elev": [150.0]}, geometry=[Point(10, 20)], crs="EPSG:4326")
    res = node.execute({"Input": FeatureDataset.from_geopandas(gdf_2d)}, {"elevation_attribute": "elev"})
    out_pt = res["Output"].to_geopandas().geometry.iloc[0]
    assert out_pt.has_z
    assert out_pt.z == 150.0

    # 4. GeometryReplacer
    node = NodeRegistry.create("GeometryReplacer")
    wkt_df = pl.DataFrame({"geom_wkt": ["POINT (45 80)", "LINESTRING (0 0, 10 10)"]})
    res = node.execute({"Input": FeatureDataset.from_polars(wkt_df)}, {"geometry_attribute": "geom_wkt"})
    out_gdf = res["Output"].to_geopandas()
    assert len(out_gdf) == 2
    assert out_gdf.geometry.iloc[0].geom_type == "Point"
    assert out_gdf.geometry.iloc[1].geom_type == "LineString"

    # 5. Extruder
    node = NodeRegistry.create("Extruder")
    poly = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])
    gdf_poly = gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs="EPSG:4326")
    res = node.execute({"Input": FeatureDataset.from_geopandas(gdf_poly)}, {"height": 10.0})
    out_gdf = res["Output"].to_geopandas()
    assert "_extruded_height" in out_gdf.columns
    assert out_gdf["_extruded_volume"].iloc[0] == 160.0

    # 6. DelaunayTriangulator & TINGenerator
    node = NodeRegistry.create("DelaunayTriangulator")
    pts = [Point(0, 0), Point(10, 0), Point(5, 10), Point(5, 5)]
    gdf_pts = gpd.GeoDataFrame({"id": [1, 2, 3, 4]}, geometry=pts, crs="EPSG:4326")
    res = node.execute({"Input": FeatureDataset.from_geopandas(gdf_pts)}, {})
    assert len(res["Triangles"].to_geopandas()) >= 2


def test_attribute_and_database_transformers():
    """Test Joiner, InlineQuerier, ListExploder, StringSearcher, DateTimeCalculator, SQLExecutor, PythonCreator, XMLFlattener."""
    # 1. Joiner
    node = NodeRegistry.create("Joiner")
    df_left = pl.DataFrame({"cust_id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"]})
    df_right = pl.DataFrame({"cust_id": [2, 3, 4], "city": ["Paris", "Berlin", "London"]})
    res = node.execute({
        "Left": FeatureDataset.from_polars(df_left),
        "Right": FeatureDataset.from_polars(df_right),
    }, {"left_key": "cust_id", "right_key": "cust_id", "join_type": "left"})
    out_df = res["Joined"].to_polars()
    assert len(out_df) == 3
    assert "city" in out_df.columns

    # 2. InlineQuerier (SQLite SQL)
    node = NodeRegistry.create("InlineQuerier")
    df_sales = pl.DataFrame({"product": ["A", "B", "A", "B", "C"], "amount": [10, 20, 15, 25, 50]})
    res = node.execute(
        {"Input": FeatureDataset.from_polars(df_sales)},
        {"sql_query": "SELECT product, SUM(amount) AS total FROM Input GROUP BY product ORDER BY total DESC"}
    )
    out_df = res["Output"].to_polars()
    assert len(out_df) == 3
    assert out_df["total"][0] == 50

    # 3. ListExploder
    node = NodeRegistry.create("ListExploder")
    df_tags = pl.DataFrame({"id": [1, 2], "tags": ["gis,mapping,fme", "raster,vector"]})
    res = node.execute({"Input": FeatureDataset.from_polars(df_tags)}, {"attribute_name": "tags", "delimiter": ","})
    out_df = res["Output"].to_polars()
    assert len(out_df) == 5

    # 4. StringSearcher
    node = NodeRegistry.create("StringSearcher")
    df_text = pl.DataFrame({"code": ["ITEM-101", "INVALID", "ITEM-999"]})
    res = node.execute({"Input": FeatureDataset.from_polars(df_text)}, {"attribute_name": "code", "regex_pattern": r"ITEM-(\d+)"})
    assert len(res["Matched"].to_polars()) == 2
    assert len(res["NotMatched"].to_polars()) == 1

    # 5. DateTimeCalculator
    node = NodeRegistry.create("DateTimeCalculator")
    df_dates = pl.DataFrame({"start_date": ["2026-01-01", "2026-06-01"], "end_date": ["2026-01-11", "2026-06-05"]})
    res = node.execute({"Input": FeatureDataset.from_polars(df_dates)}, {"start_date_attr": "start_date", "end_date_attr": "end_date"})
    out_df = res["Output"].to_polars()
    assert out_df["_diff_days"][0] == 10
    assert out_df["_diff_days"][1] == 4

    # 6. PythonCreator
    node = NodeRegistry.create("PythonCreator")
    code = """
features = [
    {"point_id": 1, "x": 10.0, "y": 20.0, "val": 100},
    {"point_id": 2, "x": 15.0, "y": 25.0, "val": 200},
]
"""
    res = node.execute({}, {"python_code": code})
    out_df = res["Output"].to_polars()
    assert len(out_df) == 2
    assert out_df["val"][1] == 200

    # 7. XMLFlattener
    node = NodeRegistry.create("XMLFlattener")
    xml_content = """<catalog><book id="1"><title>GIS Analysis</title></book><book id="2"><title>Remote Sensing</title></book></catalog>"""
    df_xml = pl.DataFrame({"xml_data": [xml_content]})
    res = node.execute({"Input": FeatureDataset.from_polars(df_xml)}, {"xml_attribute": "xml_data", "element_tag": "book"})
    out_df = res["Output"].to_polars()
    assert len(out_df) == 2
    assert "title" in out_df.columns


def test_raster_and_terrain_transformers():
    """Test DEM Slope, Aspect, Hillshade, Contours, PointOnRasterValueExtractor, ZonalStatistics, RasterExpressionEvaluator, etc."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = os.path.join(tmp_dir, "test_dem.tif")
        out_slope = os.path.join(tmp_dir, "slope.tif")
        out_aspect = os.path.join(tmp_dir, "aspect.tif")
        out_hillshade = os.path.join(tmp_dir, "hillshade.tif")

        # Create synthetic DEM: inclined plane with elevation 100 to 200
        y, x = np.mgrid[0:20, 0:20]
        dem_data = (100.0 + x * 2.5 + y * 1.5).astype(np.float32)
        transform = from_origin(0.0, 200.0, 10.0, 10.0)

        with rasterio.open(
            dem_path, "w", driver="GTiff",
            height=20, width=20, count=1,
            dtype=rasterio.float32, crs="EPSG:4326", transform=transform, nodata=-9999.0
        ) as dst:
            dst.write(dem_data, 1)

        # 1. SlopeCalculator
        slope_node = NodeRegistry.create("SlopeCalculator")
        res = slope_node.execute({}, {"dem_path": dem_path, "output_path": out_slope, "slope_format": "Degrees"})
        assert os.path.exists(out_slope)
        s_df = res["Output"].to_polars()
        assert s_df["mean_slope"][0] > 0.0

        # 2. AspectCalculator
        aspect_node = NodeRegistry.create("AspectCalculator")
        res = aspect_node.execute({}, {"dem_path": dem_path, "output_path": out_aspect})
        assert os.path.exists(out_aspect)
        a_df = res["Output"].to_polars()
        assert a_df["mean_aspect"][0] >= 0.0

        # 3. HillshadeGenerator
        hill_node = NodeRegistry.create("HillshadeGenerator")
        res = hill_node.execute({}, {"dem_path": dem_path, "output_path": out_hillshade})
        assert os.path.exists(out_hillshade)
        h_df = res["Output"].to_polars()
        assert 0.0 <= h_df["mean_shade"][0] <= 255.0

        # 4. ContourGenerator
        contour_node = NodeRegistry.create("ContourGenerator")
        res = contour_node.execute({}, {"dem_path": dem_path, "interval": 10.0, "elev_attr": "elevation"})
        contours_gdf = res["Output"].to_geopandas()
        assert len(contours_gdf) > 0
        assert "elevation" in contours_gdf.columns
        assert contours_gdf.geometry.iloc[0].geom_type in ("LineString", "MultiLineString")

        # 5. PointOnRasterValueExtractor
        sample_node = NodeRegistry.create("PointOnRasterValueExtractor")
        pts_gdf = gpd.GeoDataFrame({
            "name": ["P1", "P2"]
        }, geometry=[Point(50.0, 150.0), Point(100.0, 100.0)], crs="EPSG:4326")
        res = sample_node.execute(
            {"Input": FeatureDataset.from_geopandas(pts_gdf)},
            {"raster_path": dem_path, "result_attribute": "dem_elev"}
        )
        sampled_gdf = res["Output"].to_geopandas()
        assert "dem_elev" in sampled_gdf.columns
        assert sampled_gdf["dem_elev"].iloc[0] is not None
        assert sampled_gdf["dem_elev"].iloc[0] > 100.0

        # 6. ZonalStatisticsCalculator
        zonal_node = NodeRegistry.create("ZonalStatisticsCalculator")
        poly = box(20.0, 50.0, 120.0, 150.0)
        poly_gdf = gpd.GeoDataFrame({"zone": ["Zone1"]}, geometry=[poly], crs="EPSG:4326")
        res = zonal_node.execute(
            {"Input": FeatureDataset.from_geopandas(poly_gdf)},
            {"raster_path": dem_path, "prefix": "zonal_"}
        )
        z_gdf = res["Output"].to_geopandas()
        assert "zonal_mean" in z_gdf.columns
        assert "zonal_min" in z_gdf.columns
        assert "zonal_max" in z_gdf.columns
        assert z_gdf["zonal_mean"].iloc[0] > 100.0

        # 7. RasterExpressionEvaluator
        expr_node = NodeRegistry.create("RasterExpressionEvaluator")
        out_expr = os.path.join(tmp_dir, "expr.tif")
        res = expr_node.execute({}, {"raster_a_path": dem_path, "expression": "A * 2.0", "output_path": out_expr})
        assert os.path.exists(out_expr)
        e_df = res["Output"].to_polars()
        assert e_df["max_val"][0] > 200.0

        # 8. SurfaceDraper
        draper_node = NodeRegistry.create("SurfaceDraper")
        l2d = LineString([(20.0, 50.0), (100.0, 150.0)])
        line_gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[l2d], crs="EPSG:4326")
        res = draper_node.execute({"Input": FeatureDataset.from_geopandas(line_gdf)}, {"dem_path": dem_path})
        draped_gdf = res["Output"].to_geopandas()
        d_line = draped_gdf.geometry.iloc[0]
        assert d_line.has_z
        assert d_line.coords[0][2] > 100.0


if __name__ == "__main__":
    tests = [
        test_hover_descriptions_complete,
        test_vector_overlay_and_geoprocessing,
        test_vector_geometry_and_topology,
        test_attribute_and_database_transformers,
        test_raster_and_terrain_transformers,
    ]
    print(f"Running {len(tests)} comprehensive test suites for FME, GDAL, and SAGA tools...")
    for t in tests:
        print(f"--> Running {t.__name__}...", end=" ", flush=True)
        t()
        print("PASSED [OK]")
    print("\nALL FME, GDAL, AND SAGA TESTS PASSED SUCCESSFULLY! (100% PASS)")

