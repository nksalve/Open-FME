"""
open-FME Engine Package.
"""

import os
import importlib.util

# Normalize PROJ and GDAL environment variables to prevent Windows PostGIS / PostgreSQL collisions
def _ensure_proj_data():
    try:
        spec = importlib.util.find_spec("rasterio")
        if spec and spec.origin:
            r_dir = os.path.dirname(spec.origin)
            proj_dir = os.path.join(r_dir, "proj_data")
            if os.path.exists(proj_dir):
                os.environ["PROJ_LIB"] = proj_dir
                os.environ["PROJ_DATA"] = proj_dir
            gdal_dir = os.path.join(r_dir, "gdal_data")
            if os.path.exists(gdal_dir):
                os.environ["GDAL_DATA"] = gdal_dir
            elif "GDAL_DATA" in os.environ and "postgresql" in os.environ["GDAL_DATA"].lower():
                del os.environ["GDAL_DATA"]
    except Exception:
        pass

_ensure_proj_data()

from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry
from pyfme.engine.graph import WorkflowGraph, Connection
from pyfme.engine.runner import WorkflowRunner
from pyfme.engine.nodes.base import BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType

__all__ = [
    "FeatureDataset",
    "NodeRegistry",
    "WorkflowGraph",
    "Connection",
    "WorkflowRunner",
    "BaseNode",
    "NodeCategory",
    "Port",
    "PortType",
    "ParameterDef",
    "ParameterType",
]
