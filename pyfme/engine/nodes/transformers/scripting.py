"""
Scripting and Automation nodes (PythonCaller, SystemCaller).
Enables custom Python code execution within the visual pipeline.
"""

from typing import Any, Dict, List
import subprocess
import polars as pl
import geopandas as gpd
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry

DEFAULT_PYTHON_CODE = '''# PythonCaller Custom Script
# Inputs:
#   'dataset': FeatureDataset instance
#   'df': polars.DataFrame (columnar attributes)
#   'gdf': geopandas.GeoDataFrame (if spatial geometries present)
# Output:
#   Must assign result to variable 'output_df' or 'output_gdf' or 'output_dataset'

import polars as pl

# Example: Create an uppercase version of string columns or custom calculation
output_df = df
'''


@NodeRegistry.register
class PythonCaller(BaseNode):
    """
    Executes arbitrary Python code on incoming features.
    Provides direct access to Polars DataFrames, GeoPandas, and Shapely.
    """
    node_type = "PythonCaller"
    category = NodeCategory.SCRIPTING
    description = "Executes custom Python script on features with Polars and GeoPandas access."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("python_code", ParameterType.CODE, default=DEFAULT_PYTHON_CODE, label="Python Script"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp:
            return {"Output": FeatureDataset.empty()}

        code = params.get("python_code", DEFAULT_PYTHON_CODE)

        # Prepare execution environment
        df = inp.to_polars()
        gdf = inp.to_geopandas() if inp.has_geometry() else None

        scope = {
            "dataset": inp,
            "df": df,
            "gdf": gdf,
            "pl": pl,
            "gpd": gpd,
            "output_dataset": None,
            "output_df": None,
            "output_gdf": None,
        }

        # Execute code in isolated namespace
        exec(code, scope)

        if scope.get("output_dataset") is not None:
            return {"Output": scope["output_dataset"]}
        elif scope.get("output_gdf") is not None:
            return {"Output": FeatureDataset.from_geopandas(scope["output_gdf"])}
        elif scope.get("output_df") is not None:
            res_df = scope["output_df"]
            if inp.has_geometry() and inp.geometry_col in res_df.columns:
                return {"Output": FeatureDataset.from_polars(res_df, geometry_col=inp.geometry_col, crs=inp.crs)}
            return {"Output": FeatureDataset.from_polars(res_df)}
        else:
            # Default pass through if no output assigned
            return {"Output": inp}


@NodeRegistry.register
class SystemCaller(BaseNode):
    """
    Executes an external shell command or CLI script.
    """
    node_type = "SystemCaller"
    category = NodeCategory.SCRIPTING
    description = "Executes an external system shell command or batch script."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Output", PortType.OUTPUT, "Incoming features passed through"),
            Port("CommandOutput", PortType.OUTPUT, "Standard output from shell command"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("command", ParameterType.STRING, default="echo Running...", label="Command Line"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        cmd = params.get("command", "")
        inp = inputs.get("Input", FeatureDataset.empty())

        stdout_text = ""
        exit_code = 0
        if cmd.strip():
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            stdout_text = proc.stdout
            exit_code = proc.returncode

        res_df = pl.DataFrame({
            "command": [cmd],
            "exit_code": [exit_code],
            "stdout": [stdout_text.strip()],
        })

        return {
            "Output": inp,
            "CommandOutput": FeatureDataset.from_polars(res_df),
        }
