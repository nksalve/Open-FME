"""
open-FME Desktop Workbench Launcher.
Visual Spatial & Tabular ETL Pipeline Automation.
"""

import sys
import os

# Ensure current directory is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
import pyfme.engine.nodes  # Auto-register all readers, transformers, writers
from pyfme.ui.main_window import MainWindow
from pyfme.ui.error_handler import install_crash_protection


def main():
    # Install crash protection early so no error terminates open-FME
    crash_mgr = install_crash_protection()

    app = QApplication(sys.argv)
    app.setApplicationName("open-FME Workbench")
    app.setOrganizationName("open-FME")

    try:
        window = MainWindow()
        crash_mgr.set_main_window(window)
        window.show()
    except Exception as startup_err:
        crash_mgr.handle_exception(*sys.exc_info())

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

