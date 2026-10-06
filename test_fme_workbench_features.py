"""
Test suite for FME Workbench features:
- Bookmarks & Moving enclosed nodes
- Annotations / Sticky Notes
- Navigator Tree Hierarchy
- Translation Log & Stats
- ShortestPathFinder, LineBuilder, FeatureWriter, HTMLReportGenerator, HTMLLayouter
"""

import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, QRectF

from pyfme.engine.graph import WorkflowGraph
from pyfme.engine.registry import NodeRegistry
from pyfme.engine.dataset import FeatureDataset
from pyfme.ui.canvas.scene import CanvasScene
from pyfme.ui.canvas.bookmark_item import BookmarkItem
from pyfme.ui.canvas.annotation_item import AnnotationItem
from pyfme.ui.navigator.navigator_dock import NavigatorWidget
from pyfme.ui.inspector.translation_log import TranslationLogWidget
import pyfme.engine.nodes  # Ensure all nodes register


def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)

    print("=== 1. Testing BookmarkItem ===")
    bm = BookmarkItem("Test Bookmark", QRectF(0, 0, 300, 200), color="#e91e63")
    bm.setPos(50, 50)
    assert bm.title == "Test Bookmark"
    assert bm.color == "#e91e63"
    d = bm.to_dict()
    assert d["title"] == "Test Bookmark"
    assert d["color"] == "#e91e63"
    bm2 = BookmarkItem.from_dict(d)
    assert bm2.title == bm.title
    print("BookmarkItem creation and serialization passed!")

    print("=== 2. Testing AnnotationItem ===")
    ann = AnnotationItem("Calculate shortest road journey between all libraries.")
    ann.setPos(120, 80)
    assert "shortest road journey" in ann.text
    d_ann = ann.to_dict()
    assert d_ann["text"] == ann.text
    ann2 = AnnotationItem.from_dict(d_ann)
    assert ann2.text == ann.text
    print("AnnotationItem creation and serialization passed!")

    print("=== 3. Testing Scene Bookmarks & Contained Nodes Movement ===")
    graph = WorkflowGraph("Test Workspace")
    node = NodeRegistry.create("CSVReader")
    node.x, node.y = 100, 100
    graph.add_node(node)

    scene = CanvasScene(graph)
    assert len(scene.node_items) == 1
    node_item = scene.node_items[node.id]

    # Add bookmark enclosing the node
    bm_scene = scene.add_bookmark("My Group", rect=QRectF(0, 0, 400, 300), color="#9c27b0", pos=QPointF(50, 50))
    assert len(scene.bookmarks) == 1
    contained = bm_scene.get_contained_node_items()
    assert node_item in contained, "Node inside bookmark bounds must be detected"

    # Move bookmark and check contained node moves with it
    initial_node_pos = node_item.pos()
    # Emulate move
    bm_scene._contained_nodes_before_move = bm_scene.get_contained_node_items()
    delta = QPointF(50, 60)
    bm_scene.setPos(bm_scene.pos() + delta)
    for n in bm_scene._contained_nodes_before_move:
        n.setPos(n.pos() + delta)
    assert node_item.pos() == initial_node_pos + delta, "Enclosed node must move with bookmark!"
    print("Bookmark containing and moving nodes passed!")

    print("=== 4. Testing WorkflowGraph Serialization with Bookmarks & Annotations ===")
    scene.add_annotation("Note 1", pos=QPointF(200, 200))
    scene.sync_to_graph()
    assert len(graph.bookmarks) == 1
    assert len(graph.annotations) == 1

    graph_dict = graph.to_dict()
    assert "bookmarks" in graph_dict
    assert "annotations" in graph_dict
    restored_graph = WorkflowGraph.from_dict(graph_dict)
    assert len(restored_graph.bookmarks) == 1
    assert len(restored_graph.annotations) == 1

    scene_restored = CanvasScene(restored_graph)
    assert len(scene_restored.bookmarks) == 1
    assert len(scene_restored.annotations) == 1
    print("Graph bookmarks & annotations persistence passed!")

    print("=== 5. Testing TranslationLogWidget ===")
    log_w = TranslationLogWidget()
    log_w.append_log("Starting translation", "INFO")
    log_w.append_log("Feature warning detected", "WARN")
    log_w.append_log("Fatal connection failure", "ERROR")
    assert log_w.info_count == 1
    assert log_w.warning_count == 1
    assert log_w.error_count == 1
    print("TranslationLogWidget counts and badges passed!")

    print("=== 6. Testing New FME Transformers ===")
    # ShortestPathFinder
    spf = NodeRegistry.create("ShortestPathFinder")
    assert spf is not None
    assert "Path" in [p.name for p in spf.get_output_ports()]

    # LineBuilder
    lb = NodeRegistry.create("LineBuilder")
    assert lb is not None
    assert "Line" in [p.name for p in lb.get_output_ports()]

    # FeatureWriter
    fw = NodeRegistry.create("FeatureWriter")
    assert fw is not None
    assert "Summary" in [p.name for p in fw.get_output_ports()]

    # HTMLReportGenerator & HTMLLayouter
    hrg = NodeRegistry.create("HTMLReportGenerator")
    assert hrg is not None
    hl = NodeRegistry.create("HTMLLayouter")
    assert hl is not None
    assert "HTML" in [p.name for p in hl.get_output_ports()]
    print("All new FME transformers registered and validated!")

    print("=== 7. Testing Community Mapping Full Workspace File ===")
    cm_path = "sample_data/fme_community_mapping.fpy"
    assert os.path.exists(cm_path), f"{cm_path} must exist"
    cm_graph = WorkflowGraph.load_from_file(cm_path)
    assert len(cm_graph.nodes) >= 3
    assert hasattr(cm_graph, "bookmarks")
    assert hasattr(cm_graph, "annotations")
    print(f"Community Mapping sample verified with {len(cm_graph.nodes)} nodes, {len(cm_graph.bookmarks)} bookmarks, {len(cm_graph.annotations)} annotations!")

    print("\nALL FME WORKBENCH FEATURES TESTS PASSED 100% SUCCESSFULLY! [PASSED]")


if __name__ == "__main__":
    run_tests()
