"""
Interactive 2D spatial vector map inspector with OpenStreetMap (OSM) and ArcGIS basemaps.
Supports high-resolution vector rendering, multi-source slippy tile basemaps,
async tile streaming, disk/memory caching, smooth pan/zoom, and Leaflet web map export.
"""

from __future__ import annotations

import os
import sys
import math
import tempfile
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QSlider, QCheckBox, QToolTip
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QObject, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QWheelEvent,
    QMouseEvent, QPixmap, QImage, QCursor, QFont
)
from shapely.geometry import (
    Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon
)
import geopandas as gpd

from pyfme.engine.dataset import FeatureDataset


# Earth constants for EPSG:3857 (Spherical Mercator)
MERCATOR_R = 20037508.342789244
MERCATOR_W = 2.0 * MERCATOR_R

BASEMAP_CONFIGS: Dict[str, Dict[str, Any]] = {
    "osm": {
        "name": "OpenStreetMap",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "max_zoom": 19,
        "attribution": "© OpenStreetMap contributors",
        "user_agent": "PyFME-Data-Inspector/1.0",
    },
    "arcgis_imagery": {
        "name": "ArcGIS World Imagery",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "max_zoom": 19,
        "attribution": "Source: Esri, Maxar, Earthstar Geographics",
        "user_agent": "PyFME-Data-Inspector/1.0",
    },
    "arcgis_streets": {
        "name": "ArcGIS World Streets",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        "max_zoom": 19,
        "attribution": "Source: Esri, HERE, Garmin, USGS",
        "user_agent": "PyFME-Data-Inspector/1.0",
    },
    "arcgis_topo": {
        "name": "ArcGIS Topographic",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        "max_zoom": 19,
        "attribution": "Source: Esri, USGS, NOAA",
        "user_agent": "PyFME-Data-Inspector/1.0",
    },
    "arcgis_dark": {
        "name": "ArcGIS Dark Canvas",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        "max_zoom": 16,
        "attribution": "Source: Esri, HERE, Garmin",
        "user_agent": "PyFME-Data-Inspector/1.0",
    },
    "arcgis_light": {
        "name": "ArcGIS Light Canvas",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        "max_zoom": 16,
        "attribution": "Source: Esri, HERE, Garmin",
        "user_agent": "PyFME-Data-Inspector/1.0",
    },
    "arcgis_natgeo": {
        "name": "ArcGIS NatGeo World",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/NatGeo_World_Map/MapServer/tile/{z}/{y}/{x}",
        "max_zoom": 16,
        "attribution": "Source: National Geographic, Esri",
        "user_agent": "PyFME-Data-Inspector/1.0",
    },
    "arcgis_ocean": {
        "name": "ArcGIS Oceans",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}",
        "max_zoom": 16,
        "attribution": "Source: GEBCO, NOAA, Esri",
        "user_agent": "PyFME-Data-Inspector/1.0",
    },
    "none": {
        "name": "None (Dark Canvas)",
        "url": None,
        "max_zoom": 20,
        "attribution": "",
        "user_agent": "",
    },
}


class TileSignalEmitter(QObject):
    """Thread-safe signal dispatcher for asynchronous tile downloads."""
    tile_loaded = pyqtSignal(str, int, int, int, bytes)


class BasemapTileManager:
    """
    High-performance multi-threaded tile fetcher and multi-tier caching system
    (Memory LRU + Persistent Local Disk Cache).
    """

    def __init__(self, max_memory_tiles: int = 800):
        self.signal_emitter = TileSignalEmitter()
        self.max_memory_tiles = max_memory_tiles
        self.memory_cache: OrderedDict[Tuple[str, int, int, int], QPixmap] = OrderedDict()
        self.pending_requests: set[Tuple[str, int, int, int]] = set()
        self.failed_requests: set[Tuple[str, int, int, int]] = set()

        # Disk cache location
        self.disk_cache_dir = os.path.join(tempfile.gettempdir(), "pyfme_tile_cache")
        try:
            os.makedirs(self.disk_cache_dir, exist_ok=True)
        except Exception:
            pass

        self.executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="TileFetcher")
        self.signal_emitter.tile_loaded.connect(self._on_tile_bytes_received)

    def _get_disk_path(self, provider: str, z: int, x: int, y: int) -> str:
        return os.path.join(self.disk_cache_dir, provider, str(z), str(x), f"{y}.png")

    def _on_tile_bytes_received(self, provider: str, z: int, x: int, y: int, data: bytes):
        key = (provider, z, x, y)
        self.pending_requests.discard(key)
        pix = QPixmap()
        if pix.loadFromData(data):
            self.memory_cache[key] = pix
            if len(self.memory_cache) > self.max_memory_tiles:
                self.memory_cache.popitem(last=False)

    def get_tile(self, provider: str, z: int, x: int, y: int) -> Optional[QPixmap]:
        """
        Returns cached QPixmap immediately if available.
        Otherwise loads synchronously from disk or triggers background download.
        """
        if provider == "none" or provider not in BASEMAP_CONFIGS:
            return None

        key = (provider, z, x, y)

        # 1. Memory Cache
        if key in self.memory_cache:
            self.memory_cache.move_to_end(key)
            return self.memory_cache[key]

        # 2. Disk Cache
        disk_file = self._get_disk_path(provider, z, x, y)
        if os.path.isfile(disk_file):
            try:
                pix = QPixmap(disk_file)
                if not pix.isNull():
                    self.memory_cache[key] = pix
                    if len(self.memory_cache) > self.max_memory_tiles:
                        self.memory_cache.popitem(last=False)
                    return pix
            except Exception:
                pass

        # 3. Asynchronous Network Fetch
        if key not in self.pending_requests and key not in self.failed_requests:
            self.pending_requests.add(key)
            self.executor.submit(self._fetch_tile_worker, provider, z, x, y)

        return None

    def get_tile_fallback(self, provider: str, z: int, x: int, y: int) -> Optional[Tuple[QPixmap, QRectF]]:
        """
        If current tile is loading, look up parent tiles (z-1 or z-2) to display
        smooth intermediate previews without blank squares.
        """
        if z <= 0:
            return None

        # Check z-1
        pz = z - 1
        px = x // 2
        py = y // 2
        parent_pix = self.get_tile(provider, pz, px, py)
        if parent_pix:
            quad_x = (x % 2) * 128
            quad_y = (y % 2) * 128
            return parent_pix, QRectF(quad_x, quad_y, 128, 128)

        # Check z-2
        if z >= 2:
            ppz = z - 2
            ppx = x // 4
            ppy = y // 4
            gparent_pix = self.get_tile(provider, ppz, ppx, ppy)
            if gparent_pix:
                quad_x = (x % 4) * 64
                quad_y = (y % 4) * 64
                return gparent_pix, QRectF(quad_x, quad_y, 64, 64)

        return None

    def _fetch_tile_worker(self, provider: str, z: int, x: int, y: int):
        cfg = BASEMAP_CONFIGS.get(provider)
        if not cfg or not cfg.get("url"):
            self.failed_requests.add((provider, z, x, y))
            return

        url_template = cfg["url"]
        url = url_template.format(z=z, x=x, y=y)
        user_agent = cfg.get("user_agent", "PyFME-Data-Inspector/1.0")

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "image/webp,image/png,image/*,*/*;q=0.8",
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = resp.read()
                if len(data) > 0:
                    # Save to disk cache
                    disk_file = self._get_disk_path(provider, z, x, y)
                    try:
                        os.makedirs(os.path.dirname(disk_file), exist_ok=True)
                        tmp_file = disk_file + ".tmp"
                        with open(tmp_file, "wb") as f:
                            f.write(data)
                        if os.path.exists(disk_file):
                            os.remove(disk_file)
                        os.rename(tmp_file, disk_file)
                    except Exception:
                        pass

                    # Signal main thread
                    self.signal_emitter.tile_loaded.emit(provider, z, x, y, data)
                else:
                    self.failed_requests.add((provider, z, x, y))
        except Exception:
            self.failed_requests.add((provider, z, x, y))


# Global tile manager instance shared across views
_GLOBAL_TILE_MANAGER: Optional[BasemapTileManager] = None


def get_tile_manager() -> BasemapTileManager:
    global _GLOBAL_TILE_MANAGER
    if _GLOBAL_TILE_MANAGER is not None:
        try:
            _ = _GLOBAL_TILE_MANAGER.signal_emitter.objectName()
        except (RuntimeError, Exception):
            _GLOBAL_TILE_MANAGER = None

    if _GLOBAL_TILE_MANAGER is None:
        _GLOBAL_TILE_MANAGER = BasemapTileManager()
    return _GLOBAL_TILE_MANAGER



class MapCanvasWidget(QWidget):
    """
    Interactive 2D spatial vector & raster map canvas.
    Renders GeoPandas/Shapely vector geometries on top of OpenStreetMap (OSM)
    or ArcGIS basemap tile services with pan, zoom, and culling.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dataset: Optional[FeatureDataset] = None
        self._display_gdf: Optional[gpd.GeoDataFrame] = None
        self.is_geographic: bool = True
        self.bounds: Optional[Tuple[float, float, float, float]] = None

        # Basemap settings
        self.tile_manager = get_tile_manager()
        self.tile_manager.signal_emitter.tile_loaded.connect(self._on_tile_loaded)
        self.basemap_provider: str = "osm"
        self.basemap_opacity: float = 1.0
        self.show_vectors: bool = True

        # Viewport transform
        self.zoom: float = 1.0
        self.pan_x: float = 0.0
        self.pan_y: float = 0.0
        self.is_panning: bool = False
        self.last_mouse_pos: QPointF = QPointF(0, 0)
        self.hover_coord: QPointF = QPointF(0, 0)

        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #121216;")

        # Default world view if no dataset is loaded
        self.set_default_world_bounds()

    def set_default_world_bounds(self):
        """Initializes canvas with full world bounds in Web Mercator meters."""
        self.bounds = (-MERCATOR_R, -MERCATOR_R, MERCATOR_R, MERCATOR_R)
        self.is_geographic = True
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

    def _on_tile_loaded(self, provider: str, z: int, x: int, y: int, data: bytes):
        if provider == self.basemap_provider:
            self.update()

    def set_dataset(self, dataset: Optional[FeatureDataset]):
        """Sets dataset and calculates projected Web Mercator geometries."""
        self.dataset = dataset
        self._display_gdf = None

        if dataset and dataset.has_geometry():
            try:
                gdf = dataset.to_geopandas()
                if not gdf.empty:
                    # Check and reproject to EPSG:3857 for seamless basemap alignment
                    b = gdf.total_bounds
                    if gdf.crs is not None:
                        try:
                            self._display_gdf = gdf.to_crs(epsg=3857)
                            self.is_geographic = True
                        except Exception:
                            self._display_gdf = gdf
                            self.is_geographic = False
                    elif len(b) == 4 and -180.05 <= b[0] and b[2] <= 180.05 and -90.05 <= b[1] and b[3] <= 90.05:
                        # Auto-detect WGS84 lon/lat
                        try:
                            self._display_gdf = gdf.set_crs(epsg=4326, allow_override=True).to_crs(epsg=3857)
                            self.is_geographic = True
                        except Exception:
                            self._display_gdf = gdf
                            self.is_geographic = False
                    else:
                        self._display_gdf = gdf
                        self.is_geographic = False

                    if self._display_gdf is not None and not self._display_gdf.empty:
                        pb = self._display_gdf.total_bounds
                        self.bounds = (float(pb[0]), float(pb[1]), float(pb[2]), float(pb[3]))
                        self.zoom_to_extent()
                        self.update()
                        return
            except Exception:
                pass

        # Fallback if no valid geometry
        self.set_default_world_bounds()
        self.update()

    def set_basemap(self, provider_key: str):
        """Changes active basemap layer."""
        if provider_key in BASEMAP_CONFIGS:
            self.basemap_provider = provider_key
            self.update()

    def set_basemap_opacity(self, opacity: float):
        """Sets basemap layer opacity (0.0 to 1.0)."""
        self.basemap_opacity = max(0.0, min(1.0, opacity))
        self.update()

    def set_show_vectors(self, show: bool):
        """Toggles vector feature overlay visibility."""
        self.show_vectors = show
        self.update()

    def zoom_to_extent(self):
        """Resets zoom and pans directly to the center of dataset or world."""
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def zoom_in(self):
        self._zoom_by_factor(1.3, QPointF(self.width() / 2.0, self.height() / 2.0))

    def zoom_out(self):
        self._zoom_by_factor(1.0 / 1.3, QPointF(self.width() / 2.0, self.height() / 2.0))

    def _zoom_by_factor(self, factor: float, screen_center: QPointF):
        """Applies zoom centered precisely at the given screen coordinate."""
        if not self.bounds:
            return

        w = max(1.0, self.width() - 40)
        h = max(1.0, self.height() - 40)
        minx, miny, maxx, maxy = self.bounds
        dx = maxx - minx if (maxx - minx) > 1e-9 else 1.0
        dy = maxy - miny if (maxy - miny) > 1e-9 else 1.0
        base_scale = min(w / dx, h / dy)
        mid_wx = (minx + maxx) / 2.0
        mid_wy = (miny + maxy) / 2.0

        # World point under cursor before zoom
        scale_old = base_scale * self.zoom
        cx_old = (self.width() / 2.0) + self.pan_x
        cy_old = (self.height() / 2.0) + self.pan_y
        wx = mid_wx + (screen_center.x() - cx_old) / scale_old
        wy = mid_wy - (screen_center.y() - cy_old) / scale_old

        # Adjust zoom
        self.zoom = max(0.05, min(100000.0, self.zoom * factor))
        scale_new = base_scale * self.zoom

        # Adjust pan so wx, wy remains invariant under cursor
        self.pan_x = screen_center.x() - (self.width() / 2.0) - (wx - mid_wx) * scale_new
        self.pan_y = screen_center.y() - (self.height() / 2.0) + (wy - mid_wy) * scale_new
        self.update()

    def world_to_screen(self, wx: float, wy: float) -> QPointF:
        if not self.bounds:
            return QPointF(0, 0)
        minx, miny, maxx, maxy = self.bounds
        dx = maxx - minx if (maxx - minx) > 1e-9 else 1.0
        dy = maxy - miny if (maxy - miny) > 1e-9 else 1.0

        w = max(1.0, self.width() - 40)
        h = max(1.0, self.height() - 40)

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

        w = max(1.0, self.width() - 40)
        h = max(1.0, self.height() - 40)
        scale = min(w / dx, h / dy) * self.zoom

        cx = (self.width() / 2.0) + self.pan_x
        cy = (self.height() / 2.0) + self.pan_y

        mid_wx = (minx + maxx) / 2.0
        mid_wy = (miny + maxy) / 2.0

        wx = mid_wx + (sx - cx) / scale
        wy = mid_wy - (sy - cy) / scale
        return QPointF(wx, wy)

    def screen_to_lonlat(self, sx: float, sy: float) -> Tuple[float, float]:
        """Converts screen pixel to Longitude and Latitude degrees."""
        wpt = self.screen_to_world(sx, sy)
        if not self.is_geographic:
            return wpt.x(), wpt.y()

        mx, my = wpt.x(), wpt.y()
        lon = (mx / MERCATOR_R) * 180.0
        # Clamp latitude to Web Mercator bounds [-85.0511, 85.0511]
        val = max(-20.0, min(20.0, (my / MERCATOR_R) * math.pi))
        lat = math.degrees(math.atan(math.sinh(val)))
        return lon, lat

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # 1. Background fill
            if self.basemap_provider == "none":
                painter.fillRect(self.rect(), QColor("#121216"))
            else:
                # Sleek ocean dark-blue background while tiles stream in
                painter.fillRect(self.rect(), QColor("#182230"))

            # 2. Render Basemap Tiles (OpenStreetMap / ArcGIS)
            if self.is_geographic and self.basemap_provider != "none":
                self._render_basemap_tiles(painter)

            # 3. Render Vector Features
            has_geom = bool(
                self.dataset
                and self.dataset.has_geometry()
                and self._display_gdf is not None
                and not self._display_gdf.empty
            )

            if has_geom and self.show_vectors:
                self._render_vector_features(painter)
            elif not has_geom:
                # Subtle info badge if world map active but no dataset features
                self._render_no_features_watermark(painter)

            # 4. Render Attribution & Scale
            self._render_attribution_badge(painter)

        except Exception:
            pass

    def _render_basemap_tiles(self, painter: QPainter):
        """Renders Web Mercator slippy tiles with async caching and fallback previews."""
        if not self.bounds:
            return

        minx, miny, maxx, maxy = self.bounds
        dx = maxx - minx if (maxx - minx) > 1e-9 else 1.0
        dy = maxy - miny if (maxy - miny) > 1e-9 else 1.0
        w = max(1.0, self.width() - 40)
        h = max(1.0, self.height() - 40)
        scale = min(w / dx, h / dy) * self.zoom

        cfg = BASEMAP_CONFIGS.get(self.basemap_provider)
        if not cfg or not cfg.get("url"):
            return

        max_provider_zoom = cfg.get("max_zoom", 19)

        # Calculate continuous zoom level and integer tile zoom
        calc_z = math.log2(max(1e-9, (MERCATOR_W * scale) / 256.0))
        tile_z = max(0, min(max_provider_zoom, round(calc_z)))
        num_tiles = 2 ** tile_z
        tile_size_m = MERCATOR_W / num_tiles

        # Viewport in world coords
        tl = self.screen_to_world(-20, -20)
        br = self.screen_to_world(self.width() + 20, self.height() + 20)
        min_x = min(tl.x(), br.x())
        max_x = max(tl.x(), br.x())
        min_y = min(tl.y(), br.y())
        max_y = max(tl.y(), br.y())

        # Tile range in (x, y)
        min_tx = max(0, int(math.floor((min_x + MERCATOR_R) / MERCATOR_W * num_tiles)))
        max_tx = min(num_tiles - 1, int(math.floor((max_x + MERCATOR_R) / MERCATOR_W * num_tiles)))
        min_ty = max(0, int(math.floor((MERCATOR_R - max_y) / MERCATOR_W * num_tiles)))
        max_ty = min(num_tiles - 1, int(math.floor((MERCATOR_R - min_y) / MERCATOR_W * num_tiles)))

        painter.save()
        painter.setOpacity(self.basemap_opacity)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        for ty in range(min_ty, max_ty + 1):
            for tx in range(min_tx, max_tx + 1):
                t_x_min = -MERCATOR_R + tx * tile_size_m
                t_x_max = t_x_min + tile_size_m
                t_y_max = MERCATOR_R - ty * tile_size_m
                t_y_min = t_y_max - tile_size_m

                s_tl = self.world_to_screen(t_x_min, t_y_max)
                s_br = self.world_to_screen(t_x_max, t_y_min)
                tile_rect = QRectF(s_tl, s_br)

                pix = self.tile_manager.get_tile(self.basemap_provider, tile_z, tx, ty)
                if pix:
                    painter.drawPixmap(tile_rect, pix, QRectF(pix.rect()))
                else:
                    # Draw intermediate lower-res parent tile if available
                    fallback = self.tile_manager.get_tile_fallback(self.basemap_provider, tile_z, tx, ty)
                    if fallback:
                        parent_pix, src_quad = fallback
                        painter.drawPixmap(tile_rect, parent_pix, src_quad)

        painter.restore()

    def _render_vector_features(self, painter: QPainter):
        """Renders vector geometries with high-contrast outlines and viewport culling."""
        gdf = self._display_gdf
        if gdf is None or gdf.empty:
            return

        # Viewport bounds in world coords
        tl = self.screen_to_world(-30, -30)
        br = self.screen_to_world(self.width() + 30, self.height() + 30)
        min_x, max_x = min(tl.x(), br.x()), max(tl.x(), br.x())
        min_y, max_y = min(tl.y(), br.y()), max(tl.y(), br.y())

        try:
            if hasattr(gdf, "cx") and len(gdf) > 100:
                visible_gdf = gdf.cx[min_x:max_x, min_y:max_y].head(5000)
            else:
                visible_gdf = gdf.head(5000)
        except Exception:
            visible_gdf = gdf.head(5000)

        # High-contrast vibrant palettes designed for visibility on satellite and street maps
        poly_brush = QBrush(QColor(0, 180, 255, 75))
        poly_pen = QPen(QColor("#00e5ff"), 2.0)
        line_pen = QPen(QColor("#ffb300"), 2.8)
        point_brush = QBrush(QColor("#00e676"))
        point_pen = QPen(QColor("#112211"), 1.5)

        for geom in visible_gdf.geometry.dropna():
            try:
                self._render_single_geometry(painter, geom, poly_brush, poly_pen, line_pen, point_brush, point_pen)
            except Exception:
                pass

    def _render_single_geometry(self, painter: QPainter, geom, poly_brush, poly_pen, line_pen, point_brush, point_pen):
        if geom is None or geom.is_empty:
            return

        if isinstance(geom, (Point, MultiPoint)):
            points = [geom] if isinstance(geom, Point) else geom.geoms
            painter.setBrush(point_brush)
            painter.setPen(point_pen)
            for pt in points:
                sp = self.world_to_screen(pt.x, pt.y)
                painter.drawEllipse(sp, 5.5, 5.5)

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

    def _render_attribution_badge(self, painter: QPainter):
        """Displays subtle attribution badge at bottom-right corner."""
        cfg = BASEMAP_CONFIGS.get(self.basemap_provider)
        if not cfg or not cfg.get("attribution"):
            return

        attrib = cfg["attribution"]
        painter.save()
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)

        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(attrib) + 16
        text_h = fm.height() + 8

        badge_rect = QRectF(self.width() - text_w - 8, self.height() - text_h - 8, text_w, text_h)
        painter.setBrush(QBrush(QColor(18, 18, 24, 210)))
        painter.setPen(QPen(QColor(60, 60, 75), 1))
        painter.drawRoundedRect(badge_rect, 4, 4)

        painter.setPen(QColor("#c5c5d2"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, attrib)
        painter.restore()

    def _render_no_features_watermark(self, painter: QPainter):
        """Displays a clean helper banner when viewing basemap without loaded geometries."""
        if self.basemap_provider == "none":
            painter.setPen(QColor("#616170"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No spatial geometries to display.\n(Connect a spatial reader or VertexCreator to inspect map view)",
            )
        else:
            painter.save()
            hint = "Interactive Basemap Active • Connect or run a spatial node to overlay features"
            font = painter.font()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(hint) + 24
            th = fm.height() + 12

            rect = QRectF((self.width() - tw) / 2.0, 16, tw, th)
            painter.setBrush(QBrush(QColor(20, 24, 34, 220)))
            painter.setPen(QPen(QColor(33, 150, 243, 180), 1.2))
            painter.drawRoundedRect(rect, 6, 6)

            painter.setPen(QColor("#90caf9"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, hint)
            painter.restore()

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.25 if event.angleDelta().y() > 0 else (1.0 / 1.25)
        self._zoom_by_factor(factor, event.position())

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
        lon, lat = self.screen_to_lonlat(event.position().x(), event.position().y())
        if self.parent() and hasattr(self.parent(), "coord_label"):
            if self.is_geographic:
                self.parent().coord_label.setText(
                    f"Lon: {lon:.5f}°, Lat: {lat:.5f}° | Zoom: {self.zoom:.2f}x"
                )
            else:
                self.parent().coord_label.setText(
                    f"X: {lon:.2f}, Y: {lat:.2f} | Zoom: {self.zoom:.2f}x"
                )

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.is_panning:
            self.is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._zoom_by_factor(1.5, event.position())


class MapInspectorWidget(QWidget):
    """
    Complete GIS Map Visualizer panel with Toolbar, Basemap Switcher (OSM / ArcGIS),
    Layer Opacity Slider, Zoom Controls, Coordinate Readout, and Web Export.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(4)

        # Toolbar
        bar = QHBoxLayout()
        bar.setSpacing(6)

        # 1. Basemap Selector
        lbl_basemap = QLabel("Basemap:")
        lbl_basemap.setStyleSheet("font-weight: 600; color: #b0b0cc;")
        bar.addWidget(lbl_basemap)

        self.basemap_combo = QComboBox()
        self.basemap_combo.setToolTip("Select underlying basemap layer (OpenStreetMap or ArcGIS)")
        for key, info in BASEMAP_CONFIGS.items():
            self.basemap_combo.addItem(info["name"], userData=key)
        self.basemap_combo.setCurrentIndex(0)  # Default: OpenStreetMap
        self.basemap_combo.currentIndexChanged.connect(self._on_basemap_changed)
        bar.addWidget(self.basemap_combo)

        # 2. Opacity Slider
        lbl_opacity = QLabel("Opacity:")
        lbl_opacity.setStyleSheet("color: #8c8c9e; margin-left: 4px;")
        bar.addWidget(lbl_opacity)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(80)
        self.opacity_slider.setToolTip("Adjust basemap transparency")
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        bar.addWidget(self.opacity_slider)

        self.opacity_val_lbl = QLabel("100%")
        self.opacity_val_lbl.setStyleSheet("color: #8c8c9e; min-width: 32px;")
        bar.addWidget(self.opacity_val_lbl)

        # 3. Vector Overlay Toggle
        self.vector_check = QCheckBox("Vectors")
        self.vector_check.setChecked(True)
        self.vector_check.setToolTip("Show/hide vector feature geometries overlay")
        self.vector_check.toggled.connect(self._on_vector_toggled)
        bar.addWidget(self.vector_check)

        # 4. Zoom Buttons
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedSize(26, 26)
        self.zoom_in_btn.setToolTip("Zoom In")
        self.zoom_in_btn.clicked.connect(self._on_zoom_in_clicked)
        bar.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setFixedSize(26, 26)
        self.zoom_out_btn.setToolTip("Zoom Out")
        self.zoom_out_btn.clicked.connect(self._on_zoom_out_clicked)
        bar.addWidget(self.zoom_out_btn)

        # 5. Reset View
        self.extent_btn = QPushButton("Reset View")
        self.extent_btn.setToolTip("Zoom to full extent of data or world")
        self.extent_btn.clicked.connect(self._on_extent_clicked)
        bar.addWidget(self.extent_btn)

        # 6. Web Map Export / Browser View
        self.export_web_btn = QPushButton("🌐 View in Browser")
        self.export_web_btn.setToolTip("Open interactive Leaflet web map with OSM & ArcGIS in default browser")
        self.export_web_btn.clicked.connect(self._on_export_web_clicked)
        bar.addWidget(self.export_web_btn)

        # 7. CRS Label
        self.crs_label = QLabel("CRS: EPSG:4326")
        self.crs_label.setStyleSheet("color: #8c8c9e; margin-left: 6px;")
        bar.addWidget(self.crs_label)

        bar.addStretch()

        # 8. Cursor Coordinate Readout
        self.coord_label = QLabel("Cursor: -")
        self.coord_label.setStyleSheet("color: #00bcd4; font-family: monospace; font-size: 11px;")
        bar.addWidget(self.coord_label)

        self.layout.addLayout(bar)

        # Map canvas
        self.canvas = MapCanvasWidget(self)
        self.layout.addWidget(self.canvas)

    def set_dataset(self, dataset: FeatureDataset):
        """Updates inspected dataset and synchronizes CRS and view."""
        self.canvas.set_dataset(dataset)
        if dataset and dataset.has_geometry():
            crs_name = str(dataset.crs) if dataset.crs else "EPSG:4326 (Inferred)"
            self.crs_label.setText(f"CRS: {crs_name}")
        else:
            self.crs_label.setText("CRS: World (EPSG:3857)")

    def _on_basemap_changed(self, index: int):
        key = self.basemap_combo.itemData(index)
        self.canvas.set_basemap(key)

    def _on_opacity_changed(self, value: int):
        self.opacity_val_lbl.setText(f"{value}%")
        self.canvas.set_basemap_opacity(value / 100.0)

    def _on_vector_toggled(self, checked: bool):
        self.canvas.set_show_vectors(checked)

    def _on_zoom_in_clicked(self):
        self.canvas.zoom_in()

    def _on_zoom_out_clicked(self):
        self.canvas.zoom_out()

    def _on_extent_clicked(self):
        self.canvas.zoom_to_extent()

    def _on_export_web_clicked(self):
        """
        Generates a standalone Leaflet.js HTML map with OpenStreetMap and ArcGIS
        basemap layers and opens it in the default browser.
        """
        import webbrowser
        import json

        geojson_str = "null"
        center_lat, center_lon, zoom_level = 20.0, 0.0, 2

        if self.canvas.dataset and self.canvas.dataset.has_geometry():
            try:
                gdf = self.canvas.dataset.to_geopandas()
                if not gdf.empty:
                    # Reproject to WGS84 for GeoJSON
                    if gdf.crs is not None and str(gdf.crs).lower() not in ("epsg:4326", "4326"):
                        gdf_4326 = gdf.to_crs(epsg=4326)
                    else:
                        gdf_4326 = gdf

                    geojson_str = gdf_4326.to_json()
                    b = gdf_4326.total_bounds
                    center_lon = (b[0] + b[2]) / 2.0
                    center_lat = (b[1] + b[3]) / 2.0
                    zoom_level = 10
            except Exception:
                pass

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>open-FME Interactive GIS Map</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        html, body, #map {{ width: 100%; height: 100%; margin: 0; padding: 0; background: #121216; }}
        .leaflet-popup-content-wrapper {{ background: #1e1e28; color: #e0e0e0; font-family: sans-serif; }}
        .leaflet-popup-tip {{ background: #1e1e28; }}
        .title-banner {{
            position: absolute; top: 10px; left: 60px; z-index: 1000;
            background: rgba(20, 20, 28, 0.85); backdrop-filter: blur(8px);
            color: #ffffff; padding: 8px 16px; border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4); font-family: -apple-system, sans-serif; font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="title-banner">
        <strong>open-FME Visual Data Inspector</strong> • OpenStreetMap & ArcGIS Basemaps
    </div>
    <div id="map"></div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        // Basemap layer definitions
        const osm = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            maxZoom: 19,
            attribution: '© OpenStreetMap contributors'
        }});

        const arcgisImagery = L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            maxZoom: 19,
            attribution: 'Source: Esri, Maxar, Earthstar Geographics'
        }});

        const arcgisStreets = L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            maxZoom: 19,
            attribution: 'Source: Esri, HERE, Garmin, USGS'
        }});

        const arcgisTopo = L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            maxZoom: 19,
            attribution: 'Source: Esri, USGS, NOAA'
        }});

        const arcgisDark = L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            maxZoom: 16,
            attribution: 'Source: Esri, HERE, Garmin'
        }});

        const map = L.map('map', {{
            center: [{center_lat}, {center_lon}],
            zoom: {zoom_level},
            layers: [osm]
        }});

        const baseMaps = {{
            "OpenStreetMap": osm,
            "ArcGIS World Imagery": arcgisImagery,
            "ArcGIS World Streets": arcgisStreets,
            "ArcGIS Topographic": arcgisTopo,
            "ArcGIS Dark Canvas": arcgisDark
        }};

        const overlays = {{}};

        const geojsonData = {geojson_str};
        if (geojsonData && geojsonData.features && geojsonData.features.length > 0) {{
            const vectorLayer = L.geoJSON(geojsonData, {{
                style: function(feature) {{
                    return {{
                        color: "#00e5ff",
                        weight: 2.5,
                        fillColor: "#00b0ff",
                        fillOpacity: 0.35
                    }};
                }},
                pointToLayer: function(feature, latlng) {{
                    return L.circleMarker(latlng, {{
                        radius: 6,
                        fillColor: "#00e676",
                        color: "#003300",
                        weight: 1.5,
                        opacity: 1,
                        fillOpacity: 0.9
                    }});
                }},
                onEachFeature: function(feature, layer) {{
                    if (feature.properties) {{
                        let content = "<table style='border-collapse:collapse; width:100%;'>";
                        for (const [k, v] of Object.entries(feature.properties)) {{
                            content += `<tr><td style='padding:2px 6px; font-weight:600; color:#80cbc4;'>${{k}}</td><td style='padding:2px 6px;'>${{v}}</td></tr>`;
                        }}
                        content += "</table>";
                        layer.bindPopup(content);
                    }}
                }}
            }}).addTo(map);

            overlays["Inspected Features"] = vectorLayer;
            try {{
                map.fitBounds(vectorLayer.getBounds(), {{ padding: [30, 30] }});
            }} catch (e) {{}}
        }}

        L.control.layers(baseMaps, overlays, {{ position: 'topright' }}).addTo(map);
        L.control.scale({{ metric: true, imperial: true }}).addTo(map);
    </script>
</body>
</html>"""

        try:
            out_path = os.path.join(tempfile.gettempdir(), "pyfme_web_map.html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            webbrowser.open(f"file:///{out_path}")
        except Exception:
            pass
