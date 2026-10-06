"""
Core FeatureDataset abstraction combining Polars (for high-speed attribute operations)
and GeoPandas/Shapely (for spatial operations and geometry manipulation).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import polars as pl
import geopandas as gpd
from shapely.geometry.base import BaseGeometry
import pyarrow as pa


class FeatureDataset:
    """
    Unified dataset container representing a stream of spatial or non-spatial features.
    Maintains high performance with Polars for attribute crunching while seamlessly
    supporting GeoPandas / Shapely geometries and Coordinate Reference Systems (CRS).
    """

    def __init__(
        self,
        df: Optional[pl.DataFrame] = None,
        gdf: Optional[gpd.GeoDataFrame] = None,
        geometry_col: str = "geometry",
        crs: Any = "EPSG:4326",
    ):
        self.geometry_col = geometry_col
        self._gdf: Optional[gpd.GeoDataFrame] = None
        self._df: Optional[pl.DataFrame] = None
        self._crs = crs

        if gdf is not None:
            self._gdf = gdf
            self._crs = gdf.crs
            self.geometry_col = gdf.geometry.name if hasattr(gdf, "geometry") else geometry_col
        elif df is not None:
            self._df = df
        else:
            self._df = pl.DataFrame()

    @classmethod
    def from_polars(
        cls,
        df: pl.DataFrame,
        geometry_col: Optional[str] = None,
        crs: Any = "EPSG:4326"
    ) -> FeatureDataset:
        return cls(df=df, geometry_col=geometry_col or "geometry", crs=crs)

    @classmethod
    def from_geopandas(cls, gdf: gpd.GeoDataFrame) -> FeatureDataset:
        return cls(gdf=gdf)

    @classmethod
    def empty(cls) -> FeatureDataset:
        return cls(df=pl.DataFrame())

    @property
    def crs(self) -> Any:
        if self._gdf is not None:
            return self._gdf.crs
        return self._crs

    @crs.setter
    def crs(self, new_crs: Any) -> None:
        self._crs = new_crs
        if self._gdf is not None:
            self._gdf.set_crs(new_crs, allow_override=True, inplace=True)

    def has_geometry(self) -> bool:
        if self._gdf is not None:
            return (
                hasattr(self._gdf, "geometry")
                and self._gdf.geometry is not None
                and not self._gdf.geometry.empty
            )
        if self._df is not None:
            return self.geometry_col in self._df.columns
        return False

    def to_polars(self) -> pl.DataFrame:
        """Return dataset as a Polars DataFrame with zero-copy or fast PyArrow conversion."""
        if self._df is not None:
            return self._df
        if self._gdf is not None:
            try:
                import shapely
                temp_gdf = self._gdf.copy()
                if hasattr(temp_gdf, "geometry") and temp_gdf.geometry is not None:
                    # High-speed vectorized WKT conversion via Shapely C-extension
                    temp_gdf["_geom_wkt"] = shapely.to_wkt(temp_gdf.geometry.values)
                arrow_table = pa.Table.from_pandas(temp_gdf)
                self._df = pl.from_arrow(arrow_table)
            except Exception:
                self._df = pl.from_pandas(self._gdf.drop(columns=[self.geometry_col], errors="ignore"))
            return self._df
        return pl.DataFrame()

    def to_geopandas(self) -> gpd.GeoDataFrame:
        """Return dataset as a GeoPandas GeoDataFrame with vectorized geometry reconstruction."""
        if self._gdf is not None:
            return self._gdf
        if self._df is not None:
            import shapely
            arrow_table = self._df.to_arrow()
            pandas_df = arrow_table.to_pandas()

            # 1. Existing geometry or _geom_wkt column
            geom_target = self.geometry_col if self.geometry_col in pandas_df.columns else ("_geom_wkt" if "_geom_wkt" in pandas_df.columns else None)
            if geom_target:
                vals = pandas_df[geom_target].dropna()
                if not vals.empty:
                    first_val = vals.iloc[0]
                    if isinstance(first_val, str):
                        try:
                            # Blazing-fast vectorized from_wkt
                            geometries = shapely.from_wkt(pandas_df[geom_target].fillna("GEOMETRYCOLLECTION EMPTY").values)
                            self._gdf = gpd.GeoDataFrame(pandas_df, geometry=geometries, crs=self._crs)
                        except Exception:
                            self._gdf = gpd.GeoDataFrame(pandas_df)
                    elif isinstance(first_val, BaseGeometry):
                        self._gdf = gpd.GeoDataFrame(pandas_df, geometry=geom_target, crs=self._crs)
                    else:
                        self._gdf = gpd.GeoDataFrame(pandas_df)
                else:
                    self._gdf = gpd.GeoDataFrame(pandas_df)
            else:
                # 2. Auto-detect coordinate columns (lon/lat, x/y)
                coords_found = False
                for x_col, y_col in [("lon", "lat"), ("longitude", "latitude"), ("x", "y"), ("X", "Y"), ("LONGITUDE", "LATITUDE")]:
                    if x_col in pandas_df.columns and y_col in pandas_df.columns:
                        try:
                            geoms = gpd.points_from_xy(pandas_df[x_col], pandas_df[y_col], crs=self._crs or "EPSG:4326")
                            self._gdf = gpd.GeoDataFrame(pandas_df, geometry=geoms, crs=self._crs or "EPSG:4326")
                            coords_found = True
                            break
                        except Exception:
                            pass
                if not coords_found:
                    self._gdf = gpd.GeoDataFrame(pandas_df)

            return self._gdf
        return gpd.GeoDataFrame()

    def rename_columns(self, mapping: Dict[str, str]) -> FeatureDataset:
        """Fast rename preserving native backend."""
        if not mapping:
            return self
        if self._gdf is not None:
            renamed_gdf = self._gdf.rename(columns=mapping)
            return FeatureDataset.from_geopandas(renamed_gdf)
        if self._df is not None:
            clean_map = {k: v for k, v in mapping.items() if k in self._df.columns}
            renamed_df = self._df.rename(clean_map) if clean_map else self._df
            return FeatureDataset.from_polars(renamed_df, geometry_col=self.geometry_col, crs=self._crs)
        return FeatureDataset.empty()

    def drop_columns(self, columns_to_drop: List[str]) -> FeatureDataset:
        """Fast column drop preserving native backend."""
        if not columns_to_drop:
            return self
        if self._gdf is not None:
            clean_drop = [c for c in columns_to_drop if c in self._gdf.columns and c != self._gdf.geometry.name]
            dropped_gdf = self._gdf.drop(columns=clean_drop)
            return FeatureDataset.from_geopandas(dropped_gdf)
        if self._df is not None:
            clean_drop = [c for c in columns_to_drop if c in self._df.columns]
            dropped_df = self._df.drop(clean_drop) if clean_drop else self._df
            return FeatureDataset.from_polars(dropped_df, geometry_col=self.geometry_col, crs=self._crs)
        return FeatureDataset.empty()

    def add_column(self, col_name: str, value: Any) -> FeatureDataset:
        """Fast column creation preserving native backend."""
        if not col_name:
            return self
        if self._gdf is not None:
            new_gdf = self._gdf.copy()
            new_gdf[col_name] = value
            return FeatureDataset.from_geopandas(new_gdf)
        if self._df is not None:
            new_df = self._df.with_columns(pl.lit(value).alias(col_name))
            return FeatureDataset.from_polars(new_df, geometry_col=self.geometry_col, crs=self._crs)
        return FeatureDataset.empty()

    def sort_by(self, col_name: str, descending: bool = False) -> FeatureDataset:
        """Fast sorting preserving native backend."""
        if not col_name:
            return self
        if self._gdf is not None and col_name in self._gdf.columns:
            sorted_gdf = self._gdf.sort_values(by=col_name, ascending=not descending)
            return FeatureDataset.from_geopandas(sorted_gdf)
        if self._df is not None and col_name in self._df.columns:
            sorted_df = self._df.sort(col_name, descending=descending)
            return FeatureDataset.from_polars(sorted_df, geometry_col=self.geometry_col, crs=self._crs)
        return self

    def make_valid(self) -> FeatureDataset:
        """Repairs any self-intersections or invalid geometries accurately."""
        if self.has_geometry():
            gdf = self.to_geopandas().copy()
            if hasattr(gdf, "geometry") and not gdf.geometry.is_valid.all():
                gdf[gdf.geometry.name] = gdf.geometry.make_valid()
                return FeatureDataset.from_geopandas(gdf)
        return self

    def count(self) -> int:
        if self._df is not None:
            return len(self._df)
        if self._gdf is not None:
            return len(self._gdf)
        return 0

    def __len__(self) -> int:
        return self.count()

    def is_empty(self) -> bool:
        return self.count() == 0

    @property
    def columns(self) -> List[str]:
        if self._df is not None:
            return self._df.columns
        if self._gdf is not None:
            return list(self._gdf.columns)
        return []

    def get_column_types(self) -> Dict[str, str]:
        if self._df is not None:
            return {col: str(dtype) for col, dtype in zip(self._df.columns, self._df.dtypes)}
        if self._gdf is not None:
            return {col: str(dtype) for col, dtype in self._gdf.dtypes.items()}
        return {}

    def get_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        """Returns (minx, miny, maxx, maxy) bounding box if spatial."""
        if self.has_geometry():
            gdf = self.to_geopandas()
            if hasattr(gdf, "total_bounds") and len(gdf) > 0:
                b = gdf.total_bounds
                return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        return None

    def sample(self, n: int = 500) -> FeatureDataset:
        """Returns a preview slice of the dataset."""
        if self.count() <= n:
            return self
        if self._gdf is not None:
            return FeatureDataset.from_geopandas(self._gdf.head(n).copy())
        if self._df is not None:
            return FeatureDataset.from_polars(self._df.head(n), geometry_col=self.geometry_col, crs=self._crs)
        return FeatureDataset.empty()

    def copy(self) -> FeatureDataset:
        if self._gdf is not None:
            return FeatureDataset.from_geopandas(self._gdf.copy())
        if self._df is not None:
            return FeatureDataset.from_polars(self._df.clone(), geometry_col=self.geometry_col, crs=self._crs)
        return FeatureDataset.empty()
