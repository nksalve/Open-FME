"""
Spatial Transformers (Reprojector, Bufferer, CentroidExtractor, SpatialFilter, etc.)
Leveraging GeoPandas, Shapely, and PyProj for professional GIS and CAD data pipelines.
"""

from typing import Any, Dict, List
import geopandas as gpd
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class Reprojector(BaseNode):
    """
    Transforms coordinates of vector geometries to a new Coordinate Reference System (CRS).
    """
    node_type = "Reprojector"
    category = NodeCategory.SPATIAL
    description = "Reprojects features from source CRS to destination CRS (e.g. EPSG:3857, EPSG:4326)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("destination_crs", ParameterType.STRING, default="EPSG:3857", label="Destination CRS (e.g. EPSG:3857)"),
            ParameterDef("source_crs_override", ParameterType.STRING, default="", label="Source CRS Override (if missing)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        target_crs = params.get("destination_crs", "EPSG:3857").strip()
        source_override = params.get("source_crs_override", "").strip()

        if source_override and (gdf.crs is None or not gdf.crs):
            gdf = gdf.set_crs(source_override, allow_override=True)
        elif gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")

        reprojected_gdf = gdf.to_crs(target_crs)
        return {"Output": FeatureDataset.from_geopandas(reprojected_gdf)}


@NodeRegistry.register
class Bufferer(BaseNode):
    """
    Expands or contracts geometries by a specified buffer distance.
    """
    node_type = "Bufferer"
    category = NodeCategory.SPATIAL
    description = "Expands points, lines, or polygons into a buffer zone by distance in CRS units."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("buffer_distance", ParameterType.FLOAT, default=100.0, label="Buffer Distance"),
            ParameterDef("resolution", ParameterType.INTEGER, default=16, label="Segment Resolution"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        if "geometry" not in gdf.columns or not hasattr(gdf, "geometry") or gdf.geometry.isnull().all():
            for x_col, y_col in [("lon", "lat"), ("longitude", "latitude"), ("x", "y"), ("X", "Y")]:
                if x_col in gdf.columns and y_col in gdf.columns:
                    gdf = gpd.GeoDataFrame(gdf, geometry=gpd.points_from_xy(gdf[x_col], gdf[y_col]), crs="EPSG:4326")
                    break

        if "geometry" not in gdf.columns or not hasattr(gdf, "geometry") or gdf.geometry.isnull().all():
            return {"Output": inp}

        import warnings
        distance = float(params.get("buffer_distance", 100.0))
        res = int(params.get("resolution", 16))

        # Precision handling: if CRS is geographic and distance is specified in meters (> 0.05), use local UTM
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            if gdf.crs and getattr(gdf.crs, "is_geographic", False) and distance > 0.05:
                try:
                    utm_crs = gdf.estimate_utm_crs()
                    if utm_crs:
                        proj = gdf.to_crs(utm_crs)
                        proj[proj.geometry.name] = proj.geometry.buffer(distance, resolution=res)
                        gdf = proj.to_crs(gdf.crs)
                    else:
                        gdf[gdf.geometry.name] = gdf.geometry.buffer(distance, resolution=res)
                except Exception:
                    gdf[gdf.geometry.name] = gdf.geometry.buffer(distance, resolution=res)
            else:
                gdf[gdf.geometry.name] = gdf.geometry.buffer(distance, resolution=res)

        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class CentroidExtractor(BaseNode):
    """
    Extracts the center point (centroid) of polygons or lines.
    """
    node_type = "CentroidExtractor"
    category = NodeCategory.SPATIAL
    description = "Replaces polygon or line geometries with their center point (centroid)."

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
        gdf[gdf.geometry.name] = gdf.geometry.centroid
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class AreaCalculator(BaseNode):
    """
    Calculates polygon area in square units and attaches as attribute.
    """
    node_type = "AreaCalculator"
    category = NodeCategory.SPATIAL
    description = "Calculates polygon area and writes to attribute '_area'."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("result_attribute", ParameterType.STRING, default="_area", label="Output Area Attribute"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        attr_name = params.get("result_attribute", "_area").strip() or "_area"

        if gdf.crs and getattr(gdf.crs, "is_geographic", False):
            try:
                utm_crs = gdf.estimate_utm_crs()
                gdf[attr_name] = gdf.to_crs(utm_crs).geometry.area if utm_crs else gdf.geometry.area
            except Exception:
                gdf[attr_name] = gdf.geometry.area
        else:
            gdf[attr_name] = gdf.geometry.area

        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class LengthCalculator(BaseNode):
    """
    Calculates line or perimeter length in units and attaches as attribute.
    """
    node_type = "LengthCalculator"
    category = NodeCategory.SPATIAL
    description = "Calculates line length and writes to attribute '_length'."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("result_attribute", ParameterType.STRING, default="_length", label="Output Length Attribute"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        attr_name = params.get("result_attribute", "_length").strip() or "_length"

        if gdf.crs and getattr(gdf.crs, "is_geographic", False):
            try:
                utm_crs = gdf.estimate_utm_crs()
                gdf[attr_name] = gdf.to_crs(utm_crs).geometry.length if utm_crs else gdf.geometry.length
            except Exception:
                gdf[attr_name] = gdf.geometry.length
        else:
            gdf[attr_name] = gdf.geometry.length

        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class BoundingBoxReplacer(BaseNode):
    """
    Replaces geometries with their rectangular bounding envelope.
    """
    node_type = "BoundingBoxReplacer"
    category = NodeCategory.SPATIAL
    description = "Replaces geometries with their minimum rectangular bounding box (envelope)."

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
        gdf[gdf.geometry.name] = gdf.geometry.envelope
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class CoordinateExtractor(BaseNode):
    """
    Extracts X, Y coordinates of point geometries into tabular attributes.
    """
    node_type = "CoordinateExtractor"
    category = NodeCategory.SPATIAL
    description = "Extracts X and Y coordinates into attributes '_x' and '_y'."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("x_attribute", ParameterType.STRING, default="_x", label="X Attribute Name"),
            ParameterDef("y_attribute", ParameterType.STRING, default="_y", label="Y Attribute Name"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas().copy()
        x_col = params.get("x_attribute", "_x") or "_x"
        y_col = params.get("y_attribute", "_y") or "_y"

        # Extract centroids coordinates if not point
        gdf[x_col] = gdf.geometry.centroid.x
        gdf[y_col] = gdf.geometry.centroid.y
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class VertexCreator(BaseNode):
    """
    Creates Point geometries from X/Longitude and Y/Latitude attribute columns.
    Equivalent to FME's 2DPointReplacer / VertexCreator.
    """
    node_type = "VertexCreator"
    category = NodeCategory.SPATIAL
    description = "Constructs Point geometries from X and Y attribute coordinates."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("x_attribute", ParameterType.STRING, default="lon", label="X / Longitude Attribute"),
            ParameterDef("y_attribute", ParameterType.STRING, default="lat", label="Y / Latitude Attribute"),
            ParameterDef("crs", ParameterType.STRING, default="EPSG:4326", label="Coordinate System (CRS)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        df = inp.to_polars()
        x_col = params.get("x_attribute", "lon").strip()
        y_col = params.get("y_attribute", "lat").strip()
        crs_val = params.get("crs", "EPSG:4326").strip()

        if x_col not in df.columns or y_col not in df.columns:
            return {"Output": inp}

        # Convert to pandas/geopandas with Point geometries
        pdf = df.to_pandas()
        from shapely.geometry import Point
        geometries = [Point(xy) for xy in zip(pdf[x_col].astype(float), pdf[y_col].astype(float))]
        gdf = gpd.GeoDataFrame(pdf, geometry=geometries, crs=crs_val)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class SpatialFilter(BaseNode):
    """
    Tests spatial relationships between Filter (Base) and Candidate features.
    Routes Candidates to 'Passed' (meets spatial relation) or 'Failed'.
    """
    node_type = "SpatialFilter"
    category = NodeCategory.SPATIAL
    description = "Filters Candidate features against Base boundaries (Intersects, Within, Contains)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Base", PortType.INPUT, "Filter boundary geometry"),
            Port("Candidate", PortType.INPUT, "Features to be tested"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Passed", PortType.OUTPUT, "Candidates meeting spatial criteria"),
            Port("Failed", PortType.OUTPUT, "Candidates not meeting spatial criteria"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef(
                "predicate",
                ParameterType.CHOICE,
                default="intersects",
                choices=["intersects", "within", "contains", "touches"],
                label="Spatial Test",
            ),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        base_ds = inputs.get("Base")
        cand_ds = inputs.get("Candidate")

        if not cand_ds or cand_ds.count() == 0:
            return {"Passed": FeatureDataset.empty(), "Failed": FeatureDataset.empty()}
        if not base_ds or base_ds.count() == 0 or not base_ds.has_geometry():
            # If no base boundaries, all candidates fail
            return {"Passed": FeatureDataset.empty(), "Failed": cand_ds}

        base_gdf = base_ds.to_geopandas()
        cand_gdf = cand_ds.to_geopandas()

        # Align CRS if differing
        if base_gdf.crs and cand_gdf.crs and base_gdf.crs != cand_gdf.crs:
            base_gdf = base_gdf.to_crs(cand_gdf.crs)

        pred = params.get("predicate", "intersects")
        
        # Spatial join to find matching candidates
        joined = gpd.sjoin(cand_gdf, base_gdf, how="inner", predicate=pred)
        passed_indices = set(joined.index)

        passed_gdf = cand_gdf.loc[cand_gdf.index.isin(passed_indices)]
        failed_gdf = cand_gdf.loc[~cand_gdf.index.isin(passed_indices)]

        return {
            "Passed": FeatureDataset.from_geopandas(passed_gdf),
            "Failed": FeatureDataset.from_geopandas(failed_gdf),
        }
