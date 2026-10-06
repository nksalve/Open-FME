# Contributing to open-FME

Thank you for your interest in contributing to **open-FME**! 🎉
open-FME is an open-source visual Spatial & Tabular ETL automation platform built to make data integration free, accessible, and fast for GIS professionals, data scientists, and developers worldwide.

---

## 🧭 Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free environment for everyone. Please treat all contributors and users with respect and kindness.

---

## 🛠️ Development Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/your-username/open-fme.git
   cd open-fme
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies in editable mode:**
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

4. **Launch the desktop application:**
   ```bash
   python main.py
   # Or on Windows:
   run_open_fme.bat
   ```

5. **Run the automated test suite:**
   ```bash
   python test_edit_undo_redo.py
   ```

---

## 🧩 Adding a New Transformer

Creating a new transformer in open-FME is designed to be straightforward and modular.

1. **Choose the appropriate category file** under `pyfme/engine/nodes/transformers/`:
   - `attributes.py` or `fme_attribute_tools.py` — attribute management, strings, math, dates
   - `spatial.py` or `spatial_geoprocessing.py` — buffering, reprojection, bounding boxes
   - `spatial_geometry.py` or `fme_geometry_tools.py` — vertex creation, simplification, convex hull
   - `fme_overlay.py` — clipping, intersection, union, point-in-polygon
   - `fme_spatial_relations.py` — spatial predicates, neighbor finders, point counts
   - `fme_raster.py` — raster tools, extent coercers, statistics
   - `fme_automation.py` — triggers, terminators, HTTP calls, logging

2. **Define your node class** using the `@NodeRegistry.register` decorator:

```python
from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry
import polars as pl

@NodeRegistry.register
class MyNewTransformer(BaseNode):
    node_type = "MyNewTransformer"
    category = NodeCategory.ATTRIBUTE  # Or SPATIAL, GEOPROCESSING, etc.
    description = "Briefly describe what your transformer accomplishes."

    @classmethod
    def get_input_ports(cls):
        return [Port("Input", PortType.INPUT)]

    @classmethod
    def get_output_ports(cls):
        return [
            Port("Output", PortType.OUTPUT),
            # Optional additional routing ports, e.g. Port("Rejected", PortType.OUTPUT)
        ]

    @classmethod
    def get_parameter_defs(cls):
        return [
            ParameterDef("threshold", ParameterType.FLOAT, default=10.0, description="Threshold limit"),
        ]

    def execute(self, inputs, params, context=None):
        in_ds = inputs.get("Input")
        if in_ds is None or in_ds.is_empty():
            return {"Output": FeatureDataset()}

        threshold = float(params.get("threshold", 10.0))
        df = in_ds.to_polars()
        
        # Perform your transformation logic here
        result_df = df.filter(pl.col("score") >= threshold)
        
        return {"Output": FeatureDataset.from_polars(result_df)}
```

3. **Verify registration:**
   Your new transformer will be automatically discovered by:
   - The Desktop UI Transformer Gallery dock
   - The Quick-Add search dialog (`Spacebar` / `Tab`)
   - The Headless CLI engine (`python -m openfme.cli run ...`)

---

## 🧪 Testing

Always write or update tests when adding new features or fixing bugs:
- Add unit tests for engine transformations.
- Run `python test_edit_undo_redo.py` to ensure UI undo/redo and canvas stability are preserved.

---

## 🚀 Submitting Pull Requests

1. Create a descriptive feature branch:
   ```bash
   git checkout -b feature/buffer-distance-attribute
   ```
2. Commit your changes with clear commit messages:
   ```bash
   git commit -m "feat(transformers): add attribute-driven buffer distance to Bufferer"
   ```
3. Push to your branch and open a Pull Request on GitHub.
4. Describe your changes clearly in the PR description, including before/after behavior or screenshots if modifying the UI.
