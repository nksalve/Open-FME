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
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Raster bounding polygon")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
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
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Raster metadata table")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
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
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Per-band statistics table")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
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
        return []

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
        path = params.get("raster_path", "").strip()
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
