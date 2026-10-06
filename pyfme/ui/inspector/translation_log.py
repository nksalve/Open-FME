"""
FME Translation Log Dock Widget with Error/Warning Badges and Filter Bar.
Replicates FME Workbench Translation Log with structured translation statistics.
"""

from __future__ import annotations
import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTextEdit, QToolButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor


class TranslationLogWidget(QWidget):
    """
    FME Workbench Translation Log Widget.
    Provides Error/Warning/Info count badges, log filtering, clear button,
    and structured execution log output.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.error_count = 0
        self.warning_count = 0
        self.info_count = 0
        self.line_counter = 1

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Header toolbar bar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        # 1. Error badge button
        self.btn_errors = QPushButton("❌  0 Errors")
        self.btn_errors.setStyleSheet("""
            QPushButton {
                background-color: #2b1f24;
                color: #ef5350;
                border: 1px solid #c62828;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        toolbar.addWidget(self.btn_errors)

        # 2. Warning badge button
        self.btn_warnings = QPushButton("⚠️  0 Warnings")
        self.btn_warnings.setStyleSheet("""
            QPushButton {
                background-color: #2b281f;
                color: #ffa726;
                border: 1px solid #ef6c00;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        toolbar.addWidget(self.btn_warnings)

        # 3. Information badge button
        self.btn_info = QPushButton("ℹ️  Information")
        self.btn_info.setStyleSheet("""
            QPushButton {
                background-color: #1a252f;
                color: #42a5f5;
                border: 1px solid #1565c0;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
            }
        """)
        toolbar.addWidget(self.btn_info)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #3e3e4f;")
        toolbar.addWidget(sep)

        # Search filter
        self.search_filter = QLineEdit()
        self.search_filter.setPlaceholderText("Filter translation log text...")
        self.search_filter.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e26;
                border: 1px solid #3d3d4d;
                border-radius: 4px;
                padding: 2px 8px;
                color: #e0e0e0;
                font-size: 11px;
                max-width: 260px;
            }
        """)
        self.search_filter.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.search_filter)

        toolbar.addStretch()

        # Clear log button
        self.btn_clear = QToolButton()
        self.btn_clear.setText("🧹 Clear Log")
        self.btn_clear.clicked.connect(self.clear_log)
        self.btn_clear.setStyleSheet("""
            QToolButton {
                background-color: #262633;
                border: 1px solid #3d3d4d;
                border-radius: 4px;
                padding: 3px 8px;
                color: #bdbdbd;
                font-size: 11px;
            }
            QToolButton:hover {
                background-color: #37374a;
                color: #ffffff;
            }
        """)
        toolbar.addWidget(self.btn_clear)

        layout.addLayout(toolbar)

        # Monospaced Log Console
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #121216;
                color: #dcdcdc;
                font-family: 'Consolas', 'Cascadia Code', monospace;
                font-size: 11px;
                line-height: 1.4;
                border: 1px solid #23232c;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        layout.addWidget(self.log_text)

        # Raw log lines for filtering
        self._raw_lines: list[tuple[str, str]] = []

    def clear_log(self):
        self.log_text.clear()
        self._raw_lines.clear()
        self.error_count = 0
        self.warning_count = 0
        self.info_count = 0
        self.line_counter = 1
        self._update_badges()

    def append_log(self, message: str, level: str = "INFO", elapsed: float = 0.0):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"{self.line_counter:<4} {timestamp}| {elapsed:>4.1f}| {level.upper():<5}| "
        formatted_line = f"{prefix}{message}"

        color = "#e0e0e0"
        if "ERROR" in level.upper() or "[ERROR]" in message.upper():
            self.error_count += 1
            color = "#ef5350"
        elif "WARN" in level.upper() or "[WARN]" in message.upper():
            self.warning_count += 1
            color = "#ffa726"
        elif "STATS" in message or "Finished" in message:
            color = "#66bb6a"
        else:
            self.info_count += 1

        self.line_counter += 1
        self._raw_lines.append((formatted_line, color))
        self._update_badges()

        # Append to HTML viewer safely escaped
        import html
        escaped_line = html.escape(formatted_line).replace("\n", "<br>")
        self.log_text.append(f"<span style='color: {color};'>{escaped_line}</span>")
        # Scroll to bottom
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def _update_badges(self):
        self.btn_errors.setText(f"❌  {self.error_count} Errors")
        self.btn_warnings.setText(f"⚠️  {self.warning_count} Warnings")
        self.btn_info.setText(f"ℹ️  {self.info_count} Info")

    def _apply_filter(self, query: str):
        import html
        q = query.strip().lower()
        self.log_text.clear()
        for line, color in self._raw_lines:
            if not q or q in line.lower():
                escaped = html.escape(line).replace("\n", "<br>")
                self.log_text.append(f"<span style='color: {color};'>{escaped}</span>")

