"""
FME Desktop 2018 Core Most Valuable Transformers:
- TestFilter (#7 in FME Top 30)
- Counter (#15 in FME Top 30)
- AttributeFilter (#13 in FME Top 30)
- AttributeExposer (#23 in FME Top 30)
- AttributeSplitter (#29 in FME Top 30)
- CoordinateExtractor (#30 in FME Top 30)
- Inspector (#5 in FME Top 30)
- SpatialFilter (#21 in FME Top 30)
- FeatureJoiner (#28 in FME Top 30)
- FeatureReader (#17 in FME Top 30)
"""

from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
import polars as pl
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
import shapely

from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class TestFilter(BaseNode):
    """
    Evaluates sequential test clauses and routes features to multiple named output ports.
    Equivalent to FME's TestFilter transformer.
    """
    node_type = "TestFilter"
    category = NodeCategory.ATTRIBUTE
    description = "Subdivides data by evaluating sequential conditional tests into custom output ports."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Port1", PortType.OUTPUT, "Matches Condition 1"),
            Port("Port2", PortType.OUTPUT, "Matches Condition 2"),
            Port("<Else>", PortType.OUTPUT, "Fails all conditions"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("test1_attribute", ParameterType.STRING, default="", label="Test 1 Attribute"),
            ParameterDef("test1_operator", ParameterType.CHOICE, default="=", choices=["=", "!=", ">", ">=", "<", "<=", "contains"], label="Test 1 Operator"),
            ParameterDef("test1_value", ParameterType.STRING, default="", label="Test 1 Value"),
            ParameterDef("test2_attribute", ParameterType.STRING, default="", label="Test 2 Attribute"),
            ParameterDef("test2_operator", ParameterType.CHOICE, default="=", choices=["=", "!=", ">", ">=", "<", "<=", "contains"], label="Test 2 Operator"),
            ParameterDef("test2_value", ParameterType.STRING, default="", label="Test 2 Value"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Port1": FeatureDataset.empty(), "Port2": FeatureDataset.empty(), "<Else>": FeatureDataset.empty()}

        df = inp.to_polars()
        has_geom = inp.has_geometry()

        def make_expr(attr: str, op: str, val: str):
            if not attr or attr not in df.columns:
                return None
            col = pl.col(attr)
            try:
                # Attempt numeric cast
                col_type = df.schema[attr]
                if col_type in (pl.Int32, pl.Int64, pl.Float32, pl.Float64):
                    typed_val = float(val) if "." in val else int(val)
                else:
                    typed_val = str(val)
            except Exception:
                typed_val = str(val)

            if op == "=": return col == typed_val
            elif op == "!=": return col != typed_val
            elif op == ">": return col > typed_val
            elif op == ">=": return col >= typed_val
            elif op == "<": return col < typed_val
            elif op == "<=": return col <= typed_val
            elif op == "contains": return col.cast(pl.String).str.contains(str(val))
            return col == typed_val

        e1 = make_expr(params.get("test1_attribute", ""), params.get("test1_operator", "="), params.get("test1_value", ""))
        e2 = make_expr(params.get("test2_attribute", ""), params.get("test2_operator", "="), params.get("test2_value", ""))

        if e1 is not None:
            m1 = df.select(e1).to_series().to_list()
        else:
            m1 = [False] * len(df)

        if e2 is not None:
            m2 = df.select(e2).to_series().to_list()
        else:
            m2 = [False] * len(df)

        if has_geom:
            gdf = inp.to_geopandas()
            p1_mask = [b for b in m1]
            p2_mask = [b and not p1_mask[i] for i, b in enumerate(m2)]
            else_mask = [not (p1_mask[i] or p2_mask[i]) for i in range(len(gdf))]

            return {
                "Port1": FeatureDataset.from_geopandas(gdf[p1_mask]),
                "Port2": FeatureDataset.from_geopandas(gdf[p2_mask]),
                "<Else>": FeatureDataset.from_geopandas(gdf[else_mask]),
            }
        else:
            p1_df = df.filter(pl.Series(m1)) if e1 is not None else pl.DataFrame()
            rem = df.filter(~pl.Series(m1)) if e1 is not None else df
            p2_df = rem.filter(e2) if e2 is not None else pl.DataFrame()
            else_df = rem.filter(~e2) if e2 is not None else rem
            return {
                "Port1": FeatureDataset.from_polars(p1_df),
                "Port2": FeatureDataset.from_polars(p2_df),
                "<Else>": FeatureDataset.from_polars(else_df),
            }


@NodeRegistry.register
class Counter(BaseNode):
    """
    Adds a sequential integer identifier to each incoming feature.
    Matches FME Counter transformer.
    """
    node_type = "Counter"
    category = NodeCategory.ATTRIBUTE
    description = "Generates a sequential count ID attribute for each incoming feature."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("counter_name", ParameterType.STRING, default="_count", label="Count Attribute Name"),
            ParameterDef("start_value", ParameterType.INTEGER, default=1, label="Start Value"),
            ParameterDef("step", ParameterType.INTEGER, default=1, label="Step"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Output": inp or FeatureDataset.empty()}

        attr_name = params.get("counter_name", "_count").strip() or "_count"
        start = int(params.get("start_value", 1))
        step = int(params.get("step", 1))
        n = inp.count()
        counts = [start + (i * step) for i in range(n)]

        if inp.has_geometry():
            gdf = inp.to_geopandas().copy()
            gdf[attr_name] = counts
            return {"Output": FeatureDataset.from_geopandas(gdf)}
        else:
            df = inp.to_polars().with_columns(pl.Series(attr_name, counts))
            return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class AttributeFilter(BaseNode):
    """
    Filters features into output ports based on attribute values.
    Matches FME AttributeFilter.
    """
    node_type = "AttributeFilter"
    category = NodeCategory.ATTRIBUTE
    description = "Routes features to separate output ports based on the value of a selected attribute."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Match1", PortType.OUTPUT),
            Port("Match2", PortType.OUTPUT),
            Port("<Unfiltered>", PortType.OUTPUT),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("filter_attribute", ParameterType.STRING, default="", label="Attribute to Filter"),
            ParameterDef("value1", ParameterType.STRING, default="", label="Value 1 (Port Match1)"),
            ParameterDef("value2", ParameterType.STRING, default="", label="Value 2 (Port Match2)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Match1": FeatureDataset.empty(), "Match2": FeatureDataset.empty(), "<Unfiltered>": FeatureDataset.empty()}

        attr = params.get("filter_attribute", "").strip()
        v1 = params.get("value1", "").strip()
        v2 = params.get("value2", "").strip()

        if not attr or attr not in inp.columns:
            return {"Match1": FeatureDataset.empty(), "Match2": FeatureDataset.empty(), "<Unfiltered>": inp}

        if inp.has_geometry():
            gdf = inp.to_geopandas()
            s = gdf[attr].astype(str)
            m1 = (s == v1)
            m2 = (s == v2)
            rem = ~(m1 | m2)
            return {
                "Match1": FeatureDataset.from_geopandas(gdf[m1]),
                "Match2": FeatureDataset.from_geopandas(gdf[m2]),
                "<Unfiltered>": FeatureDataset.from_geopandas(gdf[rem]),
            }
        else:
            df = inp.to_polars()
            s = df[attr].cast(pl.String)
            return {
                "Match1": FeatureDataset.from_polars(df.filter(s == v1)),
                "Match2": FeatureDataset.from_polars(df.filter(s == v2)),
                "<Unfiltered>": FeatureDataset.from_polars(df.filter((s != v1) & (s != v2))),
            }


@NodeRegistry.register
class CoordinateExtractor(BaseNode):
    """
    Extracts the x, y, (and z) coordinates of geometries into attributes.
    Matches FME CoordinateExtractor.
    """
    node_type = "CoordinateExtractor"
    category = NodeCategory.SPATIAL
    description = "Extracts X, Y, and Z geometry coordinates into user-specified attributes."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("x_attribute", ParameterType.STRING, default="_x", label="X Attribute Name"),
            ParameterDef("y_attribute", ParameterType.STRING, default="_y", label="Y Attribute Name"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": inp or FeatureDataset.empty()}

        x_attr = params.get("x_attribute", "_x").strip() or "_x"
        y_attr = params.get("y_attribute", "_y").strip() or "_y"

        gdf = inp.to_geopandas().copy()
        # Fast extraction of point/representative geometry coordinates
        if (gdf.geometry.geom_type == "Point").all():
            gdf[x_attr] = gdf.geometry.x
            gdf[y_attr] = gdf.geometry.y
        else:
            rep = gdf.geometry.representative_point()
            gdf[x_attr] = rep.x
            gdf[y_attr] = rep.y

        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class AttributeSplitter(BaseNode):
    """
    Splits a string attribute by delimiter into multiple columns.
    Matches FME AttributeSplitter.
    """
    node_type = "AttributeSplitter"
    category = NodeCategory.ATTRIBUTE
    description = "Splits an attribute value by delimiter character into distinct columns."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("source_attribute", ParameterType.STRING, default="", label="Attribute to Split"),
            ParameterDef("delimiter", ParameterType.STRING, default=",", label="Delimiter Character"),
            ParameterDef("target_prefix", ParameterType.STRING, default="_split_", label="Target Attribute Prefix"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Output": inp or FeatureDataset.empty()}

        col = params.get("source_attribute", "").strip()
        delim = params.get("delimiter", ",")
        prefix = params.get("target_prefix", "_split_")

        if not col or col not in inp.columns:
            return {"Output": inp}

        if inp.has_geometry():
            gdf = inp.to_geopandas().copy()
            splits = gdf[col].astype(str).str.split(delim, expand=True)
            for i in range(splits.shape[1]):
                gdf[f"{prefix}{i}"] = splits[i]
            return {"Output": FeatureDataset.from_geopandas(gdf)}
        else:
            df = inp.to_polars()
            split_series = df[col].cast(pl.String).str.split(delim)
            max_len = max([len(x) for x in split_series if x is not None] or [1])
            new_cols = []
            for i in range(max_len):
                new_cols.append(split_series.list.get(i).alias(f"{prefix}{i}"))
            df_res = df.with_columns(new_cols)
            return {"Output": FeatureDataset.from_polars(df_res)}


@NodeRegistry.register
class Inspector(BaseNode):
    """
    Routes features directly to the visual FME Data Inspector.
    Matches FME Inspector transformer.
    """
    node_type = "Inspector"
    category = NodeCategory.ATTRIBUTE
    description = "Visual inspection sink routing features to FME Table and Map Inspectors."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        return {"Output": inp or FeatureDataset.empty()}


@NodeRegistry.register
class SpatialFilter(BaseNode):
    """
    Filters Candidate features against Filter features using spatial relationships.
    Matches FME SpatialFilter.
    """
    node_type = "SpatialFilter"
    category = NodeCategory.SPATIAL
    description = "Tests spatial relationships (Intersects, Contains, Within) between Candidate and Filter layers."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Candidate", PortType.INPUT, "Features to test"),
            Port("Filter", PortType.INPUT, "Spatial boundary filter"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Passed", PortType.OUTPUT, "Features passing the spatial test"),
            Port("Failed", PortType.OUTPUT, "Features failing the spatial test"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("predicate", ParameterType.CHOICE, default="Intersects", choices=["Intersects", "Contains", "Within", "Touches", "Disjoint"], label="Spatial Predicate"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        candidate = inputs.get("Candidate")
        filter_ds = inputs.get("Filter")

        if not candidate or candidate.is_empty() or not candidate.has_geometry():
            return {"Passed": FeatureDataset.empty(), "Failed": candidate or FeatureDataset.empty()}
        if not filter_ds or filter_ds.is_empty() or not filter_ds.has_geometry():
            return {"Passed": FeatureDataset.empty(), "Failed": candidate}

        cand_gdf = candidate.to_geopandas()
        filt_gdf = filter_ds.to_geopandas()

        if cand_gdf.crs and filt_gdf.crs and cand_gdf.crs != filt_gdf.crs:
            filt_gdf = filt_gdf.to_crs(cand_gdf.crs)

        pred = params.get("predicate", "Intersects").lower()
        if pred == "intersects":
            joined = gpd.sjoin(cand_gdf, filt_gdf, how="inner", predicate="intersects")
        elif pred == "contains":
            joined = gpd.sjoin(cand_gdf, filt_gdf, how="inner", predicate="contains")
        elif pred == "within":
            joined = gpd.sjoin(cand_gdf, filt_gdf, how="inner", predicate="within")
        elif pred == "touches":
            joined = gpd.sjoin(cand_gdf, filt_gdf, how="inner", predicate="touches")
        else:
            joined = gpd.sjoin(cand_gdf, filt_gdf, how="inner", predicate="intersects")

        passed_indices = set(joined.index.unique())
        passed_mask = [idx in passed_indices for idx in cand_gdf.index]
        failed_mask = [not b for b in passed_mask]

        return {
            "Passed": FeatureDataset.from_geopandas(cand_gdf[passed_mask]),
            "Failed": FeatureDataset.from_geopandas(cand_gdf[failed_mask]),
        }


@NodeRegistry.register
class FeatureJoiner(BaseNode):
    """
    Joins two datasets based on attribute key expressions (Inner, Left, Full).
    Matches FME FeatureJoiner.
    """
    node_type = "FeatureJoiner"
    category = NodeCategory.ATTRIBUTE
    description = "Performs tabular joins between Left and Right inputs based on key columns."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Left", PortType.INPUT),
            Port("Right", PortType.INPUT),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Joined", PortType.OUTPUT),
            Port("UnjoinedLeft", PortType.OUTPUT),
            Port("UnjoinedRight", PortType.OUTPUT),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("left_key", ParameterType.STRING, default="", label="Left Key Column"),
            ParameterDef("right_key", ParameterType.STRING, default="", label="Right Key Column"),
            ParameterDef("join_type", ParameterType.CHOICE, default="inner", choices=["inner", "left", "full"], label="Join Type"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        left = inputs.get("Left")
        right = inputs.get("Right")

        if not left or left.is_empty():
            return {"Joined": FeatureDataset.empty(), "UnjoinedLeft": FeatureDataset.empty(), "UnjoinedRight": right or FeatureDataset.empty()}
        if not right or right.is_empty():
            return {"Joined": FeatureDataset.empty(), "UnjoinedLeft": left, "UnjoinedRight": FeatureDataset.empty()}

        l_key = params.get("left_key", "").strip()
        r_key = params.get("right_key", "").strip() or l_key
        j_type = params.get("join_type", "inner")

        # Fast join in Polars or GeoPandas
        if left.has_geometry():
            lgdf = left.to_geopandas()
            rgdf = right.to_geopandas()
            if l_key in lgdf.columns and r_key in rgdf.columns:
                merged = lgdf.merge(rgdf.drop(columns=[rgdf.geometry.name], errors="ignore"), left_on=l_key, right_on=r_key, how=j_type)
                left_match = lgdf[l_key].isin(rgdf[r_key])
                right_match = rgdf[r_key].isin(lgdf[l_key])
                return {
                    "Joined": FeatureDataset.from_geopandas(merged),
                    "UnjoinedLeft": FeatureDataset.from_geopandas(lgdf[~left_match]),
                    "UnjoinedRight": FeatureDataset.from_geopandas(rgdf[~right_match]),
                }
            return {"Joined": left, "UnjoinedLeft": FeatureDataset.empty(), "UnjoinedRight": FeatureDataset.empty()}
        else:
            ldf = left.to_polars()
            rdf = right.to_polars()
            if l_key in ldf.columns and r_key in rdf.columns:
                joined_df = ldf.join(rdf, left_on=l_key, right_on=r_key, how=j_type)
                r_keys_list = rdf[r_key].to_list()
                l_keys_list = ldf[l_key].to_list()
                unjoined_l = ldf.filter(~pl.col(l_key).is_in(r_keys_list))
                unjoined_r = rdf.filter(~pl.col(r_key).is_in(l_keys_list))
                return {
                    "Joined": FeatureDataset.from_polars(joined_df),
                    "UnjoinedLeft": FeatureDataset.from_polars(unjoined_l),
                    "UnjoinedRight": FeatureDataset.from_polars(unjoined_r),
                }
            return {"Joined": left, "UnjoinedLeft": FeatureDataset.empty(), "UnjoinedRight": FeatureDataset.empty()}
