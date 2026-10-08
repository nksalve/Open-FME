"""
FME Workbench 'Generate Workspace' (Ctrl+G) Dialog and Quick Reader/Writer Dialogs.
Matches FME Desktop 2018 format-to-format translation generation.
"""

from __future__ import annotations
import os
from typing import Optional, Tuple
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFileDialog, QGroupBox, QDialogButtonBox, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon


FORMAT_READERS = {
    "CSV (Comma Separated Value)": "CSVReader",
    "ESRI Shapefile (*.shp)": "ShapefileReader",
    "GeoJSON (*.geojson, *.json)": "GeoJSONReader",
    "Microsoft Excel (*.xlsx, *.xls)": "ExcelReader",
    "Apache Parquet (*.parquet)": "ParquetReader",
}

FORMAT_WRITERS = {
    "ESRI Shapefile (*.shp)": "ShapefileWriter",
    "GeoJSON (*.geojson, *.json)": "GeoJSONWriter",
    "CSV (Comma Separated Value)": "CSVWriter",
    "Microsoft Excel (*.xlsx, *.xls)": "ExcelWriter",
    "Apache Parquet (*.parquet)": "ParquetWriter",
}


class GenerateWorkspaceDialog(QDialog):
    """
    FME Generate Workspace dialog (Ctrl+G).
    Defines reader format/dataset and writer format/dataset, then generates the complete pipeline.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Workspace - open-FME Workbench")
        self.setFixedWidth(520)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
                color: #ffffff;
            }
            QGroupBox {
                border: 1px solid #3c3c4e;
                border-radius: 6px;
                margin-top: 14px;
                font-weight: bold;
                color: #e0e0e0;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel {
                color: #cfd8dc;
            }
            QLineEdit, QComboBox {
                background-color: #2b2b36;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 6px 10px;
                color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #29b6f6;
            }
            QPushButton {
                background-color: #3949ab;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3f51b5;
            }
            QPushButton#browseBtn {
                background-color: #37474f;
                padding: 6px 12px;
            }
            QPushButton#browseBtn:hover {
                background-color: #455a64;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Header Title
        hdr = QLabel("Generate Format-to-Format Workspace")
        hdr.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(hdr)

        info = QLabel("Define source and destination datasets to automatically generate your translation.")
        info.setStyleSheet("color: #90a4ae;")
        layout.addWidget(info)

        # 1. Reader Group
        reader_group = QGroupBox("Reader (Source Data)")
        r_layout = QGridLayout(reader_group)

        r_layout.addWidget(QLabel("Format:"), 0, 0)
        self.reader_format_combo = QComboBox()
        self.reader_format_combo.addItems(list(FORMAT_READERS.keys()))
        self.reader_format_combo.currentIndexChanged.connect(self._on_reader_format_changed)
        r_layout.addWidget(self.reader_format_combo, 0, 1, 1, 2)

        r_layout.addWidget(QLabel("Dataset:"), 1, 0)
        self.reader_path_edit = QLineEdit()
        self.reader_path_edit.setPlaceholderText("Select source file path...")
        r_layout.addWidget(self.reader_path_edit, 1, 1)

        self.btn_browse_reader = QPushButton("Browse...")
        self.btn_browse_reader.setObjectName("browseBtn")
        self.btn_browse_reader.clicked.connect(self._browse_reader)
        r_layout.addWidget(self.btn_browse_reader, 1, 2)

        layout.addWidget(reader_group)

        # 2. Writer Group
        writer_group = QGroupBox("Writer (Destination Data)")
        w_layout = QGridLayout(writer_group)

        w_layout.addWidget(QLabel("Format:"), 0, 0)
        self.writer_format_combo = QComboBox()
        self.writer_format_combo.addItems(list(FORMAT_WRITERS.keys()))
        w_layout.addWidget(self.writer_format_combo, 0, 1, 1, 2)

        w_layout.addWidget(QLabel("Dataset:"), 1, 0)
        self.writer_path_edit = QLineEdit()
        self.writer_path_edit.setPlaceholderText("Select destination output path...")
        w_layout.addWidget(self.writer_path_edit, 1, 1)

        self.btn_browse_writer = QPushButton("Browse...")
        self.btn_browse_writer.setObjectName("browseBtn")
        self.btn_browse_writer.clicked.connect(self._browse_writer)
        w_layout.addWidget(self.btn_browse_writer, 1, 2)

        layout.addWidget(writer_group)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("background-color: #455a64;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton("⚡ Generate Workspace")
        self.btn_ok.setStyleSheet("background-color: #00897b; padding: 7px 18px;")
        self.btn_ok.clicked.connect(self._on_generate)
        btn_box.addWidget(self.btn_ok)

        layout.addLayout(btn_box)

    def _on_reader_format_changed(self, idx: int):
        pass

    def _browse_reader(self):
        fmt_text = self.reader_format_combo.currentText()
        filt = "All Files (*.*)"
        if "Shapefile" in fmt_text:
            filt = "Shapefiles (*.shp);;All Files (*.*)"
        elif "GeoJSON" in fmt_text:
            filt = "GeoJSON (*.geojson *.json);;All Files (*.*)"
        elif "CSV" in fmt_text:
            filt = "CSV Files (*.csv);;All Files (*.*)"
        elif "Excel" in fmt_text:
            filt = "Excel Files (*.xlsx *.xls);;All Files (*.*)"
        elif "Parquet" in fmt_text:
            filt = "Parquet Files (*.parquet);;All Files (*.*)"

        path, _ = QFileDialog.getOpenFileName(self, "Select Source Dataset", "", filt)
        if path:
            self.reader_path_edit.setText(path)
            # Auto-suggest writer path if empty
            if not self.writer_path_edit.text():
                base_dir = os.path.dirname(path)
                name, _ = os.path.splitext(os.path.basename(path))
                w_fmt = self.writer_format_combo.currentText()
                ext = ".geojson" if "GeoJSON" in w_fmt else (".shp" if "Shapefile" in w_fmt else ".csv")
                self.writer_path_edit.setText(os.path.join(base_dir, f"{name}_output{ext}"))

    def _browse_writer(self):
        w_fmt = self.writer_format_combo.currentText()
        filt = "All Files (*.*)"
        if "Shapefile" in w_fmt:
            filt = "Shapefiles (*.shp);;All Files (*.*)"
        elif "GeoJSON" in w_fmt:
            filt = "GeoJSON (*.geojson *.json);;All Files (*.*)"
        elif "CSV" in w_fmt:
            filt = "CSV Files (*.csv);;All Files (*.*)"
        elif "Excel" in fmt:
            filt = "Excel Files (*.xlsx);;All Files (*.*)"
        elif "Parquet" in w_fmt:
            filt = "Parquet Files (*.parquet);;All Files (*.*)"

        path, _ = QFileDialog.getSaveFileName(self, "Select Destination Dataset", self.writer_path_edit.text() or "", filt)
        if path:
            self.writer_path_edit.setText(path)

    def _on_generate(self):
        r_path = self.reader_path_edit.text().strip()
        w_path = self.writer_path_edit.text().strip()

        if not r_path:
            QMessageBox.warning(self, "Source Dataset Required", "Please specify a valid source dataset path.")
            return
        if not w_path:
            QMessageBox.warning(self, "Destination Dataset Required", "Please specify a destination output path.")
            return

        self.accept()

    def get_result(self) -> Tuple[str, str, str, str]:
        """Returns (reader_node_type, reader_path, writer_node_type, writer_path)."""
        r_type = FORMAT_READERS[self.reader_format_combo.currentText()]
        r_path = self.reader_path_edit.text().strip()
        w_type = FORMAT_WRITERS[self.writer_format_combo.currentText()]
        w_path = self.writer_path_edit.text().strip()
        return r_type, r_path, w_type, w_path

    def get_config(self) -> dict:
        """Returns dictionary config matching main_window expectations."""
        r_type, r_path, w_type, w_path = self.get_result()
        return {
            "reader_type": r_type,
            "reader_path": r_path,
            "writer_type": w_type,
            "writer_path": w_path,
            "workspace_name": f"{r_type} to {w_type} Translation",
        }



class AddReaderDialog(QDialog):
    """FME Add Reader dialog (Ctrl+Alt+R)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Reader - open-FME Workbench")
        self.setFixedWidth(460)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        grid = QGridLayout()

        grid.addWidget(QLabel("Format:"), 0, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(list(FORMAT_READERS.keys()))
        grid.addWidget(self.format_combo, 0, 1)

        grid.addWidget(QLabel("Dataset:"), 1, 0)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Source file path...")
        grid.addWidget(self.path_edit, 1, 1)

        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse)
        grid.addWidget(btn_browse, 1, 2)

        layout.addLayout(grid)

        bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Reader Dataset", "", "All Files (*.*)")
        if path:
            self.path_edit.setText(path)

    def get_result(self) -> Tuple[str, str]:
        return FORMAT_READERS[self.format_combo.currentText()], self.path_edit.text().strip()


class AddWriterDialog(QDialog):
    """FME Add Writer dialog (Ctrl+Alt+W)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Writer - open-FME Workbench")
        self.setFixedWidth(460)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        grid = QGridLayout()

        grid.addWidget(QLabel("Format:"), 0, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(list(FORMAT_WRITERS.keys()))
        grid.addWidget(self.format_combo, 0, 1)

        grid.addWidget(QLabel("Dataset:"), 1, 0)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Destination file path...")
        grid.addWidget(self.path_edit, 1, 1)

        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse)
        grid.addWidget(btn_browse, 1, 2)

        layout.addLayout(grid)

        bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Destination Dataset", "", "All Files (*.*)")
        if path:
            self.path_edit.setText(path)

    def get_result(self) -> Tuple[str, str]:
        return FORMAT_WRITERS[self.format_combo.currentText()], self.path_edit.text().strip()
