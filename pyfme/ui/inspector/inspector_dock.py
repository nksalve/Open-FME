"""
FME Visual Data Inspector Dock.
Combines Tabular Data, 2D Spatial Vector Map, and Schema Metadata inspection.
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTextEdit
)
from PyQt6.QtCore import Qt
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.nodes.base import BaseNode
from pyfme.ui.inspector.table_view import TableInspectorWidget
from pyfme.ui.inspector.map_view import MapInspectorWidget


class InspectorDockWidget(QWidget):
    """
    Main bottom dock panel for inspecting features at any port or node in the pipeline.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(4)

        # Header bar
        header_bar = QHBoxLayout()
        self.title_label = QLabel("Visual Data Inspector")
        self.title_label.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 13px;")
        header_bar.addWidget(self.title_label)

        self.info_label = QLabel("Click on any node or output port to inspect its features")
        self.info_label.setStyleSheet("color: #9fa8da;")
        header_bar.addWidget(self.info_label)
        header_bar.addStretch()

        self.layout.addLayout(header_bar)

        # Tab widget
        self.tabs = QTabWidget()
        self.table_widget = TableInspectorWidget()
        self.map_widget = MapInspectorWidget()
        self.schema_widget = QTextEdit()
        self.schema_widget.setReadOnly(True)

        self.tabs.addTab(self.table_widget, "Table View")
        self.tabs.addTab(self.map_widget, "Spatial Map")
        self.tabs.addTab(self.schema_widget, "Schema & Metadata")

        self.layout.addWidget(self.tabs)

    def inspect_dataset(self, node: BaseNode, port_name: str, dataset: Optional[FeatureDataset]):
        try:
            node_name = getattr(node, "name", "Node")
            if dataset is None or not hasattr(dataset, "count") or dataset.count() == 0:
                self.title_label.setText(f"Inspecting: [{node_name}] • Port: {port_name}")
                self.info_label.setText("No features generated yet (run workflow or node first).")
                self.table_widget.set_dataset(FeatureDataset.empty())
                self.map_widget.set_dataset(FeatureDataset.empty())
                self.schema_widget.setPlainText("No data to inspect.")
                return

            cnt = dataset.count()
            has_geom = False
            try:
                has_geom = dataset.has_geometry()
            except Exception:
                pass

            geom_info = " (Spatial Geometry)" if has_geom else " (Tabular)"
            self.title_label.setText(f"Inspecting: [{node_name}] • Port: {port_name}")
            self.info_label.setText(f"{cnt:,} features{geom_info}")

            # 1. Update Table
            try:
                self.table_widget.set_dataset(dataset)
            except Exception as tbl_err:
                self.info_label.setText(f"Table preview warning: {tbl_err}")

            # 2. Update Map
            try:
                self.map_widget.set_dataset(dataset)
                if has_geom:
                    self.tabs.setCurrentIndex(1)
                else:
                    self.tabs.setCurrentIndex(0)
            except Exception:
                self.tabs.setCurrentIndex(0)

            # 3. Update Schema & Metadata text
            schema_text = []
            schema_text.append(f"=== METADATA FOR [{node_name}] / {port_name} ===")
            schema_text.append(f"Total Features: {cnt:,}")
            schema_text.append(f"Has Geometry: {has_geom}")
            if has_geom:
                try:
                    schema_text.append(f"CRS: {dataset.crs}")
                    bounds = dataset.get_bounds()
                    if bounds:
                        schema_text.append(f"Extent (BBox): MinX={bounds[0]:.4f}, MinY={bounds[1]:.4f}, MaxX={bounds[2]:.4f}, MaxY={bounds[3]:.4f}")
                except Exception:
                    pass
            schema_text.append("\n=== COLUMN ATTRIBUTES ===")
            try:
                types = dataset.get_column_types()
                for col, dt in types.items():
                    schema_text.append(f" • {col}: {dt}")
            except Exception as col_err:
                schema_text.append(f"Unable to read column types: {col_err}")

            self.schema_widget.setPlainText("\n".join(schema_text))
        except Exception as e:
            self.info_label.setText(f"Inspection error: {e}")
            self.schema_widget.setPlainText(f"Could not inspect dataset:\n{e}")

