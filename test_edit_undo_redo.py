import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QKeySequence

# Ensure pyfme is in python path
sys.path.insert(0, os.path.abspath("."))

def test_edit_and_undo_redo():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    from pyfme.ui.main_window import MainWindow
    from pyfme.engine.registry import NodeRegistry

    win = MainWindow()
    win.new_workspace()
    scene = win.scene
    undo_stack = scene.undo_stack

    print(f"Initial undo stack clean: canUndo={undo_stack.canUndo()}, canRedo={undo_stack.canRedo()}")
    assert not undo_stack.canUndo()
    assert not undo_stack.canRedo()

    # 1. Test Add Node via scene
    node1 = NodeRegistry.create("CSVReader")
    scene.add_node_at_position(node1, QPointF(100, 100))
    print(f"Added CSVReader: count={len(scene.graph.nodes)}, canUndo={undo_stack.canUndo()}")
    assert len(scene.graph.nodes) == 1
    assert undo_stack.canUndo()

    # Undo Add
    undo_stack.undo()
    print(f"After Undo: count={len(scene.graph.nodes)}, canRedo={undo_stack.canRedo()}")
    assert len(scene.graph.nodes) == 0
    assert undo_stack.canRedo()

    # Redo Add
    undo_stack.redo()
    print(f"After Redo: count={len(scene.graph.nodes)}")
    assert len(scene.graph.nodes) == 1

    # 2. Add second node and wire them
    node2 = NodeRegistry.create("Tester")
    scene.add_node_at_position(node2, QPointF(350, 100))
    assert len(scene.graph.nodes) == 2

    conn = scene.graph.connect(node1.id, "Output", node2.id, "Input")
    from pyfme.ui.canvas.undo_commands import ConnectWireCommand
    # Test ConnectWireCommand
    w_cmd = ConnectWireCommand(scene, node1.id, "Output", node2.id, "Input")
    undo_stack.push(w_cmd)
    print(f"Connections count: {len(scene.graph.connections)}")
    assert len(scene.graph.connections) == 1

    # 3. Test Select All
    win.act_select_all.trigger()
    selected = [i for i in scene.selectedItems() if hasattr(i, 'node')]
    print(f"Selected nodes count after Select All: {len(selected)}")
    assert len(selected) == 2

    # 4. Test Copy & Paste
    win.act_copy.trigger()
    print("Copied selected nodes.")
    win.act_paste.trigger()
    print(f"Nodes after Paste: {len(scene.graph.nodes)}")
    assert len(scene.graph.nodes) == 4
    # The connections between the two copied nodes should also have been replicated
    print(f"Connections after Paste: {len(scene.graph.connections)}")
    assert len(scene.graph.connections) == 2

    # Undo Paste
    undo_stack.undo()
    print(f"Nodes after Undo Paste: {len(scene.graph.nodes)}")
    assert len(scene.graph.nodes) == 2

    # Redo Paste
    undo_stack.redo()
    print(f"Nodes after Redo Paste: {len(scene.graph.nodes)}")
    assert len(scene.graph.nodes) == 4

    # 5. Test Duplicate
    win.act_select_all.trigger()
    win.act_duplicate.trigger()
    print(f"Nodes after Duplicate: {len(scene.graph.nodes)}")
    assert len(scene.graph.nodes) == 8

    # Undo Duplicate
    undo_stack.undo()
    print(f"Nodes after Undo Duplicate: {len(scene.graph.nodes)}")
    assert len(scene.graph.nodes) == 4

    # 6. Test Delete Selected
    win.act_select_all.trigger()
    win.act_delete.trigger()
    print(f"Nodes after Delete All: {len(scene.graph.nodes)}")
    assert len(scene.graph.nodes) == 0

    # Undo Delete All
    undo_stack.undo()
    print(f"Nodes after Undo Delete: {len(scene.graph.nodes)}")
    assert len(scene.graph.nodes) == 4

    # 7. Test Deselect All
    win.act_deselect_all.trigger()
    selected_after = scene.selectedItems()
    print(f"Selected items after Deselect All: {len(selected_after)}")
    assert len(selected_after) == 0

    # 8. Test Node Movement Undo/Redo
    node_item = list(scene.node_items.values())[0]
    orig_pos = QPointF(node_item.pos())
    new_pos = QPointF(orig_pos.x() + 150, orig_pos.y() + 80)
    from pyfme.ui.canvas.undo_commands import MoveNodesCommand
    mv_cmd = MoveNodesCommand(scene, [(node_item.node.id, orig_pos, new_pos)])
    undo_stack.push(mv_cmd)
    print(f"Node pos after move: {node_item.pos()}")
    assert node_item.pos() == new_pos
    undo_stack.undo()
    print(f"Node pos after undo move: {node_item.pos()}")
    assert node_item.pos() == orig_pos
    undo_stack.redo()
    assert node_item.pos() == new_pos
    print("Node move undo/redo passed!")

    print("ALL EDIT AND UNDO/REDO TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_edit_and_undo_redo()
