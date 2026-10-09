"""
FME Raster Transformers from FME_Transformers_GIS.xlsx:
- RasterExtentsCoercer (Creates a polygon of the raster extent)
- RasterPropertyExtractor (Cell size, extents, number of bands, CRS)
- RasterStatisticsCalculator (Min, max, mean, standard deviation per band)
- RasterToPolygonCoercer (Converts raster cells to polygons / vectorization)
"""

from typing import Any, Dict, List
import rasterio
from rasterio.features import shapes
import numpy as np
import geopandas as gpd
from shapely.geometry import box, shape
import polars as pl
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class RasterExtentsCoercer(BaseNode):
    """
    Creates a polygon vector feature of the raster extent.
    FME RasterExtentsCoercer transformer.
    """
    node_type = "RasterExtentsCoercer"
    category = NodeCategory.SPATIAL
    description = "Extracts bounding extent polygon from a raster file (FME RasterExtentsCoercer)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Raster dataset (Optional)")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Raster bounding polygon")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        path = params.get("raster_path", "").strip()
        if not path and inp is not None:
            if getattr(inp, "raster_path", None):
                path = inp.raster_path
            elif inp.has_raster():
                return {"Output": FeatureDataset.from_geopandas(inp.to_geopandas())}

        if not path:
            return {"Output": FeatureDataset.empty()}

        with rasterio.open(path) as src:
            b = src.bounds
            crs = src.crs.to_string() if src.crs else "EPSG:4326"
            geom = box(b.left, b.bottom, b.right, b.top)
            gdf = gpd.GeoDataFrame({
                "raster_file": [path],
                "width": [src.width],
                "height": [src.height],
                "bands": [src.count],
            }, geometry=[geom], crs=crs)

        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class RasterPropertyExtractor(BaseNode):
    """
    Extracts raster metadata: dimensions, resolution, bounds, CRS, band count.
    FME RasterPropertyExtractor transformer.
    """
    node_type = "RasterPropertyExtractor"
    category = NodeCategory.SPATIAL
    description = "Extracts raster dimensions, cell size, and CRS properties (FME RasterPropertyExtractor)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Raster dataset (Optional)")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Raster metadata table")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        path = params.get("raster_path", "").strip()
        if not path and inp is not None:
            if getattr(inp, "raster_path", None):
                path = inp.raster_path
            elif inp.has_raster():
                prof = inp.raster_profile
                data, _ = inp.get_raster()
                w = prof.get("width", 0)
                h = prof.get("height", 0)
                if data is not None and (not w or not h):
                    h = data.shape[-2]
                    w = data.shape[-1]
                b = inp.get_raster_bounds() or (0.0, 0.0, 1.0, 1.0)
                trans = prof.get("transform")
                dx = abs(trans.a if hasattr(trans, "a") else (trans[0] if trans else 1.0))
                dy = abs(trans.e if hasattr(trans, "e") else (trans[4] if trans else 1.0))
                bands = prof.get("count", 1 if data is None or data.ndim == 2 else data.shape[0])
                df = pl.DataFrame({
                    "raster_file": [inp.raster_path or "(In-memory raster)"],
                    "width_pixels": [w],
                    "height_pixels": [h],
                    "cell_size_x": [float(dx)],
                    "cell_size_y": [float(dy)],
                    "minx": [b[0]],
                    "miny": [b[1]],
                    "maxx": [b[2]],
                    "maxy": [b[3]],
                    "num_bands": [bands],
                    "crs": [str(inp.crs or "EPSG:4326")],
                    "driver": [prof.get("driver", "GTiff")],
                })
                return {"Output": FeatureDataset.from_polars(df)}

        if not path:
            return {"Output": FeatureDataset.empty()}

        with rasterio.open(path) as src:
            b = src.bounds
            crs = src.crs.to_string() if src.crs else "EPSG:4326"
            df = pl.DataFrame({
                "raster_file": [path],
                "width_pixels": [src.width],
                "height_pixels": [src.height],
                "cell_size_x": [abs(src.transform[0])],
                "cell_size_y": [abs(src.transform[4])],
                "minx": [b.left],
                "miny": [b.bottom],
                "maxx": [b.right],
                "maxy": [b.top],
                "num_bands": [src.count],
                "crs": [crs],
                "driver": [src.driver],
            })

        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class RasterStatisticsCalculator(BaseNode):
    """
    Calculates min, max, mean, standard deviation per band.
    FME RasterStatisticsCalculator transformer.
    """
    node_type = "RasterStatisticsCalculator"
    category = NodeCategory.SPATIAL
    description = "Calculates min, max, mean, std per raster band (FME RasterStatisticsCalculator)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Raster dataset (Optional)")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Per-band statistics table")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        path = params.get("raster_path", "").strip()
        if not path and inp is not None:
            if getattr(inp, "raster_path", None):
                path = inp.raster_path
            elif inp.has_raster():
                data, prof = inp.get_raster()
                if data is not None:
                    rows = []
                    is_3d = (data.ndim == 3)
                    count = data.shape[0] if is_3d else 1
                    for b_idx in range(1, count + 1):
                        band_arr = data[b_idx - 1] if is_3d else data
                        nodata_val = prof.get("nodata")
                        if nodata_val is not None:
                            valid_data = band_arr[band_arr != nodata_val]
                        else:
                            valid_data = band_arr
                        rows.append({
                            "band": b_idx,
                            "min": float(np.nanmin(valid_data)) if valid_data.size > 0 else None,
                            "max": float(np.nanmax(valid_data)) if valid_data.size > 0 else None,
                            "mean": float(np.nanmean(valid_data)) if valid_data.size > 0 else None,
                            "std": float(np.nanstd(valid_data)) if valid_data.size > 0 else None,
                            "valid_cells": int(valid_data.size),
                        })
                    return {"Output": FeatureDataset.from_polars(pl.DataFrame(rows))}

        if not path:
            return {"Output": FeatureDataset.empty()}

        rows = []
        with rasterio.open(path) as src:
            for b_idx in range(1, src.count + 1):
                data = src.read(b_idx, masked=True)
                rows.append({
                    "band": b_idx,
                    "min": float(data.min()) if data.count() > 0 else None,
                    "max": float(data.max()) if data.count() > 0 else None,
                    "mean": float(data.mean()) if data.count() > 0 else None,
                    "std": float(data.std()) if data.count() > 0 else None,
                    "valid_cells": int(data.count()),
                })

        df = pl.DataFrame(rows)
        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class RasterToPolygonCoercer(BaseNode):
    """
    Converts raster cells into polygon vector features (vectorization).
    FME RasterToPolygonCoercer transformer.
    """
    node_type = "RasterToPolygonCoercer"
    category = NodeCategory.SPATIAL
    description = "Vectorizes raster cells into polygon features (FME RasterToPolygonCoercer)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Raster dataset (Optional)")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Vectorized polygon features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("band_index", ParameterType.INTEGER, default=1, label="Band Index to Vectorize"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        path = params.get("raster_path", "").strip()
        if not path and inp is not None:
            if getattr(inp, "raster_path", None):
                path = inp.raster_path
            elif inp.has_raster():
                data, prof = inp.get_raster()
                if data is not None:
                    band_idx = int(params.get("band_index", 1))
                    is_3d = (data.ndim == 3)
                    band_data = data[band_idx - 1] if is_3d else data
                    crs = str(inp.crs or prof.get("crs") or "EPSG:4326")
                    nodata = prof.get("nodata")
                    mask = band_data != nodata if nodata is not None else None
                    trans = prof.get("transform")
                    polys, vals = [], []
                    for geom_dict, val in shapes(band_data, mask=mask, transform=trans):
                        polys.append(shape(geom_dict))
                        vals.append(float(val))
                    gdf = gpd.GeoDataFrame({"pixel_value": vals}, geometry=polys, crs=crs)
                    return {"Output": FeatureDataset.from_geopandas(gdf)}

        if not path:
            return {"Output": FeatureDataset.empty()}

        band_idx = int(params.get("band_index", 1))
        polys = []
        vals = []

        with rasterio.open(path) as src:
            data = src.read(band_idx)
            crs = src.crs.to_string() if src.crs else "EPSG:4326"
            mask = data != src.nodata if src.nodata is not None else None

            for geom_dict, val in shapes(data, mask=mask, transform=src.transform):
                polys.append(shape(geom_dict))
                vals.append(float(val))

        gdf = gpd.GeoDataFrame({"pixel_value": vals}, geometry=polys, crs=crs)
        return {"Output": FeatureDataset.from_geopandas(gdf)}
