"""
FME Database & Automation Transformers from FME_Transformers_GIS.xlsx:
- HTTPCaller (Performs HTTP GET/POST API requests)
- JSONFragmenter (Explodes JSON array into separate features)
- Creator (Creates N blank features to kick off workflows)
- Terminator (Halts execution with a fatal error if features arrive)
- Logger (Logs feature attributes and summaries to console)
"""

from typing import Any, Dict, List
import json
import requests
import polars as pl
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class Creator(BaseNode):
    """
    Creates N blank or counter features to trigger downstream processing.
    FME Creator transformer.
    """
    node_type = "Creator"
    category = NodeCategory.SCRIPTING
    description = "Generates initial features to initiate workflow execution (FME Creator)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Created features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("num_features", ParameterType.INTEGER, default=1, label="Number of Features to Create"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        n = max(int(params.get("num_features", 1)), 1)
        df = pl.DataFrame({"_creation_instance": list(range(1, n + 1))})
        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class Terminator(BaseNode):
    """
    Terminates workflow execution with a fatal error message when a feature arrives.
    FME Terminator transformer.
    """
    node_type = "Terminator"
    category = NodeCategory.SCRIPTING
    description = "Halts workspace execution with error when a feature reaches it (FME Terminator)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("error_message", ParameterType.STRING, default="Terminator triggered: critical condition met.", label="Termination Message"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if inp and inp.count() > 0:
            msg = params.get("error_message", "Terminator triggered.")
            raise RuntimeError(f"FME Terminator: {msg} (Encountered {inp.count()} features)")
        return {}


@NodeRegistry.register
class Logger(BaseNode):
    """
    Logs feature schemas and sample values to execution log.
    FME Logger transformer.
    """
    node_type = "Logger"
    category = NodeCategory.SCRIPTING
    description = "Logs feature schemas and attributes to execution console (FME Logger)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Pass-through features")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("log_message", ParameterType.STRING, default="Feature Logger", label="Prefix Log Message"),
            ParameterDef("max_features_to_log", ParameterType.INTEGER, default=5, label="Max Features to Print"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp:
            return {"Output": FeatureDataset.empty()}

        prefix = params.get("log_message", "Logger")
        max_log = int(params.get("max_features_to_log", 5))

        print(f"[{prefix}] Total features: {inp.count()}, Columns: {inp.columns}")
        if inp.count() > 0:
            df = inp.to_polars().head(max_log)
            print(f"[{prefix}] Sample:\n", df)

        return {"Output": inp}


@NodeRegistry.register
class HTTPCaller(BaseNode):
    """
    Performs HTTP API requests (GET, POST, PUT, DELETE) and writes response into attributes.
    FME HTTPCaller transformer.
    """
    node_type = "HTTPCaller"
    category = NodeCategory.SCRIPTING
    description = "Sends HTTP REST requests and attaches response body (FME HTTPCaller)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("url", ParameterType.STRING, default="https://httpbin.org/get", label="Request URL"),
            ParameterDef("http_method", ParameterType.CHOICE, default="GET", choices=["GET", "POST", "PUT", "DELETE"], label="HTTP Method"),
            ParameterDef("headers_json", ParameterType.STRING, default="{}", label="Headers (JSON string)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        url = params.get("url", "").strip()
        method = params.get("http_method", "GET")

        if not url:
            return {"Output": inp or FeatureDataset.empty()}

        headers = {}
        try:
            h_str = params.get("headers_json", "{}")
            if h_str.strip():
                headers = json.loads(h_str)
        except Exception:
            pass

        try:
            resp = requests.request(method, url, headers=headers, timeout=15)
            status_code = resp.status_code
            body_text = resp.text
        except Exception as e:
            status_code = -1
            body_text = str(e)

        if inp and inp.count() > 0:
            df = inp.to_polars()
            df = df.with_columns(
                pl.lit(status_code).alias("_http_status_code"),
                pl.lit(body_text).alias("_http_response_body"),
            )
            return {"Output": FeatureDataset.from_polars(df)}
        else:
            df = pl.DataFrame({
                "_http_status_code": [status_code],
                "_http_response_body": [body_text],
            })
            return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class JSONFragmenter(BaseNode):
    """
    Explodes a JSON array or extracts keys from a JSON attribute into multiple features.
    FME JSONFragmenter transformer.
    """
    node_type = "JSONFragmenter"
    category = NodeCategory.SCRIPTING
    description = "Explodes a JSON array string into separate feature records (FME JSONFragmenter)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("json_attribute", ParameterType.STRING, default="_http_response_body", label="JSON Attribute Name"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        attr = params.get("json_attribute", "_http_response_body").strip()
        df = inp.to_polars()

        if attr not in df.columns:
            return {"Output": inp}

        rows = []
        for val in df[attr]:
            if not val:
                continue
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            rows.append(item)
                        else:
                            rows.append({"_json_value": str(item)})
                elif isinstance(parsed, dict):
                    rows.append(parsed)
            except Exception:
                continue

        if not rows:
            return {"Output": inp}

        frag_df = pl.DataFrame(rows)
        return {"Output": FeatureDataset.from_polars(frag_df)}
