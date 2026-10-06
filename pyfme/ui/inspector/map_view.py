"""
Interactive 2D spatial vector map inspector.
Renders Shapely & GeoPandas geometries (Points, LineStrings, Polygons) with pan and zoom.
"""

from typing import Optional, Tuple
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QWheelEvent, QMouseEvent
)
from shapely.geometry import (
    Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon
)
from pyfme.engine.dataset import FeatureDataset


class MapCanvasWidget(QWidget):
    """
    Custom 2D vector canvas rendering GeoPandas geometries.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dataset: Optional[FeatureDataset] = None
        self.bounds: Optional[Tuple[float, float, float, float]] = None

        # Viewport transform
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.is_panning = False
        self.last_mouse_pos = QPointF(0, 0)
        self.hover_coord = QPointF(0, 0)

        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #121216;")

    def set_dataset(self, dataset: Optional[FeatureDataset]):
        self.dataset = dataset
        if dataset and dataset.has_geometry():
            self.bounds = dataset.get_bounds()
            self.zoom_to_extent()
        else:
            self.bounds = None
        self.update()

    def zoom_to_extent(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def world_to_screen(self, wx: float, wy: float) -> QPointF:
        if not self.bounds:
            return QPointF(0, 0)
        minx, miny, maxx, maxy = self.bounds
        dx = maxx - minx if (maxx - minx) > 1e-9 else 1.0
        dy = maxy - miny if (maxy - miny) > 1e-9 else 1.0

        w = self.width() - 40
        h = self.height() - 40

        # Uniform aspect ratio scaling
        scale = min(w / dx, h / dy) * self.zoom

        # Center in canvas
        cx = (self.width() / 2.0) + self.pan_x
        cy = (self.height() / 2.0) + self.pan_y

        mid_wx = (minx + maxx) / 2.0
        mid_wy = (miny + maxy) / 2.0

        sx = cx + (wx - mid_wx) * scale
        # Invert Y for screen coordinates
        sy = cy - (wy - mid_wy) * scale
        return QPointF(sx, sy)

    def screen_to_world(self, sx: float, sy: float) -> QPointF:
        if not self.bounds:
            return QPointF(0, 0)
        minx, miny, maxx, maxy = self.bounds
        dx = maxx - minx if (maxx - minx) > 1e-9 else 1.0
        dy = maxy - miny if (maxy - miny) > 1e-9 else 1.0

        w = self.width() - 40
        h = self.height() - 40
        scale = min(w / dx, h / dy) * self.zoom

        cx = (self.width() / 2.0) + self.pan_x
        cy = (self.height() / 2.0) + self.pan_y

        mid_wx = (minx + maxx) / 2.0
        mid_wy = (miny + maxy) / 2.0

        wx = mid_wx + (sx - cx) / scale
        wy = mid_wy - (sy - cy) / scale
        return QPointF(wx, wy)

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Background
            painter.fillRect(self.rect(), QColor("#121216"))

            if not self.dataset or not self.dataset.has_geometry():
                painter.setPen(QColor("#616170"))
                painter.drawText(
                    self.rect(),
                    Qt.AlignmentFlag.AlignCenter,
                    "No spatial geometries to display.\n(Connect a spatial reader or VertexCreator to inspect map view)",
                )
                return

            gdf = self.dataset.to_geopandas()
            if gdf.empty:
                painter.setPen(QColor("#616170"))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Dataset contains 0 features.")
                return

            # Render features with viewport bounding-box culling for ultra-smooth 60 FPS map panning
            poly_brush = QBrush(QColor(33, 150, 243, 60))
            poly_pen = QPen(QColor("#29b6f6"), 1.8)
            line_pen = QPen(QColor("#ffb300"), 2.2)
            point_brush = QBrush(QColor("#00e676"))
            point_pen = QPen(QColor("#1b5e20"), 1.2)

            # Viewport bounds in world coords
            tl = self.screen_to_world(-20, -20)
            br = self.screen_to_world(self.width() + 20, self.height() + 20)
            min_x, max_x = min(tl.x(), br.x()), max(tl.x(), br.x())
            min_y, max_y = min(tl.y(), br.y()), max(tl.y(), br.y())

            # Fast spatial slice or index
            try:
                if hasattr(gdf, "cx") and len(gdf) > 100:
                    visible_gdf = gdf.cx[min_x:max_x, min_y:max_y].head(5000)
                else:
                    visible_gdf = gdf.head(5000)
            except Exception:
                visible_gdf = gdf.head(5000)

            for geom in visible_gdf.geometry.dropna():
                try:
                    self._render_geometry(painter, geom, poly_brush, poly_pen, line_pen, point_brush, point_pen)
                except Exception:
                    pass
        except Exception:
            pass

    def _render_geometry(self, painter: QPainter, geom, poly_brush, poly_pen, line_pen, point_brush, point_pen):
        try:
            if geom is None or geom.is_empty:
                return

            if isinstance(geom, (Point, MultiPoint)):
                points = [geom] if isinstance(geom, Point) else geom.geoms
                painter.setBrush(point_brush)
                painter.setPen(point_pen)
                for pt in points:
                    sp = self.world_to_screen(pt.x, pt.y)
                    painter.drawEllipse(sp, 5.0, 5.0)

            elif isinstance(geom, (LineString, MultiLineString)):
                lines = [geom] if isinstance(geom, LineString) else geom.geoms
                painter.setPen(line_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for line in lines:
                    path = QPainterPath()
                    coords = list(line.coords)
                    if coords:
                        p0 = self.world_to_screen(coords[0][0], coords[0][1])
                        path.moveTo(p0)
                        for x, y in coords[1:]:
                            path.lineTo(self.world_to_screen(x, y))
                        painter.drawPath(path)

            elif isinstance(geom, (Polygon, MultiPolygon)):
                polys = [geom] if isinstance(geom, Polygon) else geom.geoms
                painter.setBrush(poly_brush)
                painter.setPen(poly_pen)
                for poly in polys:
                    path = QPainterPath()
                    coords = list(poly.exterior.coords)
                    if coords:
                        p0 = self.world_to_screen(coords[0][0], coords[0][1])
                        path.moveTo(p0)
                        for x, y in coords[1:]:
                            path.lineTo(self.world_to_screen(x, y))
                        path.closeSubpath()

                        # Holes (interiors)
                        for interior in poly.interiors:
                            in_coords = list(interior.coords)
                            if in_coords:
                                p0_in = self.world_to_screen(in_coords[0][0], in_coords[0][1])
                                path.moveTo(p0_in)
                                for x, y in in_coords[1:]:
                                    path.lineTo(self.world_to_screen(x, y))
                                path.closeSubpath()

                        painter.drawPath(path)

        except Exception:
            pass

    def wheelEvent(self, event: QWheelEvent):

        factor = 1.2 if event.angleDelta().y() > 0 else (1.0 / 1.2)
        self.zoom *= factor
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self.is_panning = True
            self.last_mouse_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_panning:
            delta = event.position() - self.last_mouse_pos
            self.last_mouse_pos = event.position()
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self.update()

        # Update world coordinates for status bar
        world_pt = self.screen_to_world(event.position().x(), event.position().y())
        if self.parent() and hasattr(self.parent(), "coord_label"):
            self.parent().coord_label.setText(f"Lon: {world_pt.x():.5f}, Lat: {world_pt.y():.5f} | Zoom: {self.zoom:.2f}x")

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.is_panning:
            self.is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)


class MapInspectorWidget(QWidget):
    """Container with toolbar and map canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(4)

        # Toolbar
        bar = QHBoxLayout()
        self.extent_btn = QPushButton("Reset View")
        self.extent_btn.clicked.connect(self._on_extent_clicked)
        bar.addWidget(self.extent_btn)

        self.crs_label = QLabel("CRS: None")
        self.crs_label.setStyleSheet("color: #8c8c9e;")
        bar.addWidget(self.crs_label)

        bar.addStretch()

        self.coord_label = QLabel("Cursor: -")
        self.coord_label.setStyleSheet("color: #00bcd4; font-family: monospace;")
        bar.addWidget(self.coord_label)

        self.layout.addLayout(bar)

        # Map canvas
        self.canvas = MapCanvasWidget(self)
        self.layout.addWidget(self.canvas)

    def set_dataset(self, dataset: FeatureDataset):
        self.canvas.set_dataset(dataset)
        if dataset and dataset.has_geometry():
            crs_name = str(dataset.crs) if dataset.crs else "Unknown"
            self.crs_label.setText(f"CRS: {crs_name}")
        else:
            self.crs_label.setText("CRS: None")

    def _on_extent_clicked(self):
        self.canvas.zoom_to_extent()
