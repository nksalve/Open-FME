"""
FME Geometry Measurement, Creation & Editing from FME_Transformers_GIS.xlsx:
- GeometryValidator (Valid / Invalid output ports with error message)
- GeometryFilter (Routes to Point, Line, Polygon, Null ports)
- GeometryPropertyExtractor (Extracts type, vertex count, bounds into attributes)
- BoundingBoxAccumulator (Single cumulative extent polygon)
- ConvexHullAccumulator (Single cumulative convex hull)
- CenterPointReplacer (Replaces geometry with centroid or point on surface)
- PolygonBuilder (Builds polygons from lines)
- LineBuilder (Connects points into lines by grouping)
- CoordinateSystemSetter (Sets CRS without reprojection)
- Mover (Translates geometry by dX, dY)
- Rotator (Rotates geometry by angle degrees)
- Scaler (Scales geometry by factor X, Y)
- 2DForcer (Strips Z/M coordinates)
- VoronoiDiagrammer (Thiessen/Voronoi polygons)
- DelaunayTriangulator (Delaunay triangulation)
"""

from typing import Any, Dict, List
import geopandas as gpd
from shapely.geometry import (
    Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon, box
)
from shapely import (
    unary_union, polygonize, voronoi_polygons, delaunay_triangles
)
from shapely.affinity import translate, rotate, scale
from shapely.validation import explain_validity
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class GeometryValidator(BaseNode):
    """
    Validates vector geometries. Routes features to Valid and Invalid ports,
    appending '_is_valid' and '_validation_error' attributes.
    """
    node_type = "GeometryValidator"
    category = NodeCategory.SPATIAL
    description = "Checks geometries for validity, self-intersections, and errors (FME GeometryValidator)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Valid", PortType.OUTPUT, "Geometrically valid features"),
            Port("Invalid", PortType.OUTPUT, "Invalid features with error messages"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Valid": FeatureDataset.empty(), "Invalid": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        is_valid_mask = gdf.geometry.is_valid
        gdf["_is_valid"] = is_valid_mask
        gdf["_validation_error"] = gdf.geometry.apply(lambda g: "" if (g and g.is_valid) else explain_validity(g) if g else "Null geometry")

        valid_gdf = gdf[is_valid_mask]
        invalid_gdf = gdf[~is_valid_mask]

        return {
            "Valid": FeatureDataset.from_geopandas(valid_gdf),
            "Invalid": FeatureDataset.from_geopandas(invalid_gdf),
        }


@NodeRegistry.register
class GeometryFilter(BaseNode):
    """
    Routes features to Point, Line, Polygon, or Null output ports based on geometry type.
    """
    node_type = "GeometryFilter"
    category = NodeCategory.SPATIAL
    description = "Routes features to Point, Line, Polygon, or Null ports by geometry type (FME GeometryFilter)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Point", PortType.OUTPUT, "Point and MultiPoint features"),
            Port("Line", PortType.OUTPUT, "LineString and MultiLineString features"),
            Port("Area", PortType.OUTPUT, "Polygon and MultiPolygon features"),
            Port("Null", PortType.OUTPUT, "Features with null or unknown geometry"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {
                "Point": FeatureDataset.empty(),
                "Line": FeatureDataset.empty(),
                "Area": FeatureDataset.empty(),
                "Null": FeatureDataset.empty(),
            }

        gdf = inp.to_geopandas()
        pt_mask = gdf.geometry.type.isin(["Point", "MultiPoint"])
        line_mask = gdf.geometry.type.isin(["LineString", "MultiLineString"])
        poly_mask = gdf.geometry.type.isin(["Polygon", "MultiPolygon"])
        null_mask = gdf.geometry.isna() | gdf.geometry.is_empty

        return {
            "Point": FeatureDataset.from_geopandas(gdf[pt_mask]),
            "Line": FeatureDataset.from_geopandas(gdf[line_mask]),
            "Area": FeatureDataset.from_geopandas(gdf[poly_mask]),
            "Null": FeatureDataset.from_geopandas(gdf[null_mask]),
        }


@NodeRegistry.register
class GeometryPropertyExtractor(BaseNode):
    """
    Extracts geometry type, vertex count, and bounds into attributes:
    _geom_type, _num_vertices, _minx, _miny, _maxx, _maxy.
    """
    node_type = "GeometryPropertyExtractor"
    category = NodeCategory.SPATIAL
    description = "Extracts geometry type, vertex count, bounds into attributes (FME GeometryPropertyExtractor)."

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
        bounds_df = gdf.geometry.bounds

        gdf["_geom_type"] = gdf.geometry.type
        gdf["_minx"] = bounds_df["minx"]
        gdf["_miny"] = bounds_df["miny"]
        gdf["_maxx"] = bounds_df["maxx"]
        gdf["_maxy"] = bounds_df["maxy"]

        def count_vertices(g):
            if not g or g.is_empty:
                return 0
            if hasattr(g, "coords"):
                return len(g.coords)
            if hasattr(g, "exterior"):
                cnt = len(g.exterior.coords)
                for hole in g.interiors:
                    cnt += len(hole.coords)
                return cnt
            if hasattr(g, "geoms"):
                return sum(count_vertices(sub) for sub in g.geoms)
            return 0

        gdf["_num_vertices"] = gdf.geometry.apply(count_vertices)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class BoundingBoxAccumulator(BaseNode):
    """
    Builds a single cumulative bounding box rectangle covering all features in the dataset.
    """
    node_type = "BoundingBoxAccumulator"
    category = NodeCategory.SPATIAL
    description = "Builds a single cumulative extent polygon for the entire dataset (FME BoundingBoxAccumulator)."

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
            return {"Output": FeatureDataset.empty()}

        b = inp.get_bounds()
        if not b:
            return {"Output": FeatureDataset.empty()}

        env = box(b[0], b[1], b[2], b[3])
        res_gdf = gpd.GeoDataFrame({"_total_features": [inp.count()]}, geometry=[env], crs=inp.crs)
        return {"Output": FeatureDataset.from_geopandas(res_gdf)}


@NodeRegistry.register
class ConvexHullAccumulator(BaseNode):
    """
    Builds a single cumulative convex hull polygon enclosing all features in the dataset.
    """
    node_type = "ConvexHullAccumulator"
    category = NodeCategory.SPATIAL
    description = "Builds a single convex hull covering all features combined (FME ConvexHullAccumulator)."

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
            return {"Output": FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        hull = unary_union(gdf.geometry).convex_hull
        res_gdf = gpd.GeoDataFrame({"_total_features": [inp.count()]}, geometry=[hull], crs=inp.crs)
        return {"Output": FeatureDataset.from_geopandas(res_gdf)}


@NodeRegistry.register
class CenterPointReplacer(BaseNode):
    """
    Replaces geometry with its centroid or representative point on surface.
    """
    node_type = "CenterPointReplacer"
    category = NodeCategory.SPATIAL
    description = "Replaces geometry with center point or point on surface (FME CenterPointReplacer)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef(
                "point_type",
                ParameterType.CHOICE,
                default="centroid",
                choices=["centroid", "point_on_surface"],
                label="Center Point Type",
            ),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        mode = params.get("point_type", "centroid")
        if mode == "point_on_surface":
            gdf[gdf.geometry.name] = gdf.geometry.representative_point()
        else:
            gdf[gdf.geometry.name] = gdf.geometry.centroid
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class PolygonBuilder(BaseNode):
    """
    Assembles lines into closed polygons (polygonize).
    """
    node_type = "PolygonBuilder"
    category = NodeCategory.SPATIAL
    description = "Assembles lines into closed polygon features (FME PolygonBuilder / AreaBuilder)."

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
            return {"Output": FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        lines = [g for g in gdf.geometry if g and isinstance(g, (LineString, MultiLineString))]
        polys = list(polygonize(lines))
        res_gdf = gpd.GeoDataFrame({"_polygon_id": list(range(1, len(polys) + 1))}, geometry=polys, crs=gdf.crs)
        return {"Output": FeatureDataset.from_geopandas(res_gdf)}


@NodeRegistry.register
class CoordinateSystemSetter(BaseNode):
    """
    Sets or updates the Coordinate Reference System (CRS) without transforming coordinates.
    """
    node_type = "CoordinateSystemSetter"
    category = NodeCategory.SPATIAL
    description = "Assigns CRS metadata without altering coordinate numbers (FME CoordinateSystemSetter)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("crs", ParameterType.STRING, default="EPSG:4326", label="Assigned Coordinate System (CRS)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": inp or FeatureDataset.empty()}

        new_crs = params.get("crs", "EPSG:4326").strip()
        ds = inp.copy()
        ds.crs = new_crs
        return {"Output": ds}


@NodeRegistry.register
class Mover(BaseNode):
    """
    Translates geometry by delta X and delta Y.
    """
    node_type = "Mover"
    category = NodeCategory.SPATIAL
    description = "Translates geometries by delta X and delta Y (FME Mover / Offsetter)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("delta_x", ParameterType.FLOAT, default=0.0, label="Delta X (Offset)"),
            ParameterDef("delta_y", ParameterType.FLOAT, default=0.0, label="Delta Y (Offset)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        dx = float(params.get("delta_x", 0.0))
        dy = float(params.get("delta_y", 0.0))
        gdf[gdf.geometry.name] = gdf.geometry.apply(lambda g: translate(g, xoff=dx, yoff=dy) if g else g)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class Rotator(BaseNode):
    """
    Rotates geometries by angle in degrees.
    """
    node_type = "Rotator"
    category = NodeCategory.SPATIAL
    description = "Rotates geometry by angle in degrees around origin or centroid (FME Rotator)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("angle_degrees", ParameterType.FLOAT, default=45.0, label="Rotation Angle (Degrees)"),
            ParameterDef("origin", ParameterType.CHOICE, default="center", choices=["center", "origin"], label="Rotation Pivot"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        angle = float(params.get("angle_degrees", 45.0))
        origin_val = params.get("origin", "center")
        gdf[gdf.geometry.name] = gdf.geometry.apply(lambda g: rotate(g, angle, origin=origin_val) if g else g)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class Scaler(BaseNode):
    """
    Scales geometry by factor X and factor Y.
    """
    node_type = "Scaler"
    category = NodeCategory.SPATIAL
    description = "Scales geometry by factor X and Y (FME Scaler)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("factor_x", ParameterType.FLOAT, default=1.5, label="Scale Factor X"),
            ParameterDef("factor_y", ParameterType.FLOAT, default=1.5, label="Scale Factor Y"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        fx = float(params.get("factor_x", 1.5))
        fy = float(params.get("factor_y", 1.5))
        gdf[gdf.geometry.name] = gdf.geometry.apply(lambda g: scale(g, xfact=fx, yfact=fy) if g else g)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class TwoDForcer(BaseNode):
    """
    Forces 2D geometries by stripping Z and M coordinate dimensions.
    """
    node_type = "2DForcer"
    category = NodeCategory.SPATIAL
    description = "Strips Z and M coordinates to force 2D planar geometry (FME 2DForcer)."

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
        from shapely import force_2d
        gdf[gdf.geometry.name] = gdf.geometry.apply(force_2d)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class VoronoiDiagrammer(BaseNode):
    """
    Constructs Voronoi (Thiessen) polygons from input points.
    FME VoronoiDiagrammer transformer.
    """
    node_type = "VoronoiDiagrammer"
    category = NodeCategory.SPATIAL
    description = "Constructs Thiessen / Voronoi polygons from point features (FME VoronoiDiagrammer)."

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
            return {"Output": FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        pts = [g for g in gdf.geometry if g and isinstance(g, Point)]
        if len(pts) < 3:
            return {"Output": FeatureDataset.empty()}

        multi_pt = MultiPoint(pts)
        voronoi_res = voronoi_polygons(multi_pt)
        v_polys = list(voronoi_res.geoms) if hasattr(voronoi_res, "geoms") else [voronoi_res]

        res_gdf = gpd.GeoDataFrame({"_voronoi_id": list(range(1, len(v_polys) + 1))}, geometry=v_polys, crs=gdf.crs)
        return {"Output": FeatureDataset.from_geopandas(res_gdf)}
