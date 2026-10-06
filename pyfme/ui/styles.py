"""
Modern dark styling and design tokens for open-FME.
Inspired by FME Workbench / modern spatial IDE interfaces.
"""

DARK_THEME_QSS = """
QMainWindow, QWidget {
    background-color: #1a1a20;
    color: #e0e0e0;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
    font-size: 12px;
}

/* Toolbars */
QToolBar {
    background-color: #24242c;
    border-bottom: 1px solid #32323e;
    spacing: 6px;
    padding: 4px 8px;
}

QToolButton {
    background-color: #2e2e38;
    color: #ffffff;
    border: 1px solid #3c3c4a;
    border-radius: 4px;
    padding: 5px 12px;
    font-weight: 500;
}

QToolButton:hover {
    background-color: #3b3b48;
    border-color: #55556a;
}

QToolButton:pressed {
    background-color: #1e1e26;
}

QToolButton#runBtn {
    background-color: #2e7d32;
    border-color: #388e3c;
    color: #ffffff;
    font-weight: bold;
    padding: 6px 16px;
}

QToolButton#runBtn:hover {
    background-color: #388e3c;
    border-color: #4caf50;
}

QToolButton#stopBtn {
    background-color: #c62828;
    border-color: #d32f2f;
    color: #ffffff;
    font-weight: bold;
}

QToolButton#stopBtn:hover {
    background-color: #d32f2f;
}

/* Dock Widgets */
QDockWidget {
    titlebar-close-icon: url(close.png);
    titlebar-normal-icon: url(undock.png);
    font-weight: 600;
    color: #b0b0cc;
}

QDockWidget::title {
    background: #24242c;
    border-bottom: 1px solid #32323e;
    padding: 6px 10px;
    text-align: left;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #32323e;
    background-color: #1e1e24;
}

QTabBar::tab {
    background: #24242c;
    color: #9e9ea8;
    padding: 7px 16px;
    border: 1px solid #32323e;
    border-bottom: none;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background: #1e1e24;
    color: #ffffff;
    border-top: 2px solid #2196f3;
}

QTabBar::tab:hover:!selected {
    background: #2e2e38;
}

/* Tables */
QTableView {
    background-color: #18181e;
    alternate-background-color: #202028;
    color: #e4e4ee;
    gridline-color: #2a2a36;
    border: 1px solid #32323e;
    selection-background-color: #1976d2;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #24242c;
    color: #c0c0d0;
    padding: 5px;
    border: 1px solid #32323e;
    font-weight: 600;
}

/* Trees and Lists */
QTreeWidget, QListWidget {
    background-color: #1e1e24;
    border: 1px solid #32323e;
    color: #dcdce6;
}

QTreeWidget::item:hover, QListWidget::item:hover {
    background-color: #2c2c38;
}

QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #1976d2;
    color: #ffffff;
}

/* Inputs & Form Controls */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #24242c;
    border: 1px solid #3a3a48;
    border-radius: 4px;
    padding: 5px 8px;
    color: #ffffff;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #2196f3;
    background-color: #282834;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #1e1e24;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #3b3b4a;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #55556a;
}

QScrollBar:horizontal {
    border: none;
    background: #1e1e24;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #3b3b4a;
    min-width: 20px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: #55556a;
}

/* Status Bar */
QStatusBar {
    background-color: #18181e;
    color: #8c8c9e;
    border-top: 1px solid #2c2c38;
}

/* Menu Bar */
QMenuBar {
    background-color: #202028;
    color: #e0e0e0;
    border-bottom: 1px solid #2e2e3a;
}

QMenuBar::item:selected {
    background-color: #2e2e3c;
}

QMenu {
    background-color: #24242e;
    border: 1px solid #3a3a48;
    color: #ffffff;
    padding: 4px;
}

QMenu::item:selected {
    background-color: #1976d2;
    border-radius: 3px;
}
"""

# Color schemes for visual node cards
CATEGORY_COLORS = {
    "Readers (Inputs)": {
        "header": "#2e7d32",
        "header_text": "#ffffff",
        "bg": "#1c2e20",
        "border": "#388e3c",
    },
    "Attribute Transformers": {
        "header": "#0d47a1",
        "header_text": "#ffffff",
        "bg": "#172338",
        "border": "#1976d2",
    },
    "Spatial Transformers": {
        "header": "#4a148c",
        "header_text": "#ffffff",
        "bg": "#261738",
        "border": "#7b1fa2",
    },
    "Scripting & Automation": {
        "header": "#e65100",
        "header_text": "#ffffff",
        "bg": "#382216",
        "border": "#f57c00",
    },
    "Writers (Outputs)": {
        "header": "#880e4f",
        "header_text": "#ffffff",
        "bg": "#351724",
        "border": "#c2185b",
    },
}
