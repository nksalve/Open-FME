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

