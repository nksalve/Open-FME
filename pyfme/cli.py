"""
Headless CLI Runner for open-FME.
Enables running workflows in headless automation, CI/CD, cron jobs, and scripts.
"""

import sys
import argparse
import time
from pyfme.engine.graph import WorkflowGraph
from pyfme.engine.runner import WorkflowRunner
import pyfme.engine.nodes  # Ensure all nodes register


def main():
    parser = argparse.ArgumentParser(description="open-FME Headless Automation Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Run command
    run_parser = subparsers.add_parser("run", help="Execute an open-FME workflow file")
    run_parser.add_argument("workflow_file", help="Path to .fpy or .json workflow file")
    run_parser.add_argument(
        "--param",
        action="append",
        help="Override node parameter: node_name.param_name=value",
    )

    args = parser.parse_args()

    if args.command == "run":
        print(f"Loading workspace: {args.workflow_file}")
        try:
            graph = WorkflowGraph.load_from_file(args.workflow_file)
        except Exception as e:
            print(f"[ERROR] Failed to load workflow file: {e}")
            sys.exit(1)

        # Apply parameter overrides if specified
        if args.param:
            for p in args.param:
                if "=" in p and "." in p:
                    target, val = p.split("=", 1)
                    node_name, param_name = target.split(".", 1)
                    # Find node by name
                    for n in graph.nodes.values():
                        if n.name == node_name or n.node_type == node_name:
                            n.set_param(param_name, val)
                            print(f"[OVERRIDE] {n.name}.{param_name} = {val}")

        def log_cb(msg, lvl):
            print(msg)

        try:
            runner = WorkflowRunner(graph, log_callback=log_cb)
            success = runner.run()
        except Exception as e:
            print(f"[ERROR] Workflow execution failed: {e}")
            sys.exit(1)

        if not success:
            sys.exit(1)
        print("Workflow completed successfully.")



if __name__ == "__main__":
    main()
