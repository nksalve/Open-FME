"""
Workflow execution engine. Runs DAG pipelines, routes datasets across ports,
tracks metrics and emits execution events.
"""

from __future__ import annotations
import time
from typing import Any, Callable, Dict, List, Optional
import polars as pl
import geopandas as gpd
from pyfme.engine.graph import WorkflowGraph, Connection
from pyfme.engine.dataset import FeatureDataset


class ExecutionLogger:
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback
        self.messages: List[Tuple[str, str, str]] = []

    def log(self, message: str, level: str = "INFO"):
        timestamp = time.strftime("%H:%M:%S")
        self.messages.append((timestamp, level, message))
        if self.log_callback:
            self.log_callback(f"[{timestamp}] [{level}] {message}", level)


class WorkflowRunner:
    """
    Executes a WorkflowGraph sequentially or with partial runs.
    """

    def __init__(self, graph: WorkflowGraph, log_callback: Optional[Callable[[str, str], None]] = None):
        self.graph = graph
        self.logger = ExecutionLogger(log_callback)
        self.is_running = False
        self.stop_requested = False

        # Hooks
        self.on_node_start: Optional[Callable[[str], None]] = None
        self.on_node_complete: Optional[Callable[[str, bool, int, float, Optional[str]], None]] = None
        self.on_connection_updated: Optional[Callable[[Connection, int], None]] = None
        self.on_workflow_complete: Optional[Callable[[bool, float, str], None]] = None

    def request_stop(self):
        self.stop_requested = True

    def run(self, target_node_id: Optional[str] = None, mode: str = "all") -> bool:
        """Execute the complete graph or a partial run ('to_this', 'from_this')."""
        self.is_running = True
        self.stop_requested = False
        start_time = time.time()

        mode_desc = f" ({mode} [{self.graph.nodes[target_node_id].name}])" if target_node_id and mode != "all" and target_node_id in self.graph.nodes else ""
        self.logger.log(f"Starting workflow execution: '{self.graph.name}'{mode_desc}")

        try:
            if mode == "to_this" and target_node_id and target_node_id in self.graph.nodes:
                sub = self.graph.get_ancestors(target_node_id) | {target_node_id}
                order = self.graph.get_topological_order_for_subgraph(sub)
            elif mode == "from_this" and target_node_id and target_node_id in self.graph.nodes:
                sub = self.graph.get_descendants(target_node_id) | {target_node_id}
                order = self.graph.get_topological_order_for_subgraph(sub)
            else:
                order = self.graph.get_topological_order()
        except Exception as e:
            self.logger.log(f"Graph validation error: {str(e)}", "ERROR")
            if self.on_workflow_complete:
                self.on_workflow_complete(False, 0.0, str(e))
            self.is_running = False
            return False

        # Buffer holding node outputs: node_id -> {port_name: FeatureDataset}
        node_outputs: Dict[str, Dict[str, FeatureDataset]] = {}

        total_features = 0
        overall_success = True

        for node_id in order:
            if self.stop_requested:
                self.logger.log("Workflow execution stopped by user.", "WARN")
                overall_success = False
                break

            node = self.graph.nodes[node_id]
            self.logger.log(f"Running transformer: [{node.name}] ({node.node_type})")

            if self.on_node_start:
                self.on_node_start(node_id)

            node_t0 = time.time()
            node.last_error = None

            try:
                # 1. Gather inputs for this node from incoming connections
                incoming = self.graph.get_upstream_connections(node_id)
                inputs_map: Dict[str, List[FeatureDataset]] = {}

                for conn in incoming:
                    src_outputs = node_outputs.get(conn.from_node_id)
                    # Feature Caching: if not produced in current run, reuse cached upstream output!
                    if src_outputs is None:
                        src_node = self.graph.nodes.get(conn.from_node_id)
                        if src_node and src_node.last_outputs:
                            src_outputs = src_node.last_outputs

                    src_ds = src_outputs.get(conn.from_port) if src_outputs else None
                    if src_ds is not None:
                        inputs_map.setdefault(conn.to_port, []).append(src_ds)
                        # Update wire feature count
                        conn.feature_count = src_ds.count()
                        if self.on_connection_updated:
                            self.on_connection_updated(conn, conn.feature_count)

                # Merge inputs if multiple connections lead to the same port
                resolved_inputs: Dict[str, FeatureDataset] = {}
                for port_name, datasets in inputs_map.items():
                    if len(datasets) == 1:
                        resolved_inputs[port_name] = datasets[0]
                    elif len(datasets) > 1:
                        # Combine multiple datasets
                        resolved_inputs[port_name] = self._merge_datasets(datasets)

                # 2. Execute node
                outputs = node.execute(resolved_inputs, node.params)
                node_duration = time.time() - node_t0

                if not isinstance(outputs, dict):
                    outputs = {"Output": outputs} if isinstance(outputs, FeatureDataset) else {}

                # 3. Store outputs & cache on node for inspection
                node.last_inputs = resolved_inputs
                node.last_outputs = outputs
                node.execution_duration_sec = node_duration

                node_count = sum(
                    ds.count() for ds in outputs.values()
                    if ds is not None and hasattr(ds, "count")
                )
                node.features_processed = node_count
                total_features += node_count

                node_outputs[node_id] = outputs

                self.logger.log(f"Done [{node.name}]: {node_count} features in {node_duration:.3f}s")
                if self.on_node_complete:
                    self.on_node_complete(node_id, True, node_count, node_duration, None)

            except Exception as ex:
                node_duration = time.time() - node_t0
                node.last_error = str(ex)
                node.execution_duration_sec = node_duration
                if not hasattr(node, "last_outputs") or node.last_outputs is None:
                    node.last_outputs = {}
                self.logger.log(f"Error in [{node.name}]: {str(ex)}", "ERROR")
                if self.on_node_complete:
                    self.on_node_complete(node_id, False, 0, node_duration, str(ex))
                overall_success = False
                break

        total_duration = time.time() - start_time
        summary = f"Execution finished in {total_duration:.2f}s with {total_features} features processed."
        self.logger.log(summary, "INFO" if overall_success else "ERROR")

        if self.on_workflow_complete:
            self.on_workflow_complete(overall_success, total_duration, summary)

        self.is_running = False
        return overall_success

    def _merge_datasets(self, datasets: List[FeatureDataset]) -> FeatureDataset:
        """Merges multiple FeatureDatasets into one defensively."""
        try:
            valid_datasets = [d for d in datasets if d is not None and d.count() > 0]
            if not valid_datasets:
                return FeatureDataset.empty()

            has_geom = any(d.has_geometry() for d in valid_datasets)
            if has_geom:
                gdfs = []
                for d in valid_datasets:
                    try:
                        gdfs.append(d.to_geopandas())
                    except Exception:
                        pass
                if not gdfs:
                    return FeatureDataset.empty()
                combined_gdf = gpd.pd.concat(gdfs, ignore_index=True)
                target_crs = gdfs[0].crs if hasattr(gdfs[0], "crs") else "EPSG:4326"
                return FeatureDataset.from_geopandas(gpd.GeoDataFrame(combined_gdf, crs=target_crs))
            else:
                dfs = []
                for d in valid_datasets:
                    try:
                        dfs.append(d.to_polars())
                    except Exception:
                        pass
                if not dfs:
                    return FeatureDataset.empty()
                combined_df = pl.concat(dfs, how="diagonal")
                return FeatureDataset.from_polars(combined_df)
        except Exception as e:
            self.logger.log(f"Dataset merge warning: {e}", "WARN")
            for d in datasets:
                if d is not None and d.count() > 0:
                    return d
            return FeatureDataset.empty()

