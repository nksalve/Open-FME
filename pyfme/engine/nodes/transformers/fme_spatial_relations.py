"""
FME Spatial Relationships & Queries from FME_Transformers_GIS.xlsx:
- SpatialRelator (Tests predicates and records relationships as attributes)
- NeighborFinder (Finds nearest neighbor, distance, with Matched/Unmatched ports)
- Matcher (Identifies duplicate or identical geometry/attributes)
- Counter (Adds incremental sequential number to features)
- Sampler (Samples every Nth feature or first N features)
"""

from typing import Any, Dict, List
import geopandas as gpd
import polars as pl
from shapely.strtree import STRtree
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class SpatialRelator(BaseNode):
    """
    Evaluates spatial relationships between Base and Candidate features,
    recording matching flags (intersects, contains, within, touches) as attributes.
    """
    node_type = "SpatialRelator"
    category = NodeCategory.SPATIAL
    description = "Tests and records spatial relationships (intersects, within, etc.) as attributes (FME SpatialRelator)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Base", PortType.INPUT, "Base features to test"),
            Port("Candidate", PortType.INPUT, "Candidate features to test against"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Base features with relationship attributes")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef(
                "tests",
                ParameterType.STRING,
                default="intersects,contains,within",
                label="Tests to Run (comma-separated: intersects, contains, within, touches)",
            ),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        base_ds = inputs.get("Base")
        cand_ds = inputs.get("Candidate")

        if not base_ds or base_ds.count() == 0:
            return {"Output": FeatureDataset.empty()}
        if not cand_ds or cand_ds.count() == 0 or not cand_ds.has_geometry():
            return {"Output": base_ds}

        base_gdf = base_ds.to_geopandas().copy()
        cand_gdf = cand_ds.to_geopandas()

        if base_gdf.crs and cand_gdf.crs and base_gdf.crs != cand_gdf.crs:
            cand_gdf = cand_gdf.to_crs(base_gdf.crs)

        cand_tree = STRtree(cand_gdf.geometry.dropna())
        tests_str = params.get("tests", "intersects,contains,within")
        tests = [t.strip().lower() for t in tests_str.split(",")]

        for t in tests:
            col_name = f"_relates_{t}"
            results = []
            for geom in base_gdf.geometry:
                if geom is None or geom.is_empty:
                    results.append(False)
                    continue
                indices = cand_tree.query(geom, predicate=t if hasattr(cand_tree, "query") else None)
                results.append(len(indices) > 0)
            base_gdf[col_name] = results

        return {"Output": FeatureDataset.from_geopandas(base_gdf)}


@NodeRegistry.register
class NeighborFinder(BaseNode):
    """
    Finds the nearest neighbor and its distance in CRS units.
    Outputs Matched (nearest found) and Unmatched ports.
    """
    node_type = "NeighborFinder"
    category = NodeCategory.SPATIAL
    description = "Finds nearest neighbor, attaches distance and candidate attributes (FME NeighborFinder)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [
            Port("Base", PortType.INPUT, "Source features"),
            Port("Candidate", PortType.INPUT, "Neighbor candidates"),
        ]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Matched", PortType.OUTPUT, "Features with nearest neighbor found"),
            Port("Unmatched", PortType.OUTPUT, "Features with no neighbor within search radius"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("max_distance", ParameterType.FLOAT, default=0.0, label="Max Search Distance (0 for unlimited)"),
            ParameterDef("distance_attribute", ParameterType.STRING, default="_distance", label="Distance Attribute Name"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        base_ds = inputs.get("Base")
        cand_ds = inputs.get("Candidate")

        if not base_ds or base_ds.count() == 0:
            return {"Matched": FeatureDataset.empty(), "Unmatched": FeatureDataset.empty()}
        if not cand_ds or cand_ds.count() == 0 or not cand_ds.has_geometry():
            return {"Matched": FeatureDataset.empty(), "Unmatched": base_ds}

        base_gdf = base_ds.to_geopandas()
        cand_gdf = cand_ds.to_geopandas()

        if base_gdf.crs and cand_gdf.crs and base_gdf.crs != cand_gdf.crs:
            cand_gdf = cand_gdf.to_crs(base_gdf.crs)

        dist_col = params.get("distance_attribute", "_distance").strip() or "_distance"
        max_dist = float(params.get("max_distance", 0.0))
        max_d_arg = max_dist if max_dist > 0 else None

        joined = gpd.sjoin_nearest(
            base_gdf,
            cand_gdf,
            how="left",
            distance_col=dist_col,
            max_distance=max_d_arg,
        )

        matched_mask = joined[dist_col].notnull()
        matched_gdf = joined[matched_mask].copy()
        unmatched_gdf = joined[~matched_mask].copy()

        if "index_right" in matched_gdf.columns:
            matched_gdf = matched_gdf.drop(columns=["index_right"])
        if "index_right" in unmatched_gdf.columns:
            unmatched_gdf = unmatched_gdf.drop(columns=["index_right"])

        return {
            "Matched": FeatureDataset.from_geopandas(matched_gdf),
            "Unmatched": FeatureDataset.from_geopandas(unmatched_gdf),
        }


@NodeRegistry.register
class Matcher(BaseNode):
    """
    Identifies duplicate or identical geometries.
    Routes to Matched and NotMatched ports.
    """
    node_type = "Matcher"
    category = NodeCategory.SPATIAL
    description = "Finds duplicate or identical geometries (FME Matcher)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Matched", PortType.OUTPUT, "Duplicate matching geometries"),
            Port("SingleMatched", PortType.OUTPUT, "Unique features without duplicates"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return []

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0 or not inp.has_geometry():
            return {"Matched": FeatureDataset.empty(), "SingleMatched": inp or FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        # Compute WKB hashes for exact geometry matching
        wkb_series = gdf.geometry.apply(lambda g: g.wkb if g else None)
        dupe_mask = wkb_series.duplicated(keep=False)

        matched = gdf[dupe_mask]
        single = gdf[~dupe_mask]

        return {
            "Matched": FeatureDataset.from_geopandas(matched),
            "SingleMatched": FeatureDataset.from_geopandas(single),
        }


@NodeRegistry.register
class Counter(BaseNode):
    """
    Adds a sequential integer counter attribute to each feature.
    FME Counter transformer.
    """
    node_type = "Counter"
    category = NodeCategory.ATTRIBUTE
    description = "Numbers features with an incremental counter sequence (FME Counter)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT)]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("counter_name", ParameterType.STRING, default="_count", label="Counter Attribute Name"),
            ParameterDef("start_value", ParameterType.INTEGER, default=1, label="Start Value"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Output": FeatureDataset.empty()}

        c_name = params.get("counter_name", "_count").strip() or "_count"
        start = int(params.get("start_value", 1))

        df = inp.to_polars()
        cnt_series = pl.int_range(start, start + len(df), dtype=pl.Int64).alias(c_name)
        res_df = df.with_columns(cnt_series)

        if inp.has_geometry():
            return {"Output": FeatureDataset.from_polars(res_df, geometry_col=inp.geometry_col, crs=inp.crs)}
        return {"Output": FeatureDataset.from_polars(res_df)}


@NodeRegistry.register
class Sampler(BaseNode):
    """
    Takes every Nth feature, first N, or random sample of features.
    Routes to Sampled and NotSampled output ports.
    """
    node_type = "Sampler"
    category = NodeCategory.ATTRIBUTE
    description = "Takes every Nth or first N features, routing to Sampled and NotSampled (FME Sampler)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Sampled", PortType.OUTPUT, "Sampled features"),
            Port("NotSampled", PortType.OUTPUT, "Unsampled features"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef(
                "sample_type",
                ParameterType.CHOICE,
                default="every_nth",
                choices=["every_nth", "first_n", "random_fraction"],
                label="Sampling Mode",
            ),
            ParameterDef("sample_rate", ParameterType.FLOAT, default=2.0, label="Rate / N Value"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.count() == 0:
            return {"Sampled": FeatureDataset.empty(), "NotSampled": FeatureDataset.empty()}

        mode = params.get("sample_type", "every_nth")
        rate = float(params.get("sample_rate", 2.0))
        df = inp.to_polars()

        if mode == "first_n":
            n = int(rate)
            sampled_df = df.head(n)
            not_sampled_df = df.slice(n)
        elif mode == "every_nth":
            step = max(int(rate), 1)
            indices = list(range(0, len(df), step))
            sampled_df = df[indices]
            not_indices = [i for i in range(len(df)) if i % step != 0]
            not_sampled_df = df[not_indices]
        else:
            # Random fraction
            frac = min(max(rate, 0.0), 1.0)
            sampled_df = df.sample(fraction=frac, seed=42)
            sampled_set = set(sampled_df.with_row_index("__r")["__r"])
            not_sampled_df = df.with_row_index("__r").filter(~pl.col("__r").is_in(list(sampled_set))).drop("__r")

        if inp.has_geometry():
            return {
                "Sampled": FeatureDataset.from_polars(sampled_df, geometry_col=inp.geometry_col, crs=inp.crs),
                "NotSampled": FeatureDataset.from_polars(not_sampled_df, geometry_col=inp.geometry_col, crs=inp.crs),
            }
        return {
            "Sampled": FeatureDataset.from_polars(sampled_df),
            "NotSampled": FeatureDataset.from_polars(not_sampled_df),
        }
