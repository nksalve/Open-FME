"""
Writer nodes for saving features and datasets to disk files or databases.
"""

from typing import Any, Dict, List
import polars as pl
import geopandas as gpd
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


import os


def _ensure_dir(path: str):
    if path:
        try:
            parent = os.path.dirname(os.path.abspath(path))
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
        except Exception:
            pass


@NodeRegistry.register
class GeoJSONWriter(BaseNode):
    node_type = "GeoJSONWriter"
    category = NodeCategory.WRITER
    description = "Writes spatial features and geometries to a GeoJSON file."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Features to write")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Pass-through features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_SAVE, default="output.geojson", label="GeoJSON File Path", file_filter="GeoJSON Files (*.geojson);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        path = params.get("file_path", "output.geojson")
        _ensure_dir(path)
        gdf = inp.to_geopandas()
        gdf.to_file(path, driver="GeoJSON")
        return {"Output": inp}



@NodeRegistry.register
class ShapefileWriter(BaseNode):
    node_type = "ShapefileWriter"
    category = NodeCategory.WRITER
    description = "Writes vector features and attributes to an ESRI Shapefile (.shp)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Features to write")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Pass-through features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_SAVE, default="output.shp", label="Shapefile Path (.shp)", file_filter="ESRI Shapefiles (*.shp);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        path = params.get("file_path", "output.shp")
        _ensure_dir(path)
        gdf = inp.to_geopandas()
        gdf.to_file(path, driver="ESRI Shapefile")
        return {"Output": inp}


@NodeRegistry.register
class CSVWriter(BaseNode):
    node_type = "CSVWriter"
    category = NodeCategory.WRITER
    description = "Writes tabular features to a CSV file."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_SAVE, default="output.csv", label="CSV File Path", file_filter="CSV Files (*.csv);;All Files (*.*)"),
            ParameterDef("separator", ParameterType.STRING, default=",", label="Separator"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        path = params.get("file_path", "output.csv")
        _ensure_dir(path)
        sep = params.get("separator", ",")
        df = inp.to_polars()
        df.write_csv(path, separator=sep)
        return {"Output": inp}


@NodeRegistry.register
class ExcelWriter(BaseNode):
    node_type = "ExcelWriter"
    category = NodeCategory.WRITER
    description = "Writes tabular features to an Excel workbook (.xlsx)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_SAVE, default="output.xlsx", label="Excel File Path", file_filter="Excel Files (*.xlsx);;All Files (*.*)"),
            ParameterDef("sheet_name", ParameterType.STRING, default="Sheet1", label="Sheet Name"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        path = params.get("file_path", "output.xlsx")
        _ensure_dir(path)
        sheet = params.get("sheet_name", "Sheet1") or "Sheet1"
        df = inp.to_polars()
        df.write_excel(path, worksheet=sheet)
        return {"Output": inp}


@NodeRegistry.register
class ParquetWriter(BaseNode):
    node_type = "ParquetWriter"
    category = NodeCategory.WRITER
    description = "Writes features to Apache Parquet or GeoParquet format."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_SAVE, default="output.parquet", label="Parquet File Path", file_filter="Parquet Files (*.parquet);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        path = params.get("file_path", "output.parquet")
        _ensure_dir(path)
        if inp.has_geometry():
            gdf = inp.to_geopandas()
            gdf.to_parquet(path)
        else:
            df = inp.to_polars()
            df.write_parquet(path)
        return {"Output": inp}


@NodeRegistry.register
class GeoTIFFWriter(BaseNode):
    node_type = "GeoTIFFWriter"
    category = NodeCategory.WRITER
    description = "Writes raster data, DEMs, or vectorized features to a GeoTIFF raster file (.tif, .tiff)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Raster or spatial features to write")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Pass-through features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_SAVE, default="output.tif", label="GeoTIFF File Path", file_filter="GeoTIFF Files (*.tif *.tiff);;All Files (*.*)"),
            ParameterDef("compression", ParameterType.CHOICE, default="lzw", label="Compression", choices=["lzw", "deflate", "packbits", "none"]),
            ParameterDef("nodata", ParameterType.STRING, default="", label="NoData Value (Optional)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        path = params.get("file_path", "output.tif").strip() or "output.tif"
        _ensure_dir(path)

        import rasterio
        from rasterio.transform import from_origin, from_bounds
        import numpy as np

        compression = params.get("compression", "lzw").lower()
        compress_val = compression if compression != "none" else None
        nodata_str = params.get("nodata", "").strip()

        # 1. Input has native raster data or raster path
        if inp.has_raster():
            data, profile = inp.get_raster()
            if data is None and inp.raster_path and os.path.exists(inp.raster_path):
                with rasterio.open(inp.raster_path) as src:
                    data = src.read()
                    profile = src.profile.copy()

            if data is not None:
                prof = profile.copy() if profile else {}
                is_3d = (data.ndim == 3)
                count = data.shape[0] if is_3d else 1
                height = data.shape[1] if is_3d else data.shape[0]
                width = data.shape[2] if is_3d else data.shape[1]

                prof["driver"] = "GTiff"
                prof["height"] = height
                prof["width"] = width
                prof["count"] = count
                prof["dtype"] = str(data.dtype)
                if compress_val:
                    prof["compress"] = compress_val
                elif "compress" in prof:
                    del prof["compress"]

                if nodata_str:
                    try:
                        prof["nodata"] = float(nodata_str)
                    except ValueError:
                        pass

                if "transform" not in prof or prof["transform"] is None:
                    prof["transform"] = from_origin(0.0, float(height), 1.0, 1.0)
                if "crs" not in prof or prof["crs"] is None:
                    prof["crs"] = inp.crs or "EPSG:4326"

                with rasterio.open(path, "w", **prof) as dst:
                    if is_3d:
                        dst.write(data)
                    else:
                        dst.write(data, 1)

                return {"Output": inp}

        # 2. Check if tabular input points to an existing raster file
        try:
            df = inp.to_polars()
            for col in ["slope_output", "aspect_output", "hillshade_output", "output_raster", "raster_file", "dem_source"]:
                if col in df.columns and len(df) > 0:
                    val = df[col][0]
                    if val and isinstance(val, str) and os.path.exists(val):
                        with rasterio.open(val) as src:
                            prof = src.profile.copy()
                            prof["driver"] = "GTiff"
                            if compress_val:
                                prof["compress"] = compress_val
                            with rasterio.open(path, "w", **prof) as dst:
                                dst.write(src.read())
                        return {"Output": inp}
        except Exception:
            pass

        # 3. Vector rasterization fallback
        if inp.has_geometry():
            gdf = inp.to_geopandas()
            if not gdf.empty and hasattr(gdf, "geometry") and gdf.geometry is not None:
                import rasterio.features
                bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
                w, h = 512, 512
                dx = max(bounds[2] - bounds[0], 1e-6)
                dy = max(bounds[3] - bounds[1], 1e-6)
                transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], w, h)
                shapes = [(geom, 1) for geom in gdf.geometry if geom and not geom.is_empty]

                burned = rasterio.features.rasterize(
                    shapes=shapes,
                    out_shape=(h, w),
                    transform=transform,
                    fill=0,
                    dtype=np.uint8,
                )

                prof = {
                    "driver": "GTiff",
                    "height": h,
                    "width": w,
                    "count": 1,
                    "dtype": "uint8",
                    "crs": gdf.crs or "EPSG:4326",
                    "transform": transform,
                }
                if compress_val:
                    prof["compress"] = compress_val

                with rasterio.open(path, "w", **prof) as dst:
                    dst.write(burned, 1)

        return {"Output": inp}


@NodeRegistry.register
class RasterWriter(GeoTIFFWriter):
    node_type = "RasterWriter"
    category = NodeCategory.WRITER
    description = "Writes raster features or grid data to a GeoTIFF / raster file (.tif, .tiff)."


