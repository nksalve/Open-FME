"""
QGIS-grade Geoprocessing & Spatial Analysis Transformers:
- OverlayIntersection (QGIS Intersection / FME Clipper)
- OverlayDifference (QGIS Difference / Erase)
- OverlayUnion (QGIS Union)
- OverlaySymmetricalDifference (QGIS Symmetrical Difference / XOR)
- Dissolver (QGIS Dissolve)
- SpatialJoin (QGIS Join Attributes by Location)
- NearestNeighborJoin (QGIS Join Attributes by Nearest)
- CountPointsInPolygon (QGIS Count Points in Polygon)
"""

from typing import Any, Dict, List
import geopandas as gpd
import polars as pl
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class OverlayIntersection(BaseNode):
    """
    Computes geometric intersection of Input and Overlay layers.
    Yields only the overlapping geometry with attributes joined from both layers.
    Equivalent to QGIS 'Intersection' and FME 'Clipper' (Inside).
    """
    node_type = "OverlayIntersection"
    category = NodeCategory.SPATIAL
    description = "Computes geometric intersection between Input and Overlay layers (QGIS Intersection)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Input", PortType.INPUT, "Base features to intersect"),
            Port("Overlay", PortType.INPUT, "Intersecting layer boundary"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Intersected features with combined attributes")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        overlay = inputs.get("Overlay")

        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": FeatureDataset.empty()}
        if not overlay or overlay.count() == 0 or not overlay.has_geometry():
            return {"Output": FeatureDataset.empty()}

        inp = inp.make_valid()
        overlay = overlay.make_valid()
        gdf1 = inp.to_geopandas()
        gdf2 = overlay.to_geopandas()

        if gdf1.crs and gdf2.crs and gdf1.crs != gdf2.crs:
            gdf2 = gdf2.to_crs(gdf1.crs)

        result_gdf = gpd.overlay(gdf1, gdf2, how="intersection", keep_geom_type=False)
        return {"Output": FeatureDataset.from_geopandas(result_gdf)}


@NodeRegistry.register
class OverlayDifference(BaseNode):
    """
    Computes geometric difference (erases Overlay areas from Input layer).
    Equivalent to QGIS 'Difference' / FME 'SpatialRelator' (Outside).
    """
    node_type = "OverlayDifference"
    category = NodeCategory.SPATIAL
    description = "Erases overlay regions from input features (QGIS Difference / Erase)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Input", PortType.INPUT, "Source features"),
            Port("Overlay", PortType.INPUT, "Erase boundary layer"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Remaining non-overlapping features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        overlay = inputs.get("Overlay")

        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": FeatureDataset.empty()}
        if not overlay or overlay.count() == 0 or not overlay.has_geometry():
            return {"Output": inp}

        inp = inp.make_valid()
        overlay = overlay.make_valid()
        gdf1 = inp.to_geopandas()
        gdf2 = overlay.to_geopandas()

        if gdf1.crs and gdf2.crs and gdf1.crs != gdf2.crs:
            gdf2 = gdf2.to_crs(gdf1.crs)

        result_gdf = gpd.overlay(gdf1, gdf2, how="difference", keep_geom_type=False)
        return {"Output": FeatureDataset.from_geopandas(result_gdf)}


@NodeRegistry.register
class OverlayUnion(BaseNode):
    """
    Computes geometric union of both layers.
    Preserves all overlapping and non-overlapping slices with joined attributes.
    Equivalent to QGIS 'Union'.
    """
    node_type = "OverlayUnion"
    category = NodeCategory.SPATIAL
    description = "Computes geometric union of both layers (QGIS Union)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Input", PortType.INPUT, "First layer"),
            Port("Overlay", PortType.INPUT, "Second layer"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Union of both layers")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        overlay = inputs.get("Overlay")

        if not inp or inp.count() == 0:
            return {"Output": overlay or FeatureDataset.empty()}
        if not overlay or overlay.count() == 0:
            return {"Output": inp}

        inp = inp.make_valid()
        overlay = overlay.make_valid()
        gdf1 = inp.to_geopandas()
        gdf2 = overlay.to_geopandas()

        if gdf1.crs and gdf2.crs and gdf1.crs != gdf2.crs:
            gdf2 = gdf2.to_crs(gdf1.crs)

        result_gdf = gpd.overlay(gdf1, gdf2, how="union", keep_geom_type=False)
        return {"Output": FeatureDataset.from_geopandas(result_gdf)}


@NodeRegistry.register
class OverlaySymmetricalDifference(BaseNode):
    """
    Computes symmetrical difference (XOR) between Input and Overlay layers.
    Preserves areas that appear in either layer, but not in both.
    Equivalent to QGIS 'Symmetrical Difference'.
    """
    node_type = "OverlaySymmetricalDifference"
    category = NodeCategory.SPATIAL
    description = "Extracts areas that fall in either layer but not both (QGIS Symmetrical Difference)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Input", PortType.INPUT, "First layer"),
            Port("Overlay", PortType.INPUT, "Second layer"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Symmetrical difference features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        overlay = inputs.get("Overlay")

        if not inp or inp.count() == 0:
            return {"Output": overlay or FeatureDataset.empty()}
        if not overlay or overlay.count() == 0:
            return {"Output": inp}

        gdf1 = inp.to_geopandas()
        gdf2 = overlay.to_geopandas()

        if gdf1.crs and gdf2.crs and gdf1.crs != gdf2.crs:
            gdf2 = gdf2.to_crs(gdf1.crs)

        result_gdf = gpd.overlay(gdf1, gdf2, how="symmetric_difference", keep_geom_type=False)
        return {"Output": FeatureDataset.from_geopandas(result_gdf)}


@NodeRegistry.register
class Dissolver(BaseNode):
    """
    Merges geometries sharing the same attribute value, or merges all geometries into one.
    Equivalent to QGIS 'Dissolve' and FME 'Dissolver'.
    """
    node_type = "Dissolver"
    category = NodeCategory.SPATIAL
    description = "Merges adjacent or overlapping geometries sharing an attribute (QGIS Dissolve)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("by_attribute", ParameterType.STRING, default="", label="Dissolve by Attribute (Blank to merge all)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        by_col = params.get("by_attribute", "").strip()

        if by_col and by_col in gdf.columns:
            dissolved = gdf.dissolve(by=by_col, as_index=False)
        else:
            dissolved = gdf.dissolve(as_index=False)

        return {"Output": FeatureDataset.from_geopandas(dissolved)}


@NodeRegistry.register
class SpatialJoin(BaseNode):
    """
    Joins attributes from JoinLayer to TargetLayer based on spatial relationship.
    Equivalent to QGIS 'Join attributes by location'.
    """
    node_type = "SpatialJoin"
    category = NodeCategory.SPATIAL
    description = "Joins attributes from another layer based on spatial intersection/containment (QGIS Spatial Join)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Target", PortType.INPUT, "Base layer to receive attributes"),
            Port("JoinLayer", PortType.INPUT, "Layer supplying attributes"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Target features with joined attributes")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef(
                "predicate",
                ParameterType.CHOICE,
                default="intersects",
                choices=["intersects", "within", "contains", "touches", "crosses"],
                label="Geometric Predicate",
            ),
            ParameterDef(
                "how",
                ParameterType.CHOICE,
                default="left",
                choices=["left", "inner"],
                label="Join Mode",
            ),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        target = inputs.get("Target")
        join_layer = inputs.get("JoinLayer")

        if not target or target.count() == 0 or not target.has_geometry():
            return {"Output": target or FeatureDataset.empty()}
        if not join_layer or join_layer.count() == 0 or not join_layer.has_geometry():
            return {"Output": target}

        target_gdf = target.to_geopandas()
        join_gdf = join_layer.to_geopandas()

        if target_gdf.crs and join_gdf.crs and target_gdf.crs != join_gdf.crs:
            join_gdf = join_gdf.to_crs(target_gdf.crs)

        pred = params.get("predicate", "intersects")
        join_how = params.get("how", "left")

        joined = gpd.sjoin(target_gdf, join_gdf, how=join_how, predicate=pred)
        if "index_right" in joined.columns:
            joined = joined.drop(columns=["index_right"])

        return {"Output": FeatureDataset.from_geopandas(joined)}


@NodeRegistry.register
class NearestNeighborJoin(BaseNode):
    """
    Finds the closest feature in JoinLayer for each feature in TargetLayer,
    computes the Euclidean distance attribute, and joins attributes.
    Equivalent to QGIS 'Join attributes by nearest'.
    """
    node_type = "NearestNeighborJoin"
    category = NodeCategory.SPATIAL
    description = "Finds the closest feature from another layer and calculates distance (QGIS Join Nearest)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Target", PortType.INPUT, "Source features"),
            Port("JoinLayer", PortType.INPUT, "Candidate features to find closest"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Target features with closest attributes + distance")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("distance_col", ParameterType.STRING, default="_distance", label="Distance Attribute Name"),
            ParameterDef("max_distance", ParameterType.FLOAT, default=0.0, label="Max Search Distance (0 for unlimited)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        target = inputs.get("Target")
        join_layer = inputs.get("JoinLayer")

        if not target or target.count() == 0 or not target.has_geometry():
            return {"Output": target or FeatureDataset.empty()}
        if not join_layer or join_layer.count() == 0 or not join_layer.has_geometry():
            return {"Output": target}

        target_gdf = target.to_geopandas()
        join_gdf = join_layer.to_geopandas()

        if target_gdf.crs and join_gdf.crs and target_gdf.crs != join_gdf.crs:
            join_gdf = join_gdf.to_crs(target_gdf.crs)

        dist_col = params.get("distance_col", "_distance").strip() or "_distance"
        max_dist = float(params.get("max_distance", 0.0))
        max_d_arg = max_dist if max_dist > 0 else None

        joined = gpd.sjoin_nearest(
            target_gdf,
            join_gdf,
            how="left",
            distance_col=dist_col,
            max_distance=max_d_arg,
        )
        if "index_right" in joined.columns:
            joined = joined.drop(columns=["index_right"])

        return {"Output": FeatureDataset.from_geopandas(joined)}


@NodeRegistry.register
class CountPointsInPolygon(BaseNode):
    """
    Counts how many points fall inside each polygon feature.
    Appends '_point_count' attribute.
    Equivalent to QGIS 'Count points in polygon'.
    """
    node_type = "CountPointsInPolygon"
    category = NodeCategory.SPATIAL
    description = "Counts how many points fall within each polygon (QGIS Count Points in Polygon)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Polygons", PortType.INPUT, "Polygon boundary layer"),
            Port("Points", PortType.INPUT, "Point features to count"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Polygons with appended count attribute")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("count_attribute", ParameterType.STRING, default="_point_count", label="Count Attribute Name"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        polys = inputs.get("Polygons")
        points = inputs.get("Points")

        if not polys or polys.count() == 0 or not polys.has_geometry():
            return {"Output": polys or FeatureDataset.empty()}

        poly_gdf = polys.to_geopandas().copy()
        count_col = params.get("count_attribute", "_point_count").strip() or "_point_count"

        if not points or points.count() == 0 or not points.has_geometry():
            poly_gdf[count_col] = 0
            return {"Output": FeatureDataset.from_geopandas(poly_gdf)}

        pt_gdf = points.to_geopandas()
        if poly_gdf.crs and pt_gdf.crs and poly_gdf.crs != pt_gdf.crs:
            pt_gdf = pt_gdf.to_crs(poly_gdf.crs)

        # Spatial join points into polygons
        joined = gpd.sjoin(pt_gdf, poly_gdf, how="inner", predicate="within")
        counts = joined.groupby("index_right").size()

        poly_gdf[count_col] = poly_gdf.index.map(counts).fillna(0).astype(int)
        return {"Output": FeatureDataset.from_geopandas(poly_gdf)}
