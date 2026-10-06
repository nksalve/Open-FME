"""
open-FME Crash-Proof Exception & Error Recovery System.
Ensures the workbench never terminates unexpectedly on any runtime error,
unhandled exception, corrupted file, or node execution failure.
"""

from __future__ import annotations
import sys
import os
import time
import traceback
import html
import threading
from typing import Optional, Callable, Any
from functools import wraps

from PyQt6.QtWidgets import (
    QApplication, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QStyle
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QIcon


LOG_FILE_PATH = os.path.abspath("open_fme_error.log")


class ErrorRecoveryDialog(QDialog):
    """
    A modern, non-fatal error dialog that explains what happened,
    allows expanding full traceback details, provides a 1-click copy button,
    and assures the user that open-FME has safely recovered without crashing.
    """

    def __init__(self, exc_type, exc_value, exc_traceback, parent=None):
        super().__init__(parent)
        self.setWindowTitle("open-FME Error Recovery")
        self.resize(580, 420)
        self.setModal(True)

        self.exc_type = exc_type
        self.exc_value = exc_value
        self.formatted_tb = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header banner
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        icon_label.setPixmap(icon.pixmap(40, 40))
        header_layout.addWidget(icon_label)

        title_layout = QVBoxLayout()
        title = QLabel("open-FME Recovered Safely")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #ef5350;")
        subtitle = QLabel("An error occurred, but open-FME prevented the software from crashing.\nYour workspace, parameters, and open pipeline remain intact.")
        subtitle.setStyleSheet("color: #cfd8dc; font-size: 11px;")
        subtitle.setWordWrap(True)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header_layout.addLayout(title_layout, 1)

        layout.addLayout(header_layout)

        # Short error summary
        summary_box = QLabel(f"<b>{self.exc_type.__name__}:</b> {html.escape(str(self.exc_value))}")
        summary_box.setStyleSheet("""
            background-color: #212129;
            color: #ffb74d;
            border: 1px solid #3e3e50;
            border-radius: 4px;
            padding: 8px;
            font-size: 11px;
        """)
        summary_box.setWordWrap(True)
        layout.addWidget(summary_box)

        # Detailed traceback view
        details_label = QLabel("Diagnostic Traceback Details:")
        details_label.setStyleSheet("color: #9e9ea8; font-size: 11px;")
        layout.addWidget(details_label)

        self.tb_text = QTextEdit()
        self.tb_text.setReadOnly(True)
        self.tb_text.setPlainText(self.formatted_tb)
        self.tb_text.setStyleSheet("""
            QTextEdit {
                background-color: #121216;
                color: #cfd8dc;
                font-family: 'Consolas', monospace;
                font-size: 10px;
                border: 1px solid #282834;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        layout.addWidget(self.tb_text, 1)

        # Actions toolbar
        btn_layout = QHBoxLayout()
        self.copy_btn = QPushButton("📋 Copy Error Details")
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #282834;
                color: #e0e0e0;
                border: 1px solid #444455;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #38384a;
            }
        """)
        self.copy_btn.clicked.connect(self._copy_details)
        btn_layout.addWidget(self.copy_btn)

        btn_layout.addStretch()

        self.continue_btn = QPushButton("Continue Working")
        self.continue_btn.setDefault(True)
        self.continue_btn.setStyleSheet("""
            QPushButton {
                background-color: #1976d2;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 18px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2196f3;
            }
        """)
        self.continue_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.continue_btn)

        layout.addLayout(btn_layout)

    def _copy_details(self):
        cb = QApplication.clipboard()
        if cb:
            cb.setText(f"open-FME Error: {self.exc_type.__name__}: {self.exc_value}\n\n{self.formatted_tb}")
            self.copy_btn.setText("✓ Copied!")


class CrashProtectionManager:
    """
    Singleton manager that catches all unhandled exceptions from Python,
    PyQt event loops, and worker threads, logs them, alerts the UI, and
    keeps open-FME alive.
    """

    _instance: Optional[CrashProtectionManager] = None

    def __init__(self):
        self._main_window: Optional[Any] = None
        self._installed = False
        self._original_excepthook = sys.excepthook

    @classmethod
    def get_instance(cls) -> CrashProtectionManager:
        if cls._instance is None:
            cls._instance = CrashProtectionManager()
        return cls._instance

    def set_main_window(self, window: Any):
        self._main_window = window

    def log_to_file(self, message: str):
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception:
            pass

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        # Ignore KeyboardInterrupt or normal SystemExit
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            if self._original_excepthook:
                self._original_excepthook(exc_type, exc_value, exc_traceback)
            return

        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        # 1. Log to console safely
        sys.stderr.write(f"\n[open-FME Crash Guard Trapped Exception]: {exc_type.__name__}: {exc_value}\n{tb_str}\n")

        # 2. Log to disk file
        self.log_to_file(f"CRITICAL ERROR | {exc_type.__name__}: {exc_value}\n{tb_str}")

        # 3. Route to active Translation Log and Status Bar
        if self._main_window:
            try:
                if hasattr(self._main_window, "log_widget") and self._main_window.log_widget:
                    self._main_window.log_widget.append_log(
                        f"Crash Guard Trapped Error: {exc_type.__name__}: {exc_value}",
                        level="ERROR"
                    )
                if hasattr(self._main_window, "status_msg") and self._main_window.status_msg:
                    self._main_window.status_msg.setText(f"Recovered from error: {exc_value}")
            except Exception:
                pass

        # 4. Display non-fatal error recovery dialog if Qt application is active and not suppressed
        try:
            app = QApplication.instance()
            suppress = not getattr(self, "show_dialogs", True) or os.environ.get("OPENFME_TEST_MODE") == "1"
            if app and not suppress:
                dlg = ErrorRecoveryDialog(exc_type, exc_value, exc_traceback, parent=self._main_window)
                dlg.exec()
        except Exception as dialog_err:
            sys.stderr.write(f"[open-FME Error Dialog Warning]: {dialog_err}\n")

    def handle_thread_exception(self, args):
        self.handle_exception(args.exc_type, args.exc_value, args.exc_traceback)

    def install(self):
        if self._installed:
            return
        self._installed = True

        # Override global exception hook
        sys.excepthook = self.handle_exception

        # Python 3.8+ threading exception hook
        if hasattr(threading, "excepthook"):
            threading.excepthook = self.handle_thread_exception


def install_crash_protection(main_window=None) -> CrashProtectionManager:
    """Installs the crash-proof exception system for open-FME."""
    manager = CrashProtectionManager.get_instance()
    manager.install()
    if main_window:
        manager.set_main_window(main_window)
    return manager


def safe_slot(error_msg: str = "Operation failed", show_dialog: bool = True):
    """
    Decorator for PyQt slots to guarantee that any exception inside the slot
    is caught, logged in the Translation Log, and never crashes the application.
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                tb = traceback.format_exc()
                sys.stderr.write(f"[open-FME Safe Slot Guard in {func.__name__}]: {e}\n{tb}\n")

                # Try to find window instance
                win = None
                if args and hasattr(args[0], "log_widget"):
                    win = args[0]
                elif CrashProtectionManager.get_instance()._main_window:
                    win = CrashProtectionManager.get_instance()._main_window

                if win and hasattr(win, "log_widget") and win.log_widget:
                    win.log_widget.append_log(f"{error_msg}: {str(e)}", "ERROR")
                    if hasattr(win, "status_msg") and win.status_msg:
                        win.status_msg.setText(f"Error in {func.__name__}: {e}")

                CrashProtectionManager.get_instance().log_to_file(f"SafeSlot [{func.__name__}] {error_msg}: {e}\n{tb}")

                if show_dialog:
                    app = QApplication.instance()
                    if app:
                        dlg = ErrorRecoveryDialog(type(e), e, sys.exc_info()[2], parent=win)
                        dlg.exec()
                return None
        return wrapper
    return decorator
