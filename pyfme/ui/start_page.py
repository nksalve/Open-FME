"""
FME Workbench Start Page Tab.
Displays recent workspaces, template starters, quick action cards, and getting started guides.
"""

from __future__ import annotations
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QGridLayout, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QCursor


class StartPageWidget(QWidget):
    """
    Start Tab widget shown in open-FME Workbench (matching FME Start tab).
    """

    new_workspace_clicked = pyqtSignal()
    open_workspace_clicked = pyqtSignal()
    generate_workspace_clicked = pyqtSignal()
    open_sample_clicked = pyqtSignal()
    open_file_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        # 1. Header Banner
        header_layout = QVBoxLayout()
        header_layout.setSpacing(6)

        title = QLabel("open-FME Workbench")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(title)

        subtitle = QLabel("Open-Source Spatial & Tabular ETL Automation Platform • Polars + GeoPandas Engine")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setStyleSheet("color: #9e9ea8;")
        header_layout.addWidget(subtitle)

        main_layout.addLayout(header_layout)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #2f2f3d;")
        main_layout.addWidget(divider)

        # 2. Main Content Grid (Get Started Cards + Recent Workspaces)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(20)

        # Left Column: Quick Actions
        left_box = QVBoxLayout()
        left_box.setSpacing(12)

        sec_title = QLabel("Get Started")
        sec_title.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        sec_title.setStyleSheet("color: #e0e0e0;")
        left_box.addWidget(sec_title)

        # Card 1: New Workspace
        btn_new = self._create_card_button(
            "📄  New Workspace",
            "Start with an empty canvas and build a new visual DAG pipeline.",
            "#1976d2"
        )
        btn_new.clicked.connect(self.new_workspace_clicked.emit)
        left_box.addWidget(btn_new)

        # Card 2: Generate Workspace (Ctrl+G)
        btn_gen = self._create_card_button(
            "⚡  Generate Workspace (Ctrl+G)",
            "Automated FME translation generator: connect Reader formats directly to Writer datasets.",
            "#8e24aa"
        )
        btn_gen.clicked.connect(self.generate_workspace_clicked.emit)
        left_box.addWidget(btn_gen)

        # Card 3: Open Workspace
        btn_open = self._create_card_button(
            "📂  Open Existing Workspace (.fpy)",
            "Browse and open an open-FME workspace file or FME-compatible workflow.",
            "#00897b"
        )
        btn_open.clicked.connect(self.open_workspace_clicked.emit)
        left_box.addWidget(btn_open)

        # Card 4: Community Mapping Spatial Sample
        btn_sample = self._create_card_button(
            "🌍  Open Community Mapping & Routing Sample",
            "Pre-configured spatial pipeline featuring Bookmarks, Notes, ShortestPathFinder, and Bufferers.",
            "#e65100"
        )
        btn_sample.clicked.connect(self.open_sample_clicked.emit)
        left_box.addWidget(btn_sample)

        left_box.addStretch()
        grid.addLayout(left_box, 0, 0)

        # Right Column: Recent Files & Tips
        right_box = QVBoxLayout()
        right_box.setSpacing(12)

        recent_title = QLabel("Recent Workspaces & Templates")
        recent_title.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        recent_title.setStyleSheet("color: #e0e0e0;")
        right_box.addWidget(recent_title)

        self.recent_list = QListWidget()
        self.recent_list.setStyleSheet("""
            QListWidget {
                background-color: #1a1a24;
                border: 1px solid #2d2d3c;
                border-radius: 6px;
                padding: 6px;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid #232330;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #272738;
            }
            QListWidget::item:selected {
                background-color: #1976d2;
                color: #ffffff;
            }
        """)
        self.recent_list.itemDoubleClicked.connect(self._on_recent_double_clicked)
        self._populate_recent_items()
        right_box.addWidget(self.recent_list)

        # Keyboard cheat sheet footer
        shortcuts_box = QFrame()
        shortcuts_box.setStyleSheet("background-color: #16161e; border: 1px solid #292936; border-radius: 6px; padding: 10px;")
        sc_layout = QVBoxLayout(shortcuts_box)
        sc_layout.setContentsMargins(8, 8, 8, 8)
        sc_layout.setSpacing(4)
        sc_header = QLabel("⚡ Quick Canvas Keys")
        sc_header.setStyleSheet("color: #29b6f6; font-weight: bold; font-size: 11px;")
        sc_layout.addWidget(sc_header)
        sc_text = QLabel("• <b>Spacebar / Tab:</b> Quick-Add Transformer search\n• <b>Ctrl+B:</b> Insert Bookmark Container\n• <b>F5:</b> Run entire pipeline\n• <b>Ctrl+Z / Ctrl+Y:</b> Undo / Redo")
        sc_text.setStyleSheet("color: #9e9ea8; font-size: 11px; line-height: 1.4;")
        sc_layout.addWidget(sc_text)
        right_box.addWidget(shortcuts_box)

        grid.addLayout(right_box, 0, 1)
        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 5)

        main_layout.addLayout(grid)

    def _create_card_button(self, title_text: str, desc_text: str, accent_color: str) -> QPushButton:
        btn = QPushButton()
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e1e28;
                border: 1px solid #2f2f40;
                border-left: 5px solid {accent_color};
                border-radius: 6px;
                padding: 14px 16px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: #282836;
                border: 1px solid #3f3f56;
                border-left: 5px solid {accent_color};
            }}
            QPushButton:pressed {{
                background-color: #181822;
            }}
        """)
        card_layout = QVBoxLayout(btn)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(4)

        t_lbl = QLabel(title_text)
        t_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; background: transparent;")
        card_layout.addWidget(t_lbl)

        d_lbl = QLabel(desc_text)
        d_lbl.setFont(QFont("Segoe UI", 10))
        d_lbl.setStyleSheet("color: #a0a0b0; background: transparent;")
        d_lbl.setWordWrap(True)
        card_layout.addWidget(d_lbl)

        return btn

    def _populate_recent_items(self):
        from pyfme.engine.predefined_flows import get_predefined_flows, ensure_predefined_flow_files
        ensure_predefined_flow_files()
        flows = get_predefined_flows()
        for flow in flows:
            item = QListWidgetItem(f"{flow['icon']}  {flow['title']}\n    [{flow['category']}] {flow['description']}")
            item.setData(Qt.ItemDataRole.UserRole, flow["file_path"])
            item.setToolTip(f"{flow['title']} - {flow['category']}\n{flow['file_path']}")
            self.recent_list.addItem(item)

    def _on_recent_double_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            self.open_file_requested.emit(path)
