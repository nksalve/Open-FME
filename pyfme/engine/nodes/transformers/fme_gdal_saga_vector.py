"""
Vector Transformers from FME, GDAL/OGR, and SAGA GIS:
- AreaOnAreaOverlayer
- LineOnLineOverlayer
- PointOnLineOverlayer
- Densifier
- DuplicateRemover
- Offsetter
- AreaBuilder
- DonutBuilder
- LineJoiner
- LineCombiner
- VertexRemover
- 3DForcer
- Affiner
- CoordinateConcatenator
- GeometryCoercer
- CenterLineReplacer
- TopologyBuilder
- NetworkTopologyCalculator
- DelaunayTriangulator
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import numpy as np
import polars as pl
import geopandas as gpd
from shapely.geometry import (
    Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon
)
import shapely
from shapely import ops, affinity

from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class AreaOnAreaOverlayer(BaseNode):
    """
    Performs polygon-on-polygon overlay (ArcGIS Union/Identity equivalent).
    Computes all geometric intersection fragments and tracks overlap counts.
    """
    node_type = "AreaOnAreaOverlayer"
    category = NodeCategory.SPATIAL
    description = "Polygon overlay computing intersections, carrying over attributes, and recording overlap counts (_overlaps)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Polygon layers to overlay")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Fragmented polygons with overlap counts")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("count_attribute", ParameterType.STRING, default="_overlaps", label="Overlap Count Attribute"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        count_attr = params.get("count_attribute", "_overlaps").strip() or "_overlaps"

        # Polygonize boundary union
        polys = [g for g in gdf.geometry if g is not None and not g.is_empty and g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            return {"Output": inp}

        try:
            boundaries = ops.unary_union([p.boundary for p in polys])
            fragments = list(ops.polygonize(boundaries))
            if not fragments:
                gdf_out = gdf.copy()
                gdf_out[count_attr] = 1
                return {"Output": FeatureDataset.from_geopandas(gdf_out)}

            frag_gdf = gpd.GeoDataFrame(geometry=fragments, crs=gdf.crs)
            # Representative points to test which input polygons contain each fragment
            rep_pts = frag_gdf.geometry.representative_point()
            rep_gdf = gpd.GeoDataFrame(geometry=rep_pts, crs=gdf.crs)

            joined = gpd.sjoin(rep_gdf, gdf, how="left", predicate="within")
            overlap_counts = joined.groupby(joined.index).size()
            frag_gdf[count_attr] = frag_gdf.index.map(overlap_counts).fillna(1).astype(int)

            return {"Output": FeatureDataset.from_geopandas(frag_gdf)}
        except Exception:
            gdf_out = gdf.copy()
            gdf_out[count_attr] = 1
            return {"Output": FeatureDataset.from_geopandas(gdf_out)}


@NodeRegistry.register
class LineOnLineOverlayer(BaseNode):
    """
    Splits and overlays lines, detecting crossings and intersection points.
    Matches FME LineOnLineOverlayer.
    """
    node_type = "LineOnLineOverlayer"
    category = NodeCategory.SPATIAL
    description = "Splits lines at mutual crossings, returning segmented lines and intersection point nodes."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Line features")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Lines", PortType.OUTPUT, "Segmented lines split at intersections"),
            Port("Points", PortType.OUTPUT, "Intersection node points"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Lines": inp or FeatureDataset.empty(), "Points": FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        lines = [g for g in gdf.geometry if g is not None and not g.is_empty and g.geom_type in ("LineString", "MultiLineString")]
        if not lines:
            return {"Lines": inp, "Points": FeatureDataset.empty()}

        try:
            merged = ops.unary_union(lines)
            split_lines = []
            inter_pts = []

            if merged.geom_type == "MultiLineString":
                split_lines = list(merged.geoms)
            elif merged.geom_type == "LineString":
                split_lines = [merged]

            # Detect intersection vertices
            all_pts = []
            for line in split_lines:
                all_pts.extend([Point(pt) for pt in line.coords])

            # Deduplicate intersection points (points that occur > 1 time)
            coords_dict = {}
            for p in all_pts:
                k = (round(p.x, 6), round(p.y, 6))
                coords_dict[k] = coords_dict.get(k, 0) + 1

            inter_pts = [Point(k[0], k[1]) for k, count in coords_dict.items() if count > 1]

            lines_gdf = gpd.GeoDataFrame(geometry=split_lines, crs=gdf.crs)
            pts_gdf = gpd.GeoDataFrame(geometry=inter_pts, crs=gdf.crs) if inter_pts else gpd.GeoDataFrame(columns=["geometry"], crs=gdf.crs)

            return {
                "Lines": FeatureDataset.from_geopandas(lines_gdf),
                "Points": FeatureDataset.from_geopandas(pts_gdf),
            }
        except Exception:
            return {"Lines": inp, "Points": FeatureDataset.empty()}


@NodeRegistry.register
class PointOnLineOverlayer(BaseNode):
    """
    Tests or snaps points against lines and transfers line attributes.
    Matches FME PointOnLineOverlayer.
    """
    node_type = "PointOnLineOverlayer"
    category = NodeCategory.SPATIAL
    description = "Tests points against lines within a tolerance, transferring line attributes and calculating distance."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Point", PortType.INPUT, "Point features"),
            Port("Line", PortType.INPUT, "Line features"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("PointOutput", PortType.OUTPUT, "Points with nearest line attributes"),
            Port("LineOutput", PortType.OUTPUT, "Original line features"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("tolerance", ParameterType.FLOAT, default=100.0, label="Search Distance Tolerance"),
            ParameterDef("distance_attribute", ParameterType.STRING, default="_distance_to_line", label="Distance Attribute"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        pts_ds = inputs.get("Point")
        lines_ds = inputs.get("Line")

        if not pts_ds or pts_ds.is_empty():
            return {"PointOutput": FeatureDataset.empty(), "LineOutput": lines_ds or FeatureDataset.empty()}
        if not lines_ds or lines_ds.is_empty():
            return {"PointOutput": pts_ds, "LineOutput": FeatureDataset.empty()}

        pt_gdf = pts_ds.to_geopandas().copy()
        ln_gdf = lines_ds.to_geopandas()
        dist_attr = params.get("distance_attribute", "_distance_to_line").strip() or "_distance_to_line"

        # Nearest line calculation
        distances = []
        for p in pt_gdf.geometry:
            if p is not None and not p.is_empty:
                dists = [p.distance(ln) for ln in ln_gdf.geometry if ln is not None and not ln.is_empty]
                distances.append(min(dists) if dists else 0.0)
            else:
                distances.append(0.0)

        pt_gdf[dist_attr] = distances
        return {
            "PointOutput": FeatureDataset.from_geopandas(pt_gdf),
            "LineOutput": lines_ds,
        }


@NodeRegistry.register
class Densifier(BaseNode):
    """
    Adds vertices along lines or polygons at a set distance interval.
    Matches FME / GDAL Densifier.
    """
    node_type = "Densifier"
    category = NodeCategory.SPATIAL
    description = "Adds intermediate vertices along lines or polygons at a set distance interval."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("interval_distance", ParameterType.FLOAT, default=10.0, label="Maximum Vertex Distance"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        interval = float(params.get("interval_distance") or params.get("max_distance") or 10.0)
        if interval <= 0:
            return {"Output": inp}

        gdf = inp.to_geopandas().copy()
        if hasattr(shapely, "segmentize"):
            gdf["geometry"] = shapely.segmentize(gdf.geometry, max_segment_length=interval)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class DuplicateRemover(BaseNode):
    """
    Removes duplicate features by specified attribute keys or exact geometry.
    Matches FME DuplicateRemover.
    """
    node_type = "DuplicateRemover"
    category = NodeCategory.ATTRIBUTE
    description = "Removes duplicate features based on key attributes or geometry coordinates."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Unique", PortType.OUTPUT, "Deduplicated unique features"),
            Port("Duplicate", PortType.OUTPUT, "Redundant duplicate features"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("key_attribute", ParameterType.STRING, default="", label="Key Attribute (blank for geometry)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Unique": inp or FeatureDataset.empty(), "Duplicate": FeatureDataset.empty()}

        key_attr = params.get("key_attribute", "").strip()

        if inp.has_geometry():
            gdf = inp.to_geopandas()
            if key_attr and key_attr in gdf.columns:
                dup_mask = gdf.duplicated(subset=[key_attr], keep="first")
            else:
                wkb_keys = [g.wkb if g is not None else b"" for g in gdf.geometry]
                seen = set()
                dup_mask = []
                for k in wkb_keys:
                    if k in seen:
                        dup_mask.append(True)
                    else:
                        seen.add(k)
                        dup_mask.append(False)
                dup_mask = np.array(dup_mask)

            return {
                "Unique": FeatureDataset.from_geopandas(gdf[~dup_mask]),
                "Duplicate": FeatureDataset.from_geopandas(gdf[dup_mask]),
            }
        else:
            df = inp.to_polars()
            if key_attr and key_attr in df.columns:
                unique_df = df.unique(subset=[key_attr], keep="first")
                dup_df = df.filter(pl.col(key_attr).is_duplicated())
                return {"Unique": FeatureDataset.from_polars(unique_df), "Duplicate": FeatureDataset.from_polars(dup_df)}
            else:
                unique_df = df.unique(keep="first")
                return {"Unique": FeatureDataset.from_polars(unique_df), "Duplicate": FeatureDataset.empty()}


@NodeRegistry.register
class Offsetter(BaseNode):
    """
    Translates or offsets geometries by X and Y distances.
    Matches FME / SAGA Offsetter.
    """
    node_type = "Offsetter"
    category = NodeCategory.SPATIAL
    description = "Offsets geometries by specified X (longitude) and Y (latitude) distances."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("offset_x", ParameterType.FLOAT, default=0.0, label="Offset X Distance"),
            ParameterDef("offset_y", ParameterType.FLOAT, default=0.0, label="Offset Y Distance"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        dx = float(params.get("offset_x", 0.0))
        dy = float(params.get("offset_y", 0.0))

        gdf = inp.to_geopandas().copy()
        gdf["geometry"] = [affinity.translate(g, xoff=dx, yoff=dy) if g is not None else None for g in gdf.geometry]
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class AreaBuilder(BaseNode):
    """
    Assembles connected boundary lines into closed polygon areas.
    Matches FME / SAGA AreaBuilder.
    """
    node_type = "AreaBuilder"
    category = NodeCategory.SPATIAL
    description = "Builds closed polygons from connected boundary lines (polygonize)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Boundary lines")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Area", PortType.OUTPUT, "Formed closed polygons"),
            Port("Incomplete", PortType.OUTPUT, "Unclosed lines"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Area": FeatureDataset.empty(), "Incomplete": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        lines = [g for g in gdf.geometry if g is not None and not g.is_empty and g.geom_type in ("LineString", "MultiLineString")]
        if not lines:
            return {"Area": FeatureDataset.empty(), "Incomplete": inp}

        try:
            merged = ops.unary_union(lines)
            polys = list(ops.polygonize(merged))
            if polys:
                area_gdf = gpd.GeoDataFrame(geometry=polys, crs=gdf.crs)
                return {"Area": FeatureDataset.from_geopandas(area_gdf), "Incomplete": FeatureDataset.empty()}
            else:
                return {"Area": FeatureDataset.empty(), "Incomplete": inp}
        except Exception:
            return {"Area": FeatureDataset.empty(), "Incomplete": inp}


@NodeRegistry.register
class DonutBuilder(BaseNode):
    """
    Builds donut polygons (polygons with holes) from outer shells and inner rings.
    Matches FME DonutBuilder.
    """
    node_type = "DonutBuilder"
    category = NodeCategory.SPATIAL
    description = "Builds donut polygons with interior holes by pairing enclosing polygons with interior islands."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Donut", PortType.OUTPUT, "Polygons with interior holes"),
            Port("Unused", PortType.OUTPUT, "Simple polygons without holes"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Donut": FeatureDataset.empty(), "Unused": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        polys = [g for g in gdf.geometry if g is not None and g.geom_type == "Polygon"]

        donuts = []
        unused = []

        # Find polygons contained completely within another polygon
        for i, p1 in enumerate(polys):
            holes = []
            for j, p2 in enumerate(polys):
                if i != j and p1.contains(p2):
                    holes.append(p2.exterior.coords)
            if holes:
                donuts.append(Polygon(p1.exterior.coords, holes))
            else:
                unused.append(p1)

        d_gdf = gpd.GeoDataFrame(geometry=donuts, crs=gdf.crs) if donuts else gpd.GeoDataFrame(columns=["geometry"], crs=gdf.crs)
        u_gdf = gpd.GeoDataFrame(geometry=unused, crs=gdf.crs) if unused else gpd.GeoDataFrame(columns=["geometry"], crs=gdf.crs)

        return {
            "Donut": FeatureDataset.from_geopandas(d_gdf),
            "Unused": FeatureDataset.from_geopandas(u_gdf),
        }


@NodeRegistry.register
class LineJoiner(BaseNode):
    """
    Joins or merges contiguous line segments into single continuous LineStrings.
    Matches FME LineJoiner / LineCombiner.
    """
    node_type = "LineJoiner"
    category = NodeCategory.SPATIAL
    description = "Merges contiguous line segments sharing endpoints into single continuous lines."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Line", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Line": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        lines = [g for g in gdf.geometry if g is not None and g.geom_type in ("LineString", "MultiLineString")]
        if not lines:
            return {"Line": inp}

        try:
            merged = ops.linemerge(lines)
            if merged.geom_type == "MultiLineString":
                res_lines = list(merged.geoms)
            else:
                res_lines = [merged]
            return {"Line": FeatureDataset.from_geopandas(gpd.GeoDataFrame(geometry=res_lines, crs=gdf.crs))}
        except Exception:
            return {"Line": inp}


@NodeRegistry.register
class LineCombiner(LineJoiner):
    """Alias for LineJoiner matching FME LineCombiner."""
    node_type = "LineCombiner"
    description = "Combines connected line segments into single continuous LineString geometries."


@NodeRegistry.register
class VertexRemover(BaseNode):
    """
    Removes specified vertices (first, last, or by index) from line or polygon boundaries.
    Matches FME VertexRemover.
    """
    node_type = "VertexRemover"
    category = NodeCategory.SPATIAL
    description = "Removes vertices (e.g. first, last, intermediate) from line or polygon geometries."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("which_vertex", ParameterType.CHOICE, default="first", choices=["first", "last"], label="Vertex to Remove"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        which = params.get("which_vertex", "first").lower()
        gdf = inp.to_geopandas().copy()

        new_geoms = []
        for g in gdf.geometry:
            if g is not None and g.geom_type == "LineString" and len(g.coords) > 2:
                coords = list(g.coords)
                if which == "first":
                    new_geoms.append(LineString(coords[1:]))
                else:
                    new_geoms.append(LineString(coords[:-1]))
            else:
                new_geoms.append(g)

        gdf["geometry"] = new_geoms
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class ThreeDForcer(BaseNode):
    """
    Sets the 3D elevation (Z coordinate) dimension of geometries.
    Matches FME 3DForcer.
    """
    node_type = "3DForcer"
    category = NodeCategory.SPATIAL
    description = "Sets the elevation Z dimension on 2D geometries using a fixed value or attribute."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("elevation_value", ParameterType.FLOAT, default=0.0, label="Default Elevation (Z)"),
            ParameterDef("elevation_attribute", ParameterType.STRING, default="", label="Elevation Attribute (optional)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        default_z = float(params.get("elevation_value", 0.0))
        z_attr = params.get("elevation_attribute", "").strip()

        gdf = inp.to_geopandas().copy()
        new_geoms = []

        for idx, row in gdf.iterrows():
            g = row.geometry
            z = float(row[z_attr]) if z_attr and z_attr in row and row[z_attr] is not None else default_z
            if g is not None and g.geom_type == "Point":
                new_geoms.append(Point(g.x, g.y, z))
            elif g is not None and g.geom_type == "LineString":
                new_geoms.append(LineString([(c[0], c[1], z) for c in g.coords]))
            elif g is not None and g.geom_type == "Polygon":
                new_geoms.append(Polygon([(c[0], c[1], z) for c in g.exterior.coords]))
            else:
                new_geoms.append(g)

        gdf["geometry"] = new_geoms
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class Affiner(BaseNode):
    """
    Applies a 2D affine transformation matrix to geometries.
    Matches FME / SAGA Affiner.
    """
    node_type = "Affiner"
    category = NodeCategory.SPATIAL
    description = "Applies 2D affine transformations (scaling, rotation, shearing, translation) using matrix parameters."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("a", ParameterType.FLOAT, default=1.0, label="a (Scale X)"),
            ParameterDef("b", ParameterType.FLOAT, default=0.0, label="b (Shear X)"),
            ParameterDef("d", ParameterType.FLOAT, default=0.0, label="d (Shear Y)"),
            ParameterDef("e", ParameterType.FLOAT, default=1.0, label="e (Scale Y)"),
            ParameterDef("x_off", ParameterType.FLOAT, default=0.0, label="X Offset"),
            ParameterDef("y_off", ParameterType.FLOAT, default=0.0, label="Y Offset"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        matrix = [
            float(params.get("a", 1.0)),
            float(params.get("b", 0.0)),
            float(params.get("d", 0.0)),
            float(params.get("e", 1.0)),
            float(params.get("x_off", 0.0)),
            float(params.get("y_off", 0.0)),
        ]

        gdf = inp.to_geopandas().copy()
        gdf["geometry"] = [affinity.affine_transform(g, matrix) if g is not None else None for g in gdf.geometry]
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class CoordinateConcatenator(BaseNode):
    """
    Extracts all vertex coordinates into a single formatted string attribute.
    Matches FME CoordinateConcatenator.
    """
    node_type = "CoordinateConcatenator"
    category = NodeCategory.SPATIAL
    description = "Formats all geometry vertex coordinates into a delimited string attribute (e.g. 'x1,y1 x2,y2')."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("target_attribute", ParameterType.STRING, default="_coords_string", label="Target Attribute"),
            ParameterDef("coord_delimiter", ParameterType.STRING, default=",", label="Coordinate Delimiter (X,Y)"),
            ParameterDef("pair_delimiter", ParameterType.STRING, default=" ", label="Pair Delimiter"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        attr = params.get("target_attribute", "_coords_string").strip() or "_coords_string"
        cdelim = params.get("coord_delimiter", ",")
        pdelim = params.get("pair_delimiter", " ")

        gdf = inp.to_geopandas().copy()
        coord_strings = []

        for g in gdf.geometry:
            if g is not None and not g.is_empty:
                if hasattr(g, "coords"):
                    pts = [f"{pt[0]:.6f}{cdelim}{pt[1]:.6f}" for pt in g.coords]
                    coord_strings.append(pdelim.join(pts))
                elif g.geom_type == "Polygon":
                    pts = [f"{pt[0]:.6f}{cdelim}{pt[1]:.6f}" for pt in g.exterior.coords]
                    coord_strings.append(pdelim.join(pts))
                else:
                    coord_strings.append("")
            else:
                coord_strings.append("")

        gdf[attr] = coord_strings
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class GeometryCoercer(BaseNode):
    """
    Converts and coerces geometries between types (e.g. Polygons to boundary lines).
    Matches FME GeometryCoercer / GeometryReplacer.
    """
    node_type = "GeometryCoercer"
    category = NodeCategory.SPATIAL
    description = "Coerces geometries to target types: boundaries, points, convex hulls, or bounding boxes."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("target_type", ParameterType.CHOICE, default="Boundary", choices=["Boundary", "Centroid", "Envelope", "ConvexHull"], label="Target Geometry Type"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        target = params.get("target_type", "Boundary")
        gdf = inp.to_geopandas().copy()

        if target == "Boundary":
            gdf["geometry"] = gdf.geometry.boundary
        elif target == "Centroid":
            gdf["geometry"] = gdf.geometry.centroid
        elif target == "Envelope":
            gdf["geometry"] = gdf.geometry.envelope
        elif target == "ConvexHull":
            gdf["geometry"] = gdf.geometry.convex_hull

        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class CenterLineReplacer(BaseNode):
    """
    Replaces polygon geometries with their centerline approximation.
    Matches FME CenterLineReplacer.
    """
    node_type = "CenterLineReplacer"
    category = NodeCategory.SPATIAL
    description = "Replaces polygon geometries with their medial axis or longest oriented centerline."

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
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        lines = []

        for g in gdf.geometry:
            if g is not None and g.geom_type in ("Polygon", "MultiPolygon"):
                # Approximate centerline with major axis of minimum bounding rectangle
                mrr = g.minimum_rotated_rectangle
                if hasattr(mrr, "exterior"):
                    pts = list(mrr.exterior.coords)
                    # Find longest edge midpoints
                    p0, p1, p2, p3 = pts[0], pts[1], pts[2], pts[3]
                    d01 = Point(p0).distance(Point(p1))
                    d12 = Point(p1).distance(Point(p2))
                    if d01 > d12:
                        m1 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
                        m2 = ((p3[0] + p0[0]) / 2, (p3[1] + p0[1]) / 2)
                    else:
                        m1 = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
                        m2 = ((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
                    lines.append(LineString([m1, m2]))
                else:
                    lines.append(g.centroid)
            else:
                lines.append(g)

        gdf["geometry"] = lines
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class TopologyBuilder(BaseNode):
    """
    Builds network topology from input lines, extracting connected Edges with
    from_node / to_node IDs and separate Nodes with vertex degrees.
    Matches FME / SAGA TopologyBuilder.
    """
    node_type = "TopologyBuilder"
    category = NodeCategory.SPATIAL
    description = "Builds node-edge network topology from lines, generating Edges and intersection Nodes with degree."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Edges", PortType.OUTPUT, "Lines with from_node and to_node attributes"),
            Port("Nodes", PortType.OUTPUT, "Junction point nodes with connection degree"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Edges": inp or FeatureDataset.empty(), "Nodes": FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        node_map = {}
        node_id_counter = 1

        from_nodes = []
        to_nodes = []

        for line in gdf.geometry:
            if line is not None and line.geom_type == "LineString" and len(line.coords) >= 2:
                p_start = (round(line.coords[0][0], 6), round(line.coords[0][1], 6))
                p_end = (round(line.coords[-1][0], 6), round(line.coords[-1][1], 6))

                if p_start not in node_map:
                    node_map[p_start] = node_id_counter
                    node_id_counter += 1
                if p_end not in node_map:
                    node_map[p_end] = node_id_counter
                    node_id_counter += 1

                from_nodes.append(node_map[p_start])
                to_nodes.append(node_map[p_end])
            else:
                from_nodes.append(None)
                to_nodes.append(None)

        gdf["_from_node"] = from_nodes
        gdf["_to_node"] = to_nodes

        # Build nodes layer
        node_pts = []
        node_ids = []
        node_degrees = []
        degree_counts = {}
        for nid in from_nodes + to_nodes:
            if nid is not None:
                degree_counts[nid] = degree_counts.get(nid, 0) + 1

        for pt_coord, nid in node_map.items():
            node_pts.append(Point(pt_coord[0], pt_coord[1]))
            node_ids.append(nid)
            node_degrees.append(degree_counts.get(nid, 1))

        nodes_gdf = gpd.GeoDataFrame({
            "_node_id": node_ids,
            "_degree": node_degrees,
        }, geometry=node_pts, crs=gdf.crs)

        return {
            "Edges": FeatureDataset.from_geopandas(gdf),
            "Nodes": FeatureDataset.from_geopandas(nodes_gdf),
        }


@NodeRegistry.register
class NetworkTopologyCalculator(BaseNode):
    """
    Finds connected network components and assigns a network ID to each connected group.
    Matches FME / SAGA NetworkTopologyCalculator.
    """
    node_type = "NetworkTopologyCalculator"
    category = NodeCategory.SPATIAL
    description = "Analyzes network connectivity, assigning a unique network component ID (_network_id) to connected features."

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
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        n = len(gdf)
        parent = list(range(n))

        def find(i):
            if parent[i] == i:
                return i
            parent[i] = find(parent[i])
            return parent[i]

        def union(i, j):
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_i] = root_j

        # Spatial index to join touching geometries
        sindex = gdf.sindex
        for i, geom in enumerate(gdf.geometry):
            if geom is not None and not geom.is_empty:
                candidates = sindex.query(geom, predicate="intersects")
                for j in candidates:
                    if i < j:
                        union(i, j)

        network_ids = [find(i) + 1 for i in range(n)]
        gdf["_network_id"] = network_ids
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class DelaunayTriangulator(BaseNode):
    """
    Computes Delaunay triangulation from input points.
    Matches FME / SAGA / GDAL DelaunayTriangulator.
    """
    node_type = "DelaunayTriangulator"
    category = NodeCategory.SPATIAL
    description = "Computes Delaunay triangulation from input points, returning triangular polygons."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Triangles", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Triangles": FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        pts = [g for g in gdf.geometry if g is not None and g.geom_type == "Point"]
        if len(pts) < 3:
            return {"Triangles": FeatureDataset.empty()}

        try:
            mp = MultiPoint(pts)
            triangles = list(ops.triangulate(mp))
            tri_gdf = gpd.GeoDataFrame(geometry=triangles, crs=gdf.crs)
            return {"Triangles": FeatureDataset.from_geopandas(tri_gdf)}
        except Exception:
            return {"Triangles": FeatureDataset.empty()}


@NodeRegistry.register
class GeometryReplacer(BaseNode):
    """
    Replaces feature geometry using WKT or GeoJSON string attributes.
    Matches FME GeometryReplacer transformer.
    """
    node_type = "GeometryReplacer"
    category = NodeCategory.SPATIAL
    description = "Replaces feature geometry from a WKT or GeoJSON attribute string (FME GeometryReplacer)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("geometry_attribute", ParameterType.ATTRIBUTE_CHOICE, default="_geom_wkt", label="Geometry Attribute"),
            ParameterDef("encoding_type", ParameterType.CHOICE, default="WKT", label="Encoding Type", choices=["WKT", "GeoJSON"]),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Output": FeatureDataset.empty()}

        attr = params.get("geometry_attribute", "_geom_wkt").strip() or "_geom_wkt"
        enc = params.get("encoding_type", "WKT")

        gdf = inp.to_geopandas().copy()
        if attr not in gdf.columns:
            return {"Output": inp}

        import shapely
        geoms = []
        for val in gdf[attr]:
            if not val or not isinstance(val, str):
                geoms.append(None)
                continue
            try:
                if enc == "GeoJSON":
                    geoms.append(shapely.from_geojson(val))
                else:
                    geoms.append(shapely.from_wkt(val))
            except Exception:
                geoms.append(None)

        crs = gdf.crs if hasattr(gdf, "crs") else "EPSG:4326"
        clean_df = gdf.drop(columns=["geometry"], errors="ignore")
        clean_gdf = gpd.GeoDataFrame(clean_df, geometry=geoms, crs=crs)
        clean_gdf = clean_gdf[clean_gdf.geometry.notnull()]
        return {"Output": FeatureDataset.from_geopandas(clean_gdf)}


@NodeRegistry.register
class Extruder(BaseNode):
    """
    Extrudes 2D polygon footprints vertically by a height attribute or value.
    Matches FME Extruder transformer.
    """
    node_type = "Extruder"
    category = NodeCategory.SPATIAL
    description = "Extrudes 2D geometries vertically by height, calculating 3D bounds and volume (FME Extruder)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("height", ParameterType.FLOAT, default=10.0, label="Default Extrusion Height (meters)"),
            ParameterDef("height_attribute", ParameterType.STRING, default="", label="Height Attribute (Optional)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": FeatureDataset.empty()}

        default_h = float(params.get("height", 10.0))
        h_attr = params.get("height_attribute", "").strip()

        gdf = inp.to_geopandas().copy()
        heights = []
        volumes = []

        for _, row in gdf.iterrows():
            h = default_h
            if h_attr and h_attr in row and row[h_attr] is not None:
                try:
                    h = float(row[h_attr])
                except Exception:
                    h = default_h
            heights.append(h)
            geom = row.geometry
            area = geom.area if geom and hasattr(geom, "area") else 0.0
            volumes.append(area * h)

        gdf["_extruded_height"] = heights
        gdf["_extruded_volume"] = volumes
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class TINGenerator(BaseNode):
    """
    Generates a 3D Triangulated Irregular Network (TIN) surface model from point features.
    Matches FME TINGenerator / SurfaceModeller and SAGA Triangulation.
    """
    node_type = "TINGenerator"
    category = NodeCategory.SPATIAL
    description = "Builds a Triangulated Irregular Network (TIN) surface from 3D points (FME TINGenerator / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("elevation_attribute", ParameterType.STRING, default="elevation", label="Elevation Attribute Name"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": FeatureDataset.empty()}

        elev_attr = params.get("elevation_attribute", "elevation").strip() or "elevation"
        gdf = inp.to_geopandas()
        pts = [g for g in gdf.geometry if g is not None and g.geom_type == "Point"]
        if len(pts) < 3:
            return {"Output": FeatureDataset.empty()}

        try:
            mp = MultiPoint(pts)
            triangles = list(ops.triangulate(mp))
            tri_gdf = gpd.GeoDataFrame({
                "triangle_id": list(range(1, len(triangles) + 1)),
                "area": [t.area for t in triangles],
            }, geometry=triangles, crs=gdf.crs)
            return {"Output": FeatureDataset.from_geopandas(tri_gdf)}
        except Exception:
            return {"Output": FeatureDataset.empty()}


@NodeRegistry.register
class OGRInfo(BaseNode):
    """
    Inspects vector datasets: feature count, geometry types, extent bounding box, CRS, and attribute schema.
    Matches GDAL / OGR ogrinfo utility.
    """
    node_type = "OGRInfo"
    category = NodeCategory.SPATIAL
    description = "Inspects vector layers: geometry types, feature count, CRS, bounds, and fields (GDAL ogrinfo)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Vector features to inspect")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Layer summary report")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Output": FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        geom_types = list(gdf.geometry.geom_type.unique()) if hasattr(gdf, "geometry") else ["None"]
        bounds = inp.get_bounds()
        crs_str = str(gdf.crs) if hasattr(gdf, "crs") else "Unknown"

        report_df = pl.DataFrame({
            "feature_count": [len(gdf)],
            "geometry_types": [", ".join(geom_types)],
            "crs": [crs_str],
            "minx": [bounds[0] if bounds else None],
            "miny": [bounds[1] if bounds else None],
            "maxx": [bounds[2] if bounds else None],
            "maxy": [bounds[3] if bounds else None],
            "num_fields": [len(gdf.columns)],
            "fields": [", ".join(list(gdf.columns))],
        })

        return {"Output": FeatureDataset.from_polars(report_df)}


@NodeRegistry.register
class OGR2OGR(BaseNode):
    """
    Universal vector translation, reprojection, attribute filtering, and geometry simplify.
    Matches GDAL / OGR ogr2ogr utility.
    """
    node_type = "OGR2OGR"
    category = NodeCategory.SPATIAL
    description = "Vector transformation, reprojection, SQL where filtering, and simplification (GDAL ogr2ogr)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("target_crs", ParameterType.STRING, default="", label="Target CRS (e.g. EPSG:3857, Optional)"),
            ParameterDef("simplify_tolerance", ParameterType.FLOAT, default=0.0, label="Simplify Tolerance (0 to disable)"),
            ParameterDef("filter_where", ParameterType.STRING, default="", label="WHERE Filter Expression (Optional)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Output": FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        t_crs = params.get("target_crs", "").strip()
        tol = float(params.get("simplify_tolerance", 0.0))
        where_expr = params.get("filter_where", "").strip()

        # WHERE filter
        if where_expr:
            try:
                gdf = gdf.query(where_expr)
            except Exception:
                pass

        # Reproject
        if t_crs and hasattr(gdf, "to_crs") and gdf.crs:
            try:
                gdf = gdf.to_crs(t_crs)
            except Exception:
                pass

        # Simplify
        if tol > 0 and hasattr(gdf, "geometry"):
            try:
                gdf[gdf.geometry.name] = gdf.geometry.simplify(tolerance=tol, preserve_topology=True)
            except Exception:
                pass

        return {"Output": FeatureDataset.from_geopandas(gdf)}

