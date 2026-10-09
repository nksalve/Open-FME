"""
Comprehensive FME, GDAL, and SAGA GIS Raster & Terrain Transformers:
- PointOnRasterValueExtractor: Samples raster pixel values at vector point locations (FME / GDAL gdallocationinfo / SAGA Add Grid Values to Points)
- SlopeCalculator: Topographic slope in degrees or percent from DEM (FME / GDAL gdaldem slope / SAGA ta_morphometry Slope)
- AspectCalculator: Compass aspect in degrees 0-360 from DEM (FME / GDAL gdaldem aspect / SAGA ta_morphometry Aspect)
- HillshadeGenerator: 8-bit shaded relief hillshade from DEM (FME / GDAL gdaldem hillshade / SAGA ta_lighting Hillshading)
- ContourGenerator: Extracts vector contour LineStrings from DEM (FME / GDAL gdal_contour / SAGA Contour Lines from Grid)
- RasterExpressionEvaluator: Map algebra on raster bands e.g. NDVI, conditionals (FME / GDAL gdal_calc.py / SAGA grid_calculus)
- RasterCellValueReplacer: Reclassifies / replaces cell values (FME / SAGA Reclassify Grid Values)
- RasterCellValueRounder: Rounds cell values to decimal places or integers (FME)
- RasterConvolver: Kernel filters: smoothing, Gaussian blur, Sobel, Laplacian (FME / SAGA grid_filter)
- RasterDEMGenerator: Interpolates DEM raster from point features via IDW or Nearest (FME / GDAL gdal_grid / SAGA grid_gridding)
- RasterToPointCoercer: Converts raster cells to point vector features (FME / SAGA Grid Values to Points)
- ZonalStatisticsCalculator: Zonal statistics min/max/mean/sum per polygon feature (SAGA shapes_grid / FME)
- RasterDiffer: Calculates difference between two rasters A - B (FME / GDAL gdalcompare)
- RasterResampler: Resamples cell size / resolution (FME / GDAL gdalwarp / SAGA Resampling)
"""

from __future__ import annotations
import os
import importlib.util
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import ndimage
import polars as pl
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import linemerge

# Ensure PROJ and GDAL paths from rasterio are configured prior to C runtime init
def _ensure_proj_data():
    try:
        spec = importlib.util.find_spec("rasterio")
        if spec and spec.origin:
            r_dir = os.path.dirname(spec.origin)
            proj_dir = os.path.join(r_dir, "proj_data")
            if os.path.exists(proj_dir):
                os.environ["PROJ_LIB"] = proj_dir
                os.environ["PROJ_DATA"] = proj_dir
            gdal_dir = os.path.join(r_dir, "gdal_data")
            if os.path.exists(gdal_dir):
                os.environ["GDAL_DATA"] = gdal_dir
            elif "GDAL_DATA" in os.environ and "postgresql" in os.environ["GDAL_DATA"].lower():
                del os.environ["GDAL_DATA"]
    except Exception:
        pass

_ensure_proj_data()

import rasterio
from rasterio.transform import from_origin, Affine
from rasterio.enums import Resampling

from pyfme.engine.nodes.base import (
    BaseNode, NodeCategory, Port, PortType, ParameterDef, ParameterType
)
from pyfme.engine.dataset import FeatureDataset
from pyfme.engine.registry import NodeRegistry


@NodeRegistry.register
class PointOnRasterValueExtractor(BaseNode):
    """
    Samples raster cell values at point locations and transfers pixel values as attributes.
    Matches FME PointOnRasterValueExtractor, GDAL gdallocationinfo, and SAGA Add Grid Values to Points.
    """
    node_type = "PointOnRasterValueExtractor"
    category = NodeCategory.SPATIAL
    description = "Samples raster cell values at point locations and adds raster band attributes (FME / GDAL gdallocationinfo / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Vector point features to sample raster with")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [
            Port("Output", PortType.OUTPUT, "Point features with sampled raster attributes"),
        ]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("band_index", ParameterType.INTEGER, default=1, label="Band Index to Sample (1-based)"),
            ParameterDef("result_attribute", ParameterType.STRING, default="_raster_val", label="Result Attribute Name"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if inp is None or inp.is_empty():
            return {"Output": FeatureDataset.empty()}

        raster_path = params.get("raster_path", "").strip()
        if not raster_path or not os.path.exists(raster_path):
            return {"Output": inp}

        band_idx = int(params.get("band_index", 1))
        res_attr = params.get("result_attribute", "_raster_val").strip() or "_raster_val"

        gdf = inp.to_geopandas().copy()
        if not hasattr(gdf, "geometry") or gdf.geometry is None:
            return {"Output": inp}

        coords = [(geom.x, geom.y) if geom and hasattr(geom, "x") else (np.nan, np.nan) for geom in gdf.geometry]

        with rasterio.open(raster_path) as src:
            nodata_val = src.nodata
            # sample coords directly using rasterio
            sampled = list(src.sample(coords, indexes=band_idx))
            vals = []
            for s in sampled:
                v = float(s[0]) if len(s) > 0 else np.nan
                if nodata_val is not None and v == nodata_val:
                    vals.append(None)
                else:
                    vals.append(v)

        gdf[res_attr] = vals
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class SlopeCalculator(BaseNode):
    """
    Calculates topographic slope in degrees or percent from a DEM raster.
    Matches FME SlopeCalculator, GDAL gdaldem slope, and SAGA ta_morphometry Slope.
    """
    node_type = "SlopeCalculator"
    category = NodeCategory.SPATIAL
    description = "Calculates topographic slope in degrees or percent from DEM (FME / GDAL gdaldem slope / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Optional input features (pass-through)")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Slope calculation summary and metadata")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("dem_path", ParameterType.FILE_OPEN, default="", label="DEM Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Slope Raster (.tif, Optional)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("slope_format", ParameterType.CHOICE, default="Degrees", label="Slope Format", choices=["Degrees", "Percent"]),
            ParameterDef("z_factor", ParameterType.FLOAT, default=1.0, label="Vertical Z Factor"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        dem_path = params.get("dem_path", "").strip()
        inp = inputs.get("Input")
        if not dem_path and inp is not None:
            if getattr(inp, "raster_path", None) and os.path.exists(inp.raster_path):
                dem_path = inp.raster_path

        if not dem_path or not os.path.exists(dem_path):
            return {"Output": FeatureDataset.empty()}

        slope_fmt = params.get("slope_format", "Degrees")
        z_factor = float(params.get("z_factor", 1.0))
        out_path = params.get("output_path", "").strip()

        with rasterio.open(dem_path) as src:
            dem = src.read(1).astype(np.float32)
            profile = src.profile.copy()
            dx = abs(src.transform[0])
            dy = abs(src.transform[4])
            nodata = src.nodata

        # Horn 3x3 finite-difference kernels
        kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32) / (8.0 * dx)
        ky = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=np.float32) / (8.0 * dy)

        dz_dx = ndimage.convolve(dem, kx) * z_factor
        dz_dy = ndimage.convolve(dem, ky) * z_factor

        rise_run = np.sqrt(dz_dx**2 + dz_dy**2)
        if slope_fmt == "Percent":
            slope = rise_run * 100.0
        else:
            slope = np.degrees(np.arctan(rise_run))

        if nodata is not None:
            slope[dem == nodata] = nodata

        profile.update(dtype=rasterio.float32, count=1, nodata=nodata if nodata is not None else -9999.0)
        if out_path:
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(slope.astype(np.float32), 1)

        valid = slope[slope != nodata] if nodata is not None else slope
        summary_df = pl.DataFrame({
            "dem_source": [dem_path],
            "slope_output": [out_path if out_path else "(In-memory)"],
            "unit": [slope_fmt],
            "min_slope": [float(np.nanmin(valid))],
            "max_slope": [float(np.nanmax(valid))],
            "mean_slope": [float(np.nanmean(valid))],
            "std_slope": [float(np.nanstd(valid))],
            "width": [dem.shape[1]],
            "height": [dem.shape[0]],
        })

        return {"Output": FeatureDataset(df=summary_df, raster_data=slope.astype(np.float32), raster_profile=profile, raster_path=out_path, crs=profile.get("crs"))}


@NodeRegistry.register
class AspectCalculator(BaseNode):
    """
    Calculates compass aspect in degrees (0 - 360 clockwise from North) from a DEM raster.
    Matches FME AspectCalculator, GDAL gdaldem aspect, and SAGA ta_morphometry Aspect.
    """
    node_type = "AspectCalculator"
    category = NodeCategory.SPATIAL
    description = "Calculates compass aspect in degrees (0-360) from DEM (FME / GDAL gdaldem aspect / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Optional input features (pass-through)")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Aspect calculation summary and metadata")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("dem_path", ParameterType.FILE_OPEN, default="", label="DEM Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Aspect Raster (.tif, Optional)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        dem_path = params.get("dem_path", "").strip()
        inp = inputs.get("Input")
        if not dem_path and inp is not None:
            if getattr(inp, "raster_path", None) and os.path.exists(inp.raster_path):
                dem_path = inp.raster_path

        if not dem_path or not os.path.exists(dem_path):
            return {"Output": FeatureDataset.empty()}

        out_path = params.get("output_path", "").strip()

        with rasterio.open(dem_path) as src:
            dem = src.read(1).astype(np.float32)
            profile = src.profile.copy()
            dx = abs(src.transform[0])
            dy = abs(src.transform[4])
            nodata = src.nodata

        kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32) / (8.0 * dx)
        ky = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=np.float32) / (8.0 * dy)

        dz_dx = ndimage.convolve(dem, kx)
        dz_dy = ndimage.convolve(dem, ky)

        # Standard compass aspect: 0=North, 90=East, 180=South, 270=West
        aspect_rad = np.arctan2(dz_dy, -dz_dx)
        aspect = (90.0 - np.degrees(aspect_rad)) % 360.0

        # Mark flat areas as -1.0
        flat = (dz_dx == 0) & (dz_dy == 0)
        aspect[flat] = -1.0

        if nodata is not None:
            aspect[dem == nodata] = -9999.0

        profile.update(dtype=rasterio.float32, count=1, nodata=-9999.0)
        if out_path:
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(aspect.astype(np.float32), 1)

        valid = aspect[(aspect >= 0)]
        summary_df = pl.DataFrame({
            "dem_source": [dem_path],
            "aspect_output": [out_path if out_path else "(In-memory)"],
            "mean_aspect": [float(np.nanmean(valid)) if len(valid) > 0 else 0.0],
            "width": [dem.shape[1]],
            "height": [dem.shape[0]],
        })

        return {"Output": FeatureDataset(df=summary_df, raster_data=aspect.astype(np.float32), raster_profile=profile, raster_path=out_path, crs=profile.get("crs"))}


@NodeRegistry.register
class HillshadeGenerator(BaseNode):
    """
    Generates analytical shaded relief (8-bit grayscale 0-255) from a DEM raster.
    Matches FME HillshadeGenerator, GDAL gdaldem hillshade, and SAGA ta_lighting Hillshading.
    """
    node_type = "HillshadeGenerator"
    category = NodeCategory.SPATIAL
    description = "Generates 8-bit shaded relief hillshade from DEM (FME / GDAL gdaldem hillshade / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Optional input features (pass-through)")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Hillshade summary and metadata")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("dem_path", ParameterType.FILE_OPEN, default="", label="DEM Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Hillshade Raster (.tif, Optional)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("azimuth", ParameterType.FLOAT, default=315.0, label="Sun Azimuth (degrees, 315=NW)"),
            ParameterDef("altitude", ParameterType.FLOAT, default=45.0, label="Sun Altitude / Elevation (degrees)"),
            ParameterDef("z_factor", ParameterType.FLOAT, default=1.0, label="Vertical Z Factor"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        dem_path = params.get("dem_path", "").strip()
        inp = inputs.get("Input")
        if not dem_path and inp is not None:
            if getattr(inp, "raster_path", None) and os.path.exists(inp.raster_path):
                dem_path = inp.raster_path

        if not dem_path or not os.path.exists(dem_path):
            return {"Output": FeatureDataset.empty()}

        azimuth = float(params.get("azimuth", 315.0))
        altitude = float(params.get("altitude", 45.0))
        z_factor = float(params.get("z_factor", 1.0))
        out_path = params.get("output_path", "").strip()

        with rasterio.open(dem_path) as src:
            dem = src.read(1).astype(np.float32)
            profile = src.profile.copy()
            dx = abs(src.transform[0])
            dy = abs(src.transform[4])
            nodata = src.nodata

        kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32) / (8.0 * dx)
        ky = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=np.float32) / (8.0 * dy)

        dz_dx = ndimage.convolve(dem, kx) * z_factor
        dz_dy = ndimage.convolve(dem, ky) * z_factor

        slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
        aspect_rad = np.arctan2(dz_dy, -dz_dx)
        aspect_compass = (90.0 - np.degrees(aspect_rad)) % 360.0

        zenith_rad = np.radians(90.0 - altitude)
        azimuth_rad = np.radians(azimuth)

        hillshade = 255.0 * (
            np.cos(zenith_rad) * np.cos(slope_rad) +
            np.sin(zenith_rad) * np.sin(slope_rad) * np.cos(azimuth_rad - np.radians(aspect_compass))
        )
        hillshade = np.clip(hillshade, 0.0, 255.0).astype(np.uint8)

        if nodata is not None:
            hillshade[dem == nodata] = 0

        profile.update(dtype=rasterio.uint8, count=1, nodata=0)
        if out_path:
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(hillshade, 1)

        summary_df = pl.DataFrame({
            "dem_source": [dem_path],
            "hillshade_output": [out_path if out_path else "(In-memory)"],
            "azimuth": [azimuth],
            "altitude": [altitude],
            "mean_shade": [float(hillshade.mean())],
            "width": [dem.shape[1]],
            "height": [dem.shape[0]],
        })

        return {"Output": FeatureDataset(df=summary_df, raster_data=hillshade, raster_profile=profile, raster_path=out_path, crs=profile.get("crs"))}


@NodeRegistry.register
class ContourGenerator(BaseNode):
    """
    Extracts vector contour LineStrings from a DEM raster at given elevation intervals.
    Matches FME ContourGenerator, GDAL gdal_contour, and SAGA Contour Lines from Grid.
    """
    node_type = "ContourGenerator"
    category = NodeCategory.SPATIAL
    description = "Extracts vector contour lines from a DEM raster (FME / GDAL gdal_contour / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Extracted contour lines with elevation attributes")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("dem_path", ParameterType.FILE_OPEN, default="", label="DEM Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("interval", ParameterType.FLOAT, default=10.0, label="Contour Interval (e.g. 10.0, 50.0)"),
            ParameterDef("base_contour", ParameterType.FLOAT, default=0.0, label="Base Contour Elevation"),
            ParameterDef("elev_attr", ParameterType.STRING, default="elevation", label="Elevation Attribute Name"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        dem_path = params.get("dem_path", "").strip()
        if not dem_path or not os.path.exists(dem_path):
            return {"Output": FeatureDataset.empty()}

        interval = float(params.get("interval", 10.0))
        if interval <= 0:
            interval = 10.0
        base_contour = float(params.get("base_contour", 0.0))
        elev_attr = params.get("elev_attr", "elevation").strip() or "elevation"

        with rasterio.open(dem_path) as src:
            data = src.read(1).astype(np.float64)
            transform = src.transform
            crs = src.crs.to_string() if src.crs else "EPSG:4326"
            nodata = src.nodata

        if nodata is not None:
            valid_mask = data != nodata
            if not np.any(valid_mask):
                return {"Output": FeatureDataset.empty()}
            min_val = float(np.nanmin(data[valid_mask]))
            max_val = float(np.nanmax(data[valid_mask]))
        else:
            min_val = float(np.nanmin(data))
            max_val = float(np.nanmax(data))

        first_contour = base_contour + np.ceil((min_val - base_contour) / interval) * interval
        if first_contour > max_val:
            return {"Output": FeatureDataset.empty()}

        levels = np.arange(first_contour, max_val + 1e-5, interval)
        if len(levels) == 0:
            return {"Output": FeatureDataset.empty()}

        contour_lines = []
        contour_elevs = []

        ny, nx = data.shape
        for lvl in levels:
            b0 = (data[:-1, :-1] >= lvl).astype(int)
            b1 = (data[:-1, 1:] >= lvl).astype(int)
            b2 = (data[1:, 1:] >= lvl).astype(int)
            b3 = (data[1:, :-1] >= lvl).astype(int)
            cases = b0 + 2*b1 + 4*b2 + 8*b3

            mask = (cases > 0) & (cases < 15)
            rows, cols = np.where(mask)
            if len(rows) == 0:
                continue

            c_vals = cases[rows, cols]
            v_tl = data[rows, cols]
            v_tr = data[rows, cols + 1]
            v_br = data[rows + 1, cols + 1]
            v_bl = data[rows + 1, cols]

            def _interp(v1, v2):
                diff = v2 - v1
                diff[diff == 0] = 1e-6
                t = (lvl - v1) / diff
                return np.clip(t, 0.0, 1.0)

            t_top = _interp(v_tl, v_tr)
            t_right = _interp(v_tr, v_br)
            t_bot = _interp(v_bl, v_br)
            t_left = _interp(v_tl, v_bl)

            p_top = np.column_stack([cols + t_top, rows])
            p_right = np.column_stack([cols + 1, rows + t_right])
            p_bot = np.column_stack([cols + t_bot, rows + 1])
            p_left = np.column_stack([cols, rows + t_left])

            segments = []
            for c, pt, pr, pb, pl in zip(c_vals, p_top, p_right, p_bot, p_left):
                if c in (1, 14):
                    segments.append((pl, pt))
                elif c in (2, 13):
                    segments.append((pt, pr))
                elif c in (3, 12):
                    segments.append((pl, pr))
                elif c in (4, 11):
                    segments.append((pr, pb))
                elif c in (6, 9):
                    segments.append((pt, pb))
                elif c in (7, 8):
                    segments.append((pl, pb))
                elif c == 5:
                    segments.append((pl, pt))
                    segments.append((pr, pb))
                elif c == 10:
                    segments.append((pt, pr))
                    segments.append((pl, pb))

            geom_segments = []
            for p1, p2 in segments:
                x1, y1 = transform * (p1[0], p1[1])
                x2, y2 = transform * (p2[0], p2[1])
                if (x1, y1) != (x2, y2):
                    geom_segments.append(LineString([(x1, y1), (x2, y2)]))

            if geom_segments:
                merged = linemerge(geom_segments)
                if hasattr(merged, "geoms"):
                    for g in merged.geoms:
                        contour_lines.append(g)
                        contour_elevs.append(float(lvl))
                elif merged and not merged.is_empty:
                    contour_lines.append(merged)
                    contour_elevs.append(float(lvl))

        gdf = gpd.GeoDataFrame({elev_attr: contour_elevs}, geometry=contour_lines, crs=crs)
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class RasterExpressionEvaluator(BaseNode):
    """
    Evaluates map algebra expressions on raster bands (e.g. NDVI = (B4-B3)/(B4+B3)).
    Matches FME RasterExpressionEvaluator, GDAL gdal_calc.py, and SAGA grid_calculus.
    """
    node_type = "RasterExpressionEvaluator"
    category = NodeCategory.SPATIAL
    description = "Evaluates map algebra expressions across raster bands e.g. NDVI (FME / GDAL gdal_calc.py / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Resulting map algebra summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_a_path", ParameterType.FILE_OPEN, default="", label="Raster A File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("raster_b_path", ParameterType.FILE_OPEN, default="", label="Raster B File (.tif, Optional)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("expression", ParameterType.EXPRESSION, default="(A - B) / (A + B + 1e-6)", label="Expression (A, B, np.where...)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output GeoTIFF Path (.tif, Optional)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path_a = params.get("raster_a_path", "").strip()
        path_b = params.get("raster_b_path", "").strip()
        expr = params.get("expression", "").strip()
        out_path = params.get("output_path", "").strip()

        if not path_a or not os.path.exists(path_a):
            return {"Output": FeatureDataset.empty()}

        with rasterio.open(path_a) as src_a:
            A = src_a.read(1).astype(np.float32)
            profile = src_a.profile.copy()
            nodata_a = src_a.nodata

        B = None
        if path_b and os.path.exists(path_b):
            with rasterio.open(path_b) as src_b:
                B = src_b.read(1).astype(np.float32)

        # Safe evaluation namespace
        safe_env = {
            "A": A,
            "B": B if B is not None else A,
            "np": np,
            "sqrt": np.sqrt,
            "abs": np.abs,
            "where": np.where,
            "log": np.log,
            "exp": np.exp,
        }

        try:
            res = eval(expr, {"__builtins__": {}}, safe_env)
        except Exception as e:
            return {"Output": FeatureDataset.from_polars(pl.DataFrame({"error": [f"Evaluation error: {str(e)}"]}))}

        res = np.array(res, dtype=np.float32)

        if out_path:
            profile.update(dtype=rasterio.float32, count=1, nodata=-9999.0)
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(res, 1)

        summary_df = pl.DataFrame({
            "expression": [expr],
            "raster_a": [path_a],
            "raster_b": [path_b if path_b else "(None)"],
            "min_val": [float(np.nanmin(res))],
            "max_val": [float(np.nanmax(res))],
            "mean_val": [float(np.nanmean(res))],
            "output_path": [out_path if out_path else "(In-memory)"],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class RasterCellValueReplacer(BaseNode):
    """
    Reclassifies or replaces cell values within a specified range.
    Matches FME RasterCellValueReplacer and SAGA Reclassify Grid Values.
    """
    node_type = "RasterCellValueReplacer"
    category = NodeCategory.SPATIAL
    description = "Reclassifies or replaces raster cell values within a given range (FME / SAGA Reclassify Grid Values)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Reclassification summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("source_min", ParameterType.FLOAT, default=0.0, label="Source Min Value"),
            ParameterDef("source_max", ParameterType.FLOAT, default=100.0, label="Source Max Value"),
            ParameterDef("replacement_value", ParameterType.FLOAT, default=1.0, label="Replacement Value"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Raster File (.tif, Optional)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        if not path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        s_min = float(params.get("source_min", 0.0))
        s_max = float(params.get("source_max", 100.0))
        rep_val = float(params.get("replacement_value", 1.0))
        out_path = params.get("output_path", "").strip()

        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float32)
            profile = src.profile.copy()

        mask = (data >= s_min) & (data <= s_max)
        replaced_count = int(np.count_nonzero(mask))
        data[mask] = rep_val

        if out_path:
            profile.update(dtype=rasterio.float32, count=1)
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(data, 1)

        summary_df = pl.DataFrame({
            "raster_file": [path],
            "cells_replaced": [replaced_count],
            "replacement_value": [rep_val],
            "output_path": [out_path if out_path else "(In-memory)"],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class RasterCellValueRounder(BaseNode):
    """
    Rounds raster cell values to specified number of decimal places or integers.
    FME RasterCellValueRounder transformer.
    """
    node_type = "RasterCellValueRounder"
    category = NodeCategory.SPATIAL
    description = "Rounds raster cell values to specified decimal places or integers (FME RasterCellValueRounder)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Rounding operation summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("decimal_places", ParameterType.INTEGER, default=0, label="Decimal Places (0 for integer)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Raster File (.tif, Optional)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        if not path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        decimals = int(params.get("decimal_places", 0))
        out_path = params.get("output_path", "").strip()

        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float32)
            profile = src.profile.copy()

        rounded = np.round(data, decimals=decimals)

        if out_path:
            profile.update(dtype=rasterio.float32, count=1)
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(rounded, 1)

        summary_df = pl.DataFrame({
            "raster_file": [path],
            "decimal_places": [decimals],
            "min_val": [float(np.nanmin(rounded))],
            "max_val": [float(np.nanmax(rounded))],
            "output_path": [out_path if out_path else "(In-memory)"],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class RasterConvolver(BaseNode):
    """
    Applies spatial convolution kernel filters: Gaussian, smoothing, edge detection (Sobel/Laplacian).
    Matches FME RasterConvolver and SAGA grid_filter.
    """
    node_type = "RasterConvolver"
    category = NodeCategory.SPATIAL
    description = "Applies 2D kernel filters e.g. smoothing, Gaussian, Sobel, Laplacian (FME RasterConvolver / SAGA grid_filter)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Convolution filter summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("filter_type", ParameterType.CHOICE, default="Smoothing 3x3", label="Filter Kernel", choices=[
                "Smoothing 3x3", "Gaussian Blur", "Sobel Horizontal", "Sobel Vertical", "Laplacian Edge", "Sharpen"
            ]),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Raster File (.tif, Optional)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        if not path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        f_type = params.get("filter_type", "Smoothing 3x3")
        out_path = params.get("output_path", "").strip()

        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float32)
            profile = src.profile.copy()

        if f_type == "Smoothing 3x3":
            kernel = np.ones((3, 3), dtype=np.float32) / 9.0
            filtered = ndimage.convolve(data, kernel)
        elif f_type == "Gaussian Blur":
            filtered = ndimage.gaussian_filter(data, sigma=1.5)
        elif f_type == "Sobel Horizontal":
            filtered = ndimage.sobel(data, axis=1)
        elif f_type == "Sobel Vertical":
            filtered = ndimage.sobel(data, axis=0)
        elif f_type == "Laplacian Edge":
            filtered = ndimage.laplace(data)
        elif f_type == "Sharpen":
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
            filtered = ndimage.convolve(data, kernel)
        else:
            filtered = data

        if out_path:
            profile.update(dtype=rasterio.float32, count=1)
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(filtered.astype(np.float32), 1)

        summary_df = pl.DataFrame({
            "raster_file": [path],
            "filter": [f_type],
            "min_val": [float(np.nanmin(filtered))],
            "max_val": [float(np.nanmax(filtered))],
            "output_path": [out_path if out_path else "(In-memory)"],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class RasterDEMGenerator(BaseNode):
    """
    Builds a DEM raster from input vector point features using IDW or Nearest Neighbor.
    Matches FME RasterDEMGenerator, GDAL gdal_grid, and SAGA grid_gridding.
    """
    node_type = "RasterDEMGenerator"
    category = NodeCategory.SPATIAL
    description = "Builds a DEM surface from point features via IDW or Nearest Neighbor (FME / GDAL gdal_grid / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Vector points with elevation attribute")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "DEM generation summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("elevation_attr", ParameterType.STRING, default="elevation", label="Elevation Attribute Name"),
            ParameterDef("cell_size", ParameterType.FLOAT, default=10.0, label="Grid Cell Size"),
            ParameterDef("method", ParameterType.CHOICE, default="IDW", label="Interpolation Method", choices=["IDW", "Nearest"]),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output DEM File (.tif, Required)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if inp is None or inp.is_empty():
            return {"Output": FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        if not hasattr(gdf, "geometry") or gdf.geometry is None:
            return {"Output": FeatureDataset.empty()}

        elev_attr = params.get("elevation_attr", "elevation").strip() or "elevation"
        cell_size = float(params.get("cell_size", 10.0))
        if cell_size <= 0:
            cell_size = 10.0
        method = params.get("method", "IDW")
        out_path = params.get("output_path", "").strip()

        xs = np.array([geom.x for geom in gdf.geometry if geom and hasattr(geom, "x")])
        ys = np.array([geom.y for geom in gdf.geometry if geom and hasattr(geom, "y")])

        if elev_attr in gdf.columns:
            zs = np.array(gdf[elev_attr].fillna(0.0).values, dtype=float)
        else:
            zs = np.array([geom.z if geom.has_z else 0.0 for geom in gdf.geometry])

        if len(xs) == 0:
            return {"Output": FeatureDataset.empty()}

        minx, maxx = float(xs.min()), float(xs.max())
        miny, maxy = float(ys.min()), float(ys.max())

        width = max(2, int(np.ceil((maxx - minx) / cell_size)))
        height = max(2, int(np.ceil((maxy - miny) / cell_size)))

        grid_x = np.linspace(minx, maxx, width)
        grid_y = np.linspace(maxy, miny, height)  # top down
        gx, gy = np.meshgrid(grid_x, grid_y)

        # IDW interpolation
        grid_z = np.zeros_like(gx, dtype=np.float32)
        power = 2.0

        if method == "IDW":
            for r in range(height):
                for c in range(width):
                    dists = np.sqrt((xs - gx[r, c])**2 + (ys - gy[r, c])**2)
                    exact = np.where(dists < 1e-5)[0]
                    if len(exact) > 0:
                        grid_z[r, c] = zs[exact[0]]
                    else:
                        weights = 1.0 / (dists**power)
                        grid_z[r, c] = np.sum(weights * zs) / np.sum(weights)
        else:
            # Nearest neighbor
            for r in range(height):
                for c in range(width):
                    dists = (xs - gx[r, c])**2 + (ys - gy[r, c])**2
                    closest = np.argmin(dists)
                    grid_z[r, c] = zs[closest]

        transform = from_origin(minx, maxy, cell_size, cell_size)
        crs = gdf.crs.to_string() if gdf.crs else "EPSG:4326"

        if out_path:
            with rasterio.open(
                out_path, "w", driver="GTiff",
                height=height, width=width, count=1,
                dtype=rasterio.float32, crs=crs, transform=transform, nodata=-9999.0
            ) as dst:
                dst.write(grid_z, 1)

        summary_df = pl.DataFrame({
            "num_points": [len(xs)],
            "grid_width": [width],
            "grid_height": [height],
            "min_elevation": [float(grid_z.min())],
            "max_elevation": [float(grid_z.max())],
            "cell_size": [cell_size],
            "output_dem": [out_path if out_path else "(In-memory)"],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class RasterToPointCoercer(BaseNode):
    """
    Converts raster cells into vector Point features with coordinates and pixel value.
    Matches FME RasterToPointCoercer and SAGA Grid Values to Points.
    """
    node_type = "RasterToPointCoercer"
    category = NodeCategory.SPATIAL
    description = "Converts raster cells into vector Point features with pixel value attributes (FME / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Vector points representing raster cells")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("band_index", ParameterType.INTEGER, default=1, label="Band Index (1-based)"),
            ParameterDef("sample_stride", ParameterType.INTEGER, default=1, label="Sampling Stride (e.g. 1=All cells, 2=Every 2nd cell)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        if not path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        band_idx = int(params.get("band_index", 1))
        stride = max(1, int(params.get("sample_stride", 1)))

        with rasterio.open(path) as src:
            data = src.read(band_idx)
            transform = src.transform
            crs = src.crs.to_string() if src.crs else "EPSG:4326"
            nodata = src.nodata

        rows, cols = np.where(data != nodata) if nodata is not None else np.indices(data.shape).reshape(2, -1)
        if stride > 1:
            rows = rows[::stride]
            cols = cols[::stride]

        xs, ys = rasterio.transform.xy(transform, rows, cols)
        vals = data[rows, cols]

        points = [Point(x, y) for x, y in zip(xs, ys)]
        gdf = gpd.GeoDataFrame({
            "pixel_value": vals.astype(float),
            "row": rows,
            "col": cols,
        }, geometry=points, crs=crs)

        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class ZonalStatisticsCalculator(BaseNode):
    """
    Calculates zonal statistics (min, max, mean, sum, std, count) for polygon features from a raster.
    Matches SAGA shapes_grid Grid Statistics for Polygons and FME zonal analysis.
    """
    node_type = "ZonalStatisticsCalculator"
    category = NodeCategory.SPATIAL
    description = "Calculates zonal statistics (mean, min, max, sum) per polygon from a raster (SAGA shapes_grid / FME)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Polygon vector zones")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Polygon zones with zonal statistics attributes")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("band_index", ParameterType.INTEGER, default=1, label="Band Index (1-based)"),
            ParameterDef("prefix", ParameterType.STRING, default="zonal_", label="Attribute Prefix"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if inp is None or inp.is_empty():
            return {"Output": FeatureDataset.empty()}

        path = params.get("raster_path", "").strip()
        if not path or not os.path.exists(path):
            return {"Output": inp}

        band_idx = int(params.get("band_index", 1))
        prefix = params.get("prefix", "zonal_").strip() or "zonal_"

        gdf = inp.to_geopandas().copy()
        if not hasattr(gdf, "geometry") or gdf.geometry is None:
            return {"Output": inp}

        with rasterio.open(path) as src:
            data = src.read(band_idx)
            nodata = src.nodata
            inv_transform = ~src.transform

            means, mins, maxs, sums, counts = [], [], [], [], []

            for geom in gdf.geometry:
                if geom is None or geom.is_empty:
                    means.append(None); mins.append(None); maxs.append(None); sums.append(None); counts.append(0)
                    continue

                b = geom.bounds
                # Transform bbox to pixel coords
                c_min, r_min = inv_transform * (b[0], b[3])
                c_max, r_max = inv_transform * (b[2], b[1])

                r0 = max(0, int(np.floor(min(r_min, r_max))))
                r1 = min(data.shape[0], int(np.ceil(max(r_min, r_max))))
                c0 = max(0, int(np.floor(min(c_min, c_max))))
                c1 = min(data.shape[1], int(np.ceil(max(c_min, c_max))))

                if r1 <= r0 or c1 <= c0:
                    means.append(None); mins.append(None); maxs.append(None); sums.append(None); counts.append(0)
                    continue

                window_data = data[r0:r1, c0:c1]
                valid = window_data[window_data != nodata] if nodata is not None else window_data.flatten()

                if len(valid) == 0:
                    means.append(None); mins.append(None); maxs.append(None); sums.append(None); counts.append(0)
                else:
                    means.append(float(np.mean(valid)))
                    mins.append(float(np.min(valid)))
                    maxs.append(float(np.max(valid)))
                    sums.append(float(np.sum(valid)))
                    counts.append(int(len(valid)))

        gdf[f"{prefix}mean"] = means
        gdf[f"{prefix}min"] = mins
        gdf[f"{prefix}max"] = maxs
        gdf[f"{prefix}sum"] = sums
        gdf[f"{prefix}count"] = counts

        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class RasterDiffer(BaseNode):
    """
    Computes cell-by-cell difference between two rasters: Difference = Raster A - Raster B.
    Matches FME RasterDiffer and GDAL gdalcompare.
    """
    node_type = "RasterDiffer"
    category = NodeCategory.SPATIAL
    description = "Calculates pixel-by-pixel difference between two rasters (Raster A - Raster B) (FME / GDAL gdalcompare)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Difference summary table")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_a_path", ParameterType.FILE_OPEN, default="", label="Raster A File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("raster_b_path", ParameterType.FILE_OPEN, default="", label="Raster B File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Difference GeoTIFF (.tif, Optional)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path_a = params.get("raster_a_path", "").strip()
        path_b = params.get("raster_b_path", "").strip()
        out_path = params.get("output_path", "").strip()

        if not path_a or not os.path.exists(path_a) or not path_b or not os.path.exists(path_b):
            return {"Output": FeatureDataset.empty()}

        with rasterio.open(path_a) as src_a, rasterio.open(path_b) as src_b:
            A = src_a.read(1).astype(np.float32)
            B = src_b.read(1).astype(np.float32)
            profile = src_a.profile.copy()

        # Handle size mismatches by matching minimum bounding shapes
        min_h = min(A.shape[0], B.shape[0])
        min_w = min(A.shape[1], B.shape[1])
        diff = A[:min_h, :min_w] - B[:min_h, :min_w]

        if out_path:
            profile.update(dtype=rasterio.float32, count=1, height=min_h, width=min_w)
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(diff, 1)

        summary_df = pl.DataFrame({
            "raster_a": [path_a],
            "raster_b": [path_b],
            "min_diff": [float(np.min(diff))],
            "max_diff": [float(np.max(diff))],
            "mean_diff": [float(np.mean(diff))],
            "output_path": [out_path if out_path else "(In-memory)"],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class RasterResampler(BaseNode):
    """
    Resamples raster cell size and resolution using nearest, bilinear, or cubic methods.
    Matches FME RasterResampler, GDAL gdalwarp -tr, and SAGA Resampling.
    """
    node_type = "RasterResampler"
    category = NodeCategory.SPATIAL
    description = "Resamples raster cell size and resolution (FME RasterResampler / GDAL gdalwarp / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Resampling summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("scale_factor", ParameterType.FLOAT, default=0.5, label="Scale Factor (e.g. 0.5=half size, 2.0=double size)"),
            ParameterDef("resampling", ParameterType.CHOICE, default="bilinear", label="Resampling Method", choices=["nearest", "bilinear", "cubic"]),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Resampled GeoTIFF (.tif, Required)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        out_path = params.get("output_path", "").strip()
        scale = float(params.get("scale_factor", 0.5))
        method_str = params.get("resampling", "bilinear").lower()

        if not path or not os.path.exists(path) or not out_path or scale <= 0:
            return {"Output": FeatureDataset.empty()}

        resample_method = (
            Resampling.nearest if method_str == "nearest" else
            Resampling.cubic if method_str == "cubic" else
            Resampling.bilinear
        )

        with rasterio.open(path) as src:
            new_height = max(1, int(src.height * scale))
            new_width = max(1, int(src.width * scale))

            data = src.read(
                out_shape=(src.count, new_height, new_width),
                resampling=resample_method
            )

            # Adjust transform matrix
            new_transform = src.transform * src.transform.scale(
                (src.width / new_width),
                (src.height / new_height)
            )

            profile = src.profile.copy()
            profile.update({
                "height": new_height,
                "width": new_width,
                "transform": new_transform
            })

            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(data)

        summary_df = pl.DataFrame({
            "source_raster": [path],
            "resampled_raster": [out_path],
            "original_width": [src.width],
            "original_height": [src.height],
            "new_width": [new_width],
            "new_height": [new_height],
            "scale_factor": [scale],
            "method": [method_str],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class SurfaceDraper(BaseNode):
    """
    Drapes 2D vector geometries onto a DEM raster by interpolating Z elevations at each vertex.
    Matches FME SurfaceDraper transformer.
    """
    node_type = "SurfaceDraper"
    category = NodeCategory.SPATIAL
    description = "Drapes 2D vectors onto a DEM surface, assigning interpolated Z elevations to all vertices (FME SurfaceDraper)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "2D vector features to drape")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "3D draped vector features with Z elevations")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("dem_path", ParameterType.FILE_OPEN, default="", label="DEM Raster File (.tif)", file_filter="GeoTIFF / Raster (*.tif *.tiff *.geotiff);;All Files (*.*)"),
            ParameterDef("default_z", ParameterType.FLOAT, default=0.0, label="Default Z if outside raster"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": FeatureDataset.empty()}

        dem_path = params.get("dem_path", "").strip()
        default_z = float(params.get("default_z", 0.0))

        if not dem_path or not os.path.exists(dem_path):
            return {"Output": inp}

        gdf = inp.to_geopandas().copy()

        with rasterio.open(dem_path) as src:
            nodata = src.nodata

            def _sample_z(x, y):
                try:
                    vals = list(src.sample([(x, y)]))
                    if vals and len(vals[0]) > 0:
                        v = float(vals[0][0])
                        if nodata is not None and v == nodata:
                            return default_z
                        return v
                except Exception:
                    pass
                return default_z

            draped_geoms = []
            z_mins, z_maxs = [], []

            for geom in gdf.geometry:
                if geom is None or geom.is_empty:
                    draped_geoms.append(geom)
                    z_mins.append(None); z_maxs.append(None)
                    continue

                if geom.geom_type == "Point":
                    z = _sample_z(geom.x, geom.y)
                    draped_geoms.append(Point(geom.x, geom.y, z))
                    z_mins.append(z); z_maxs.append(z)
                elif geom.geom_type == "LineString":
                    new_coords = [(x, y, _sample_z(x, y)) for x, y in geom.coords]
                    zs = [c[2] for c in new_coords]
                    draped_geoms.append(LineString(new_coords))
                    z_mins.append(min(zs)); z_maxs.append(max(zs))
                elif geom.geom_type == "Polygon":
                    ext_coords = [(x, y, _sample_z(x, y)) for x, y in geom.exterior.coords]
                    int_rings = []
                    for interior in geom.interiors:
                        int_rings.append([(x, y, _sample_z(x, y)) for x, y in interior.coords])
                    zs = [c[2] for c in ext_coords]
                    draped_geoms.append(Polygon(ext_coords, int_rings))
                    z_mins.append(min(zs)); z_maxs.append(max(zs))
                else:
                    draped_geoms.append(geom)
                    z_mins.append(None); z_maxs.append(None)

        gdf[gdf.geometry.name] = draped_geoms
        gdf["_draped_z_min"] = z_mins
        gdf["_draped_z_max"] = z_maxs
        return {"Output": FeatureDataset.from_geopandas(gdf)}


@NodeRegistry.register
class RasterMosaicker(BaseNode):
    """
    Merges multiple raster files into a single seamless mosaic.
    Matches FME RasterMosaicker, GDAL gdal_merge.py, and SAGA Mosaicking.
    """
    node_type = "RasterMosaicker"
    category = NodeCategory.SPATIAL
    description = "Mosaics multiple raster files into a single seamless output raster (FME / GDAL gdal_merge / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Mosaic summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_paths", ParameterType.STRING, default="", label="Input Raster Paths (comma or semicolon separated)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Mosaic GeoTIFF (.tif, Required)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        raw_paths = params.get("raster_paths", "").strip()
        out_path = params.get("output_path", "").strip()

        if not raw_paths or not out_path:
            return {"Output": FeatureDataset.empty()}

        import re
        paths = [p.strip() for p in re.split(r"[,;]", raw_paths) if p.strip() and os.path.exists(p.strip())]
        if len(paths) == 0:
            return {"Output": FeatureDataset.empty()}

        from rasterio.merge import merge
        src_files = [rasterio.open(p) for p in paths]
        try:
            mosaic, out_trans = merge(src_files)
            out_meta = src_files[0].meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": out_trans
            })
            with rasterio.open(out_path, "w", **out_meta) as dst:
                dst.write(mosaic)
        finally:
            for sf in src_files:
                sf.close()

        summary_df = pl.DataFrame({
            "num_mosaicked": [len(paths)],
            "output_mosaic": [out_path],
            "width": [mosaic.shape[2]],
            "height": [mosaic.shape[1]],
            "bands": [mosaic.shape[0]],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class RasterRGBCombiner(BaseNode):
    """
    Combines single-band Red, Green, and Blue rasters into a composite 3-band RGB GeoTIFF.
    Matches FME RasterRGBCombiner and GDAL pct2rgb / composite.
    """
    node_type = "RasterRGBCombiner"
    category = NodeCategory.SPATIAL
    description = "Combines separate Red, Green, and Blue single-band rasters into an RGB 3-band GeoTIFF (FME / GDAL)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "RGB composite summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("red_path", ParameterType.FILE_OPEN, default="", label="Red Band Raster (.tif)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("green_path", ParameterType.FILE_OPEN, default="", label="Green Band Raster (.tif)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("blue_path", ParameterType.FILE_OPEN, default="", label="Blue Band Raster (.tif)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output RGB GeoTIFF (.tif, Required)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        r_p = params.get("red_path", "").strip()
        g_p = params.get("green_path", "").strip()
        b_p = params.get("blue_path", "").strip()
        out_path = params.get("output_path", "").strip()

        if not r_p or not g_p or not b_p or not out_path:
            return {"Output": FeatureDataset.empty()}

        with rasterio.open(r_p) as r_src, rasterio.open(g_p) as g_src, rasterio.open(b_p) as b_src:
            r_data = r_src.read(1)
            g_data = g_src.read(1)
            b_data = b_src.read(1)

            profile = r_src.profile.copy()
            profile.update(count=3, dtype=r_data.dtype)

            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(r_data, 1)
                dst.write(g_data, 2)
                dst.write(b_data, 3)

        summary_df = pl.DataFrame({
            "red_band": [r_p],
            "green_band": [g_p],
            "blue_band": [b_p],
            "output_rgb": [out_path],
            "width": [r_src.width],
            "height": [r_src.height],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class RasterBandSelector(BaseNode):
    """
    Extracts a specific single band from a multi-band raster into a 1-band GeoTIFF.
    Matches FME RasterBandSelector / GDAL gdal_translate -b.
    """
    node_type = "RasterBandSelector"
    category = NodeCategory.SPATIAL
    description = "Extracts a single band from a multi-band raster into a 1-band GeoTIFF (FME / GDAL)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Band selection summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Source Raster File (.tif)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("band_index", ParameterType.INTEGER, default=1, label="Band Index to Extract (1-based)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output 1-Band GeoTIFF (.tif, Required)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        band_idx = int(params.get("band_index", 1))
        out_path = params.get("output_path", "").strip()

        if not path or not out_path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        with rasterio.open(path) as src:
            if band_idx < 1 or band_idx > src.count:
                return {"Output": FeatureDataset.empty()}

            data = src.read(band_idx)
            profile = src.profile.copy()
            profile.update(count=1, dtype=data.dtype)

            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(data, 1)

        summary_df = pl.DataFrame({
            "source_raster": [path],
            "extracted_band": [band_idx],
            "output_raster": [out_path],
            "min_val": [float(np.nanmin(data))],
            "max_val": [float(np.nanmax(data))],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class RasterTiler(BaseNode):
    """
    Cuts a raster into smaller grid tiles of specified pixel dimensions.
    Matches FME RasterTiler, GDAL gdal_retile.py, and SAGA Tiling.
    """
    node_type = "RasterTiler"
    category = NodeCategory.SPATIAL
    description = "Cuts a raster into regular grid tiles (FME RasterTiler / GDAL gdal_retile / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Generated tile list table")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Source Raster File (.tif)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("tile_width", ParameterType.INTEGER, default=256, label="Tile Width (pixels)"),
            ParameterDef("tile_height", ParameterType.INTEGER, default=256, label="Tile Height (pixels)"),
            ParameterDef("output_dir", ParameterType.STRING, default="", label="Output Directory for Tiles"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        t_w = max(16, int(params.get("tile_width", 256)))
        t_h = max(16, int(params.get("tile_height", 256)))
        out_dir = params.get("output_dir", "").strip()

        if not path or not out_dir or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        os.makedirs(out_dir, exist_ok=True)
        tile_rows = []

        with rasterio.open(path) as src:
            for r in range(0, src.height, t_h):
                for c in range(0, src.width, t_w):
                    w = min(t_w, src.width - c)
                    h = min(t_h, src.height - r)
                    window = rasterio.windows.Window(c, r, w, h)
                    tile_data = src.read(window=window)
                    tile_transform = rasterio.windows.transform(window, src.transform)

                    tile_fname = f"tile_r{r}_c{c}.tif"
                    tile_path = os.path.join(out_dir, tile_fname)

                    profile = src.profile.copy()
                    profile.update({
                        "height": h,
                        "width": w,
                        "transform": tile_transform
                    })

                    with rasterio.open(tile_path, "w", **profile) as dst:
                        dst.write(tile_data)

                    tile_rows.append({
                        "tile_file": tile_fname,
                        "tile_path": tile_path,
                        "row_offset": r,
                        "col_offset": c,
                        "width": w,
                        "height": h,
                    })

        return {"Output": FeatureDataset.from_polars(pl.DataFrame(tile_rows))}


@NodeRegistry.register
class GDALRasterize(BaseNode):
    """
    Burns vector geometries and attribute values onto a raster grid (vector to raster).
    Matches GDAL gdal_rasterize and SAGA Shapes to Grid.
    """
    node_type = "GDALRasterize"
    category = NodeCategory.SPATIAL
    description = "Burns vector features and attribute values into a raster grid (GDAL gdal_rasterize / SAGA Shapes to Grid)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return [Port("Input", PortType.INPUT, "Vector features to rasterize")]

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Rasterization summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("cell_size", ParameterType.FLOAT, default=10.0, label="Raster Cell Size"),
            ParameterDef("burn_attribute", ParameterType.STRING, default="", label="Burn Attribute (Optional)"),
            ParameterDef("default_burn_value", ParameterType.FLOAT, default=1.0, label="Default Burn Value"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output GeoTIFF (.tif, Required)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        inp = inputs.get("Input")
        if not inp or inp.is_empty() or not inp.has_geometry():
            return {"Output": FeatureDataset.empty()}

        cell_size = float(params.get("cell_size", 10.0))
        burn_attr = params.get("burn_attribute", "").strip()
        default_val = float(params.get("default_burn_value", 1.0))
        out_path = params.get("output_path", "").strip()

        if cell_size <= 0 or not out_path:
            return {"Output": FeatureDataset.empty()}

        gdf = inp.to_geopandas()
        bounds = inp.get_bounds()
        if not bounds:
            return {"Output": FeatureDataset.empty()}

        minx, miny, maxx, maxy = bounds
        width = max(2, int(np.ceil((maxx - minx) / cell_size)))
        height = max(2, int(np.ceil((maxy - miny) / cell_size)))
        transform = from_origin(minx, maxy, cell_size, cell_size)

        shapes = []
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            val = default_val
            if burn_attr and burn_attr in row and row[burn_attr] is not None:
                try:
                    val = float(row[burn_attr])
                except Exception:
                    val = default_val
            shapes.append((geom, val))

        from rasterio.features import rasterize
        burned = rasterize(
            shapes,
            out_shape=(height, width),
            transform=transform,
            fill=0,
            dtype=np.float32
        )

        crs = gdf.crs.to_string() if gdf.crs else "EPSG:4326"
        with rasterio.open(
            out_path, "w", driver="GTiff",
            height=height, width=width, count=1,
            dtype=rasterio.float32, crs=crs, transform=transform, nodata=0
        ) as dst:
            dst.write(burned, 1)

        summary_df = pl.DataFrame({
            "features_burned": [len(shapes)],
            "grid_width": [width],
            "grid_height": [height],
            "cell_size": [cell_size],
            "output_raster": [out_path],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class GDALProximity(BaseNode):
    """
    Computes Euclidean distance-to-feature raster from target pixels.
    Matches GDAL gdal_proximity.py and SAGA Proximity Grid.
    """
    node_type = "GDALProximity"
    category = NodeCategory.SPATIAL
    description = "Calculates Euclidean distance from target pixel values across the grid (GDAL gdal_proximity / SAGA)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Proximity calculation summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Source Raster File (.tif)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("target_value", ParameterType.FLOAT, default=1.0, label="Target Pixel Value (Features)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Distance GeoTIFF (.tif, Required)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        target_val = float(params.get("target_value", 1.0))
        out_path = params.get("output_path", "").strip()

        if not path or not out_path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        with rasterio.open(path) as src:
            data = src.read(1)
            profile = src.profile.copy()
            dx = abs(src.transform[0])
            dy = abs(src.transform[4])

        feature_mask = (data == target_val)
        # distance_transform_edt computes distance from zero cells, so invert mask
        dist_px = ndimage.distance_transform_edt(~feature_mask, sampling=(dy, dx))

        profile.update(dtype=rasterio.float32, count=1, nodata=-9999.0)
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(dist_px.astype(np.float32), 1)

        summary_df = pl.DataFrame({
            "raster_file": [path],
            "target_value": [target_val],
            "max_distance": [float(np.max(dist_px))],
            "mean_distance": [float(np.mean(dist_px))],
            "output_path": [out_path],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class GDALInfo(BaseNode):
    """
    Comprehensive raster metadata inspector: CRS, bounds, resolution, band counts, and pixel statistics.
    Matches GDAL gdalinfo utility.
    """
    node_type = "GDALInfo"
    category = NodeCategory.SPATIAL
    description = "Comprehensive raster metadata inspection: CRS, bounds, bands, and statistics (GDAL gdalinfo)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "GDAL info report table")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Raster File (.tif)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        if not path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        with rasterio.open(path) as src:
            b = src.bounds
            crs_str = src.crs.to_string() if src.crs else "Unknown"
            df = pl.DataFrame({
                "driver": [src.driver],
                "file_path": [path],
                "width": [src.width],
                "height": [src.height],
                "num_bands": [src.count],
                "crs": [crs_str],
                "minx": [b.left],
                "miny": [b.bottom],
                "maxx": [b.right],
                "maxy": [b.top],
                "cell_size_x": [abs(src.transform[0])],
                "cell_size_y": [abs(src.transform[4])],
                "nodata": [str(src.nodata)],
                "dtypes": [", ".join(src.dtypes)],
            })

        return {"Output": FeatureDataset.from_polars(df)}


@NodeRegistry.register
class GDALTranslate(BaseNode):
    """
    Subsets, rescales pixel values, or converts raster formats.
    Matches GDAL gdal_translate utility.
    """
    node_type = "GDALTranslate"
    category = NodeCategory.SPATIAL
    description = "Converts formats, subsets, and rescales pixel value ranges (GDAL gdal_translate)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Translation summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Source Raster (.tif)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Raster (.tif, Required)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("scale_min", ParameterType.FLOAT, default=0.0, label="Output Scale Min (0 to disable)"),
            ParameterDef("scale_max", ParameterType.FLOAT, default=0.0, label="Output Scale Max (0 to disable)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        out_path = params.get("output_path", "").strip()
        s_min = float(params.get("scale_min", 0.0))
        s_max = float(params.get("scale_max", 0.0))

        if not path or not out_path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        with rasterio.open(path) as src:
            data = src.read()
            profile = src.profile.copy()

            if s_min != 0.0 or s_max != 0.0:
                d_min, d_max = float(np.nanmin(data)), float(np.nanmax(data))
                if d_max > d_min:
                    data = ((data - d_min) / (d_max - d_min)) * (s_max - s_min) + s_min

            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(data)

        summary_df = pl.DataFrame({
            "source_file": [path],
            "output_file": [out_path],
            "width": [src.width],
            "height": [src.height],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class GDALWarp(BaseNode):
    """
    Reprojects and resamples raster layers to a target Coordinate Reference System.
    Matches GDAL gdalwarp utility.
    """
    node_type = "GDALWarp"
    category = NodeCategory.SPATIAL
    description = "Reprojects and resamples rasters to a target CRS (GDAL gdalwarp)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Reprojection summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("raster_path", ParameterType.FILE_OPEN, default="", label="Source Raster (.tif)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("target_crs", ParameterType.STRING, default="EPSG:3857", label="Target CRS (e.g. EPSG:3857)"),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Reprojected Raster (.tif, Required)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("raster_path", "").strip()
        t_crs = params.get("target_crs", "EPSG:3857").strip()
        out_path = params.get("output_path", "").strip()

        if not path or not out_path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        from rasterio.warp import calculate_default_transform, reproject, Resampling

        with rasterio.open(path) as src:
            transform, width, height = calculate_default_transform(
                src.crs, t_crs, src.width, src.height, *src.bounds
            )
            kwargs = src.meta.copy()
            kwargs.update({
                "crs": t_crs,
                "transform": transform,
                "width": width,
                "height": height
            })

            with rasterio.open(out_path, "w", **kwargs) as dst:
                for i in range(1, src.count + 1):
                    reproject(
                        source=rasterio.band(src, i),
                        destination=rasterio.band(dst, i),
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=transform,
                        dst_crs=t_crs,
                        resampling=Resampling.nearest
                    )

        summary_df = pl.DataFrame({
            "source_raster": [path],
            "target_crs": [t_crs],
            "output_raster": [out_path],
            "new_width": [width],
            "new_height": [height],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}


@NodeRegistry.register
class SAGATerrainAnalysis(BaseNode):
    """
    Computes topographic morphometry: Slope, Aspect, Terrain Ruggedness Index (TRI),
    Topographic Position Index (TPI), and Surface Roughness.
    Matches SAGA GIS ta_morphometry library.
    """
    node_type = "SAGATerrainAnalysis"
    category = NodeCategory.SPATIAL
    description = "SAGA Morphometry: calculates Slope, Aspect, TRI, TPI, and Roughness from DEM (SAGA ta_morphometry)."

    @classmethod
    def get_input_ports(cls) -> List[Port]:
        return []

    @classmethod
    def get_output_ports(cls) -> List[Port]:
        return [Port("Output", PortType.OUTPUT, "Terrain analysis morphometry summary")]

    @classmethod
    def get_parameter_defs(cls) -> List[ParameterDef]:
        return [
            ParameterDef("dem_path", ParameterType.FILE_OPEN, default="", label="DEM Raster File (.tif)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
            ParameterDef("metric", ParameterType.CHOICE, default="All", label="Morphometry Metric", choices=[
                "All", "TRI (Terrain Ruggedness)", "TPI (Position Index)", "Roughness", "Slope", "Aspect"
            ]),
            ParameterDef("output_path", ParameterType.FILE_SAVE, default="", label="Output Metric GeoTIFF (.tif, Optional)", file_filter="GeoTIFF (*.tif);;All Files (*.*)"),
        ]

    def execute(self, inputs: Dict[str, FeatureDataset], params: Dict[str, Any], context=None) -> Dict[str, FeatureDataset]:
        path = params.get("dem_path", "").strip()
        metric = params.get("metric", "All")
        out_path = params.get("output_path", "").strip()

        if not path or not os.path.exists(path):
            return {"Output": FeatureDataset.empty()}

        with rasterio.open(path) as src:
            dem = src.read(1).astype(np.float32)
            profile = src.profile.copy()
            dx = abs(src.transform[0])
            dy = abs(src.transform[4])

        # TPI: dem - mean(neighborhood)
        mean_filter = ndimage.uniform_filter(dem, size=3)
        tpi = dem - mean_filter

        # Roughness: max(neighborhood) - min(neighborhood)
        max_filter = ndimage.maximum_filter(dem, size=3)
        min_filter = ndimage.minimum_filter(dem, size=3)
        roughness = max_filter - min_filter

        # TRI: mean absolute difference between center and 8 neighbors
        # Using 3x3 kernel differences
        tri = np.zeros_like(dem)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                shifted = np.roll(np.roll(dem, dr, axis=0), dc, axis=1)
                tri += np.abs(shifted - dem)
        tri /= 8.0

        if out_path:
            profile.update(dtype=rasterio.float32, count=1, nodata=-9999.0)
            res_layer = tri if "TRI" in metric else (tpi if "TPI" in metric else roughness)
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(res_layer.astype(np.float32), 1)

        summary_df = pl.DataFrame({
            "dem_file": [path],
            "metric": [metric],
            "mean_tri": [float(np.mean(tri))],
            "mean_tpi": [float(np.mean(tpi))],
            "mean_roughness": [float(np.mean(roughness))],
            "output_raster": [out_path if out_path else "(In-memory)"],
        })

        return {"Output": FeatureDataset.from_polars(summary_df)}

