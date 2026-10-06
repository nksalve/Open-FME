"""
Background execution thread for running workflows without blocking the PyQt UI.
"""

from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal
from pyfme.engine.graph import WorkflowGraph, Connection
from pyfme.engine.runner import WorkflowRunner


class WorkflowExecutionThread(QThread):
    """
    QThread worker executing the DAG pipeline in the background.
    """

    log_emitted = pyqtSignal(str, str)  # (message, level)
    node_started = pyqtSignal(str)  # (node_id)
    node_completed = pyqtSignal(str, bool, int, float, str)  # (node_id, success, feature_count, duration, error)
    connection_updated = pyqtSignal(str, str, str, str, int)  # (from_id, from_port, to_id, to_port, feature_count)
    workflow_finished = pyqtSignal(bool, float, str)  # (success, duration, summary)

    def __init__(self, graph: WorkflowGraph, target_node_id: Optional[str] = None, mode: str = "all", parent=None):
        super().__init__(parent)
        self.graph = graph
        self.target_node_id = target_node_id
        self.mode = mode
        self.runner: Optional[WorkflowRunner] = None

    def run(self):
        try:
            self.runner = WorkflowRunner(
                self.graph,
                log_callback=lambda msg, lvl: self.log_emitted.emit(msg, lvl)
            )

            self.runner.on_node_start = lambda node_id: self.node_started.emit(node_id)
            self.runner.on_node_complete = lambda nid, succ, cnt, dur, err: self.node_completed.emit(
                nid, succ, cnt, dur, err or ""
            )
            self.runner.on_connection_updated = lambda conn, cnt: self.connection_updated.emit(
                conn.from_node_id, conn.from_port, conn.to_node_id, conn.to_port, cnt
            )
            self.runner.on_workflow_complete = lambda succ, dur, summ: self.workflow_finished.emit(
                succ, dur, summ
            )

            self.runner.run(target_node_id=self.target_node_id, mode=self.mode)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.log_emitted.emit(f"Execution error encountered: {e}\n{tb}", "ERROR")
            self.workflow_finished.emit(False, 0.0, f"Workflow halted with error: {e}")

    def request_stop(self):
        try:
            if self.runner:
                self.runner.request_stop()
        except Exception:
            pass

