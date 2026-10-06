"""
QGIS-grade Vector Geometry Tools:
- ConvexHull (QGIS Convex Hull)
- Simplify (QGIS Simplify Geometries / Douglas-Peucker)
- Densify (QGIS Densify by Interval)
- MultipartToSingleparts (QGIS Multipart to Singleparts)
- PolygonsToLines (QGIS Polygons to Lines / Boundary)
- LinesToPolygons (QGIS Lines to Polygons)
- ExtractVertices (QGIS Extract Vertices)
- OrientedMinimumBoundingBox (QGIS Oriented Minimum Bounding Box)
- CreateGrid (QGIS Create Grid / Fishnet)
- RandomPointsInPolygon (QGIS Random Points in Polygon)
- VoronoiDiagram (QGIS Voronoi Polygons)
"""

from typing import Any, Dict, List
import numpy as np
import geopandas as gpd
from shapely.geometry import (
    Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon, box
)
from shapely import (
    convex_hull, simplify, segmentize, minimum_rotated_rectangle, voronoi_polygons
)
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class ConvexHull(BaseNode):
    """
    Computes the smallest convex polygon enclosing each geometry.
    Equivalent to QGIS 'Convex Hull'.
    """
    node_type = "ConvexHull"
    category = NodeCategory.SPATIAL
    description = "Computes the minimum convex polygon enclosing each feature (QGIS Convex Hull)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        gdf[gdf.geometry.name] = gdf.geometry.convex_hull
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class Simplify(BaseNode):
    """
    Simplifies line and polygon geometries using the Douglas-Peucker algorithm.
    Equivalent to QGIS 'Simplify Geometries'.
    """
    node_type = "Simplify"
    category = NodeCategory.SPATIAL
    description = "Simplifies geometries by reducing vertices with Douglas-Peucker (QGIS Simplify)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("tolerance", ParameterType.FLOAT, default=0.01, label="Simplification Tolerance"),
            ParameterDef("preserve_topology", ParameterType.BOOLEAN, default=True, label="Preserve Topology"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        tol = float(params.get("tolerance", 0.01))
        pres = bool(params.get("preserve_topology", True))

        gdf[gdf.geometry.name] = gdf.geometry.simplify(tolerance=tol, preserve_topology=pres)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class Densify(BaseNode):
    """
    Adds additional vertices along line or polygon segments by maximum distance interval.
    Equivalent to QGIS 'Densify by interval'.
    """
    node_type = "Densify"
    category = NodeCategory.SPATIAL
    description = "Adds intermediate vertices along segments based on max length (QGIS Densify)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("max_segment_length", ParameterType.FLOAT, default=0.1, label="Max Segment Length"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        max_len = float(params.get("max_segment_length", 0.1))

        gdf[gdf.geometry.name] = gdf.geometry.segmentize(max_segment_length=max_len)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class MultipartToSingleparts(BaseNode):
    """
    Explodes MultiPolygons, MultiLineStrings, and MultiPoints into individual single-part records.
    Equivalent to QGIS 'Multipart to singleparts' and FME 'Deaggregator'.
    """
    node_type = "MultipartToSingleparts"
    category = NodeCategory.SPATIAL
    description = "Explodes multipart geometries into individual single-part features (QGIS Multipart to Singleparts)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        exploded = gdf.explode(index_parts=False).reset_index(drop=True)
        return {"Output": FeatureDataset.from_geopandas(exploded)}


@NodeRegistry.register
class PolygonsToLines(BaseNode):
    """
    Extracts the exterior and interior boundary rings of polygons into LineStrings.
    Equivalent to QGIS 'Polygons to lines'.
    """
    node_type = "PolygonsToLines"
    category = NodeCategory.SPATIAL
    description = "Converts polygon boundaries into LineString features (QGIS Polygons to lines)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        gdf[gdf.geometry.name] = gdf.geometry.boundary
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class ExtractVertices(BaseNode):
    """
    Explodes line or polygon vertices into individual Point features,
    attaching '_vertex_index', '_x', '_y' attributes.
    Equivalent to QGIS 'Extract vertices'.
    """
    node_type = "ExtractVertices"
    category = NodeCategory.SPATIAL
    description = "Extracts all coordinate vertices into Point features (QGIS Extract vertices)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        rows = []

        for idx, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            coords = []
            if isinstance(geom, Point):
                coords = [(geom.x, geom.y)]
            elif isinstance(geom, LineString):
                coords = list(geom.coords)
            elif isinstance(geom, Polygon):
                coords = list(geom.exterior.coords)
            elif hasattr(geom, "geoms"):
                for sub in geom.geoms:
                    if hasattr(sub, "exterior"):
                        coords.extend(list(sub.exterior.coords))
                    elif hasattr(sub, "coords"):
                        coords.extend(list(sub.coords))

            for v_idx, (x, y) in enumerate(coords):
                r_dict = row.drop("geometry").to_dict()
                r_dict["_vertex_index"] = v_idx
                r_dict["_x"] = x
                r_dict["_y"] = y
                r_dict["geometry"] = Point(x, y)
                rows.append(r_dict)

        res_gdf = gpd.GeoDataFrame(rows, crs=gdf.crs)
        return {"Output": FeatureDataset.from_geopandas(res_gdf)}


@NodeRegistry.register
class OrientedMinimumBoundingBox(BaseNode):
    """
    Calculates the minimum rotated bounding rectangle (oriented bounding box).
    Equivalent to QGIS 'Oriented minimum bounding box'.
    """
    node_type = "OrientedMinimumBoundingBox"
    category = NodeCategory.SPATIAL
    description = "Calculates the minimum rotated bounding rectangle for features (QGIS Oriented BBox)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        gdf[gdf.geometry.name] = gdf.geometry.apply(minimum_rotated_rectangle)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class CreateGrid(BaseNode):
    """
    Generates a fishnet grid of polygon cells across the input layer's bounding box extent.
    Equivalent to QGIS 'Create grid'.
    """
    node_type = "CreateGrid"
    category = NodeCategory.SPATIAL
    description = "Generates a regular fishnet grid covering the input layer extent (QGIS Create Grid)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("cell_width", ParameterType.FLOAT, default=1.0, label="Cell Width (CRS units)"),
            ParameterDef("cell_height", ParameterType.FLOAT, default=1.0, label="Cell Height (CRS units)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": FeatureDataset.empty()}

        bounds = inp.get_bounds()
        if not bounds:
            return {"Output": FeatureDataset.empty()}

        minx, miny, maxx, maxy = bounds
        cell_w = max(float(params.get("cell_width", 1.0)), 1e-6)
        cell_h = max(float(params.get("cell_height", 1.0)), 1e-6)

        x_coords = np.arange(minx, maxx + cell_w, cell_w)
        y_coords = np.arange(miny, maxy + cell_h, cell_h)

        grid_cells = []
        cell_ids = []
        c_id = 0

        for x in x_coords[:-1]:
            for y in y_coords[:-1]:
                grid_cells.append(box(x, y, x + cell_w, y + cell_h))
                cell_ids.append(c_id)
                c_id += 1

        grid_gdf = gpd.GeoDataFrame({"grid_id": cell_ids}, geometry=grid_cells, crs=inp.crs)
        return {"Output": FeatureDataset.from_geopandas(grid_gdf)}


@NodeRegistry.register
class RandomPointsInPolygon(BaseNode):
    """
    Generates random point features inside polygon boundaries.
    Equivalent to QGIS 'Random points in polygon'.
    """
    node_type = "RandomPointsInPolygon"
    category = NodeCategory.SPATIAL
    description = "Generates N random point features inside polygons (QGIS Random Points in Polygon)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("points_per_polygon", ParameterType.INTEGER, default=10, label="Points per Polygon"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        num_pts = max(int(params.get("points_per_polygon", 10)), 1)
        point_rows = []

        for idx, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            minx, miny, maxx, maxy = geom.bounds
            pts_found = 0
            attempts = 0
            max_attempts = num_pts * 100

            while pts_found < num_pts and attempts < max_attempts:
                rx = np.random.uniform(minx, maxx)
                ry = np.random.uniform(miny, maxy)
                pt = Point(rx, ry)
                if geom.contains(pt):
                    r_dict = row.drop("geometry").to_dict()
                    r_dict["geometry"] = pt
                    point_rows.append(r_dict)
                    pts_found += 1
                attempts += 1

        res_gdf = gpd.GeoDataFrame(point_rows, crs=gdf.crs)
        return {"Output": FeatureDataset.from_geopandas(res_gdf)}
