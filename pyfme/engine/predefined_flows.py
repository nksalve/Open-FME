"""
Predefined Workflows and Templates for open-FME Workbench.
Provides turnkey, production-grade spatial and tabular ETL pipelines
with visual nodes, bookmarks, and sticky note annotations.
"""

from __future__ import annotations
import os
import json
from typing import Dict, List, Any, Optional

from pyfme.engine.graph import WorkflowGraph
from pyfme.engine.registry import NodeRegistry


def get_sample_data_dir() -> str:
    """Returns absolute path to sample_data directory."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "sample_data")


def create_customer_spatial_profiling_flow() -> WorkflowGraph:
    """
    Template 1: Customer Spatial Profiling & Buffering
    Reads customer records (CSV), filters active accounts, geocodes points,
    buffers service delivery radii, and exports to GeoJSON.
    """
    data_dir = get_sample_data_dir()
    csv_path = os.path.join(data_dir, "customers.csv")
    out_path = os.path.join(data_dir, "active_customers_buffered.geojson")

    graph = WorkflowGraph("01_Customer_Spatial_Profiling")

    # 1. CSV Reader
    reader = NodeRegistry.create("CSVReader")
    reader.set_param("file_path", csv_path)
    reader.set_param("delimiter", ",")
    reader.set_param("has_header", True)
    reader.x, reader.y = 100.0, 180.0
    graph.add_node(reader)

    # 2. Tester (Filter status == 'active')
    tester = NodeRegistry.create("Tester")
    tester.set_param("attribute", "status")
    tester.set_param("operator", "=")
    tester.set_param("test_value", "active")
    tester.x, tester.y = 360.0, 180.0
    graph.add_node(tester)

    # 3. Vertex Creator (lon, lat -> Point)
    vertex = NodeRegistry.create("VertexCreator")
    vertex.set_param("x_attribute", "lon")
    vertex.set_param("y_attribute", "lat")
    vertex.set_param("crs", "EPSG:4326")
    vertex.x, vertex.y = 620.0, 140.0
    graph.add_node(vertex)

    # 4. Bufferer (0.25 degree radius)
    bufferer = NodeRegistry.create("Bufferer")
    bufferer.set_param("buffer_distance", 0.25)
    bufferer.set_param("resolution", 16)
    bufferer.x, bufferer.y = 880.0, 140.0
    graph.add_node(bufferer)

    # 5. GeoJSON Writer
    writer = NodeRegistry.create("GeoJSONWriter")
    writer.set_param("file_path", out_path)
    writer.x, writer.y = 1140.0, 140.0
    graph.add_node(writer)

    # Connections
    graph.connect(reader.id, "Output", tester.id, "Input")
    graph.connect(tester.id, "Passed", vertex.id, "Input")
    graph.connect(vertex.id, "Output", bufferer.id, "Input")
    graph.connect(bufferer.id, "Output", writer.id, "Input")

    # Bookmarks
    graph.bookmarks = [
        {
            "title": "1. Ingestion & Quality Filter",
            "rect": [60.0, 100.0, 520.0, 240.0],
            "color": "#1976d2",
            "pos": [60.0, 100.0],
        },
        {
            "title": "2. Geocoding & Buffer Analysis",
            "rect": [580.0, 60.0, 520.0, 280.0],
            "color": "#7b1fa2",
            "pos": [580.0, 60.0],
        },
        {
            "title": "3. Spatial Export",
            "rect": [1110.0, 60.0, 250.0, 280.0],
            "color": "#388e3c",
            "pos": [1110.0, 60.0],
        },
    ]

    # Annotations
    graph.annotations = [
        {
            "text": "Extracts customer addresses from CSV and isolates only 'active' status accounts.",
            "pos": [100.0, 360.0],
        },
        {
            "text": "Converts lon/lat coordinates to WGS84 point geometries and calculates a 0.25-deg buffer area.",
            "pos": [620.0, 360.0],
        },
    ]

    return graph


def create_regional_spatial_overlay_flow() -> WorkflowGraph:
    """
    Template 2: Regional Point-in-Polygon Overlay & Analysis
    Performs a 2-stream spatial join between Customer points and Region boundaries,
    tagging each customer with territory name and growth rate.
    """
    data_dir = get_sample_data_dir()
    csv_path = os.path.join(data_dir, "customers.csv")
    regions_path = os.path.join(data_dir, "regions.geojson")
    out_path = os.path.join(data_dir, "customers_by_region.geojson")

    graph = WorkflowGraph("02_Regional_Spatial_Overlay")

    # Stream 1: Customers CSV
    r_cust = NodeRegistry.create("CSVReader")
    r_cust.set_param("file_path", csv_path)
    r_cust.x, r_cust.y = 80.0, 120.0
    graph.add_node(r_cust)

    v_cust = NodeRegistry.create("VertexCreator")
    v_cust.set_param("x_attribute", "lon")
    v_cust.set_param("y_attribute", "lat")
    v_cust.set_param("crs", "EPSG:4326")
    v_cust.x, v_cust.y = 340.0, 120.0
    graph.add_node(v_cust)

    # Stream 2: Region Polygons
    r_reg = NodeRegistry.create("GeoJSONReader")
    r_reg.set_param("file_path", regions_path)
    r_reg.x, r_reg.y = 80.0, 320.0
    graph.add_node(r_reg)

    # Spatial Join / Overlay
    overlay = NodeRegistry.create("PointOnAreaOverlayer")
    overlay.x, overlay.y = 620.0, 200.0
    graph.add_node(overlay)

    # Output Writer
    writer = NodeRegistry.create("GeoJSONWriter")
    writer.set_param("file_path", out_path)
    writer.x, writer.y = 900.0, 200.0
    graph.add_node(writer)

    # Connections
    graph.connect(r_cust.id, "Output", v_cust.id, "Input")
    graph.connect(v_cust.id, "Output", overlay.id, "Point")
    graph.connect(r_reg.id, "Output", overlay.id, "Area")
    graph.connect(overlay.id, "Point", writer.id, "Input")

    # Bookmarks
    graph.bookmarks = [
        {
            "title": "Stream A: Customer Point Layer",
            "rect": [60.0, 60.0, 500.0, 190.0],
            "color": "#0288d1",
            "pos": [60.0, 60.0],
        },
        {
            "title": "Stream B: Territory Boundary Layer",
            "rect": [60.0, 270.0, 280.0, 170.0],
            "color": "#f57c00",
            "pos": [60.0, 270.0],
        },
        {
            "title": "Point-in-Polygon Spatial Association",
            "rect": [580.0, 130.0, 520.0, 230.0],
            "color": "#43a047",
            "pos": [580.0, 130.0],
        },
    ]

    # Annotations
    graph.annotations = [
        {
            "text": "Spatial point-in-polygon overlay: transfers region_name, zone_code, and target_growth to each customer point.",
            "pos": [580.0, 380.0],
        }
    ]

    return graph


def create_attribute_cleansing_flow() -> WorkflowGraph:
    """
    Template 3: Attribute Cleansing & Standardization
    Cleans tabular records, filters valid spend, sorts highest value accounts,
    and exports a sanitized CSV.
    """
    data_dir = get_sample_data_dir()
    csv_path = os.path.join(data_dir, "customers.csv")
    out_path = os.path.join(data_dir, "cleansed_customers.csv")

    graph = WorkflowGraph("03_Attribute_Cleansing_Pipeline")

    # 1. CSV Reader
    reader = NodeRegistry.create("CSVReader")
    reader.set_param("file_path", csv_path)
    reader.x, reader.y = 80.0, 180.0
    graph.add_node(reader)

    # 2. Quality Filter (annual_spend > 0)
    tester = NodeRegistry.create("Tester")
    tester.set_param("attribute", "annual_spend")
    tester.set_param("operator", ">")
    tester.set_param("test_value", "0")
    tester.x, tester.y = 340.0, 180.0
    graph.add_node(tester)

    # 3. String Replacer (Normalize pending status)
    replacer = NodeRegistry.create("StringReplacer")
    replacer.set_param("attribute", "status")
    replacer.set_param("search_value", "pending")
    replacer.set_param("replace_value", "under_review")
    replacer.x, replacer.y = 600.0, 180.0
    graph.add_node(replacer)

    # 4. Sorter (Rank by annual_spend descending)
    sorter = NodeRegistry.create("Sorter")
    sorter.set_param("sort_by", "annual_spend")
    sorter.set_param("descending", True)
    sorter.x, sorter.y = 860.0, 180.0
    graph.add_node(sorter)

    # 5. CSV Writer
    writer = NodeRegistry.create("CSVWriter")
    writer.set_param("file_path", out_path)
    writer.set_param("delimiter", ",")
    writer.x, writer.y = 1120.0, 180.0
    graph.add_node(writer)

    # Connections
    graph.connect(reader.id, "Output", tester.id, "Input")
    graph.connect(tester.id, "Passed", replacer.id, "Input")
    graph.connect(replacer.id, "Output", sorter.id, "Input")
    graph.connect(sorter.id, "Output", writer.id, "Input")

    # Bookmarks
    graph.bookmarks = [
        {
            "title": "Tabular ETL & Normalization Pipeline",
            "rect": [50.0, 110.0, 1280.0, 240.0],
            "color": "#00897b",
            "pos": [50.0, 110.0],
        }
    ]

    # Annotations
    graph.annotations = [
        {
            "text": "Filters out invalid rows, updates status tokens, and orders customer accounts by revenue descending.",
            "pos": [340.0, 370.0],
        }
    ]

    return graph


def create_bounding_box_and_centroids_flow() -> WorkflowGraph:
    """
    Template 4: Bounding Box Extents & Centroid Extraction
    Calculates geographic bounding boxes, extracts polygon centroids,
    and captures coordinate attributes.
    """
    data_dir = get_sample_data_dir()
    regions_path = os.path.join(data_dir, "regions.geojson")
    out_path = os.path.join(data_dir, "region_centroids.geojson")

    graph = WorkflowGraph("04_Bounding_Box_and_Centroids")

    # 1. GeoJSON Reader
    reader = NodeRegistry.create("GeoJSONReader")
    reader.set_param("file_path", regions_path)
    reader.x, reader.y = 80.0, 180.0
    graph.add_node(reader)

    # 2. Bounding Box Replacer
    bbox = NodeRegistry.create("BoundingBoxReplacer")
    bbox.x, bbox.y = 340.0, 180.0
    graph.add_node(bbox)

    # 3. Centroid Extractor
    centroid = NodeRegistry.create("CentroidExtractor")
    centroid.x, centroid.y = 600.0, 180.0
    graph.add_node(centroid)

    # 4. Coordinate Extractor
    coord = NodeRegistry.create("CoordinateExtractor")
    coord.set_param("x_attribute", "centroid_x")
    coord.set_param("y_attribute", "centroid_y")
    coord.x, coord.y = 860.0, 180.0
    graph.add_node(coord)

    # 5. GeoJSON Writer
    writer = NodeRegistry.create("GeoJSONWriter")
    writer.set_param("file_path", out_path)
    writer.x, writer.y = 1120.0, 180.0
    graph.add_node(writer)

    # Connections
    graph.connect(reader.id, "Output", bbox.id, "Input")
    graph.connect(bbox.id, "Output", centroid.id, "Input")
    graph.connect(centroid.id, "Output", coord.id, "Input")
    graph.connect(coord.id, "Output", writer.id, "Input")

    # Bookmarks
    graph.bookmarks = [
        {
            "title": "Geometric Transformation Pipeline",
            "rect": [50.0, 110.0, 1280.0, 240.0],
            "color": "#6d4c41",
            "pos": [50.0, 110.0],
        }
    ]

    # Annotations
    graph.annotations = [
        {
            "text": "Computes rectangular bounding envelope, calculates center of gravity centroid, and appends X/Y coordinates.",
            "pos": [340.0, 370.0],
        }
    ]

    return graph


def create_html_reporting_flow() -> WorkflowGraph:
    """
    Template 5: Executive Summary & HTML Report Dashboard
    Aggregates high-value accounts and creates a standalone styled HTML report.
    """
    data_dir = get_sample_data_dir()
    csv_path = os.path.join(data_dir, "customers.csv")
    out_path = os.path.join(data_dir, "report.html")

    graph = WorkflowGraph("05_HTML_Reporting_Pipeline")

    # 1. CSV Reader
    reader = NodeRegistry.create("CSVReader")
    reader.set_param("file_path", csv_path)
    reader.x, reader.y = 80.0, 180.0
    graph.add_node(reader)

    # 2. Tester (Filter top tier customers >= 25,000)
    tester = NodeRegistry.create("Tester")
    tester.set_param("attribute", "annual_spend")
    tester.set_param("operator", ">=")
    tester.set_param("test_value", "25000")
    tester.x, tester.y = 340.0, 180.0
    graph.add_node(tester)

    # 3. HTML Report Generator
    report_gen = NodeRegistry.create("HTMLReportGenerator")
    report_gen.set_param("report_title", "Top Customer Accounts Executive Briefing")
    report_gen.set_param("style", "Modern Card Table")
    report_gen.x, report_gen.y = 600.0, 180.0
    graph.add_node(report_gen)

    # 4. HTML Layouter
    layouter = NodeRegistry.create("HTMLLayouter")
    layouter.set_param("page_title", "Executive Financial Summary")
    layouter.set_param("output_file", out_path)
    layouter.x, layouter.y = 860.0, 180.0
    graph.add_node(layouter)

    # Connections
    graph.connect(reader.id, "Output", tester.id, "Input")
    graph.connect(tester.id, "Passed", report_gen.id, "Input")
    graph.connect(report_gen.id, "Output", layouter.id, "Input")

    # Bookmarks
    graph.bookmarks = [
        {
            "title": "Business Intelligence & Report Generation",
            "rect": [50.0, 110.0, 1030.0, 240.0],
            "color": "#5c6bc0",
            "pos": [50.0, 110.0],
        }
    ]

    # Annotations
    graph.annotations = [
        {
            "text": "Filters top revenue accounts and renders a polished web-ready HTML summary dashboard.",
            "pos": [340.0, 370.0],
        }
    ]

    return graph


PREDEFINED_FLOW_BUILDERS = [
    {
        "id": "customer_spatial_profiling",
        "title": "Customer Spatial Profiling & Buffering",
        "filename": "01_customer_spatial_profiling.fpy",
        "category": "Spatial Analysis",
        "icon": "📍",
        "accent": "#1976d2",
        "description": "Ingests customer CSV records, filters active status, geocodes points, calculates a 0.25-deg buffer radius, and exports to GeoJSON.",
        "builder": create_customer_spatial_profiling_flow,
    },
    {
        "id": "regional_spatial_overlay",
        "title": "Regional Point-in-Polygon Overlay",
        "filename": "02_regional_spatial_overlay.fpy",
        "category": "Spatial Relationships",
        "icon": "🗺️",
        "accent": "#7b1fa2",
        "description": "Performs dual-stream point-in-polygon overlay joining customer points with region territories to tag territory codes and growth targets.",
        "builder": create_regional_spatial_overlay_flow,
    },
    {
        "id": "attribute_cleansing_pipeline",
        "title": "Attribute Cleansing & Standardization",
        "filename": "03_attribute_cleansing_pipeline.fpy",
        "category": "Tabular ETL",
        "icon": "🧹",
        "accent": "#00897b",
        "description": "Validates rows, standardizes text tokens, ranks customers by annual spend descending, and exports a cleansed CSV.",
        "builder": create_attribute_cleansing_flow,
    },
    {
        "id": "bounding_box_and_centroids",
        "title": "Bounding Box Extents & Centroid Extraction",
        "filename": "04_bounding_box_and_centroids.fpy",
        "category": "Geometry Processing",
        "icon": "📐",
        "accent": "#e65100",
        "description": "Ingests region polygons, calculates bounding envelope rectangles, computes center-of-gravity centroids, and extracts coordinates.",
        "builder": create_bounding_box_and_centroids_flow,
    },
    {
        "id": "html_reporting_pipeline",
        "title": "Executive Summary & HTML Report Dashboard",
        "filename": "05_html_reporting_pipeline.fpy",
        "category": "Business Intelligence",
        "icon": "📊",
        "accent": "#5c6bc0",
        "description": "Filters enterprise accounts (spend >= $25k), compiles KPI statistics, and outputs a styled HTML report.",
        "builder": create_html_reporting_flow,
    },
]


def ensure_predefined_flow_files():
    """Generates all predefined .fpy template files in sample_data/predefined_flows/."""
    data_dir = get_sample_data_dir()
    templates_dir = os.path.join(data_dir, "predefined_flows")
    os.makedirs(templates_dir, exist_ok=True)

    for item in PREDEFINED_FLOW_BUILDERS:
        fpath = os.path.join(templates_dir, item["filename"])
        # Always generate or update if missing
        graph = item["builder"]()
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(graph.to_dict(), f, indent=2)


def get_predefined_flows() -> List[Dict[str, Any]]:
    """Returns the list of available predefined workflow metadata."""
    data_dir = get_sample_data_dir()
    templates_dir = os.path.join(data_dir, "predefined_flows")
    res = []
    for item in PREDEFINED_FLOW_BUILDERS:
        fpath = os.path.join(templates_dir, item["filename"])
        entry = dict(item)
        entry["file_path"] = fpath
        res.append(entry)
    return res
