"""
High-performance table view model for Polars and GeoPandas FeatureDatasets.
"""

from typing import Any, List, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QLineEdit, QLabel, QHeaderView
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
import polars as pl
from pyfme.engine.dataset import FeatureDataset


class FeatureTableModel(QAbstractTableModel):
    def __init__(self, dataset: Optional[FeatureDataset] = None, parent=None):
        super().__init__(parent)
        self.dataset = dataset or FeatureDataset.empty()
        self.columns: List[str] = []
        self._df: Optional[pl.DataFrame] = None
        self._col_series: List[Any] = []
        self._row_count: int = 0
        self._load_data()

    def _load_data(self):
        try:
            if not self.dataset or self.dataset.count() == 0:
                self.columns = []
                self._df = None
                self._col_series = []
                self._row_count = 0
                return

            # Up to 5,000 rows preview with instant zero-copy columnar indexing
            self._df = self.dataset.to_polars().head(5000)
            self.columns = self._df.columns
            self._row_count = len(self._df)
            self._col_series = [self._df[col] for col in self.columns]
        except Exception:
            self.columns = []
            self._df = None
            self._col_series = []
            self._row_count = 0

    def rowCount(self, parent=QModelIndex()) -> int:
        return self._row_count

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.columns)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            col_idx = index.column()
            row_idx = index.row()
            if col_idx < len(self._col_series) and row_idx < self._row_count:
                val = self._col_series[col_idx][row_idx]
                return "<null>" if val is None else str(val)
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder):
        """Instant high-speed sorting in Polars."""
        try:
            if self._df is None or not (0 <= column < len(self.columns)):
                return

            col_name = self.columns[column]
            descending = (order == Qt.SortOrder.DescendingOrder)

            self.layoutAboutToBeChanged.emit()
            self._df = self._df.sort(col_name, descending=descending)
            self._col_series = [self._df[col] for col in self.columns]
            self.layoutChanged.emit()
        except Exception:
            pass

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                if section < len(self.columns):
                    col = self.columns[section]
                    types = self.dataset.get_column_types()
                    dtype = types.get(col, "")
                    return f"{col}\n({dtype})" if dtype else col
            else:
                return str(section + 1)
        return None


class TableInspectorWidget(QWidget):
    """Container with search filter and table view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(4)

        # Filter bar
        top_bar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter attributes / rows...")
        self.search_box.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_box)

        self.count_label = QLabel("0 features")
        self.count_label.setStyleSheet("color: #9fa8da; font-weight: 500;")
        top_bar.addWidget(self.count_label)
        self.layout.addLayout(top_bar)

        # Table view
        self.table_view = QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.verticalHeader().setDefaultSectionSize(24)
        self.table_view.setSortingEnabled(True)
        self.layout.addWidget(self.table_view)

        self.current_dataset: Optional[FeatureDataset] = None

    def set_dataset(self, dataset: FeatureDataset):
        try:
            self.current_dataset = dataset
            model = FeatureTableModel(dataset, self)
            self.table_view.setModel(model)
            cnt = dataset.count() if dataset else 0
            shown = min(cnt, 2000)
            suffix = f" (showing first {shown})" if cnt > 2000 else ""
            self.count_label.setText(f"{cnt:,} features{suffix}")
        except Exception as e:
            self.count_label.setText("Preview unavailable")

    def _on_search_changed(self, text: str):
        try:
            if not self.current_dataset or self.current_dataset.count() == 0:
                return
            query = text.strip().lower()
            if not query:
                self.set_dataset(self.current_dataset)
                return

            # Safe filter on string columns with literal matching
            df = self.current_dataset.to_polars().head(2000)
            conditions = []
            for col in df.columns:
                conditions.append(pl.col(col).cast(pl.String).str.to_lowercase().str.contains(query, literal=True))
            if conditions:
                expr = conditions[0]
                for c in conditions[1:]:
                    expr = expr | c
                filtered_df = df.filter(expr)
                filtered_ds = FeatureDataset.from_polars(filtered_df)
                model = FeatureTableModel(filtered_ds, self)
                self.table_view.setModel(model)
                self.count_label.setText(f"{filtered_ds.count()} matching")
        except Exception:
            pass

