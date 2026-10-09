"""
Reader nodes for extracting data from files and endpoints.
"""

from typing import Any, Dict, List
import polars as pl
import geopandas as gpd
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class CSVReader(BaseNode):
    node_type = "CSVReader"
    category = NodeCategory.READER
    description = "Reads tabular data from a CSV or TSV file using high-speed Polars."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Loaded tabular features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_OPEN, default="", label="CSV File Path", file_filter="CSV Files (*.csv *.tsv);;All Files (*.*)"),
            ParameterDef("delimiter", ParameterType.STRING, default=",", label="Delimiter"),
            ParameterDef("has_header", ParameterType.BOOLEAN, default=True, label="Has Header"),
            ParameterDef("ignore_errors", ParameterType.BOOLEAN, default=True, label="Ignore Parse Errors"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("file_path", "")
        if not path:
            return {"Output": FeatureDataset.empty()}
        
        sep = params.get("delimiter", ",") or ","
        has_header = params.get("has_header", True)
        ignore_errors = params.get("ignore_errors", True)

        df = pl.read_csv(
            path,
            separator=sep,
            has_header=has_header,
            ignore_errors=ignore_errors,
            infer_schema_length=10000,
        )
        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class GeoJSONReader(BaseNode):
    node_type = "GeoJSONReader"
    category = NodeCategory.READER
    description = "Reads vector spatial features and geometries from a GeoJSON file."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Spatial features with geometry")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_OPEN, default="", label="GeoJSON File Path", file_filter="GeoJSON Files (*.geojson *.json);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("file_path", "")
        if not path:
            return {"Output": FeatureDataset.empty()}

        gdf = gpd.read_file(path)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class ShapefileReader(BaseNode):
    node_type = "ShapefileReader"
    category = NodeCategory.READER
    description = "Reads ESRI Shapefile vector features and attributes (.shp)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Shapefile spatial features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_OPEN, default="", label="Shapefile Path (.shp)", file_filter="ESRI Shapefiles (*.shp);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("file_path", "")
        if not path:
            return {"Output": FeatureDataset.empty()}

        gdf = gpd.read_file(path)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class ExcelReader(BaseNode):
    node_type = "ExcelReader"
    category = NodeCategory.READER
    description = "Reads Excel worksheets (.xlsx, .xls) into tabular features."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Excel features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_OPEN, default="", label="Excel File Path", file_filter="Excel Files (*.xlsx *.xls);;All Files (*.*)"),
            ParameterDef("sheet_name", ParameterType.STRING, default="", label="Sheet Name (Blank for first)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("file_path", "")
        if not path:
            return {"Output": FeatureDataset.empty()}

        sheet = params.get("sheet_name") or None
        df = pl.read_excel(path, sheet_name=sheet)
        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class ParquetReader(BaseNode):
    node_type = "ParquetReader"
    category = NodeCategory.READER
    description = "Reads columnar Apache Parquet or GeoParquet files."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Parquet features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_OPEN, default="", label="Parquet File Path", file_filter="Parquet Files (*.parquet);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("file_path", "")
        if not path:
            return {"Output": FeatureDataset.empty()}

        try:
            # Try reading as GeoParquet first if spatial
            gdf = gpd.read_parquet(path)
            return {"Output": FeatureDataset.from_geopandas(gdf)}
        except Exception:
            df = pl.read_parquet(path)
            return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class GeoTIFFReader(BaseNode):
    node_type = "GeoTIFFReader"
    category = NodeCategory.READER
    description = "Reads raster imagery, DEMs, and grid data from GeoTIFF / TIFF files (.tif, .tiff)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Loaded raster features and imagery")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("file_path", ParameterType.FILE_OPEN, default="", label="GeoTIFF / TIFF File Path", file_filter="GeoTIFF / Raster Files (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("band_index", ParameterType.INTEGER, default=0, label="Band Index (0 for All Bands)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        import os
        path = params.get("file_path", "").strip()
        if not path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        import rasterio
        band_idx = int(params.get("band_index", 0))

        with rasterio.open(path) as src:
            profile = src.profile.copy()
            crs_str = src.crs.to_string() if src.crs else "EPSG:4326"
            if band_idx > 0 and band_idx <= src.count:
                data = src.read(band_idx)
                profile["count"] = 1
            else:
                data = src.read()

        return {"Output": FeatureDataset.from_raster(data, profile=profile, raster_path=path, crs=crs_str)}


@NodeRegistry.register
class RasterReader(GeoTIFFReader):
    node_type = "RasterReader"
    category = NodeCategory.READER
    description = "Reads raster datasets, imagery, and DEM grids from GeoTIFF / TIFF and raster files."

