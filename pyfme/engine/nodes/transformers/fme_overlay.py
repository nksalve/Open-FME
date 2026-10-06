"""
FME Overlay and Geoprocessing Transformers from FME_Transformers_GIS.xlsx:
- Clipper (Clipper / Candidate -> Inside / Outside)
- PointOnAreaOverlayer (Point-in-polygon attribute transfer)
- LineOnAreaOverlayer (Splits lines by polygons with attribute transfer)
- Intersector (Splits lines at crossings)
- Snapper (Snaps vertices within tolerance)
- Aggregator (Combines features into multi-part geometries)
- Deaggregator (Explodes multi-part geometries into single-parts)
- Chopper (Splits geometry into segments of N vertices)
- Generalizer (Douglas-Peucker line & polygon simplification)
"""

from typing import Any, Dict, List
import geopandas as gpd
from shapely.geometry import (
    Point, LineString, Polygon, MultiPolygon, MultiLineString, MultiPoint
)
from shapely.ops import split, snap, unary_union, linemerge
import polars as pl
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class Clipper(BaseNode):
    """
    Clips candidate features against clipper boundary polygons.
    Routes features to 'Inside' and 'Outside' output ports.
    Iconic FME Clipper transformer.
    """
    node_type = "Clipper"
    category = NodeCategory.SPATIAL
    description = "Clips Candidate features by a polygon layer into Inside and Outside output ports."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Candidate", PortType.INPUT, "Features to be clipped"),
            Port("Clipper", PortType.INPUT, "Clipping boundary polygon"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Inside", PortType.OUTPUT, "Clipped features inside boundaries"),
            Port("Outside", PortType.OUTPUT, "Features outside boundaries"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        candidate = inputs.get("Candidate")
        clipper_ds = inputs.get("Clipper")

        if not candidate or candidate.count() == 0 or not candidate.has_geometry():
            return {"Inside": FeatureDataset.empty(), "Outside": FeatureDataset.empty()}
        if not clipper_ds or clipper_ds.count() == 0 or not clipper_ds.has_geometry():
            return {"Inside": FeatureDataset.empty(), "Outside": candidate}

        cand_gdf = candidate.to_geopandas()
        clip_gdf = clipper_ds.to_geopandas()

        if cand_gdf.crs and clip_gdf.crs and cand_gdf.crs != clip_gdf.crs:
            clip_gdf = clip_gdf.to_crs(cand_gdf.crs)

        clip_union = unary_union(clip_gdf.geometry)

        # Inside: intersection with clipping mask
        inside_gdf = gpd.overlay(cand_gdf, clip_gdf[["geometry"]], how="intersection", keep_geom_type=False)
        # Outside: difference with clipping mask
        outside_gdf = cand_gdf.copy()
        outside_gdf[outside_gdf.geometry.name] = outside_gdf.geometry.difference(clip_union)
        outside_gdf = outside_gdf[~outside_gdf.geometry.is_empty]

        return {
            "Inside": FeatureDataset.from_geopandas(inside_gdf),
            "Outside": FeatureDataset.from_geopandas(outside_gdf),
        }


@NodeRegistry.register
class PointOnAreaOverlayer(BaseNode):
    """
    Point-in-polygon attribute transfer.
    Transfers attributes of containing polygons onto points.
    Outputs Point and Area ports.
    """
    node_type = "PointOnAreaOverlayer"
    category = NodeCategory.SPATIAL
    description = "Point-in-polygon attribute transfer between points and areas (FME PointOnAreaOverlayer)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Point", PortType.INPUT, "Point features"),
            Port("Area", PortType.INPUT, "Polygon area features"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Point", PortType.OUTPUT, "Points with joined area attributes"),
            Port("Area", PortType.OUTPUT, "Area features unchanged"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        pt_ds = inputs.get("Point")
        area_ds = inputs.get("Area")

        if not pt_ds or pt_ds.count() == 0:
            return {"Point": FeatureDataset.empty(), "Area": area_ds or FeatureDataset.empty()}
        if not area_ds or area_ds.count() == 0:
            return {"Point": pt_ds, "Area": FeatureDataset.empty()}

        pt_gdf = pt_ds.to_geopandas()
        area_gdf = area_ds.to_geopandas()

        if pt_gdf.crs and area_gdf.crs and pt_gdf.crs != area_gdf.crs:
            area_gdf = area_gdf.to_crs(pt_gdf.crs)

        joined_pt = gpd.sjoin(pt_gdf, area_gdf, how="left", predicate="within")
        if "index_right" in joined_pt.columns:
            joined_pt = joined_pt.drop(columns=["index_right"])

        return {
            "Point": FeatureDataset.from_geopandas(joined_pt),
            "Area": area_ds,
        }


@NodeRegistry.register
class LineOnAreaOverlayer(BaseNode):
    """
    Splits lines by polygon boundaries and carries over polygon attributes.
    """
    node_type = "LineOnAreaOverlayer"
    category = NodeCategory.SPATIAL
    description = "Splits lines by polygons and carries over polygon attributes (FME LineOnAreaOverlayer)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Line", PortType.INPUT, "Line features"),
            Port("Area", PortType.INPUT, "Polygon boundaries"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Line", PortType.OUTPUT, "Split line segments with area attributes")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        line_ds = inputs.get("Line")
        area_ds = inputs.get("Area")

        if not line_ds or line_ds.count() == 0:
            return {"Line": FeatureDataset.empty()}
        if not area_ds or area_ds.count() == 0:
            return {"Line": line_ds}

        line_gdf = line_ds.to_geopandas()
        area_gdf = area_ds.to_geopandas()

        if line_gdf.crs and area_gdf.crs and line_gdf.crs != area_gdf.crs:
            area_gdf = area_gdf.to_crs(line_gdf.crs)

        res_gdf = gpd.overlay(line_gdf, area_gdf, how="intersection", keep_geom_type=False)
        return {"Line": FeatureDataset.from_geopandas(res_gdf)}


@NodeRegistry.register
class Intersector(BaseNode):
    """
    Splits intersecting lines and polygons at their crossing intersections and builds nodes.
    """
    node_type = "Intersector"
    category = NodeCategory.SPATIAL
    description = "Splits lines at their intersections and builds nodes (FME Intersector)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Segments", PortType.OUTPUT, "Split line segments"),
            Port("Nodes", PortType.OUTPUT, "Intersection node points"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Segments": FeatureDataset.empty(), "Nodes": FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        lines = [g for g in gdf.geometry if g and isinstance(g, (LineString, MultiLineString))]

        if not lines:
            return {"Segments": inp, "Nodes": FeatureDataset.empty()}

        union_geom = unary_union(lines)
        # Nodalize with unary_union
        split_lines = []
        if isinstance(union_geom, LineString):
            split_lines = [union_geom]
        elif hasattr(union_geom, "geoms"):
            split_lines = list(union_geom.geoms)

        seg_gdf = gpd.GeoDataFrame(geometry=split_lines, crs=gdf.crs)

        # Extract node points
        nodes = []
        for l in split_lines:
            coords = list(l.coords)
            if coords:
                nodes.append(Point(coords[0]))
                nodes.append(Point(coords[-1]))
        unique_nodes = list({(pt.x, pt.y): pt for pt in nodes}.values())
        node_gdf = gpd.GeoDataFrame(geometry=unique_nodes, crs=gdf.crs)

        return {
            "Segments": FeatureDataset.from_geopandas(seg_gdf),
            "Nodes": FeatureDataset.from_geopandas(node_gdf),
        }


@NodeRegistry.register
class Snapper(BaseNode):
    """
    Snaps candidate vertices to nearby reference points/lines within a tolerance distance.
    """
    node_type = "Snapper"
    category = NodeCategory.SPATIAL
    description = "Snaps vertices and features within a distance tolerance (FME Snapper)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Candidate", PortType.INPUT, "Features to snap"),
            Port("Anchor", PortType.INPUT, "Reference features to snap to"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Snapped", PortType.OUTPUT, "Snapped features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("tolerance", ParameterType.FLOAT, default=1.0, label="Snapping Tolerance (CRS units)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        cand = inputs.get("Candidate")
        anchor = inputs.get("Anchor")

        if not cand or cand.count() == 0:
            return {"Snapped": FeatureDataset.empty()}
        if not anchor or anchor.count() == 0:
            return {"Snapped": cand}

        cand_gdf = cand.to_geopandas().copy()
        anchor_gdf = anchor.to_geopandas()

        if cand_gdf.crs and anchor_gdf.crs and cand_gdf.crs != anchor_gdf.crs:
            anchor_gdf = anchor_gdf.to_crs(cand_gdf.crs)

        anchor_union = unary_union(anchor_gdf.geometry)
        tol = float(params.get("tolerance", 1.0))

        cand_gdf[cand_gdf.geometry.name] = cand_gdf.geometry.apply(lambda g: snap(g, anchor_union, tol) if g else g)
        return {"Snapped": FeatureDataset.from_geopandas(cand_gdf)}


@NodeRegistry.register
class Aggregator(BaseNode):
    """
    Combines features into multi-part geometries based on a group-by attribute or globally.
    """
    node_type = "Aggregator"
    category = NodeCategory.SPATIAL
    description = "Combines features into multi-part geometries (FME Aggregator)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("group_by", ParameterType.STRING, default="", label="Group By Attribute (Blank for all)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        grp = params.get("group_by", "").strip()

        if grp and grp in gdf.columns:
            dissolved = gdf.dissolve(by=grp, as_index=False)
        else:
            dissolved = gdf.dissolve(as_index=False)

        return {"Output": FeatureDataset.from_geopandas(dissolved)}


@NodeRegistry.register
class Deaggregator(BaseNode):
    """
    Splits multi-part geometries into individual single-part features.
    """
    node_type = "Deaggregator"
    category = NodeCategory.SPATIAL
    description = "Splits multi-part geometries into individual single-part features (FME Deaggregator)."

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
class Chopper(BaseNode):
    """
    Splits geometries by vertex count (e.g. into lines of 2 vertices each) or adds points.
    """
    node_type = "Chopper"
    category = NodeCategory.SPATIAL
    description = "Splits geometry into segments of N vertices (FME Chopper)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("max_vertices", ParameterType.INTEGER, default=2, label="Max Vertices per Segment"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        max_v = max(int(params.get("max_vertices", 2)), 2)
        new_rows = []

        for idx, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            coords = []
            if isinstance(geom, LineString):
                coords = list(geom.coords)
            elif isinstance(geom, Polygon):
                coords = list(geom.exterior.coords)

            if len(coords) <= max_v:
                new_rows.append(row.to_dict())
            else:
                for i in range(0, len(coords) - 1, max_v - 1):
                    seg_coords = coords[i : i + max_v]
                    if len(seg_coords) >= 2:
                        r_dict = row.drop("geometry").to_dict()
                        r_dict["geometry"] = LineString(seg_coords)
                        new_rows.append(r_dict)

        if not new_rows:
            return {"Output": inp}
        return {"Output": FeatureDataset.from_geopandas(gpd.GeoDataFrame(new_rows, crs=gdf.crs))}


@NodeRegistry.register
class Generalizer(BaseNode):
    """
    Simplifies lines and polygons using Douglas-Peucker algorithm.
    FME Generalizer transformer.
    """
    node_type = "Generalizer"
    category = NodeCategory.SPATIAL
    description = "Simplifies lines and polygons with Douglas-Peucker (FME Generalizer)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("tolerance", ParameterType.FLOAT, default=0.05, label="Tolerance (CRS units)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        tol = float(params.get("tolerance", 0.05))
        gdf[gdf.geometry.name] = gdf.geometry.simplify(tolerance=tol, preserve_topology=True)
        return {"Output": FeatureDataset.from_geopandas(gdf)}
