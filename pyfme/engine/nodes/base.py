"""
Base node definitions, Ports, and execution interface for all FME-style transformers.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pyfme.engine.dataset import FeatureDataset


class NodeCategory(str, Enum):
    READER = "Readers (Inputs)"
    ATTRIBUTE = "Attribute Transformers"
    SPATIAL = "Spatial Transformers"
    SCRIPTING = "Scripting & Automation"
    WRITER = "Writers (Outputs)"


class PortType(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


class Port:
    """Represents a connection pin on a node."""
    def __init__(self, name: str, port_type: PortType, description: str = ""):
        self.name = name
        self.port_type = port_type
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "port_type": self.port_type.value,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Port:
        return cls(
            name=data["name"],
            port_type=PortType(data["port_type"]),
            description=data.get("description", ""),
        )


class ParameterType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    FILE_OPEN = "file_open"
    FILE_SAVE = "file_save"
    CHOICE = "choice"
    CODE = "code"
    ATTRIBUTE_CHOICE = "attribute_choice"
    EXPRESSION = "expression"


class ParameterDef:
    """Describes a configurable parameter on a node."""
    def __init__(
        self,
        name: str,
        param_type: ParameterType,
        default: Any = None,
        label: Optional[str] = None,
        choices: Optional[List[str]] = None,
        description: str = "",
        file_filter: str = "All Files (*.*)",
    ):
        self.name = name
        self.param_type = param_type
        self.default = default
        self.label = label or name.replace("_", " ").title()
        self.choices = choices or []
        self.description = description
        self.file_filter = file_filter

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "param_type": self.param_type.value,
            "default": self.default,
            "label": self.label,
            "choices": self.choices,
            "description": self.description,
            "file_filter": self.file_filter,
        }


SPECIAL_TOOL_NAMES = {
    "2DForcer": "2D Forcer",
    "3DForcer": "3D Forcer",
    "GeoJSONReader": "GeoJSON Reader",
    "GeoJSONWriter": "GeoJSON Writer",
    "GeoTIFFReader": "GeoTIFF Reader",
    "GeoTIFFWriter": "GeoTIFF Writer",
    "RasterReader": "Raster Reader",
    "RasterWriter": "Raster Writer",
    "OGR2OGR": "OGR2OGR",
}


def format_tool_name(name: str, separator: str = " ") -> str:
    """
    Formats a tool/node class or type name into a clean, human-readable name.
    e.g. 'CSVReader' -> 'CSV Reader' (or 'CSV-Reader' if separator='-')
         'GeoJSONReader' -> 'GeoJSON Reader'
         'VertexCreator' -> 'Vertex Creator'
         'AreaOnAreaOverlayer' -> 'Area On Area Overlayer'
    """
    if not name:
        return ""
    if separator == " " and name in SPECIAL_TOOL_NAMES:
        return SPECIAL_TOOL_NAMES[name]
    elif separator == "-" and name in SPECIAL_TOOL_NAMES:
        return SPECIAL_TOOL_NAMES[name].replace(" ", "-")

    import re
    # 1. Acronym followed by capitalized word: e.g. CSVReader -> CSV Reader
    res = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1' + separator + r'\2', name)
    # 2. Lowercase/digit followed by capital: e.g. AreaBuilder -> Area Builder, 2DForcer -> 2D Forcer
    res = re.sub(r'([a-z\d])([A-Z])', r'\1' + separator + r'\2', res)
    return res


class BaseNode:
    """
    Abstract base class for all FME Readers, Transformers, and Writers.
    Every node declares its inputs, outputs, parameters, and execution logic.
    """

    node_type: str = "BaseNode"
    display_name: Optional[str] = None
    category: NodeCategory = NodeCategory.ATTRIBUTE
    description: str = "Base processing node"

    @classmethod
    def get_display_name(cls, separator: str = " ") -> str:
        """Return the formatted human-readable display name for this node (e.g. 'CSV Reader')."""
        if cls.display_name:
            if separator == "-":
                return cls.display_name.replace(" ", "-")
            return cls.display_name
        return format_tool_name(cls.node_type, separator=separator)

    def __init__(self, node_id: Optional[str] = None, custom_name: Optional[str] = None):
        self.id = node_id or str(uuid.uuid4())
        self.name = custom_name or self.get_display_name()
        self.x: float = 0.0
        self.y: float = 0.0
        self.params: Dict[str, Any] = {}
        
        # Initialize default parameters
        for param_def in self.get_parameter_defs():
            self.params[param_def.name] = param_def.default

        # Runtime cached state
        self.last_inputs: Dict[str, FeatureDataset] = {}
        self.last_outputs: Dict[str, FeatureDataset] = {}
        self.last_error: Optional[str] = None
        self.execution_duration_sec: float = 0.0
        self.features_processed: int = 0

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        """Define incoming data ports (e.g. Input, Clipper, Candidate)."""
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        """Define outgoing data ports (e.g. Output, Passed, Failed, Inside, Outside)."""
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        """Define user-configurable parameters in the Inspector/Properties panel."""
        return []

    def set_param(self, name: str, value: Any) -> None:
        self.params[name] = value

    def get_param(self, name: str, default: Any = None) -> Any:
        return self.params.get(name, default)

    def execute(
        self,
        inputs: Dict[str, FeatureDataset],
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, FeatureDataset]:
        """
        Core transform method.
        inputs: Mapping of port name -> FeatureDataset
        params: Evaluated parameter values
        returns: Mapping of port name -> FeatureDataset
        """
        raise NotImplementedError("Each node must implement execute()")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize node state for saving to .fpy / .json workflow file."""
        return {
            "id": self.id,
            "node_type": self.node_type,
            "custom_name": self.name,
            "position": {"x": self.x, "y": self.y},
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaseNode:
        node = cls(node_id=data["id"], custom_name=data.get("custom_name"))
        pos = data.get("position", {})
        node.x = pos.get("x", 0.0)
        node.y = pos.get("y", 0.0)
        node.params.update(data.get("params", {}))
        return node
