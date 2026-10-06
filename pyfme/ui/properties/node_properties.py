"""
Dynamic Parameter & Property Inspector for selected nodes.
Generates input controls matching node parameters, including file pickers and code editors.
"""

from typing import Any, Dict, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QComboBox, QPushButton, QFileDialog,
    QPlainTextEdit, QFormLayout, QGroupBox, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from pyfme.engine.nodes.base import BaseNode, ParameterDef, ParameterType


class NodePropertiesWidget(QWidget):
    """
    Inspector pane that dynamically builds parameter inputs for the selected node.
    """

    parameters_changed = pyqtSignal(object)  # Emits BaseNode

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_node: Optional[BaseNode] = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Header info
        self.header_title = QLabel("No Selection")
        self.header_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        main_layout.addWidget(self.header_title)

        self.desc_label = QLabel("Select a node on the canvas to configure parameters.")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #9fa8da; margin-bottom: 6px;")
        main_layout.addWidget(self.desc_label)

        # Scroll area for form
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.form_layout = QFormLayout(self.scroll_content)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

    def set_node(self, node: Optional[BaseNode]):
        self.current_node = node
        # Clear existing controls
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not node:
            self.header_title.setText("No Selection")
            self.desc_label.setText("Select a node on the canvas to configure parameters.")
            return

        self.header_title.setText(f"{node.name} ({node.node_type})")
        self.desc_label.setText(node.description)

        # 1. Custom Name input
        name_edit = QLineEdit(node.name)
        name_edit.textChanged.connect(self._on_name_changed)
        self.form_layout.addRow("Title:", name_edit)

        # 2. Parameters defined by node
        defs = node.get_parameter_defs()
        if not defs:
            lbl = QLabel("(This transformer has no configurable parameters)")
            lbl.setStyleSheet("color: #757585; font-style: italic;")
            self.form_layout.addRow("", lbl)
            return

        for p_def in defs:
            val = node.get_param(p_def.name, p_def.default)
            control = self._create_control_for_param(p_def, val)
            self.form_layout.addRow(f"{p_def.label}:", control)

    def _create_control_for_param(self, p_def: ParameterDef, val: Any) -> QWidget:
        if p_def.param_type == ParameterType.STRING:
            w = QLineEdit(str(val if val is not None else ""))
            w.textChanged.connect(lambda txt, name=p_def.name: self._update_param(name, txt))
            return w

        elif p_def.param_type == ParameterType.INTEGER:
            w = QSpinBox()
            w.setRange(-9999999, 9999999)
            try:
                i_val = int(float(val)) if val is not None else 0
            except (ValueError, TypeError):
                i_val = 0
            w.setValue(i_val)
            w.valueChanged.connect(lambda v, name=p_def.name: self._update_param(name, v))
            return w

        elif p_def.param_type == ParameterType.FLOAT:
            w = QDoubleSpinBox()
            w.setRange(-9999999.0, 9999999.0)
            w.setDecimals(4)
            try:
                f_val = float(val) if val is not None else 0.0
            except (ValueError, TypeError):
                f_val = 0.0
            w.setValue(f_val)
            w.valueChanged.connect(lambda v, name=p_def.name: self._update_param(name, v))
            return w


        elif p_def.param_type == ParameterType.BOOLEAN:
            w = QCheckBox()
            w.setChecked(bool(val))
            w.stateChanged.connect(lambda st, name=p_def.name: self._update_param(name, st == Qt.CheckState.Checked.value))
            return w

        elif p_def.param_type == ParameterType.CHOICE:
            w = QComboBox()
            w.addItems(p_def.choices)
            if str(val) in p_def.choices:
                w.setCurrentText(str(val))
            w.currentTextChanged.connect(lambda txt, name=p_def.name: self._update_param(name, txt))
            return w

        elif p_def.param_type in (ParameterType.FILE_OPEN, ParameterType.FILE_SAVE):
            container = QWidget()
            h_box = QHBoxLayout(container)
            h_box.setContentsMargins(0, 0, 0, 0)
            path_edit = QLineEdit(str(val if val is not None else ""))
            path_edit.textChanged.connect(lambda txt, name=p_def.name: self._update_param(name, txt))
            h_box.addWidget(path_edit)

            btn = QPushButton("Browse...")
            if p_def.param_type == ParameterType.FILE_OPEN:
                btn.clicked.connect(lambda checked, edit=path_edit, flt=p_def.file_filter: self._pick_open_file(edit, flt))
            else:
                btn.clicked.connect(lambda checked, edit=path_edit, flt=p_def.file_filter: self._pick_save_file(edit, flt))
            h_box.addWidget(btn)
            return container

        elif p_def.param_type == ParameterType.CODE:
            # Code editor for PythonCaller
            w = QPlainTextEdit()
            w.setPlainText(str(val or ""))
            font = QFont("Consolas", 10)
            w.setFont(font)
            w.setMinimumHeight(180)
            w.textChanged.connect(lambda ed=w, name=p_def.name: self._update_param(name, ed.toPlainText()))
            return w

        # Default fallback
        w = QLineEdit(str(val or ""))
        w.textChanged.connect(lambda txt, name=p_def.name: self._update_param(name, txt))
        return w

    def _update_param(self, name: str, value: Any):
        if self.current_node:
            self.current_node.set_param(name, value)
            self.parameters_changed.emit(self.current_node)

    def _on_name_changed(self, new_name: str):
        if self.current_node and new_name.strip():
            self.current_node.name = new_name.strip()
            self.parameters_changed.emit(self.current_node)

    def _pick_open_file(self, line_edit: QLineEdit, file_filter: str):
        path, _ = QFileDialog.getOpenFileName(self, "Select Input File", line_edit.text(), file_filter)
        if path:
            line_edit.setText(path)

    def _pick_save_file(self, line_edit: QLineEdit, file_filter: str):
        path, _ = QFileDialog.getSaveFileName(self, "Select Output Destination", line_edit.text(), file_filter)
        if path:
            line_edit.setText(path)
