"""
Attribute, Table, Database, and Automation Transformers from FME, GDAL, and SAGA GIS:
- Joiner
- InlineQuerier
- ListExploder
- ListBuilder
- StringSearcher
- StringFormatter
- DateTimeCalculator
- FeatureReader
- SQLExecutor
- PythonCreator
- XMLFlattener
"""

from __future__ import annotations
import os
import re
import sqlite3
import datetime
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

import polars as pl
import geopandas as gpd
import numpy as np

from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class Joiner(BaseNode):
    """
    Standard tabular join between Left and Right inputs based on key columns.
    Matches FME Joiner.
    """
    node_type = "Joiner"
    category = NodeCategory.ATTRIBUTE
    description = "Joins two tables or feature layers based on matching key column values."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Left", PortType.INPUT, "Primary table"),
            Port("Right", PortType.INPUT, "Lookup table"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Output", PortType.OUTPUT, "Joined features"),
            Port("Joined", PortType.OUTPUT, "Joined features (alias)"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("left_key", ParameterType.STRING, default="", label="Left Table Key Column"),
            ParameterDef("right_key", ParameterType.STRING, default="", label="Right Table Key Column"),
            ParameterDef("join_type", ParameterType.CHOICE, default="left", choices=["left", "inner", "full"], label="Join Type"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        left = inputs.get("Left")
        right = inputs.get("Right")

        if not left or left.is_empty():
            return {"Output": FeatureDataset.empty(), "Joined": FeatureDataset.empty()}
        if not right or right.is_empty():
            return {"Output": left, "Joined": left}

        l_key = params.get("left_key", "").strip()
        r_key = params.get("right_key", "").strip() or l_key
        j_type = params.get("join_type", "left")

        if left.has_geometry():
            lgdf = left.to_geopandas()
            rgdf = right.to_geopandas()
            if l_key in lgdf.columns and r_key in rgdf.columns:
                drop_geom = [rgdf.geometry.name] if hasattr(rgdf, "geometry") else []
                merged = lgdf.merge(rgdf.drop(columns=drop_geom, errors="ignore"), left_on=l_key, right_on=r_key, how=j_type)
                res_ds = FeatureDataset.from_geopandas(merged)
                return {"Output": res_ds, "Joined": res_ds}
            return {"Output": left, "Joined": left}
        else:
            ldf = left.to_polars()
            rdf = right.to_polars()
            if l_key in ldf.columns and r_key in rdf.columns:
                joined = ldf.join(rdf, left_on=l_key, right_on=r_key, how=j_type)
                res_ds = FeatureDataset.from_polars(joined)
                return {"Output": res_ds, "Joined": res_ds}
            return {"Output": left, "Joined": left}


@NodeRegistry.register
class InlineQuerier(BaseNode):
    """
    Executes in-memory SQL queries across input tables using SQLite.
    Matches FME InlineQuerier.
    """
    node_type = "InlineQuerier"
    category = NodeCategory.ATTRIBUTE
    description = "Executes custom in-memory SQL queries (JOINs, aggregations, filters) across connected input datasets."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Input", PortType.INPUT, "Primary table (accessible as 'Input')"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "SQL query results")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("sql_query", ParameterType.EXPRESSION, default="SELECT * FROM Input", label="SQL Query"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Output": FeatureDataset.empty()}

        sql = params.get("sql_query", "SELECT * FROM Input").strip()

        # In-memory SQLite execution
        conn = sqlite3.connect(":memory:")
        pdf = inp.to_polars().to_pandas()
        # Drop shapely geometry object for pure SQL execution, or keep as WKT
        geom_col = None
        if "geometry" in pdf.columns:
            geom_col = pdf["geometry"]
            pdf["_wkt_geom"] = [g.wkt if g is not None else "" for g in pdf["geometry"]]
            pdf = pdf.drop(columns=["geometry"])

        pdf.to_sql("Input", conn, index=False, if_exists="replace")

        try:
            res_pdf = pl.read_database(sql, conn)
            conn.close()
            return {"Output": FeatureDataset.from_polars(res_pdf)}
        except Exception as e:
            conn.close()
            # Fallback to pandas read_sql
            try:
                import pandas as pd
                conn2 = sqlite3.connect(":memory:")
                pdf.to_sql("Input", conn2, index=False, if_exists="replace")
                res2 = pd.read_sql_query(sql, conn2)
                conn2.close()
                return {"Output": FeatureDataset.from_pandas(res2)}
            except Exception:
                return {"Output": inp}


@NodeRegistry.register
class ListExploder(BaseNode):
    """
    Explodes a delimited string column into individual rows.
    Matches FME ListExploder.
    """
    node_type = "ListExploder"
    category = NodeCategory.ATTRIBUTE
    description = "Explodes a delimited list attribute into individual rows (1 feature per list element)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("list_attribute", ParameterType.STRING, default="", label="List Attribute to Explode"),
            ParameterDef("delimiter", ParameterType.STRING, default=",", label="Delimiter (if string)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Output": inp or FeatureDataset.empty()}

        col = (params.get("list_attribute") or params.get("attribute_name") or "").strip()
        delim = params.get("delimiter", ",")

        if not col or col not in inp.columns:
            return {"Output": inp}

        if inp.has_geometry():
            gdf = inp.to_geopandas()
            gdf_copy = gdf.copy()
            gdf_copy[col] = gdf_copy[col].astype(str).str.split(delim)
            exploded = gdf_copy.explode(col).reset_index(drop=True)
            return {"Output": FeatureDataset.from_geopandas(exploded)}
        else:
            df = inp.to_polars()
            exploded = df.with_columns(pl.col(col).cast(pl.String).str.split(delim)).explode(col)
            return {"Output": FeatureDataset.from_polars(exploded)}


@NodeRegistry.register
class ListBuilder(BaseNode):
    """
    Aggregates features by group and builds a delimited list string.
    Matches FME ListBuilder.
    """
    node_type = "ListBuilder"
    category = NodeCategory.ATTRIBUTE
    description = "Concatenates attribute values across grouped features into a delimited string."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("group_by", ParameterType.STRING, default="", label="Group By Attribute"),
            ParameterDef("value_attribute", ParameterType.STRING, default="", label="Value Attribute to Aggregate"),
            ParameterDef("delimiter", ParameterType.STRING, default=", ", label="List Delimiter"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Output": inp or FeatureDataset.empty()}

        grp = params.get("group_by", "").strip()
        val = params.get("value_attribute", "").strip()
        delim = params.get("delimiter", ", ")

        if not grp or not val or grp not in inp.columns or val not in inp.columns:
            return {"Output": inp}

        df = inp.to_polars()
        agg_df = df.group_by(grp).agg(
            pl.col(val).cast(pl.String).str.concat(delim).alias(f"{val}_list")
        )
        return {"Output": FeatureDataset.from_polars(agg_df)}


@NodeRegistry.register
class StringSearcher(BaseNode):
    """
    Searches attributes using regular expressions and extracts match groups.
    Matches FME StringSearcher.
    """
    node_type = "StringSearcher"
    category = NodeCategory.ATTRIBUTE
    description = "Performs regex pattern search on attributes, outputting Matched and NotMatched features."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Matched", PortType.OUTPUT, "Features matching the pattern"),
            Port("NotMatched", PortType.OUTPUT, "Features not matching"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("source_attribute", ParameterType.STRING, default="", label="Source Attribute"),
            ParameterDef("regex_pattern", ParameterType.STRING, default="\\d+", label="Regex Pattern"),
            ParameterDef("match_attribute", ParameterType.STRING, default="_matched_text", label="Match Target Attribute"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Matched": FeatureDataset.empty(), "NotMatched": FeatureDataset.empty()}

        src_attr = (params.get("source_attribute") or params.get("attribute_name") or "").strip()
        pattern = params.get("regex_pattern", "\\d+")
        match_attr = params.get("match_attribute", "_matched_text").strip() or "_matched_text"

        if not src_attr or src_attr not in inp.columns:
            return {"Matched": FeatureDataset.empty(), "NotMatched": inp}

        regex = re.compile(pattern)
        if inp.has_geometry():
            gdf = inp.to_geopandas().copy()
            matched_vals = []
            matched_mask = []
            for val in gdf[src_attr].astype(str):
                m = regex.search(val)
                if m:
                    matched_mask.append(True)
                    matched_vals.append(m.group(0))
                else:
                    matched_mask.append(False)
                    matched_vals.append("")

            gdf[match_attr] = matched_vals
            matched_mask = np.array(matched_mask)
            return {
                "Matched": FeatureDataset.from_geopandas(gdf[matched_mask]),
                "NotMatched": FeatureDataset.from_geopandas(gdf[~matched_mask]),
            }
        else:
            df = inp.to_polars()
            extracted = df.with_columns(
                pl.col(src_attr).cast(pl.String).str.extract(pattern, 0).alias(match_attr)
            )
            matched_df = extracted.filter(pl.col(match_attr).is_not_null())
            not_matched_df = extracted.filter(pl.col(match_attr).is_null())
            return {
                "Matched": FeatureDataset.from_polars(matched_df),
                "NotMatched": FeatureDataset.from_polars(not_matched_df),
            }


@NodeRegistry.register
class StringFormatter(BaseNode):
    """
    Formats text attributes using string template expressions.
    Matches FME StringFormatter.
    """
    node_type = "StringFormatter"
    category = NodeCategory.ATTRIBUTE
    description = "Formats text attributes using template expressions like '{first_name} {last_name}'."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("template", ParameterType.STRING, default="{name}", label="Format Template"),
            ParameterDef("target_attribute", ParameterType.STRING, default="_formatted", label="Target Attribute"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Output": inp or FeatureDataset.empty()}

        template = params.get("template", "{name}")
        tgt_attr = params.get("target_attribute", "_formatted").strip() or "_formatted"

        if inp.has_geometry():
            gdf = inp.to_geopandas().copy()
            res = []
            for _, row in gdf.iterrows():
                try:
                    res.append(template.format(**row.to_dict()))
                except Exception:
                    res.append(template)
            gdf[tgt_attr] = res
            return {"Output": FeatureDataset.from_geopandas(gdf)}
        else:
            pdf = inp.to_pandas()
            res = []
            for _, row in pdf.iterrows():
                try:
                    res.append(template.format(**row.to_dict()))
                except Exception:
                    res.append(template)
            pdf[tgt_attr] = res
            return {"Output": FeatureDataset.from_pandas(pdf)}


@NodeRegistry.register
class DateTimeCalculator(BaseNode):
    """
    Performs date arithmetic: difference between dates or adding/subtracting intervals.
    Matches FME DateTimeCalculator.
    """
    node_type = "DateTimeCalculator"
    category = NodeCategory.ATTRIBUTE
    description = "Calculates differences between two dates or offsets a date by days/hours."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("date_column1", ParameterType.STRING, default="", label="Date Column 1"),
            ParameterDef("operation", ParameterType.CHOICE, default="Difference", choices=["Difference", "Add Days", "Subtract Days"], label="Operation"),
            ParameterDef("date_column2", ParameterType.STRING, default="", label="Date Column 2 (for Difference)"),
            ParameterDef("days_offset", ParameterType.INTEGER, default=7, label="Days to Add/Subtract"),
            ParameterDef("result_attribute", ParameterType.STRING, default="_calc_result", label="Result Attribute"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty():
            return {"Output": inp or FeatureDataset.empty()}

        col1 = (params.get("date_column1") or params.get("start_date_attr") or "").strip()
        op = params.get("operation", "Difference")
        col2 = (params.get("date_column2") or params.get("end_date_attr") or "").strip()
        days_off = int(params.get("days_offset", 7))
        res_attr = params.get("result_attribute", "_diff_days").strip() or "_diff_days"

        if not col1 or col1 not in inp.columns:
            return {"Output": inp}

        import pandas as pd
        pdf = inp.to_polars().to_pandas()
        d1 = pd.to_datetime(pdf[col1], errors="coerce")

        if op == "Difference" and col2 and col2 in pdf.columns:
            d2 = pd.to_datetime(pdf[col2], errors="coerce")
            diff_days = np.abs((d2 - d1).dt.total_seconds() / 86400.0)
            pdf[res_attr] = diff_days
            pdf["_diff_days"] = diff_days
        elif op == "Add Days":
            pdf[res_attr] = (d1 + datetime.timedelta(days=days_off)).astype(str)
        elif op == "Subtract Days":
            pdf[res_attr] = (d1 - datetime.timedelta(days=days_off)).astype(str)

        if inp.has_geometry():
            return {"Output": FeatureDataset.from_geopandas(gpd.GeoDataFrame(pdf, crs=inp.crs))}
        return {"Output": FeatureDataset.from_polars(pl.from_pandas(pdf))}


@NodeRegistry.register
class FeatureReader(BaseNode):
    """
    Reads a spatial or tabular dataset dynamically from a file path attribute.
    Matches FME FeatureReader.
    """
    node_type = "FeatureReader"
    category = NodeCategory.READER
    description = "Dynamically reads external spatial or tabular datasets from a dataset path."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Features specifying file_path (optional)")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Read feature records")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("dataset_path", ParameterType.FILE_OPEN, default="", label="Dataset File Path"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("dataset_path", "").strip()
        inp = inputs.get("Input")
        if not path and inp and not inp.is_empty() and "file_path" in inp.columns:
            path = str(inp.to_pandas()["file_path"].iloc[0]).strip()

        if not path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            df = pl.read_csv(path)
            return {"Output": FeatureDataset.from_polars(df)}
        elif ext in (".geojson", ".json", ".shp"):
            gdf = gpd.read_file(path)
            return {"Output": FeatureDataset.from_geopandas(gdf)}
        elif ext == ".parquet":
            df = pl.read_parquet(path)
            return {"Output": FeatureDataset.from_polars(df)}
        else:
            try:
                gdf = gpd.read_file(path)
                return {"Output": FeatureDataset.from_geopandas(gdf)}
            except Exception:
                return {"Output": FeatureDataset.empty()}


@NodeRegistry.register
class SQLExecutor(BaseNode):
    """
    Executes SQL queries against an external SQLite/GeoPackage database or in-memory DB.
    Matches FME SQLExecutor.
    """
    node_type = "SQLExecutor"
    category = NodeCategory.SCRIPTING
    description = "Executes arbitrary SQL queries against a SQLite database file or in-memory SQLite."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("db_file", ParameterType.FILE_OPEN, default="", label="SQLite / GeoPackage DB File (blank for memory)"),
            ParameterDef("sql", ParameterType.EXPRESSION, default="SELECT 1 as test;", label="SQL Statement"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        db_path = params.get("db_file", "").strip() or ":memory:"
        sql = params.get("sql", "SELECT 1 as test;").strip()

        conn = sqlite3.connect(db_path)
        try:
            import pandas as pd
            res_df = pd.read_sql_query(sql, conn)
            conn.close()
            return {"Output": FeatureDataset.from_pandas(res_df)}
        except Exception:
            try:
                cursor = conn.cursor()
                cursor.execute(sql)
                conn.commit()
                conn.close()
                return {"Output": inputs.get("Input") or FeatureDataset.empty()}
            except Exception:
                conn.close()
                return {"Output": FeatureDataset.empty()}


@NodeRegistry.register
class PythonCreator(BaseNode):
    """
    Synthetic feature generator running custom Python code returning a list of dicts or DataFrame.
    Matches FME PythonCreator.
    """
    node_type = "PythonCreator"
    category = NodeCategory.SCRIPTING
    description = "Generates new synthetic features directly from custom Python generator code."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef(
                "python_code",
                ParameterType.EXPRESSION,
                default="# Return a list of dicts\nfeatures = [\n    {'id': 1, 'name': 'Item A', 'val': 100},\n    {'id': 2, 'name': 'Item B', 'val': 200}\n]",
                label="Python Generator Code"
            ),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        code = params.get("python_code", "")
        local_scope = {}
        try:
            exec(code, {}, local_scope)
            res = local_scope.get("features", local_scope.get("df", []))
            if isinstance(res, list):
                df = pl.DataFrame(res)
                return {"Output": FeatureDataset.from_polars(df)}
            elif isinstance(res, pl.DataFrame):
                return {"Output": FeatureDataset.from_polars(res)}
            elif isinstance(res, gpd.GeoDataFrame):
                return {"Output": FeatureDataset.from_geopandas(res)}
            return {"Output": FeatureDataset.empty()}
        except Exception as e:
            return {"Output": FeatureDataset.empty()}


@NodeRegistry.register
class XMLFlattener(BaseNode):
    """
    Flattens XML elements or files into tabular attribute records.
    Matches FME XMLFlattener.
    """
    node_type = "XMLFlattener"
    category = NodeCategory.ATTRIBUTE
    description = "Flattens XML elements into tabular attribute records."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("xml_file_or_string", ParameterType.STRING, default="", label="XML File Path, String, or Column Name"),
            ParameterDef("element_tag", ParameterType.STRING, default="", label="Target Element Tag (Optional)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        xml_input = (params.get("xml_file_or_string") or params.get("xml_attribute") or "").strip()
        elem_tag = params.get("element_tag", "").strip()
        inp = inputs.get("Input")
        records = []

        xml_strings = []
        if inp and not inp.is_empty() and xml_input in inp.columns:
            xml_strings = [str(x) for x in inp.to_polars()[xml_input].to_list() if x]
        elif xml_input:
            if os.path.exists(xml_input):
                with open(xml_input, "r", encoding="utf-8") as f:
                    xml_strings = [f.read()]
            else:
                xml_strings = [xml_input]

        for xml_str in xml_strings:
            try:
                root = ET.fromstring(xml_str)
                targets = root.findall(f".//{elem_tag}") if elem_tag else list(root)
                for child in targets:
                    row = dict(child.attrib)
                    for sub in child:
                        row[sub.tag] = sub.text or ""
                    records.append(row)
            except Exception:
                pass

        if records:
            return {"Output": FeatureDataset.from_polars(pl.DataFrame(records))}
        return {"Output": inputs.get("Input") or FeatureDataset.empty()}
