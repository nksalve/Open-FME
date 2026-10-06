"""
Attribute Transformers (AttributeManager, Tester, Sorter, DuplicateFilter, etc.)
Emulating the iconic FME attribute manipulation capabilities with Polars speed.
"""

from typing import Any, Dict, List
import polars as pl
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class Tester(BaseNode):
    """
    Evaluates test conditions on features and routes them to 'Passed' or 'Failed' output ports.
    Equivalent to FME's Tester transformer.
    """
    node_type = "Tester"
    category = NodeCategory.ATTRIBUTE
    description = "Tests features against conditions and routes to 'Passed' or 'Failed' ports."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Features to test")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Passed", PortType.OUTPUT, "Features meeting the condition"),
            Port("Failed", PortType.OUTPUT, "Features failing the condition"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("attribute", ParameterType.STRING, default="", label="Test Attribute / Column"),
            ParameterDef(
                "operator",
                ParameterType.CHOICE,
                default="=",
                choices=["=", "!=", ">", ">=", "<", "<=", "contains", "starts_with", "is_null", "is_not_null"],
                label="Operator",
            ),
            ParameterDef("test_value", ParameterType.STRING, default="", label="Comparison Value"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Passed": FeatureDataset.empty(), "Failed": FeatureDataset.empty()}

        attr = params.get("attribute", "").strip()
        op = params.get("operator", "=")
        val = params.get("test_value", "")

        df = inp.to_polars()
        if attr not in df.columns:
            # Fallback if attribute not present
            return {"Passed": FeatureDataset.empty(), "Failed": inp}

        col = pl.col(attr)
        col_type = df.schema[attr]

        try:
            # Type cast value to match column if numeric
            typed_val = val
            if col_type in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64]:
                typed_val = int(val)
            elif col_type in [pl.Float32, pl.Float64]:
                typed_val = float(val)
            elif col_type == pl.Boolean:
                typed_val = val.lower() in ("true", "1", "yes")

            if op == "=":
                expr = col == typed_val
            elif op == "!=":
                expr = col != typed_val
            elif op == ">":
                expr = col > typed_val
            elif op == ">=":
                expr = col >= typed_val
            elif op == "<":
                expr = col < typed_val
            elif op == "<=":
                expr = col <= typed_val
            elif op == "contains":
                expr = col.cast(pl.String).str.contains(str(val))
            elif op == "starts_with":
                expr = col.cast(pl.String).str.starts_with(str(val))
            elif op == "is_null":
                expr = col.is_null()
            elif op == "is_not_null":
                expr = col.is_not_null()
            else:
                expr = col == typed_val

            passed_df = df.filter(expr)
            failed_df = df.filter(~expr)

            # Preserve geometry if spatial
            if inp.has_geometry():
                passed_ds = FeatureDataset.from_polars(passed_df, geometry_col=inp.geometry_col, crs=inp.crs)
                failed_ds = FeatureDataset.from_polars(failed_df, geometry_col=inp.geometry_col, crs=inp.crs)
            else:
                passed_ds = FeatureDataset.from_polars(passed_df)
                failed_ds = FeatureDataset.from_polars(failed_df)

            return {"Passed": passed_ds, "Failed": failed_ds}

        except Exception as e:
            # If evaluation failed on type casting, treat all as failed
            return {"Passed": FeatureDataset.empty(), "Failed": inp}


@NodeRegistry.register
class AttributeManager(BaseNode):
    """
    Renames, removes, or creates attributes. Equivalent to FME's AttributeManager.
    """
    node_type = "AttributeManager"
    category = NodeCategory.ATTRIBUTE
    description = "Renames, removes, or adds new constant/derived attributes."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("rename_rules", ParameterType.STRING, default="", label="Rename (old:new, comma-separated)"),
            ParameterDef("remove_columns", ParameterType.STRING, default="", label="Remove Columns (comma-separated)"),
            ParameterDef("new_col_name", ParameterType.STRING, default="", label="Add New Column Name"),
            ParameterDef("new_col_value", ParameterType.STRING, default="", label="New Column Default Value"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        res = inp

        # 1. Renames
        rename_str = params.get("rename_rules", "").strip()
        if rename_str:
            rename_map = {}
            for pair in rename_str.split(","):
                if ":" in pair:
                    old_c, new_c = pair.split(":", 1)
                    old_c, new_c = old_c.strip(), new_c.strip()
                    if old_c and new_c:
                        rename_map[old_c] = new_c
            if rename_map:
                res = res.rename_columns(rename_map)

        # 2. Removes
        remove_str = params.get("remove_columns", "").strip()
        if remove_str:
            to_remove = [c.strip() for c in remove_str.split(",") if c.strip()]
            if to_remove:
                res = res.drop_columns(to_remove)

        # 3. Add column
        new_name = params.get("new_col_name", "").strip()
        new_val = params.get("new_col_value", "")
        if new_name:
            res = res.add_column(new_name, new_val)

        return {"Output": res}


@NodeRegistry.register
class Sorter(BaseNode):
    node_type = "Sorter"
    category = NodeCategory.ATTRIBUTE
    description = "Sorts features in ascending or descending order by specified attribute."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("sort_by", ParameterType.STRING, default="", label="Sort Attribute"),
            ParameterDef("descending", ParameterType.BOOLEAN, default=False, label="Sort Descending"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        col = params.get("sort_by", "").strip()
        desc = bool(params.get("descending", False))

        if col:
            res = inp.sort_by(col, descending=desc)
        else:
            res = inp

        return {"Output": res}


@NodeRegistry.register
class DuplicateFilter(BaseNode):
    """
    Detects and separates duplicate features based on key attributes.
    Routes unique features to 'Unique' and duplicates to 'Duplicate'.
    """
    node_type = "DuplicateFilter"
    category = NodeCategory.ATTRIBUTE
    description = "Separates unique records from duplicates on selected attribute(s)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Unique", PortType.OUTPUT, "First instance of each unique key"),
            Port("Duplicate", PortType.OUTPUT, "Subsequent duplicate features"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("key_attributes", ParameterType.STRING, default="", label="Key Columns (comma-separated, blank for all)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Unique": FeatureDataset.empty(), "Duplicate": FeatureDataset.empty()}

        df = inp.to_polars()
        keys_str = params.get("key_attributes", "").strip()
        subset = [k.strip() for k in keys_str.split(",") if k.strip() in df.columns] if keys_str else None

        # Polars unique and filter duplicates
        unique_df = df.unique(subset=subset, keep="first")
        # Identify duplicates by anti-join on row index
        df_with_idx = df.with_row_index("__row_id")
        unique_with_idx = df_with_idx.unique(subset=subset, keep="first")
        dupe_df = df_with_idx.join(unique_with_idx, on="__row_id", how="anti").drop("__row_id")

        if inp.has_geometry():
            return {
                "Unique": FeatureDataset.from_polars(unique_df, geometry_col=inp.geometry_col, crs=inp.crs),
                "Duplicate": FeatureDataset.from_polars(dupe_df, geometry_col=inp.geometry_col, crs=inp.crs),
            }
        return {
            "Unique": FeatureDataset.from_polars(unique_df),
            "Duplicate": FeatureDataset.from_polars(dupe_df),
        }


@NodeRegistry.register
class StatisticsCalculator(BaseNode):
    node_type = "StatisticsCalculator"
    category = NodeCategory.ATTRIBUTE
    description = "Calculates summary statistics (count, min, max, mean, sum) for numeric attributes."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Summary", PortType.OUTPUT, "Statistical summary table"),
            Port("Complete", PortType.OUTPUT, "Original features unchanged"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("attributes", ParameterType.STRING, default="", label="Numeric Attributes (comma-separated, blank for all numeric)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Summary": FeatureDataset.empty(), "Complete": FeatureDataset.empty()}

        df = inp.to_polars()
        cols_str = params.get("attributes", "").strip()
        if cols_str:
            target_cols = [c.strip() for c in cols_str.split(",") if c.strip() in df.columns]
        else:
            target_cols = [c for c, dtype in zip(df.columns, df.dtypes) if dtype.is_numeric()]

        if not target_cols:
            return {"Summary": FeatureDataset.empty(), "Complete": inp}

        stats_rows = []
        for c in target_cols:
            s = df[c]
            stats_rows.append({
                "attribute": c,
                "count": int(s.count()),
                "null_count": int(s.null_count()),
                "min": float(s.min()) if s.min() is not None else None,
                "max": float(s.max()) if s.max() is not None else None,
                "mean": float(s.mean()) if s.mean() is not None else None,
                "sum": float(s.sum()) if s.sum() is not None else None,
            })

        summary_df = pl.DataFrame(stats_rows)
        return {"Summary": FeatureDataset.from_polars(summary_df), "Complete": inp}
