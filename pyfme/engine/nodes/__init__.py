"""
Expose and auto-register all built-in nodes.
"""

from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType, format_tool_name
)
import pyfme.engine.nodes.readers
import pyfme.engine.nodes.transformers.attributes
import pyfme.engine.nodes.transformers.spatial
import pyfme.engine.nodes.transformers.spatial_geoprocessing
import pyfme.engine.nodes.transformers.spatial_geometry
import pyfme.engine.nodes.transformers.fme_overlay
import pyfme.engine.nodes.transformers.fme_spatial_relations
import pyfme.engine.nodes.transformers.fme_geometry_tools
import pyfme.engine.nodes.transformers.fme_attribute_tools
import pyfme.engine.nodes.transformers.fme_automation
import pyfme.engine.nodes.transformers.fme_raster
import pyfme.engine.nodes.transformers.scripting
import pyfme.engine.nodes.transformers.fme_workbench_tools
import pyfme.engine.nodes.transformers.fme_core_transformers
import pyfme.engine.nodes.transformers.fme_gdal_saga_vector
import pyfme.engine.nodes.transformers.fme_gdal_saga_attributes
import pyfme.engine.nodes.transformers.fme_gdal_saga_raster
import pyfme.engine.nodes.writers

__all__ = [
    "BaseNode",
    "NodeCategory",
    "Port",
    "PortType",
    "ParameterDef",
    "ParameterType",
    "format_tool_name",
]
