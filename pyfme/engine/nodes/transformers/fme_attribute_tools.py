"""
FME Attribute and Table Handling Transformers from FME_Transformers_GIS.xlsx:
- AttributeCreator (Creates new attributes with values)
- AttributeKeeper (Keeps only specified attributes, dropping all others)
- AttributeRemover (Removes specific attributes)
- AttributeRenamer (Renames specific attributes)
- FeatureMerger (FME FeatureMerger: Requestor + Supplier -> Merged, UnmergedRequestor, UnmergedSupplier)
- StringReplacer (Replaces text patterns or regex)
- DateTimeConverter (Parses and reformats datetime attributes)
"""

from typing import Any, Dict, List
import polars as pl
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class AttributeCreator(BaseNode):
    """
    Creates new attributes with assigned constant or default values.
    """
    node_type = "AttributeCreator"
    category = NodeCategory.ATTRIBUTE
    description = "Creates a new attribute with a specified value (FME AttributeCreator)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("attribute_name", ParameterType.STRING, default="new_attr", label="Attribute Name"),
            ParameterDef("attribute_value", ParameterType.STRING, default="", label="Attribute Value"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        df = inp.to_polars()
        name = params.get("attribute_name", "new_attr").strip() or "new_attr"
        val = params.get("attribute_value", "")

        df = df.with_columns(pl.lit(val).alias(name))
        if inp.has_geometry():
            return {"Output": FeatureDataset.from_polars(df, geometry_col=inp.geometry_col, crs=inp.crs)}
        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class AttributeKeeper(BaseNode):
    """
    Keeps only specified attributes, dropping all other unselected columns.
    """
    node_type = "AttributeKeeper"
    category = NodeCategory.ATTRIBUTE
    description = "Keeps only selected attributes, removing all others (FME AttributeKeeper)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("attributes_to_keep", ParameterType.STRING, default="", label="Attributes to Keep (comma-separated)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        df = inp.to_polars()
        keep_str = params.get("attributes_to_keep", "")
        cols = [c.strip() for c in keep_str.split(",") if c.strip() in df.columns]

        if inp.has_geometry() and inp.geometry_col in df.columns and inp.geometry_col not in cols:
            cols.append(inp.geometry_col)

        if cols:
            df = df.select(cols)

        if inp.has_geometry():
            return {"Output": FeatureDataset.from_polars(df, geometry_col=inp.geometry_col, crs=inp.crs)}
        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class AttributeRemover(BaseNode):
    """
    Removes specified attributes from features.
    """
    node_type = "AttributeRemover"
    category = NodeCategory.ATTRIBUTE
    description = "Removes specified attributes from features (FME AttributeRemover)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("attributes_to_remove", ParameterType.STRING, default="", label="Attributes to Remove (comma-separated)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        df = inp.to_polars()
        rem_str = params.get("attributes_to_remove", "")
        cols = [c.strip() for c in rem_str.split(",") if c.strip() in df.columns]

        if cols:
            df = df.drop(cols)

        if inp.has_geometry():
            return {"Output": FeatureDataset.from_polars(df, geometry_col=inp.geometry_col, crs=inp.crs)}
        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class AttributeRenamer(BaseNode):
    """
    Renames attributes using OldName:NewName syntax.
    """
    node_type = "AttributeRenamer"
    category = NodeCategory.ATTRIBUTE
    description = "Renames attributes using old_name:new_name mapping (FME AttributeRenamer)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("rename_pairs", ParameterType.STRING, default="", label="Rename Pairs (old:new, comma-separated)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        df = inp.to_polars()
        pairs_str = params.get("rename_pairs", "")
        rename_map = {}
        for pair in pairs_str.split(","):
            if ":" in pair:
                old_c, new_c = pair.split(":", 1)
                old_c, new_c = old_c.strip(), new_c.strip()
                if old_c in df.columns and new_c:
                    rename_map[old_c] = new_c

        if rename_map:
            df = df.rename(rename_map)

        if inp.has_geometry():
            return {"Output": FeatureDataset.from_polars(df, geometry_col=inp.geometry_col, crs=inp.crs)}
        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class FeatureMerger(BaseNode):
    """
    FME FeatureMerger: Joins two feature streams (Requestor and Supplier) based on join keys.
    Routes to Merged, UnmergedRequestor, and UnmergedSupplier output ports!
    """
    node_type = "FeatureMerger"
    category = NodeCategory.ATTRIBUTE
    description = "Merges Requestor and Supplier features by key (FME FeatureMerger / Joiner)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Requestor", PortType.INPUT, "Features to receive attributes"),
            Port("Supplier", PortType.INPUT, "Features supplying attributes"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Merged", PortType.OUTPUT, "Successfully matched and merged features"),
            Port("UnmergedRequestor", PortType.OUTPUT, "Requestor features with no match"),
            Port("UnmergedSupplier", PortType.OUTPUT, "Supplier features not referenced"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("requestor_join_key", ParameterType.STRING, default="id", label="Requestor Join Key"),
            ParameterDef("supplier_join_key", ParameterType.STRING, default="id", label="Supplier Join Key"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        req = inputs.get("Requestor")
        sup = inputs.get("Supplier")

        if not req or req.count() == 0:
            return {"Merged": FeatureDataset.empty(), "UnmergedRequestor": FeatureDataset.empty(), "UnmergedSupplier": sup or FeatureDataset.empty()}
        if not sup or sup.count() == 0:
            return {"Merged": FeatureDataset.empty(), "UnmergedRequestor": req, "UnmergedSupplier": FeatureDataset.empty()}

        req_df = req.to_polars()
        sup_df = sup.to_polars()

        r_key = params.get("requestor_join_key", "id").strip()
        s_key = params.get("supplier_join_key", "id").strip()

        if r_key not in req_df.columns or s_key not in sup_df.columns:
            return {"Merged": FeatureDataset.empty(), "UnmergedRequestor": req, "UnmergedSupplier": sup}

        # Inner join for merged
        merged_df = req_df.join(sup_df, left_on=r_key, right_on=s_key, how="inner")
        # Anti joins for unmerged
        unmerged_req_df = req_df.join(sup_df, left_on=r_key, right_on=s_key, how="anti")
        unmerged_sup_df = sup_df.join(req_df, left_on=s_key, right_on=r_key, how="anti")

        def make_ds(df_part, src):
            if src.has_geometry() and src.geometry_col in df_part.columns:
                return FeatureDataset.from_polars(df_part, geometry_col=src.geometry_col, crs=src.crs)
            return FeatureDataset.from_polars(df_part)

        return {
            "Merged": make_ds(merged_df, req),
            "UnmergedRequestor": make_ds(unmerged_req_df, req),
            "UnmergedSupplier": make_ds(unmerged_sup_df, sup),
        }


@NodeRegistry.register
class StringReplacer(BaseNode):
    """
    Finds and replaces substrings or regex patterns in a text attribute.
    """
    node_type = "StringReplacer"
    category = NodeCategory.ATTRIBUTE
    description = "Searches and replaces text or regex patterns in attributes (FME StringReplacer)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("attribute", ParameterType.STRING, default="", label="Target Attribute"),
            ParameterDef("search_value", ParameterType.STRING, default="", label="Search Text / Pattern"),
            ParameterDef("replace_value", ParameterType.STRING, default="", label="Replacement Text"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        df = inp.to_polars()
        attr = params.get("attribute", "").strip()
        search_val = params.get("search_value", "")
        replace_val = params.get("replace_value", "")

        if attr in df.columns and search_val:
            df = df.with_columns(
                pl.col(attr).cast(pl.String).str.replace_all(search_val, replace_val).alias(attr)
            )

        if inp.has_geometry():
            return {"Output": FeatureDataset.from_polars(df, geometry_col=inp.geometry_col, crs=inp.crs)}
        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class DateTimeConverter(BaseNode):
    """
    Converts and formats date/time string attributes.
    """
    node_type = "DateTimeConverter"
    category = NodeCategory.ATTRIBUTE
    description = "Parses and reformats datetime attributes (FME DateTimeConverter)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("attribute", ParameterType.STRING, default="", label="Datetime Attribute"),
            ParameterDef("output_format", ParameterType.STRING, default="%Y-%m-%d %H:%M:%S", label="Output Format"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        df = inp.to_polars()
        attr = params.get("attribute", "").strip()
        fmt = params.get("output_format", "%Y-%m-%d %H:%M:%S")

        if attr in df.columns:
            try:
                df = df.with_columns(
                    pl.col(attr).cast(pl.String).str.to_datetime().dt.strftime(fmt).alias(attr)
                )
            except Exception:
                pass

        if inp.has_geometry():
            return {"Output": FeatureDataset.from_polars(df, geometry_col=inp.geometry_col, crs=inp.crs)}
        return {"Output": FeatureDataset.from_polars(df)}
